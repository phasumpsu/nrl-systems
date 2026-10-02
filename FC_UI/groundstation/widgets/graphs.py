"""
Real-time scrolling telemetry plots with a live-value readout.

`TelemetryPlot` keeps its samples in a ring buffer and draws a rolling
window. A column to the right of each plot shows the current value of every
series, updated every redraw -- no hovering required, so the numbers are
always visible at a glance.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from ..theme import FONT_MONO, PALETTE

# Antialiasing is a well-known heavy cost for pyqtgraph's real-time
# scrolling line plots -- with 6 curves redrawn at 20 Hz over a rolling
# window of up to thousands of samples, it's the single biggest lever
# available for keeping this responsive. Off is barely noticeable on a
# 2px line; on, it can visibly throttle the whole event loop.
pg.setConfigOptions(antialias=False, background=PALETTE.bg_deep, foreground=PALETTE.text_dim)


# =====================================================================
class RingBuffer:
    """Fixed-capacity, amortised O(1) append buffer for t + N series."""

    def __init__(self, capacity: int, n_series: int):
        self.capacity = capacity
        self._t = np.zeros(capacity, dtype=float)
        self._v = np.zeros((n_series, capacity), dtype=float)
        self._n = 0

    def append(self, t: float, values) -> None:
        if self._n >= self.capacity:
            keep = self.capacity // 2
            self._t[:keep] = self._t[self._n - keep:self._n]
            self._v[:, :keep] = self._v[:, self._n - keep:self._n]
            self._n = keep
        self._t[self._n] = t
        for i, val in enumerate(values):
            self._v[i, self._n] = val
        self._n += 1

    def clear(self) -> None:
        self._n = 0

    @property
    def n(self) -> int:
        return self._n

    @property
    def t(self) -> np.ndarray:
        return self._t[:self._n]

    def series(self, i: int) -> np.ndarray:
        return self._v[i, :self._n]


# =====================================================================
class _LiveValue(QWidget):
    """One series' current value, colour-matched to its curve."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)

        name = QLabel(label.upper())
        name.setWordWrap(True)
        name.setStyleSheet(
            f"color:{color}; font-size:9px; font-weight:700; letter-spacing:0.5px;"
        )
        self._value = QLabel("—")
        self._value.setStyleSheet(
            f"color:{PALETTE.text}; font-family:{FONT_MONO}; font-size:16px; font-weight:700;"
        )
        lay.addWidget(name)
        lay.addWidget(self._value)

    def set(self, text: str) -> None:
        self._value.setText(text)


# =====================================================================
class TelemetryPlot(QWidget):
    """One titled plot with 1..N series, a rolling window and a live-value column."""

    def __init__(
        self,
        title: str,
        unit: str,
        series: list[tuple[str, str]],       # (label, colour)
        window_s: float = 45.0,
        capacity: int = 24000,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.window_s = window_s
        self.follow = True
        self._specs = series
        self._buf = RingBuffer(capacity, len(series))
        self._markers: list[pg.InfiniteLine] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addLayout(self._build_header())

        # ---- plot + live-value column ---------------------------------
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.13)
        self.plot.setLabel("left", f"{title} [{unit}]")
        self.plot.setLabel("bottom", "T+ [s]")
        self.plot.getAxis("left").setPen(pg.mkPen(PALETTE.border_bright))
        self.plot.getAxis("bottom").setPen(pg.mkPen(PALETTE.border_bright))
        self.plot.getAxis("left").setTextPen(pg.mkPen(PALETTE.text_faint))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen(PALETTE.text_faint))
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")
        body.addWidget(self.plot, 1)

        self.curves = [
            self.plot.plot(pen=pg.mkPen(color, width=2), name=label)
            for label, color in series
        ]

        values_col = QWidget()
        values_col.setFixedWidth(92)
        values_col.setStyleSheet(
            f"background-color:{PALETTE.panel_alt}; border-left:1px solid {PALETTE.border};"
        )
        vlay = QVBoxLayout(values_col)
        vlay.setContentsMargins(9, 10, 9, 10)
        vlay.setSpacing(12)
        self._value_widgets = [_LiveValue(label, color) for label, color in series]
        for w in self._value_widgets:
            vlay.addWidget(w)
        vlay.addStretch(1)
        body.addWidget(values_col)

        root.addLayout(body, 1)

        # Manual pan/zoom drops out of follow mode so the operator can
        # inspect history while data keeps streaming in.
        self.plot.getViewBox().sigRangeChangedManually.connect(self._on_manual_range)

    # -----------------------------------------------------------------
    def _build_header(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(9, 6, 8, 5)
        bar.setSpacing(10)

        name = QLabel(self.title.upper())
        name.setStyleSheet(
            f"color:{PALETTE.text}; font-size:11px; font-weight:700; letter-spacing:1.2px;"
        )
        bar.addWidget(name)

        # colour key
        for label, color in self._specs:
            chip = QLabel(f"● {label}")
            chip.setStyleSheet(f"color:{color}; font-size:10px; font-weight:600;")
            bar.addWidget(chip)

        bar.addStretch(1)

        self.follow_btn = QPushButton("FOLLOW")
        self.follow_btn.setCheckable(True)
        self.follow_btn.setChecked(True)
        self.follow_btn.setFixedHeight(22)
        self.follow_btn.setToolTip("Auto-scroll to the latest samples")
        self.follow_btn.toggled.connect(self._on_follow_toggled)
        bar.addWidget(self.follow_btn)

        return bar

    # -----------------------------------------------------------------
    # data
    # -----------------------------------------------------------------
    def append(self, t: float, values) -> None:
        self._buf.append(t, values)

    def clear(self) -> None:
        self._buf.clear()
        for curve in self.curves:
            curve.setData([], [])
        for marker in self._markers:
            self.plot.removeItem(marker)
        self._markers.clear()
        for w in self._value_widgets:
            w.set("—")

    def add_marker(self, t: float, label: str, color: str) -> None:
        """Vertical annotation for a flight event (phase change, pyro, ...)."""
        line = pg.InfiniteLine(
            pos=t,
            angle=90,
            movable=False,
            pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DotLine),
            label=label,
            labelOpts={
                "position": 0.92,
                "color": color,
                "fill": pg.mkBrush(11, 17, 26, 210),
                "movable": False,
            },
        )
        line.setZValue(50)
        self.plot.addItem(line, ignoreBounds=True)
        self._markers.append(line)

    def redraw(self) -> None:
        if self._buf.n == 0:
            return
        t = self._buf.t
        for i, curve in enumerate(self.curves):
            series = self._buf.series(i)
            curve.setData(t, series)
            self._value_widgets[i].set(f"{series[-1]:,.2f}")
        if self.follow:
            t_max = float(t[-1])
            self.plot.setXRange(max(0.0, t_max - self.window_s), t_max + 0.5, padding=0)
            self.plot.enableAutoRange(axis="y")

    def set_window(self, seconds: float) -> None:
        self.window_s = seconds
        self.redraw()

    # -----------------------------------------------------------------
    # interaction
    # -----------------------------------------------------------------
    def _on_follow_toggled(self, checked: bool) -> None:
        self.follow = checked
        if checked:
            self.redraw()

    def _on_manual_range(self) -> None:
        if self.follow:
            self.follow = False
            self.follow_btn.setChecked(False)


# =====================================================================
class GraphStack(QWidget):
    """The altitude / acceleration / velocity plot column."""

    WINDOWS = (15.0, 45.0, 120.0, 1e9)
    WINDOW_LABELS = ("15s", "45s", "2m", "ALL")

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        root.addLayout(self._build_toolbar())

        self.altitude = TelemetryPlot(
            "Altitude", "m",
            [("Baro AGL", PALETTE.cyan), ("GPS MSL", PALETTE.magenta)],
        )
        self.acceleration = TelemetryPlot(
            "Acceleration", "g",
            [("|A| high-g", PALETTE.amber), ("Axial Az", PALETTE.green)],
        )
        self.velocity = TelemetryPlot(
            "Vertical Velocity", "m/s",
            [("Kalman", PALETTE.cyan), ("IMU", PALETTE.red)],
        )

        self.plots = (self.altitude, self.acceleration, self.velocity)
        for plot in self.plots:
            plot.setStyleSheet(
                f"background-color:{PALETTE.panel}; border:1px solid {PALETTE.border};"
            )
            root.addWidget(plot, 1)

        # Shared X axis: panning one plot pans them all.
        for plot in self.plots[1:]:
            plot.plot.setXLink(self.altitude.plot)

    # -----------------------------------------------------------------
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(2, 0, 2, 0)
        bar.setSpacing(5)

        label = QLabel("WINDOW")
        label.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700; letter-spacing:1px;"
        )
        bar.addWidget(label)

        self._window_buttons: list[QPushButton] = []
        for i, text in enumerate(self.WINDOW_LABELS):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedSize(46, 22)
            btn.setChecked(i == 1)
            btn.clicked.connect(lambda _=False, n=i: self._set_window(n))
            self._window_buttons.append(btn)
            bar.addWidget(btn)

        bar.addStretch(1)
        return bar

    def _set_window(self, index: int) -> None:
        for i, btn in enumerate(self._window_buttons):
            btn.setChecked(i == index)
        for plot in self.plots:
            plot.follow = True
            plot.follow_btn.setChecked(True)
            plot.set_window(self.WINDOWS[index])

    # -----------------------------------------------------------------
    def append(self, frame) -> None:
        t = frame.t_seconds
        self.altitude.append(t, (frame.filtered_altitude, frame.gps_alt))
        self.acceleration.append(t, (frame.accel_magnitude_g, frame.az_high))
        self.velocity.append(t, (frame.vertical_velocity, frame.imu_vertical_vel))

    def redraw(self) -> None:
        for plot in self.plots:
            plot.redraw()

    def clear(self) -> None:
        for plot in self.plots:
            plot.clear()

    def add_marker(self, t: float, label: str, color: str) -> None:
        for plot in self.plots:
            plot.add_marker(t, label, color)
