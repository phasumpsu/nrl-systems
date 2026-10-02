"""
Telemetry sources.

Every source is a QThread that emits decoded `TelemetryFrame` objects on the
`frame` signal, so the UI never cares where the data came from:

    MockSource    -- full synthetic flight, no hardware needed
    SerialSource  -- USB / LoRa bridge on a COM port
    UdpSource     -- UDP datagrams (also speaks the legacy FC UI CSV schema)

All of them share the `TelemetrySource` interface: start(), stop(), and the
`frame` / `link` / `event` signals.
"""

from __future__ import annotations

import math
import random
import socket
import time

from PyQt6.QtCore import QThread, pyqtSignal

from .telemetry import (
    EXTENDED_PACKET_SIZE,
    FULL_PACKET_SIZE,
    LORA_PACKET_SIZE,
    FlightPhase,
    PyroState,
    TelemetryFrame,
    decode_csv_log,
    decode_extended_packet,
    decode_full_packet,
    decode_legacy_udp_csv,
    decode_lora_packet,
)

# Spaceport America -- Vertical Launch Area, Las Cruces NM (IREC / SA Cup).
LAUNCH_SITE = (32.99025, -106.97500)
LAUNCH_SITE_NAME = "Spaceport America — VLA"
LAUNCH_SITE_ELEV_M = 1401.0

G0 = 9.80665

# Binary framing used by SerialSource/UdpSource in binary mode.
SYNC = b"\xAA\x55"


# =====================================================================
# Base
# =====================================================================
class TelemetrySource(QThread):
    """Common interface for all telemetry producers."""

    frame = pyqtSignal(object)          # TelemetryFrame
    link = pyqtSignal(bool, str)        # connected, human-readable detail
    event = pyqtSignal(str, str)        # severity ("info"|"warn"|"error"), text
    raw = pyqtSignal(bytes)             # exact bytes as received, pre-decode

    name = "source"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def stop(self, timeout_ms: int = 2000) -> None:
        self._running = False
        if self.isRunning():
            self.wait(timeout_ms)


# =====================================================================
# Mock flight -- physics-driven, walks the real state machine
# =====================================================================
class MockSource(TelemetrySource):
    """
    Synthetic flight for UI development.

    The vertical dynamics are integrated rather than scripted, and the phase
    transitions use the same thresholds the firmware flies (config.cpp), so
    the dashboard sees a plausible mission without any hardware attached.

    Timeline: 6 s pad -> arm -> 6 s hold -> ignition -> ~3 s boost -> coast
    -> apogee + drogue -> descent -> main at 450 m AGL -> touchdown -> hold.
    """

    name = "mock"

    RATE_HZ = 50.0
    ARM_AT = 6.0
    IGNITION_AT = 12.0
    BURN_TIME = 3.0
    THRUST_ACCEL = 95.0        # m/s^2 along the body axis
    RAIL_TILT_DEG = 5.0
    RAIL_AZIMUTH_DEG = 42.0
    MAIN_DEPLOY_ALT = 450.0    # m AGL
    DROGUE_TERMINAL = 25.0     # m/s
    MAIN_TERMINAL = 7.0        # m/s
    COAST_DRAG_K = 3.2e-4      # quadratic drag coefficient / mass

    def __init__(self, speed: float = 1.0, loop: bool = True, parent=None):
        super().__init__(parent)
        self.speed = max(0.05, speed)
        self.loop = loop

    # -----------------------------------------------------------------
    def _reset(self) -> None:
        tilt = math.radians(self.RAIL_TILT_DEG)
        self.t = 0.0
        self.alt = 0.0                    # m AGL
        self.vz = 0.0                     # m/s, +up
        self.vh = 0.0                     # m/s, horizontal (downrange)
        self.north = 0.0                  # m
        self.east = 0.0                   # m
        self.roll = 0.0
        self.roll_rate = 0.0
        self.yaw = self.RAIL_AZIMUTH_DEG
        self.phase = FlightPhase.IDLE
        self.armed = False
        self.pyro = [PyroState.DISARMED] * 4
        self.apogee_counter = 0
        self.landing_counter = 0
        self.launch_counter = 0
        self.max_alt = 0.0
        self.battery = 8.31
        self._thrust_dir = (math.sin(tilt), math.cos(tilt))
        self._landed_hold = 0.0
        self._ignition_t = self.IGNITION_AT
        self._apogee_t = 0.0
        self._az_body_g = 1.0
        self._last_pitch = 90.0 - self.RAIL_TILT_DEG

    # -----------------------------------------------------------------
    def run(self) -> None:
        self._running = True
        self._reset()
        dt = 1.0 / self.RATE_HZ
        self.link.emit(True, "Mock flight generator @ 50 Hz")
        self.event.emit("info", f"Mock source armed — site {LAUNCH_SITE_NAME}")

        next_tick = time.perf_counter()
        while self._running:
            self._step(dt)
            self.frame.emit(self._build_frame())

            next_tick += dt / self.speed
            sleep_s = next_tick - time.perf_counter()
            if sleep_s > 0:
                self.msleep(int(sleep_s * 1000))
            else:
                next_tick = time.perf_counter()

        self.link.emit(False, "Mock source stopped")

    # -----------------------------------------------------------------
    def _step(self, dt: float) -> None:
        self.t += dt
        prev_phase = self.phase

        boosting = (
            self.phase == FlightPhase.BOOST
            and (self.t - self._ignition_t) < self.BURN_TIME
        )

        # ---- translational dynamics ---------------------------------
        if self.phase <= FlightPhase.ARMED:
            az_body = 0.0
        elif boosting:
            ax_t, az_t = self._thrust_dir
            self.vh += self.THRUST_ACCEL * ax_t * dt
            self.vz += (self.THRUST_ACCEL * az_t - G0) * dt
            az_body = self.THRUST_ACCEL / G0
        elif self.phase in (FlightPhase.BOOST, FlightPhase.COAST, FlightPhase.APOGEE):
            drag = self.COAST_DRAG_K * self.vz * abs(self.vz)
            self.vz += (-G0 - drag) * dt
            self.vh *= (1.0 - 0.35 * dt)
            az_body = -drag / G0
        elif self.phase == FlightPhase.DESCENT:
            terminal = self.MAIN_TERMINAL if self.alt < self.MAIN_DEPLOY_ALT else self.DROGUE_TERMINAL
            k = G0 / (terminal ** 2)
            self.vz += (-G0 + k * self.vz ** 2) * dt
            self.vh += (self._wind_at(self.alt) - self.vh) * 0.6 * dt
            az_body = (k * self.vz ** 2) / G0
        else:  # LANDED
            self.vz = 0.0
            self.vh = 0.0
            az_body = 0.0

        self.alt += self.vz * dt
        if self.alt <= 0.0:
            # Touchdown: the airframe stops, which is what lets the landing
            # detector's |vz| < LANDING_VELOCITY_THRESH test finally pass.
            self.alt = 0.0
            self.vz = 0.0
            self.vh = 0.0
        self.max_alt = max(self.max_alt, self.alt)

        heading = math.radians(self.yaw)
        self.north += self.vh * math.cos(heading) * dt
        self.east += self.vh * math.sin(heading) * dt

        # ---- attitude ------------------------------------------------
        if boosting:
            self.roll_rate = min(self.roll_rate + 90.0 * dt, 190.0)
        elif self.phase == FlightPhase.DESCENT:
            self.roll_rate += (35.0 - self.roll_rate) * 0.4 * dt
        elif self.phase == FlightPhase.LANDED:
            self.roll_rate *= (1.0 - 2.0 * dt)
        self.roll = (self.roll + self.roll_rate * dt) % 360.0
        self.yaw = (self.yaw + 1.5 * dt * math.sin(self.t * 0.3)) % 360.0

        self._az_body_g = az_body
        self._advance_state_machine(dt)

        if self.phase != prev_phase:
            self.event.emit("info", f"Phase -> {self.phase.label}")

        # ---- power ----------------------------------------------------
        self.battery -= 0.00004 * dt * (12.0 if self.phase >= FlightPhase.BOOST else 1.0)

    def _wind_at(self, alt: float) -> float:
        """Simple wind shear: stronger aloft, gusting."""
        return 4.0 + 0.004 * alt + 1.2 * math.sin(self.t * 0.7)

    # -----------------------------------------------------------------
    def _advance_state_machine(self, dt: float) -> None:
        """Mirrors state_machine.cpp using the constants from config.cpp."""
        from .telemetry import PARAMS

        if self.phase == FlightPhase.IDLE:
            if self.t >= self.ARM_AT:
                self.armed = True
                self.phase = FlightPhase.ARMED
                self.pyro = [PyroState.ARMED, PyroState.ARMED,
                             PyroState.DISARMED, PyroState.DISARMED]

        elif self.phase == FlightPhase.ARMED:
            if self.t >= self.IGNITION_AT:
                self.launch_counter += 1
                if self.launch_counter >= PARAMS.launch_debounce:
                    self.phase = FlightPhase.BOOST
                    self._ignition_t = self.t
                    self.event.emit("warn", "LAUNCH DETECTED")

        elif self.phase == FlightPhase.BOOST:
            if (self.t - self._ignition_t) >= self.BURN_TIME:
                self.phase = FlightPhase.COAST
                self.event.emit("info", f"Burnout — {self.vz:.0f} m/s")

        elif self.phase == FlightPhase.COAST:
            if self.vz < PARAMS.apogee_velocity_thresh:
                self.apogee_counter += 1
                if self.apogee_counter >= PARAMS.apogee_persist_samples:
                    self.phase = FlightPhase.APOGEE
                    self._apogee_t = self.t
                    self.event.emit("warn", f"APOGEE — {self.alt:.0f} m AGL")
            else:
                self.apogee_counter = 0

        elif self.phase == FlightPhase.APOGEE:
            # pyro.cpp fires channel 0 on entry to APOGEE.
            if self.pyro[0] != PyroState.FIRED:
                self.pyro[0] = PyroState.FIRED
                self.battery -= 0.06
                self.event.emit("warn", "PYRO 0 FIRED — DROGUE")
            if (self.t - self._apogee_t) > 0.4:
                self.phase = FlightPhase.DESCENT

        elif self.phase == FlightPhase.DESCENT:
            if self.alt < self.MAIN_DEPLOY_ALT and self.pyro[1] != PyroState.FIRED:
                self.pyro[1] = PyroState.FIRED
                self.battery -= 0.06
                self.event.emit("warn", "PYRO 1 FIRED — MAIN")
            if (self.alt < PARAMS.landing_altitude_thresh
                    and abs(self.vz) < PARAMS.landing_velocity_thresh):
                self.landing_counter += 1
                if self.landing_counter >= PARAMS.landing_persist_samples:
                    self.phase = FlightPhase.LANDED
                    self.event.emit("info", f"TOUCHDOWN — apogee {self.max_alt:.0f} m")
            else:
                self.landing_counter = 0

        elif self.phase == FlightPhase.LANDED:
            self._landed_hold += dt
            if self.loop and self._landed_hold > 8.0:
                self.event.emit("info", "Recycling mock flight")
                self._reset()

    # -----------------------------------------------------------------
    def _build_frame(self) -> TelemetryFrame:
        # Pitch follows the velocity vector, so the vehicle noses over
        # through apogee the way a real one does. Below a few m/s the
        # velocity vector is meaningless, so hold the last good attitude
        # rather than snapping to zero.
        speed = math.hypot(self.vz, self.vh)
        if self.phase <= FlightPhase.ARMED:
            pitch = 90.0 - self.RAIL_TILT_DEG
        elif self.phase == FlightPhase.LANDED:
            pitch = self._last_pitch * 0.96      # settles onto its side
        elif speed < 2.0:
            pitch = self._last_pitch
        else:
            pitch = math.degrees(math.atan2(self.vz, max(self.vh, 0.01)))
        self._last_pitch = pitch

        noise = lambda s: random.gauss(0.0, s)  # noqa: E731

        az_g = (1.0 if self.phase <= FlightPhase.ARMED else self._az_body_g)
        slant = math.hypot(self.alt, math.hypot(self.north, self.east))

        lat = LAUNCH_SITE[0] + self.north / 111_320.0
        lon = LAUNCH_SITE[1] + self.east / (111_320.0 * math.cos(math.radians(LAUNCH_SITE[0])))

        # ISA-ish pressure for the barometer channel.
        pressure = 101325.0 * (1.0 - 2.25577e-5 * (self.alt + LAUNCH_SITE_ELEV_M)) ** 5.25588

        return TelemetryFrame(
            timestamp_ms=int(self.t * 1000),
            ax_low=noise(0.05), ay_low=noise(0.05), az_low=az_g * G0 + noise(0.08),
            gx=noise(1.5), gy=noise(1.5), gz=self.roll_rate + noise(2.0),
            ax_high=noise(0.03), ay_high=noise(0.03), az_high=az_g + noise(0.05),
            pressure_pa=pressure + noise(8.0),
            temperature_c=24.0 - 0.0065 * self.alt + noise(0.15),
            filtered_altitude=self.alt + noise(0.4),
            vertical_velocity=self.vz + noise(0.25),
            imu_vertical_vel=self.vz + noise(1.1),
            battery_voltage=self.battery + noise(0.006),
            flight_phase=self.phase,
            launch_confidence=100 if self.phase >= FlightPhase.BOOST else 0,
            apogee_confidence=min(100, self.apogee_counter * 20),
            roll=self.roll, pitch=pitch, yaw=self.yaw,
            lat=lat, lon=lon,
            gps_alt=self.alt + LAUNCH_SITE_ELEV_M + noise(1.5),
            gps_speed=speed,
            gps_heading=self.yaw,
            gps_vertical_vel=self.vz,
            gps_fix=3,
            gps_sats=random.randint(9, 14),
            rssi=-52.0 - 20.0 * math.log10(max(slant, 50.0) / 50.0) + noise(1.5),
            snr=9.5 + noise(0.8),
            pyro_states=tuple(self.pyro),
            armed=self.armed,
            continuity=(True, True, False, False),
        )


# =====================================================================
# Packet framing shared by the live sources
# =====================================================================
class PacketAssembler:
    """
    Pulls frames out of a raw byte stream.

    Binary mode expects `AA 55 <len> <payload...>` and dispatches on payload
    length (17 = LoRa downlink, 55 = extended, 79 = full RocketDataPacket).
    Text mode splits on newlines and tries the CSV decoders.
    """

    def __init__(self, mode: str = "auto"):
        self.mode = mode
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[TelemetryFrame]:
        self._buf.extend(chunk)
        if len(self._buf) > 65536:            # runaway guard
            del self._buf[:-4096]
        if self.mode == "csv":
            return self._parse_text()
        if self.mode in ("lora", "extended", "full", "binary"):
            return self._parse_binary()
        # auto: binary if we ever see the sync word, otherwise text
        return self._parse_binary() if SYNC in self._buf else self._parse_text()

    # -----------------------------------------------------------------
    def _parse_text(self) -> list[TelemetryFrame]:
        out: list[TelemetryFrame] = []
        while b"\n" in self._buf:
            line, _, rest = bytes(self._buf).partition(b"\n")
            self._buf = bytearray(rest)
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            frame = decode_legacy_udp_csv(text) or decode_csv_log(text)
            if frame:
                out.append(frame)
        return out

    def _parse_binary(self) -> list[TelemetryFrame]:
        out: list[TelemetryFrame] = []
        while True:
            idx = self._buf.find(SYNC)
            if idx < 0:
                if len(self._buf) > 2:
                    del self._buf[:-1]        # keep a possible split sync byte
                break
            if idx:
                del self._buf[:idx]
            if len(self._buf) < 3:
                break
            length = self._buf[2]
            if len(self._buf) < 3 + length:
                break
            payload = bytes(self._buf[3:3 + length])
            del self._buf[:3 + length]
            frame = decode_payload(payload)
            if frame:
                out.append(frame)
        return out


def _looks_like_text(payload: bytes) -> bool:
    """True if the payload is plausibly an ASCII CSV line rather than binary."""
    return all(b in (9, 10, 13) or 32 <= b < 127 for b in payload)


def decode_payload(payload: bytes) -> TelemetryFrame | None:
    """
    Dispatch a naked payload to the right decoder by its length.

    Text payloads are rejected up front: a CSV datagram that happens to be
    exactly 79 bytes long would otherwise be misread as a binary
    RocketDataPacket, which carries no CRC to catch the mistake.
    """
    if _looks_like_text(payload):
        return None
    n = len(payload)
    if n == LORA_PACKET_SIZE:
        return decode_lora_packet(payload)
    if n == EXTENDED_PACKET_SIZE:
        return decode_extended_packet(payload)
    if n == FULL_PACKET_SIZE:
        return decode_full_packet(payload)
    return None


# =====================================================================
# Serial
# =====================================================================
class SerialSource(TelemetrySource):
    """Reads telemetry from a COM port (USB CDC, or a LoRa receiver bridge)."""

    name = "serial"

    def __init__(self, port: str, baud: int = 115200, mode: str = "auto", parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self.mode = mode

    def run(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError:
            self.link.emit(False, "pyserial not installed")
            self.event.emit("error", "pyserial missing — run: pip install pyserial")
            return

        self._running = True
        assembler = PacketAssembler(self.mode)
        try:
            with serial.Serial(self.port, self.baud, timeout=0.2) as ser:
                self.link.emit(True, f"{self.port} @ {self.baud} ({self.mode})")
                self.event.emit("info", f"Serial open on {self.port}")
                while self._running:
                    chunk = ser.read(4096) or b""
                    if chunk:
                        self.raw.emit(bytes(chunk))
                        for frame in assembler.feed(chunk):
                            self.frame.emit(frame)
                    else:
                        self.msleep(5)
        except Exception as exc:                      # noqa: BLE001
            self.link.emit(False, f"{self.port}: {exc}")
            self.event.emit("error", f"Serial error: {exc}")
            return
        self.link.emit(False, "Serial closed")


# =====================================================================
# UDP
# =====================================================================
class UdpSource(TelemetrySource):
    """
    Listens for UDP telemetry.

    Accepts the legacy 15-field CSV emitted by the previous FC UI simulator
    as well as raw binary payloads, so the old `simulate_rocket.py` still
    drives this dashboard unchanged.
    """

    name = "udp"

    def __init__(self, host: str = "0.0.0.0", port: int = 5005, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port

    def run(self) -> None:
        self._running = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            self.link.emit(False, f"bind {self.port}: {exc}")
            self.event.emit("error", f"UDP bind failed: {exc}")
            sock.close()
            return

        sock.settimeout(0.4)
        self.link.emit(True, f"UDP {self.host}:{self.port}")
        self.event.emit("info", f"Listening on UDP {self.port}")

        while self._running:
            try:
                data, _addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            self.raw.emit(bytes(data))
            frame = decode_payload(data)
            if frame is None:
                text = data.decode("utf-8", errors="replace").strip()
                frame = decode_legacy_udp_csv(text) or decode_csv_log(text)
            if frame:
                self.frame.emit(frame)

        sock.close()
        self.link.emit(False, "UDP closed")


def available_serial_ports() -> list[str]:
    """Best-effort COM port list; empty if pyserial is not installed."""
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return []
    return [p.device for p in list_ports.comports()]


__all__ = [
    "TelemetrySource", "MockSource", "SerialSource", "UdpSource",
    "PacketAssembler", "decode_payload", "available_serial_ports",
    "LAUNCH_SITE", "LAUNCH_SITE_NAME", "LAUNCH_SITE_ELEV_M",
]
