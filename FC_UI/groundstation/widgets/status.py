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
    """Read-only engine measurements and receive count."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.packet_count = 0
        self._last_rx = None

        grid = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(7)

        self.tiles = {}

        specs = (
            ("thrust", "THRUST", "N"),
            ("weight", "NITROUS WEIGHT", "lbs"),
            ("run_pressure", "RUN TANK", "psi"),
            ("cc_pressure", "CHAMBER", "psi"),
            ("top_temp", "TOP CC TEMP", "°C"),
            ("bot_temp", "BOTTOM CC TEMP", "°C"),
            ("mcu_time", "MCU TIME", "s"),
            ("packets", "VALID FRAMES", ""),
        )

        for i, (key, label, unit) in enumerate(specs):
            tile = StatTile(label, unit)
            self.tiles[key] = tile
            grid.addWidget(tile, i // 4, i % 4)

    def note_packet(self) -> None:
        self.packet_count += 1
        self._last_rx = time.monotonic()
        self.tiles["packets"].set(str(self.packet_count))

    def reset(self) -> None:
        self.packet_count = 0
        self._last_rx = None
        for tile in self.tiles.values():
            tile.set("—")

    def update_frame(self, frame) -> None:
        self.tiles["thrust"].set(f"{frame.engine_thrust_n:.1f}")
        self.tiles["weight"].set(f"{frame.nitrous_weight_lbs:.0f}")
        self.tiles["run_pressure"].set(f"{frame.run_tank_pressure_psi:.1f}")
        self.tiles["cc_pressure"].set(f"{frame.cc_pressure_psi:.1f}")
        self.tiles["top_temp"].set(f"{frame.top_cc_temp_c:.1f}")
        self.tiles["bot_temp"].set(f"{frame.bot_cc_temp_c:.1f}")
        self.tiles["mcu_time"].set(f"{frame.mcu_time_s:.1f}")


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
