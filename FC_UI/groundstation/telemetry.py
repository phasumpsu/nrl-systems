"""
Telemetry data model for the Nittany Rocket Labs ESP32 flight computer.

Every structure here is derived directly from the firmware, so the ground
station and the vehicle cannot drift apart silently:

    FlightPhase          <- Acceltra/src/config.h        (enum FlightPhase)
    TelemetryFrame       <- Acceltra/src/config.h        (struct RocketDataPacket)
    FlightParams         <- Acceltra/src/config.cpp      (tuning constants)
    decode_lora_packet   <- Acceltra/src/telemetry.cpp   (sendTelemetry)
    decode_full_packet   <- Acceltra/src/config.h        (packed RocketDataPacket)
    decode_csv_log       <- Acceltra/src/logging.cpp     (writeLowRateLog header)
    GPS scaling          <- Acceltra/src/SAM_M10Q_I2C.h

NOTE ON THE RADIO LINK
----------------------
sendTelemetry() currently downlinks only 17 bytes: timestamp, filtered
altitude, vertical velocity, phase, launch confidence and battery. It carries
no attitude, no GPS and no acceleration, so on a real link the 3D attitude
indicator, the map and the acceleration trace will have nothing to show.
`EXTENDED_PACKET_FORMAT` below is a drop-in proposal that adds them; see the
README for the matching firmware snippet.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field, replace
from enum import IntEnum

from .theme import PALETTE


# =====================================================================
# Flight phases -- config.h:78-86
# =====================================================================
class FlightPhase(IntEnum):
    IDLE = 0
    ARMED = 1
    BOOST = 2
    COAST = 3
    APOGEE = 4
    DESCENT = 5
    LANDED = 6

    @property
    def label(self) -> str:
        return _PHASE_LABELS[self]

    @property
    def color(self) -> str:
        return _PHASE_COLORS[self]

    @property
    def blurb(self) -> str:
        return _PHASE_BLURBS[self]

    @classmethod
    def from_value(cls, value: int) -> "FlightPhase":
        try:
            return cls(int(value))
        except (ValueError, TypeError):
            return cls.IDLE


_PHASE_LABELS = {
    FlightPhase.IDLE: "IDLE",
    FlightPhase.ARMED: "ARMED",
    FlightPhase.BOOST: "BOOST",
    FlightPhase.COAST: "COAST",
    FlightPhase.APOGEE: "APOGEE",
    FlightPhase.DESCENT: "DESCENT",
    FlightPhase.LANDED: "LANDED",
}

_PHASE_COLORS = {
    FlightPhase.IDLE: PALETTE.grey,
    FlightPhase.ARMED: PALETTE.green,
    FlightPhase.BOOST: PALETTE.red,
    FlightPhase.COAST: PALETTE.amber,
    FlightPhase.APOGEE: PALETTE.cyan,
    FlightPhase.DESCENT: PALETTE.magenta,
    FlightPhase.LANDED: PALETTE.white,
}

_PHASE_BLURBS = {
    FlightPhase.IDLE: "On pad / safe",
    FlightPhase.ARMED: "Arm sense high",
    FlightPhase.BOOST: "Motor burning",
    FlightPhase.COAST: "Unpowered ascent",
    FlightPhase.APOGEE: "Drogue event",
    FlightPhase.DESCENT: "Under canopy",
    FlightPhase.LANDED: "Touchdown",
}


# =====================================================================
# Flight tuning constants -- config.cpp:11-25
# Mirrored so the ground station annotates plots with the same thresholds
# the vehicle actually flies.
# =====================================================================
@dataclass(frozen=True)
class FlightParams:
    launch_threshold_g: float = 5.0
    apogee_velocity_thresh: float = -2.0
    apogee_imu_vel_thresh: float = -1.5
    apogee_gnss_vel_thresh: float = -1.0
    max_flight_seconds: float = 100.0
    backup_delay_ms: int = 5000
    apogee_persist_samples: int = 5
    launch_debounce: int = 3
    pyro_fire_ms: int = 200
    landing_altitude_thresh: float = 10.0
    landing_velocity_thresh: float = 2.0
    landing_persist_samples: int = 50


PARAMS = FlightParams()


# =====================================================================
# Pyro channels
#
# config.cpp:4 -- PYRO_PINS[4] = {4,5,6,7}
# pyro.cpp:44  -- only channel 0 (drogue) is autonomously fired by the
#                 firmware today; 1..3 are wired but unused.
# =====================================================================
class PyroState(IntEnum):
    DISARMED = 0
    ARMED = 1
    FIRED = 2
    FAULT = 3      # armed but no continuity -- pyro.cpp:37-38

    @property
    def label(self) -> str:
        return {
            PyroState.DISARMED: "DISARMED",
            PyroState.ARMED: "ARMED",
            PyroState.FIRED: "FIRED",
            PyroState.FAULT: "NO CONT",
        }[self]

    @property
    def color(self) -> str:
        return {
            PyroState.DISARMED: PALETTE.grey,
            PyroState.ARMED: PALETTE.green,
            PyroState.FIRED: PALETTE.red,
            PyroState.FAULT: PALETTE.amber,
        }[self]


PYRO_CHANNELS = (
    (0, "DROGUE", "GPIO 4"),
    (1, "MAIN", "GPIO 5"),
    (2, "AUX 1", "GPIO 6"),
    (3, "AUX 2", "GPIO 7"),
)


# =====================================================================
# Telemetry frame
# =====================================================================
@dataclass
class TelemetryFrame:
    """One decoded sample. Field names mirror RocketDataPacket."""

    # --- timing ---------------------------------------------------------
    timestamp_ms: int = 0

    # --- LSM6 low-g IMU -------------------------------------------------
    ax_low: float = 0.0
    ay_low: float = 0.0
    az_low: float = 0.0
    gx: float = 0.0
    gy: float = 0.0
    gz: float = 0.0

    # --- ADXL375 high-g accelerometer (g) -------------------------------
    ax_high: float = 0.0
    ay_high: float = 0.0
    az_high: float = 0.0

    # --- MS5611 barometer ------------------------------------------------
    pressure_pa: float = 0.0
    temperature_c: float = 0.0

    # --- fused state -----------------------------------------------------
    filtered_altitude: float = 0.0
    vertical_velocity: float = 0.0
    imu_vertical_vel: float = 0.0
    battery_voltage: float = 0.0

    # --- state machine ---------------------------------------------------
    flight_phase: FlightPhase = FlightPhase.IDLE
    launch_confidence: int = 0
    apogee_confidence: int = 0

    # --- Madgwick attitude (deg) -----------------------------------------
    roll: float = 0.0
    pitch: float = 90.0     # 90 deg == nose vertical on the pad
    yaw: float = 0.0

    # --- GNSS (SAM-M10Q) --------------------------------------------------
    # Not in RocketDataPacket today -- populated by sources that have it.
    lat: float = 0.0
    lon: float = 0.0
    gps_alt: float = 0.0
    gps_speed: float = 0.0
    gps_heading: float = 0.0
    gps_vertical_vel: float = 0.0
    gps_fix: int = 0            # >=3 is a 3D fix (SAM_M10Q_I2C.h:26)
    gps_sats: int = 0

    # --- link health (ground-side, not from the vehicle) ------------------
    rssi: float = 0.0
    snr: float = 0.0

    # --- pyro -------------------------------------------------------------
    # None => infer from flight phase (see infer_pyro_states).
    pyro_states: tuple[PyroState, ...] | None = None
    armed: bool = False
    # None means "not reported" -- distinct from a measured open circuit.
    continuity: tuple[bool, ...] | None = None

    # ---------------------------------------------------------------------
    @property
    def accel_magnitude_g(self) -> float:
        """|a| from the high-g accelerometer -- matches state_machine.cpp:28."""
        return math.sqrt(self.ax_high ** 2 + self.ay_high ** 2 + self.az_high ** 2)

    @property
    def t_seconds(self) -> float:
        return self.timestamp_ms / 1000.0

    @property
    def altitude_ft(self) -> float:
        return self.filtered_altitude * 3.280839895

    @property
    def has_gps_fix(self) -> bool:
        return self.gps_fix >= 3

    def resolved_pyro(self) -> tuple[PyroState, ...]:
        if self.pyro_states is not None:
            return self.pyro_states
        return infer_pyro_states(self)


def infer_pyro_states(frame: TelemetryFrame) -> tuple[PyroState, ...]:
    """
    Best-effort pyro state when the vehicle does not downlink it.

    RocketDataPacket carries no pyro field, so we reconstruct it from the
    flight phase using the firmware's own logic (pyro.cpp:44): the drogue
    fires on PHASE_APOGEE, and the state machine only leaves APOGEE once
    drogueFired is set or the backup timer expires (state_machine.cpp:87-101).
    """
    phase = frame.flight_phase
    if phase <= FlightPhase.IDLE:
        base = PyroState.DISARMED
    elif frame.armed or phase >= FlightPhase.ARMED:
        base = PyroState.ARMED
    else:
        base = PyroState.DISARMED

    states = [base] * 4

    # Channel 0 (drogue) is commanded at apogee and has certainly fired by
    # the time we are in DESCENT/LANDED.
    if phase >= FlightPhase.DESCENT:
        states[0] = PyroState.FIRED
    # Main is a ground-station inference only -- the firmware does not fly it.
    if phase >= FlightPhase.LANDED:
        states[1] = PyroState.FIRED

    # Downgrade armed channels to FAULT only when continuity was actually
    # measured and came back open. Unreported continuity is not a fault.
    if frame.continuity is not None:
        for i, ok in enumerate(frame.continuity[:4]):
            if states[i] == PyroState.ARMED and not ok:
                states[i] = PyroState.FAULT

    return tuple(states)


# =====================================================================
# Wire formats
# =====================================================================

# --- 1. Full RocketDataPacket (config.h:91-102, __attribute__((packed))) ---
# uint32 | 9f IMU | 2f baro | 3f fused | u8 phase | 2x u8 conf | 3f rpy | f imuVel
FULL_PACKET_FORMAT = "<I9f2f3fB2B4f"
FULL_PACKET_SIZE = struct.calcsize(FULL_PACKET_FORMAT)  # 79 bytes

# --- 2. Current LoRa downlink (telemetry.cpp:19-32) ------------------------
# ts(4) alt(4) vvel(4) phase(1) launchConf(1) vbat_mV(2) xorcrc(1) = 17 bytes
LORA_PACKET_FORMAT = "<IffBBHB"
LORA_PACKET_SIZE = struct.calcsize(LORA_PACKET_FORMAT)  # 17 bytes

# --- 3. Proposed extended downlink (see README) ---------------------------
# Adds attitude, high-g accel and GNSS so the full dashboard works in flight.
# ts(4) alt(4) vvel(4) roll(4) pitch(4) yaw(4) axh(4) ayh(4) azh(4)
# lat(4,int32 1e-7) lon(4,int32 1e-7) gpsAlt(4) phase(1) pyro(1) fix(1)
# launchConf(1) vbat_mV(2) crc(1) = 55 bytes
EXTENDED_PACKET_FORMAT = "<I8fiif4BHB"
EXTENDED_PACKET_SIZE = struct.calcsize(EXTENDED_PACKET_FORMAT)


def xor_crc(payload: bytes) -> int:
    """XOR checksum, matching telemetry.cpp:28-30."""
    crc = 0
    for b in payload:
        crc ^= b
    return crc


def decode_full_packet(raw: bytes) -> TelemetryFrame | None:
    """Decode a raw packed RocketDataPacket (SD /flight.bin or USB dump)."""
    if len(raw) < FULL_PACKET_SIZE:
        return None
    v = struct.unpack(FULL_PACKET_FORMAT, raw[:FULL_PACKET_SIZE])
    return TelemetryFrame(
        timestamp_ms=v[0],
        ax_low=v[1], ay_low=v[2], az_low=v[3],
        gx=v[4], gy=v[5], gz=v[6],
        ax_high=v[7], ay_high=v[8], az_high=v[9],
        pressure_pa=v[10], temperature_c=v[11],
        filtered_altitude=v[12], vertical_velocity=v[13], battery_voltage=v[14],
        flight_phase=FlightPhase.from_value(v[15]),
        launch_confidence=v[16], apogee_confidence=v[17],
        roll=v[18], pitch=v[19], yaw=v[20],
        imu_vertical_vel=v[21],
    )


def decode_lora_packet(raw: bytes, *, verify_crc: bool = True) -> TelemetryFrame | None:
    """
    Decode the 17-byte downlink produced by sendTelemetry().

    Returns None on a length or CRC failure so the caller can count drops.
    Attitude / GPS / acceleration stay at their defaults -- the vehicle does
    not transmit them yet.
    """
    if len(raw) < LORA_PACKET_SIZE:
        return None
    ts, alt, vvel, phase, launch_conf, vbat_mv, crc = struct.unpack(
        LORA_PACKET_FORMAT, raw[:LORA_PACKET_SIZE]
    )
    if verify_crc and xor_crc(raw[:16]) != crc:
        return None
    return TelemetryFrame(
        timestamp_ms=ts,
        filtered_altitude=alt,
        vertical_velocity=vvel,
        flight_phase=FlightPhase.from_value(phase),
        launch_confidence=launch_conf,
        battery_voltage=vbat_mv / 1000.0,
    )


def decode_extended_packet(raw: bytes, *, verify_crc: bool = True) -> TelemetryFrame | None:
    """Decode the proposed extended downlink (see README for the firmware side)."""
    if len(raw) < EXTENDED_PACKET_SIZE:
        return None
    v = struct.unpack(EXTENDED_PACKET_FORMAT, raw[:EXTENDED_PACKET_SIZE])
    if verify_crc and xor_crc(raw[:EXTENDED_PACKET_SIZE - 1]) != v[-1]:
        return None
    (ts, alt, vvel, roll, pitch, yaw, axh, ayh, azh,
     lat_i, lon_i, gps_alt, phase, pyro_bits, fix, launch_conf, vbat_mv, _crc) = v

    pyro = tuple(
        PyroState.FIRED if (pyro_bits >> (i * 2)) & 0b11 == 2
        else PyroState.ARMED if (pyro_bits >> (i * 2)) & 0b11 == 1
        else PyroState.DISARMED
        for i in range(4)
    )
    return TelemetryFrame(
        timestamp_ms=ts,
        filtered_altitude=alt, vertical_velocity=vvel,
        roll=roll, pitch=pitch, yaw=yaw,
        ax_high=axh, ay_high=ayh, az_high=azh,
        lat=lat_i * 1e-7, lon=lon_i * 1e-7, gps_alt=gps_alt,
        flight_phase=FlightPhase.from_value(phase),
        gps_fix=fix,
        launch_confidence=launch_conf,
        battery_voltage=vbat_mv / 1000.0,
        pyro_states=pyro,
        armed=phase >= FlightPhase.ARMED,
    )


# --- 4. CSV, matching logging.cpp:28 --------------------------------------
CSV_LOG_HEADER = "timestamp_ms,alt_m,vel_mps,bat_V,phase,roll,pitch,yaw,pressure_Pa"


def decode_csv_log(line: str) -> TelemetryFrame | None:
    """Parse one row of the on-board /flight.csv low-rate log."""
    parts = line.strip().split(",")
    if len(parts) < 9 or not parts[0].lstrip("-").isdigit():
        return None
    try:
        return TelemetryFrame(
            timestamp_ms=int(float(parts[0])),
            filtered_altitude=float(parts[1]),
            vertical_velocity=float(parts[2]),
            battery_voltage=float(parts[3]),
            flight_phase=FlightPhase.from_value(int(float(parts[4]))),
            roll=float(parts[5]),
            pitch=float(parts[6]),
            yaw=float(parts[7]),
            pressure_pa=float(parts[8]),
        )
    except (ValueError, IndexError):
        return None


# --- 5. Legacy 15-field UDP CSV used by the previous "FC UI" app ----------
LEGACY_UDP_FIELDS = 15


def decode_legacy_udp_csv(line: str) -> TelemetryFrame | None:
    """
    Parse the CSV schema emitted by the older FC UI simulator:

        timestamp, gx, gy, gz, ax, ay, az, high_g_ax, baro_alt,
        lat, lon, gps_alt, v_bat, rssi, pyro_status
    """
    try:
        p = [float(x) for x in line.strip().split(",")]
    except ValueError:
        return None
    if len(p) < LEGACY_UDP_FIELDS:
        return None
    fired = int(p[14]) != 0
    return TelemetryFrame(
        timestamp_ms=int(p[0] * 1000) % (2 ** 32),
        gx=p[1], gy=p[2], gz=p[3],
        ax_low=p[4], ay_low=p[5], az_low=p[6],
        ax_high=p[7],
        filtered_altitude=p[8],
        lat=p[9], lon=p[10], gps_alt=p[11],
        battery_voltage=p[12],
        rssi=p[13],
        gps_fix=3,
        pyro_states=(
            PyroState.FIRED if fired else PyroState.ARMED,
            PyroState.ARMED, PyroState.DISARMED, PyroState.DISARMED,
        ),
        armed=True,
    )


__all__ = [
    "FlightPhase", "PyroState", "PYRO_CHANNELS", "FlightParams", "PARAMS",
    "TelemetryFrame", "infer_pyro_states", "xor_crc",
    "FULL_PACKET_FORMAT", "FULL_PACKET_SIZE",
    "LORA_PACKET_FORMAT", "LORA_PACKET_SIZE",
    "EXTENDED_PACKET_FORMAT", "EXTENDED_PACKET_SIZE",
    "decode_full_packet", "decode_lora_packet", "decode_extended_packet",
    "decode_csv_log", "decode_legacy_udp_csv", "CSV_LOG_HEADER",
    "replace", "field",
]
