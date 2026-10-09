"""
Pyrotechnic channel status panel.

Four colour-coded badges, one per channel, matching PYRO_PINS[4] = {4,5,6,7}
in config.cpp.

    DISARMED  grey     safe, output low
    ARMED     green    arm sense high and continuity good
    FIRED     red      channel has been commanded
    NO CONT   amber    armed but continuity check failed (pyro.cpp:37-38)

The firmware autonomously fires channel 0 (drogue) at apogee; channels 1-3
are wired but not flown yet, so their state is a ground-station inference
until the vehicle downlinks a real pyro bitfield.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..telemetry import PYRO_CHANNELS, PyroValve
from ..theme import FONT_MONO, PALETTE


class _PyroBadge(QFrame):
    """One channel: name, pin, big state badge and a continuity dot."""

    def __init__(self, index: int, name: str, pin: str, parent=None):
        super().__init__(parent)
        self.index = index
        self._state = PyroValve.IDLE

        self.setMinimumHeight(74)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 9)
        lay.setSpacing(5)

        # ---- header row ----------------------------------------------
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)

        self._name = QLabel(f"CH{index} · {name}")
        self._name.setStyleSheet(
            f"color:{PALETTE.text}; font-size:11px; font-weight:700;"
            "letter-spacing:0.6px; background:transparent; border:none;"
        )
        head.addWidget(self._name)
        head.addStretch(1)

        self._cont = QLabel("○")
        self._cont.setToolTip("Continuity")
        self._cont.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:13px;"
            "background:transparent; border:none;"
        )
        head.addWidget(self._cont)

        self._pin = QLabel(pin)
        self._pin.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-family:{FONT_MONO}; font-size:9px;"
            "background:transparent; border:none;"
        )
        head.addWidget(self._pin)
        lay.addLayout(head)

        # ---- state badge ----------------------------------------------
        self._badge = QLabel("DISARMED")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setMinimumHeight(30)
        lay.addWidget(self._badge)

        self._apply(PyroValve.IDLE, continuity=None)

    # -----------------------------------------------------------------
    def set_state(self, state: PyroValve, continuity: bool | None) -> None:
        if state == self._state and continuity == getattr(self, "_last_cont", "unset"):
            return
        self._state = state
        self._last_cont = continuity
        self._apply(state, continuity)

    def _apply(self, state: PyroValve, continuity: bool | None) -> None:
        color = state.color
        self._badge.setText(state.label)

        # FIRED gets a filled, glowing treatment so it reads across the room.
        if state == PyroValve.FIRED:
            badge_css = (
                f"color:{PALETTE.bg_deep}; background-color:{color};"
                f"border:1px solid {color};"
            )
            frame_css = f"border:1px solid {color}; background-color:#1C1013;"
        else:
            badge_css = (
                f"color:{color}; background-color:rgba(0,0,0,0.28);"
                f"border:1px solid {color};"
            )
            frame_css = (
                f"border:1px solid {PALETTE.border}; background-color:{PALETTE.panel_alt};"
            )

        self._badge.setStyleSheet(
            badge_css
            + "border-radius:3px; font-size:14px; font-weight:800; letter-spacing:2px;"
        )
        self.setStyleSheet(frame_css + "border-radius:3px;")

        if continuity is None:
            dot, dot_color, tip = "·", PALETTE.text_faint, "Continuity not reported"
        elif continuity:
            dot, dot_color, tip = "●", PALETTE.green, "Continuity OK"
        else:
            dot, dot_color, tip = "○", PALETTE.text_faint, "No continuity"

        self._cont.setText(dot)
        self._cont.setStyleSheet(
            f"color:{dot_color}; font-size:13px; background:transparent; border:none;"
        )
        self._cont.setToolTip(tip)


class PyroPanel(QWidget):
    """2x2 grid of pyro channel badges plus a master arm indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- master arm state ----------------------------------------
        self.master = QLabel("SAFE")
        self.master.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.master.setMinimumHeight(28)
        root.addWidget(self.master)
        self._master_armed: bool | None = None
        self._set_master(False)

        # ---- channels -------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(7)
        self.badges: list[_PyroBadge] = []
        for i, (index, name, pin) in enumerate(PYRO_CHANNELS):
            badge = _PyroBadge(index, name, pin)
            self.badges.append(badge)
            grid.addWidget(badge, i // 2, i % 2)
        root.addLayout(grid)
        root.addStretch(1)

    # -----------------------------------------------------------------
    def _set_master(self, armed: bool) -> None:
        if armed == self._master_armed:
            return
        self._master_armed = armed
        color = PALETTE.green if armed else PALETTE.grey
        self.master.setText("ARM SENSE ACTIVE" if armed else "SAFE — DISARMED")
        self.master.setStyleSheet(
            f"color:{color}; border:1px solid {color}; border-radius:3px;"
            "background-color:rgba(0,0,0,0.3); font-size:12px; font-weight:800;"
            "letter-spacing:2px;"
        )

    def update_frame(self, frame) -> None:
        states = frame.resolved_pyro()
        continuity = frame.continuity
        for i, badge in enumerate(self.badges):
            badge.set_state(
                states[i] if i < len(states) else PyroValve.IDLE,
                continuity[i] if continuity and i < len(continuity) else None,
            )
        self._set_master(frame.armed or any(s != PyroValve.IDLE for s in states))
