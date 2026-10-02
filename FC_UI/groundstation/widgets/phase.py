"""
Flight phase display.

A large current-phase readout backed by a progression track showing all seven
states from config.h, so it is obvious at a glance both where the vehicle is
and how far through the mission it has got.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ..telemetry import FlightPhase
from ..theme import FONT_MONO, PALETTE


class _PhaseStep(QLabel):
    """One segment of the phase progression track."""

    def __init__(self, phase: FlightPhase, parent=None):
        super().__init__(phase.label, parent)
        self.phase = phase
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(24)
        self.set_state("pending")

    def set_state(self, state: str) -> None:
        """state: 'done' | 'active' | 'pending'"""
        if state == "active":
            color = self.phase.color
            css = (
                f"color:{PALETTE.bg_deep}; background-color:{color};"
                f"border:1px solid {color}; font-weight:800;"
            )
        elif state == "done":
            css = (
                f"color:{PALETTE.text_dim}; background-color:{PALETTE.panel_alt};"
                f"border:1px solid {PALETTE.border_bright}; font-weight:600;"
            )
        else:
            css = (
                f"color:{PALETTE.text_faint}; background-color:transparent;"
                f"border:1px solid {PALETTE.border}; font-weight:600;"
            )
        self.setStyleSheet(css + "border-radius:2px; font-size:10px; letter-spacing:1px;")


class PhaseDisplay(QFrame):
    """Prominent current-phase banner + mission clock + progression track."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = FlightPhase.IDLE

        self.setStyleSheet(
            f"background-color:{PALETTE.panel}; border:1px solid {PALETTE.border};"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 11)
        root.setSpacing(9)

        # ---- headline row ---------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(0)
        cap = QLabel("FLIGHT PHASE")
        cap.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700;"
            "letter-spacing:1.6px; border:none;"
        )
        self.phase_label = QLabel("IDLE")
        self.phase_label.setStyleSheet(
            f"color:{PALETTE.grey}; font-size:38px; font-weight:800;"
            "letter-spacing:2px; border:none;"
        )
        self.blurb = QLabel(FlightPhase.IDLE.blurb)
        self.blurb.setStyleSheet(
            f"color:{PALETTE.text_dim}; font-size:11px; border:none;"
        )
        left.addWidget(cap)
        left.addWidget(self.phase_label)
        left.addWidget(self.blurb)
        row.addLayout(left)

        row.addStretch(1)

        # ---- mission clock --------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(0)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_cap = QLabel("MISSION ELAPSED")
        clock_cap.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_cap.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700;"
            "letter-spacing:1.6px; border:none;"
        )
        self.clock = QLabel("T+ 00:00.0")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock.setStyleSheet(
            f"color:{PALETTE.cyan}; font-family:{FONT_MONO}; font-size:30px;"
            "font-weight:700; border:none;"
        )
        self.since = QLabel("in phase 0.0 s")
        self.since.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.since.setStyleSheet(
            f"color:{PALETTE.text_dim}; font-size:11px; border:none;"
        )
        right.addWidget(clock_cap)
        right.addWidget(self.clock)
        right.addWidget(self.since)
        row.addLayout(right)

        root.addLayout(row)

        # ---- progression track -----------------------------------------
        track = QHBoxLayout()
        track.setSpacing(4)
        self.steps = []
        for phase in FlightPhase:
            step = _PhaseStep(phase)
            self.steps.append(step)
            track.addWidget(step)
        root.addLayout(track)

        self._refresh_track()

    # -----------------------------------------------------------------
    def set_phase(self, phase: FlightPhase) -> None:
        if phase == self._phase:
            return
        self._phase = phase
        self.phase_label.setText(phase.label)
        self.phase_label.setStyleSheet(
            f"color:{phase.color}; font-size:38px; font-weight:800;"
            "letter-spacing:2px; border:none;"
        )
        self.blurb.setText(phase.blurb)
        self._refresh_track()

    def _refresh_track(self) -> None:
        for step in self.steps:
            if step.phase < self._phase:
                step.set_state("done")
            elif step.phase == self._phase:
                step.set_state("active")
            else:
                step.set_state("pending")

    def set_clock(self, t_seconds: float, time_in_phase: float) -> None:
        minutes, seconds = divmod(max(0.0, t_seconds), 60.0)
        self.clock.setText(f"T+ {int(minutes):02d}:{seconds:04.1f}")
        self.since.setText(f"in phase {time_in_phase:.1f} s")
