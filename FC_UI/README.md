# NRL Ground Station 2.0

Desktop telemetry dashboard for the Acceltra ESP32 flight computer.
PyQt6 + pyqtgraph, "New Space" dark theme, dock-based layout.

Everything in the data model is derived from the firmware in
`Flight-Computer-Project---ESP32/Acceltra/src/`, so the ground station and
the vehicle cannot silently drift apart.

---

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

That launches the dashboard driven by a **synthetic flight** — no radio, no
hardware. It flies a complete mission through all seven phases from
`config.h` (apogee ≈ 2 155 m / 7 070 ft, 10.6 g peak, both pyros firing) and
recycles when it lands.

The real mission takes 167 s. To review it faster:

```bash
python main.py --speed 4          # 4x playback
```

Other sources:

```bash
python main.py --source serial --port COM5 --baud 115200
python main.py --source udp --udp-port 5005
```

Verify the install end to end (builds the real window, flies the whole
mission, fails on any exception raised inside a Qt slot):

```bash
python smoke_test.py
```

---

## What you need to install

| Package | Needed for | If missing |
|---|---|---|
| `PyQt6`, `pyqtgraph`, `numpy` | everything | app will not start |
| `PyOpenGL`, `PyOpenGL-accelerate` | 3D attitude indicator | 3D pane shows an install hint; numbers still update |
| `PyQt6-WebEngine` | live Leaflet map | falls back to an offline pyqtgraph ground track |
| `pyserial` | `--source serial` | serial source reports the missing module |

Leaflet itself is vendored locally (`widgets/vendor/`), so markers, the
trajectory track, and the "NO GPS FIX" banner all work with no network
access. Only the CARTO dark tile imagery is pulled live and needs a
connection — without it the basemap stays blank but everything else keeps
working. The raw lat/lon readouts and a copyable "last known position"
field (pastable straight into Google Maps) are always shown regardless of
map or network state.

---

## Layout

```
+-------------------------------------------------------------------+
| toolbar:  NRL | source | connect | link state                      |
+------------+--------------------------------+---------------------+
| ATTITUDE   |  FLIGHT PHASE banner + track   |  GPS TRAJECTORY     |
| 3D + r/p/y |--------------------------------|  (Leaflet)          |
|------------|  ALTITUDE                      |---------------------|
| PYRO       |  ACCELERATION                  |  VEHICLE STATUS     |
| CHANNELS   |  VERTICAL VELOCITY             |  (stat tiles)       |
+------------+--------------------------------+---------------------+
| EVENT LOG                                                         |
+-------------------------------------------------------------------+
```

Every pane is a `QDockWidget` — drag them apart, float them, or push them
onto a second monitor during a launch.

### Components

- **3D attitude** (`widgets/attitude3d.py`) — OpenGL rocket (body, nose,
  navy band, four swept fins, nozzle) slewed to the Madgwick roll/pitch/yaw,
  with large numeric readouts and a derived *tilt from vertical*.
- **Map** (`widgets/mapview.py`) — dark Leaflet basemap, heading-aware
  rocket marker, live trajectory polyline, launch-site and apogee markers,
  follow/fit/clear controls, and a raw lat/lon/alt/speed/downrange strip.
- **Graphs** (`widgets/graphs.py`) — scrolling altitude, acceleration and
  vertical-velocity plots. **Hover any plot** and a crosshair snaps to the
  *nearest real sample* and shows every series' exact value at that
  timestamp — no interpolation. Phase transitions are annotated with
  vertical event markers. Manual pan/zoom drops out of follow mode so you
  can inspect history while data keeps streaming.
- **Pyro panel** (`widgets/pyro.py`) — colour-coded badges per channel.
- **Phase display** (`widgets/phase.py`) — large current phase, mission
  clock, and a progression track showing all seven states.

---

## Flight phases

Read directly from `config.h:78-86`:

| # | Phase | Colour | Enters when |
|---|---|---|---|
| 0 | `IDLE` | grey | power-up, on the pad |
| 1 | `ARMED` | green | `ARMING_SENSE_PIN` high, or BLE arm |
| 2 | `BOOST` | red | \|a\| > 5 g for 3 samples |
| 3 | `COAST` | amber | `az_high < 2.0 g` |
| 4 | `APOGEE` | cyan | baro/IMU/GNSS velocity negative for 5 samples |
| 5 | `DESCENT` | magenta | drogue fired, or 5 s backup timer |
| 6 | `LANDED` | white | < 10 m AGL and \|vz\| < 2 m/s for 50 samples |

Pyro colours: **grey** disarmed · **green** armed · **red** fired ·
**amber** armed but no continuity (`pyro.cpp:37-38`).

---

## Two firmware gaps this dashboard exposes

### 1. The radio downlink cannot feed most of this UI

`sendTelemetry()` (`telemetry.cpp:19-32`) transmits **17 bytes**:

```
timestampMs(4) filteredAltitude(4) verticalVelocity(4)
flightPhase(1) launchConfidence(1) vbat_mV(2) xorCRC(1)
```

No attitude, no GPS, no acceleration. Over a real link the 3D indicator, the
map and the acceleration trace have nothing to show. `decode_lora_packet()`
handles this frame today (CRC-checked, verified against the firmware), and
the affected panels simply hold their defaults.

`decode_extended_packet()` implements a **55-byte** drop-in replacement that
closes the gap. Firmware side:

```cpp
// telemetry.cpp — 55-byte extended downlink
void sendTelemetryExtended(const RocketDataPacket &p, uint8_t pyroBits) {
    uint8_t buf[55];
    size_t o = 0;
    memcpy(buf+o, &p.timestampMs,      4); o += 4;
    memcpy(buf+o, &p.filteredAltitude, 4); o += 4;
    memcpy(buf+o, &p.verticalVelocity, 4); o += 4;
    memcpy(buf+o, &p.roll,             4); o += 4;
    memcpy(buf+o, &p.pitch,            4); o += 4;
    memcpy(buf+o, &p.yaw,              4); o += 4;
    memcpy(buf+o, &p.ax_high,          4); o += 4;
    memcpy(buf+o, &p.ay_high,          4); o += 4;
    memcpy(buf+o, &p.az_high,          4); o += 4;

    int32_t lat = (int32_t)(gps.getLatitude()  * 1e7);
    int32_t lon = (int32_t)(gps.getLongitude() * 1e7);
    float   ga  = gps.getAltitude();
    memcpy(buf+o, &lat, 4); o += 4;
    memcpy(buf+o, &lon, 4); o += 4;
    memcpy(buf+o, &ga,  4); o += 4;

    buf[o++] = p.flightPhase;
    buf[o++] = pyroBits;                    // 2 bits/ch: 0=disarmed 1=armed 2=fired
    buf[o++] = gps.hasFix() ? 3 : 0;
    buf[o++] = p.launchConfidence;

    uint16_t vb = (uint16_t)(p.batteryVoltage * 1000);
    memcpy(buf+o, &vb, 2); o += 2;

    uint8_t crc = 0;
    for (size_t i = 0; i < o; i++) crc ^= buf[i];
    buf[o++] = crc;

    radio.transmit(buf, o);                 // o == 55
}
```

**Watch the airtime.** At the configured SF9 / BW125 / CR 4/7
(`telemetry.cpp:11`), 55 bytes is roughly 200 ms on air — a hard ceiling of
about 5 packets/s, and `radio.transmit()` blocks for all of it. Send from a
dedicated task at 5–10 Hz, not from the 100 Hz sensor loop, or the state
machine will starve. If you need more, drop to SF7 or split attitude and GPS
across alternating frames.

### 2. `RocketDataPacket` has no pyro field

`config.h:91-102` carries no pyro state, so the panel reconstructs it from
the flight phase using the firmware's own logic — channel 0 fires on
`PHASE_APOGEE` (`pyro.cpp:44`), and the state machine only leaves `APOGEE`
once `drogueFired` is set (`state_machine.cpp:87-101`). That inference is in
`infer_pyro_states()`.

It is an inference, not measurement. Channel 1 (main) in particular is shown
as fired at `LANDED` purely by convention — **the firmware never fires it.**
Add the `pyroBits` byte above and the panel switches to real data
automatically; no UI change needed.

---

## Wiring up real telemetry

All four wire formats are implemented and unit-checked against the firmware:

| Decoder | Source | Size |
|---|---|---|
| `decode_lora_packet` | `sendTelemetry()` as it stands today | 17 B |
| `decode_extended_packet` | the proposed downlink above | 55 B |
| `decode_full_packet` | packed `RocketDataPacket` (SD `/flight.bin`, USB) | 79 B |
| `decode_csv_log` | on-board `/flight.csv` (`logging.cpp:28`) | text |
| `decode_legacy_udp_csv` | the previous FC UI's 15-field UDP schema | text |

**Serial** expects either newline CSV, or binary frames `AA 55 <len>
<payload>` — the payload length selects the decoder. **UDP** accepts raw
payloads or CSV, so the old `FC UI/simulate_rocket.py` drives this dashboard
unchanged:

```bash
python "../FC UI/simulate_rocket.py"      # in one terminal
python main.py --source udp               # in another
```

To add a source of your own, subclass `TelemetrySource` in `sources.py` and
emit `TelemetryFrame` objects on the `frame` signal — nothing in the UI
needs to change.

---

## Notes

- **Threading.** Sources run on `QThread`s and emit frames at full rate.
  Frames are buffered on arrival but widgets repaint on a 20 Hz timer (map
  4 Hz), which is what keeps the UI fluid at 100 Hz telemetry. Plot data
  lives in a fixed-capacity ring buffer, so a long hold-and-scrub session
  will not grow memory without bound.
- **Attitude convention.** The model is nose-along +Z in an ENU world frame:
  `pitch` is elevation (90° = vertical on the pad), `yaw` is compass heading,
  `roll` is rotation about the long axis. If the IMU is mounted differently,
  change `PITCH_OFFSET` / `ATTITUDE_SIGNS` at the top of `attitude3d.py`
  rather than anything else.
- **Launch site** defaults to Spaceport America's Vertical Launch Area
  (32.99025, −106.97500) for IREC. Change `LAUNCH_SITE` in `sources.py`.
- **Mock playback rate.** `--speed` is a target, not a guarantee; queued
  signal delivery caps sustained throughput at roughly 250–350 frames/s
  (≈6× real time), which is well clear of the vehicle's real 100 Hz.
