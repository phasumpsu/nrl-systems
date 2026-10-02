"""
Vehicle status tiles and the mission event log.
"""

from __future__ import annotations

import time
from collections import deque

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..telemetry import PARAMS
from ..theme import FONT_MONO, PALETTE


# =====================================================================
class StatTile(QFrame):
    """A single labelled value with an optional secondary line."""

    def __init__(self, label: str, unit: str = "", color: str = PALETTE.text, parent=None):
        super().__init__(parent)
        self._unit = unit
        self._color = color

        self.setStyleSheet(
            f"background-color:{PALETTE.panel_alt}; border:1px solid {PALETTE.border};"
            "border-radius:3px;"
        )
        self.setMinimumWidth(112)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 8)
        lay.setSpacing(1)

        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700;"
            "letter-spacing:1px; border:none; background:transparent;"
        )

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)

        self._value = QLabel("—")
        self._value.setStyleSheet(
            f"color:{color}; font-family:{FONT_MONO}; font-size:20px;"
            "font-weight:600; border:none; background:transparent;"
        )
        self._unit_label = QLabel(unit)
        self._unit_label.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:10px; border:none;"
            "background:transparent;"
        )
        row.addWidget(self._value)
        row.addWidget(self._unit_label)

        self._sub = QLabel("")
        self._sub.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-family:{FONT_MONO}; font-size:9px;"
            "border:none; background:transparent;"
        )

        lay.addWidget(self._label)
        lay.addLayout(row)
        lay.addWidget(self._sub)

    def set(self, value: str, sub: str = "", color: str | None = None) -> None:
        self._value.setText(value)
        self._sub.setText(sub)
        if color and color != self._color:
            self._color = color
            self._value.setStyleSheet(
                f"color:{color}; font-family:{FONT_MONO}; font-size:20px;"
                "font-weight:600; border:none; background:transparent;"
            )


# =====================================================================
class StatusPanel(QWidget):
    """Key flight numbers, peaks, and link health."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.max_altitude = 0.0
        self.max_velocity = 0.0
        self.max_accel = 0.0
        self.packet_count = 0
        self.bad_packets = 0
        self._last_rx = 0.0
        self._rate_window: deque[float] = deque(maxlen=40)

        grid = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(7)

        self.tiles: dict[str, StatTile] = {}

        def add(key: str, label: str, unit: str, row: int, col: int,
                color: str = PALETTE.text) -> None:
            tile = StatTile(label, unit, color)
            self.tiles[key] = tile
            grid.addWidget(tile, row, col)

        add("altitude", "ALTITUDE AGL", "m", 0, 0, PALETTE.cyan)
        add("velocity", "VERT VELOCITY", "m/s", 0, 1, PALETTE.cyan)
        add("accel", "ACCELERATION", "g", 0, 2, PALETTE.amber)
        add("apogee", "APOGEE", "m", 0, 3, PALETTE.magenta)

        add("battery", "BATTERY", "V", 1, 0, PALETTE.green)
        add("rssi", "LINK RSSI", "dBm", 1, 1, PALETTE.green)
        add("rate", "PACKET RATE", "Hz", 1, 2)
        add("temp", "BOARD TEMP", "°C", 1, 3)

        for col in range(4):
            grid.setColumnStretch(col, 1)

    # -----------------------------------------------------------------
    def note_packet(self) -> None:
        now = time.perf_counter()
        self.packet_count += 1
        if self._last_rx:
            self._rate_window.append(now - self._last_rx)
        self._last_rx = now

    def reset(self) -> None:
        self.max_altitude = 0.0
        self.max_velocity = 0.0
        self.max_accel = 0.0
        self.packet_count = 0
        self.bad_packets = 0
        self._rate_window.clear()
        self._last_rx = 0.0

    # -----------------------------------------------------------------
    def update_frame(self, frame) -> None:
        self.max_altitude = max(self.max_altitude, frame.filtered_altitude)
        self.max_velocity = max(self.max_velocity, abs(frame.vertical_velocity))
        self.max_accel = max(self.max_accel, frame.accel_magnitude_g)

        self.tiles["altitude"].set(
            f"{frame.filtered_altitude:,.0f}",
            f"{frame.altitude_ft:,.0f} ft",
        )
        self.tiles["velocity"].set(
            f"{frame.vertical_velocity:+,.1f}",
            f"mach {abs(frame.vertical_velocity) / 343.0:.2f}",
            PALETTE.cyan if frame.vertical_velocity >= 0 else PALETTE.magenta,
        )

        accel = frame.accel_magnitude_g
        self.tiles["accel"].set(
            f"{accel:,.1f}",
            f"peak {self.max_accel:,.1f} g",
            PALETTE.red if accel > PARAMS.launch_threshold_g else PALETTE.amber,
        )
        self.tiles["apogee"].set(
            f"{self.max_altitude:,.0f}",
            f"{self.max_altitude * 3.28084:,.0f} ft",
        )

        volts = frame.battery_voltage
        self.tiles["battery"].set(
            f"{volts:,.2f}",
            "2S LiPo",
            PALETTE.green if volts > 7.4 else PALETTE.amber if volts > 7.0 else PALETTE.red,
        )

        rssi = frame.rssi
        self.tiles["rssi"].set(
            f"{rssi:,.0f}" if rssi else "—",
            f"snr {frame.snr:,.1f}" if frame.snr else "",
            PALETTE.green if rssi > -90 else PALETTE.amber if rssi > -110 else PALETTE.red,
        )

        if self._rate_window:
            mean_dt = sum(self._rate_window) / len(self._rate_window)
            rate = 1.0 / mean_dt if mean_dt > 0 else 0.0
            self.tiles["rate"].set(f"{rate:,.0f}", f"{self.packet_count:,} pkts")

        self.tiles["temp"].set(f"{frame.temperature_c:,.1f}", f"{frame.pressure_pa / 100:,.0f} hPa")


# =====================================================================
class EventLog(QWidget):
    """Timestamped, severity-coloured mission log."""

    COLORS = {
        "info": PALETTE.text_dim,
        "warn": PALETTE.amber,
        "error": PALETTE.red,
        "event": PALETTE.cyan,
    }

    def __init__(self, max_lines: int = 800, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(max_lines)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.view)

        self._t0 = time.time()

    def log(self, severity: str, message: str) -> None:
        elapsed = time.time() - self._t0
        stamp = f"[{int(elapsed // 60):02d}:{elapsed % 60:05.2f}]"

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.COLORS.get(severity, PALETTE.text_dim)))

        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"{stamp}  {message}\n", fmt)
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()

    def clear(self) -> None:
        self.view.clear()
        self._t0 = time.time()
