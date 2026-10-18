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

    def __init__(self, host: str, port: int = 5555, parent=None):
        super().__init__(parent)
        self.host, self.port = host, port
        self._running = True
        self._fresh = False
        self._pi_telemetry = False
        self._last_pi_frame_at: float | None = None
        self._requests: Queue[dict] = Queue(maxsize=32)

    def command_available(self) -> bool:
        """A conservative local gate; the Pi still makes the final decision."""
        return (self._running and self.isRunning() and self._fresh and self._pi_telemetry
                and self._last_pi_frame_at is not None
                and time.monotonic() - self._last_pi_frame_at < 0.4)

    def request(self, **fields: int) -> bool:
        """Queue one validated request; False means there is no fresh link."""
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
        try:
            self._requests.put_nowait(dict(fields))
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
                sock.settimeout(0.2)
                if not self._running:
                    return
                self.link.emit(False, "Connected to Pi; waiting for engine telemetry")
                next_hb_at = time.monotonic()

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

                    # This worker alone writes the socket, so command and heartbeat lines do not interleave.
                    if self.command_available():
                        try:
                            fields = self._requests.get_nowait()
                        except Empty:
                            pass
                        else:
                            if self.command_available():
                                sock.sendall((json.dumps(fields, separators=(",", ":")) + "\n").encode("utf-8"))
                                self.event.emit("info", f"Request written to TCP: {fields} (not acknowledged)")
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
            self._fresh = self._pi_telemetry = False
            self._last_pi_frame_at = None
            self._discard_requests()
            self.link.emit(False, "Engine telemetry disconnected")

    def stop(self) -> None:
        self._running = False
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
