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
from ..telemetry import ObservedState, RoutineSequence

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
        row.setSpacing(1)
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
    """Compact read-only panel for either states or numerical measurements."""

    NUMERIC_SPECS = (
        ("thrust", "THRUST", "Lbf"),
        ("weight", "NITROUS WEIGHT", "lbs"),
        ("run_pressure", "RUN TANK", "psi"),
        ("cc_pressure", "CHAMBER", "psi"),
        ("top_temp", "TOP CC TEMP", "°F"),
        ("bot_temp", "BOTTOM CC TEMP", "°F"),
        ("mcu_time", "MCU TIME", "s"),
        ("packets", "VALID FRAMES", ""),
    )

    STATE_SPECS = (
        ("sv11_state", "SV11 - Ground Tank", ""),
        ("sv12_state", "SV12 - Vent", ""),
        ("sv13_state", "SV13 - Fill Tank", ""),
        ("ignitor_state", "IGNITOR", ""),
        ("armed_status", "ARMED?", ""),
        ("routine_sequence", "CURRENT ROUTINE", ""),
    )

    def __init__(self, kind: str = "numbers", parent=None):
        super().__init__(parent)

        if kind not in ("numbers", "states"):
            raise ValueError(f"Unknown status panel kind: {kind}")

        self.kind = kind
        self.packet_count = 0
        self._last_rx = None
        self.tiles: dict[str, StatTile] = {}

        grid = QGridLayout(self)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(2)

        specs = self.STATE_SPECS if kind == "states" else self.NUMERIC_SPECS

        for i, (key, label, unit) in enumerate(specs):
            tile = StatTile(label, unit)
            self.tiles[key] = tile

            if kind == "states":
                grid.addWidget(tile, i, 0)       # Vertical left column
            else:
                grid.addWidget(tile, i // 4, i % 4)  # Two compact bottom rows

        if kind == "states":
            grid.setRowStretch(len(specs), 1)
            self.setFixedWidth(100)
        else:
            for column in range(4):
                grid.setColumnStretch(column, 1)

    def note_packet(self) -> None:
        if self.kind == "numbers":
            self.packet_count += 1
            self._last_rx = time.monotonic()
            self.tiles["packets"].set(str(self.packet_count))

    def reset(self) -> None:
        self.packet_count = 0
        self._last_rx = None
        for tile in self.tiles.values():
            tile.set("—")

    def update_frame(self, frame) -> None:
        if self.kind == "numbers":
            values = {
                "thrust": ("engine_thrust_lbf", ".1f"),
                "weight": ("nitrous_weight_lbs", ".0f"),
                "run_pressure": ("run_tank_pressure_psi", ".1f"),
                "cc_pressure": ("cc_pressure_psi", ".1f"),
                "top_temp": ("top_cc_temp_f", ".1f"),
                "bot_temp": ("bot_cc_temp_f", ".1f"),
                "mcu_time": ("mcu_time_s", ".1f"),
            }
            for tile_key, (field_name, format_spec) in values.items():
                value = getattr(frame, field_name, None)
                text = format(value, format_spec) if value is not None else "—"
                self.tiles[tile_key].set(text)
            return

        state_names = {
            "sv11_state": {0: "UNKNOWN", 1: "OPEN", 2: "CLOSED", 3: "FAULT"},
            "sv12_state": {0: "UNKNOWN", 1: "OPEN", 2: "CLOSED", 3: "FAULT"},
            "sv13_state": {0: "UNKNOWN", 1: "OPEN", 2: "CLOSED", 3: "FAULT"},
            "ignitor_state": {0: "UNKNOWN", 1: "OPEN", 2: "CLOSED", 3: "FAULT"},
            "armed_status": {0: "UNKNOWN", 1: "ARMED", 2: "DISARMED", 3: "FAULT"},
            "routine_sequence": {0: "NONE", 1: "FIRE", 2: "LONG_FILL", 3: "SHORT_FILL", 4: "ROUTINE_4", 5: "ROUTINE_5"},
        }
        for key, _, _ in self.STATE_SPECS:
            value = getattr(frame, key, None)
            text = state_names[key].get(value, f"UNKNOWN ({value})")
            self.tiles[key].set(text)

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
