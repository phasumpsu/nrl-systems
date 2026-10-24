"""Telemetry and command transport for the Pi bridge."""
from __future__ import annotations

import json
from queue import Empty, Full, Queue
import socket
import time

from PyQt6.QtCore import QThread, pyqtSignal
from .telemetry import TelemetryFrame

_STATE = {"UNKNOWN": 0, "OPEN": 1, "CLOSED": 2, "FAULT": 3}
_ARMED = {"UNKNOWN": 0, "ARMED": 1, "DISARMED": 2, "FAULT": 3}
_ROUTINE = {"NONE": 0, "FIRE": 1, "LONG_FILL": 2, "SHORT_FILL": 3,
            "ROUTINE_4": 4, "ROUTINE_5": 5}
_COMMAND_RANGES = {
    "sv11": (0, 1), "sv12": (0, 1), "sv13": (0, 1),
    "armed": (0, 1), "routine": (0, 3),
    "fire_delay_ms": (1, 65535), "tare": (1, 3),
}


def _decode_pi_frame(values: dict) -> TelemetryFrame:
    def state(key: str, mapping: dict[str, int]) -> int:
        name = values[key]
        if not isinstance(name, str) or name not in mapping:
            raise ValueError(f"Unrecognized {key}: {name!r}")
        return mapping[name]

    return TelemetryFrame(
        mcu_time_s=values["mcu_timer_s"],
        engine_thrust_lbf=values["engine_thrust_raw"],
        nitrous_weight_lbs=values["nitrous_weight_raw"],
        run_tank_pressure_psi=values["run_tank_pressure_psi"],
        cc_pressure_psi=values["cc_pressure_psi"],
        top_cc_temp_f=values["top_cc_temp_f"],
        bot_cc_temp_f=values["bot_cc_temp_f"],
        sv11_state=state("sv11_state", _STATE),
        sv12_state=state("sv12_state", _STATE),
        sv13_state=state("sv13_state", _STATE),
        ignitor_state=state("ignitor_state", _STATE),
        armed_status=state("armed_status", _ARMED),
        routine_sequence=state("routine_sequence", _ROUTINE),
    )


class CTelemetrySource(QThread):
    frame = pyqtSignal(object)
    link = pyqtSignal(bool, str)
    event = pyqtSignal(str, str)
    bridge_status = pyqtSignal(str)  # Pi link health, independent of STM32 telemetry

    def __init__(self, host: str, port: int = 5555, parent=None):
        super().__init__(parent)
        self.host, self.port = host, port
        self._running = True
        self._fresh = False
        self._pi_telemetry = False
        self._last_pi_frame_at: float | None = None
        self._requests: Queue[dict] = Queue(maxsize=32)
        self._probes: Queue[None] = Queue(maxsize=1)
        self._heartbeat_confirmed = False
        self._last_heartbeat_ack_at: float | None = None
        self._active_session = False
        self._next_request_id = 1

    def probe(self) -> bool:
        """Ask the Pi for a read-only state snapshot; works without the STM32."""
        if not self._running or not self.isRunning():
            return False
        try:
            self._probes.put_nowait(None)
        except Full:
            return False
        return True

    def command_available(self) -> bool:
        """Pi TCP session is active and responding; NOT permission from the MCU."""
        return (self._running and self.isRunning() and self._active_session
                and self._last_heartbeat_ack_at is not None
                and time.monotonic() - self._last_heartbeat_ack_at < 2.0)

    def mcu_telemetry_available(self) -> bool:
        return (self._running and self._fresh and self._pi_telemetry
                and self._last_pi_frame_at is not None
                and time.monotonic() - self._last_pi_frame_at < 0.4)

    def request(self, **fields: int) -> bool:
        """Queue a request for the active Pi; Pi can reject it if the MCU is stale."""
        if not fields or "hb" in fields:
            raise ValueError("Specify command fields, not a heartbeat")
        for key, value in fields.items():
            if key not in _COMMAND_RANGES:
                raise ValueError(f"Unsupported Pi command key: {key}")
            low, high = _COMMAND_RANGES[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer in {low}..{high}")
        if not self.command_available():
            return False
        request = dict(fields)
        request["request_id"] = self._next_request_id
        self._next_request_id += 1
        try:
            self._requests.put_nowait(request)
        except Full:
            return False
        return True

    def _discard_requests(self) -> None:
        while True:
            try:
                self._requests.get_nowait()
            except Empty:
                break

    def run(self) -> None:
        silence_timeout_s = 3.0
        last_frame_at = None
        connected = False
        pending = b""
        try:
            with socket.create_connection((self.host, self.port), timeout=2.0) as sock:
                self._heartbeat_confirmed = False
                self._last_heartbeat_ack_at = None
                self._active_session = False
                sock.settimeout(0.2)
                if not self._running:
                    return
                self.link.emit(False, "TCP connected; checking Pi bridge (engine telemetry not yet verified)")
                sock.sendall(b'{"hb":1}\n{"get_state":true}\n')
                next_hb_at = time.monotonic() + 0.5

                while self._running:
                    now = time.monotonic()
                    if now >= next_hb_at:
                        sock.sendall(b'{"hb":1}\n')
                        next_hb_at = time.monotonic() + 0.5
                    if connected and last_frame_at is not None and now - last_frame_at >= silence_timeout_s:
                        connected = self._fresh = self._pi_telemetry = False
                        self._last_pi_frame_at = None
                        self._discard_requests()
                        self.link.emit(False, "Engine telemetry timed out")

                    # Diagnostic probes do not enter the Pi's command parser.
                    try:
                        self._probes.get_nowait()
                    except Empty:
                        pass
                    else:
                        sock.sendall(b'{"get_state":true}\n')

                    # Only this worker writes the socket, so JSON lines cannot interleave.
                    if self.command_available():
                        try:
                            fields = self._requests.get_nowait()
                        except Empty:
                            pass
                        else:
                            if self.command_available():
                                sock.sendall((json.dumps(fields, separators=(",", ":")) + "\n").encode("utf-8"))
                                self.event.emit("info", f"Request {fields['request_id']} written to TCP; awaiting Pi response")
                    else:
                        self._discard_requests()

                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk or not self._running:
                        break
                    pending += chunk
                    while b"\n" in pending:
                        raw_line, pending = pending.split(b"\n", 1)
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        if len(raw_line) > 65536:
                            self.event.emit("error", "Telemetry line exceeded 64 KiB")
                            return
                        try:
                            values = json.loads(raw_line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            self.event.emit("warn", f"Non-JSON telemetry: {raw_line[:200]!r}")
                            continue
                        if not isinstance(values, dict):
                            self.event.emit("warn", "Telemetry JSON is not an object")
                            continue
                        if values.get("type") == "pi_status":
                            continue
                        if values.get("type") == "state_snapshot":
                            self._active_session = values.get("is_active") is True
                            if not self._active_session:
                                self._discard_requests()
                            self.bridge_status.emit(
                                f"Pi answered state query; active: {values.get('is_active')}; "
                                f"STM32 telemetry age: {values.get('mcu_telemetry_age_s')}; "
                                f"forced safe: {values.get('forced')}; "
                                f"reason: {values.get('reason', 'unknown')}"
                            )
                            continue
                        if values.get("type") == "promoted":
                            self._active_session = True
                            self.probe()  # Refresh an initial snapshot that may predate promotion.
                            self.bridge_status.emit("Pi promoted this ground-station session to active")
                            continue
                        if values.get("type") == "ack":
                            if values.get("reason") == "heartbeat":
                                if values.get("status") == "accepted":
                                    self._last_heartbeat_ack_at = time.monotonic()
                                    if not self._heartbeat_confirmed:
                                        self._heartbeat_confirmed = True
                                        self.event.emit("info", "Pi accepted ground-station heartbeat")
                            else:
                                if values.get("reason") == "not_active_session":
                                    self._active_session = False
                                    self._discard_requests()
                                self.event.emit(
                                    "info" if values.get("status") == "accepted" else "warn",
                                    f"Pi request {values.get('request_id')}: "
                                    f"{values.get('status')} ({values.get('reason')})"
                                )
                            continue
                        if "type" in values and values.get("type") != "telemetry":
                            continue
                        try:
                            telemetry = (_decode_pi_frame(values) if "mcu_timer_s" in values else
                                TelemetryFrame(
                                    mcu_time_s=values["mcu timer"],
                                    engine_thrust_lbf=values["thrust"],
                                    nitrous_weight_lbs=values["nitrous weight"],
                                    run_tank_pressure_psi=values["run tank pressure"],
                                    cc_pressure_psi=values["chamber pressure"],
                                    top_cc_temp_f=values["top temp"],
                                    bot_cc_temp_f=values["bot temp"],
                                    sv11_state=values["sv11_state"],
                                    sv12_state=values["sv12_state"],
                                    sv13_state=values["sv13_state"],
                                    ignitor_state=values["ignitor_state"],
                                    armed_status=values["armed_status"],
                                    routine_sequence=values["routine_sequence"],
                                ))
                        except KeyError as exc:
                            self.event.emit("warn", f"Missing telemetry key {exc}; received keys: {list(values)}")
                            continue
                        except (TypeError, ValueError) as exc:
                            self.event.emit("error", f"Invalid telemetry values: {exc}")
                            continue
                        last_frame_at = time.monotonic()
                        self._pi_telemetry = "mcu_timer_s" in values
                        self._last_pi_frame_at = last_frame_at if self._pi_telemetry else None
                        self._fresh = True
                        self.frame.emit(telemetry)
                        if not connected:
                            connected = True
                            self.link.emit(True, "ENGINE TELEMETRY")
                    if len(pending) > 65536:
                        self.event.emit("error", "Telemetry line exceeded 64 KiB")
                        return
        except OSError as exc:
            if self._running:
                self.event.emit("error", f"Telemetry connection failed: {exc}")
        finally:
            self._heartbeat_confirmed = False
            self._last_heartbeat_ack_at = None
            self._active_session = False
            self._fresh = self._pi_telemetry = False
            self._last_pi_frame_at = None
            self._discard_requests()
            self.link.emit(False, "Engine telemetry disconnected")

    def stop(self) -> None:
        self._running = False
        self._active_session = False
        self._last_heartbeat_ack_at = None
        self._fresh = self._pi_telemetry = False
        self._last_pi_frame_at = None
        self._discard_requests()
        if self.isRunning():
            self.wait(3000)


class MockSource(QThread):
    frame = pyqtSignal(object)
    link = pyqtSignal(bool, str)
    event = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def run(self) -> None:
        self._running = True
        started = time.monotonic()
        self.link.emit(True, "SIMULATED DATA — NO HARDWARE")
        self.event.emit("info", "Read-only engine telemetry simulation started")
        while self._running:
            elapsed = time.monotonic() - started
            frame = TelemetryFrame(
                mcu_time_s=round(elapsed * 2) / 2,
                engine_thrust_lbf=0.0, nitrous_weight_lbs=0.0,
                run_tank_pressure_psi=0.0, cc_pressure_psi=0.0,
                top_cc_temp_f=0.0, bot_cc_temp_f=0.0,
                sv11_state=0, sv12_state=0, sv13_state=0,
                ignitor_state=0, armed_status=0, routine_sequence=0,
            )
            self.frame.emit(frame)
            self.msleep(100)
        self.link.emit(False, "Simulation stopped")

    def stop(self) -> None:
        self._running = False
        if self.isRunning():
            self.wait(2000)
