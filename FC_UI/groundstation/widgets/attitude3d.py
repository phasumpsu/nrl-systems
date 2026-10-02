"""
3D attitude indicator.

Renders a rocket model with pyqtgraph's OpenGL engine and slews it to the
Madgwick roll / pitch / yaw coming off the flight computer, with the raw
numbers alongside.

ATTITUDE CONVENTION
-------------------
The model is built nose-along +Z and the world frame is ENU-ish
(+X east, +Y north, +Z up), so:

    pitch  elevation of the nose above horizontal; 90 deg = vertical on the
           pad, 0 deg = horizontal, negative = nose down
    yaw    compass heading of the nose, degrees clockwise from north
    roll   rotation about the vehicle's own long axis

If the flight computer's Madgwick output uses a different board mounting,
change `ATTITUDE_SIGNS` / `PITCH_OFFSET` below rather than touching the
rest of the app.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import pyqtgraph as pg

from ..theme import FONT_MONO, PALETTE

try:
    import pyqtgraph.opengl as gl
    OPENGL_AVAILABLE = True
except Exception:                                  # noqa: BLE001
    gl = None
    OPENGL_AVAILABLE = False


# Tweak these if the IMU is mounted differently.
PITCH_OFFSET = 90.0          # pitch value that means "nose straight up"
ATTITUDE_SIGNS = (1.0, 1.0, 1.0)   # (roll, pitch, yaw) sign flips


# =====================================================================
# Geometry
# =====================================================================
def _fin_mesh(
    n_fins: int = 4,
    body_r: float = 0.32,
    root_z: float = 0.12,
    root_chord: float = 1.05,
    tip_chord: float = 0.45,
    span: float = 0.62,
    sweep: float = 0.38,
    thickness: float = 0.035,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a solid, swept fin set as a single vertex/face mesh."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    for i in range(n_fins):
        ang = 2.0 * np.pi * i / n_fins
        c, s = np.cos(ang), np.sin(ang)
        # (radial distance, z) profile: root trailing -> root leading ->
        # tip leading -> tip trailing
        profile = [
            (body_r, root_z),
            (body_r, root_z + root_chord),
            (body_r + span, root_z + root_chord - sweep),
            (body_r + span, root_z + root_chord - sweep - tip_chord),
        ]
        base = len(verts)
        for side in (+1.0, -1.0):
            for r, z in profile:
                # offset along the tangential direction to give the fin body
                verts.append((r * c - side * thickness * s,
                              r * s + side * thickness * c,
                              z))
        # two faces
        faces += [
            (base + 0, base + 1, base + 2), (base + 0, base + 2, base + 3),
            (base + 4, base + 6, base + 5), (base + 4, base + 7, base + 6),
        ]
        # rim connecting the two faces
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            faces += [
                (base + a, base + b, base + 4 + b),
                (base + a, base + 4 + b, base + 4 + a),
            ]

    return np.array(verts, dtype=float), np.array(faces, dtype=int)


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0, alpha)


# =====================================================================
# Numeric readout
# =====================================================================
class _AxisReadout(QFrame):
    """One large monospace angle readout with a signed bar indicator."""

    def __init__(self, label: str, color: str, span: float = 180.0, parent=None):
        super().__init__(parent)
        self._span = span
        self._value = 0.0
        self._color = color

        self.setFixedHeight(58)
        self.setStyleSheet(
            f"background-color: {PALETTE.panel_alt};"
            f"border: 1px solid {PALETTE.border};"
            "border-radius: 3px;"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 5, 9, 6)
        lay.setSpacing(1)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._name = QLabel(label)
        self._name.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700;"
            "letter-spacing:1px; background:transparent; border:none;"
        )
        self._val = QLabel("0.0°")
        self._val.setStyleSheet(
            f"color:{color}; font-family:{FONT_MONO}; font-size:19px;"
            "font-weight:600; background:transparent; border:none;"
        )
        self._val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._name)
        top.addStretch(1)
        top.addWidget(self._val)
        lay.addLayout(top)

        self._bar = _SignedBar(color, span)
        lay.addWidget(self._bar)

    def set_value(self, value: float) -> None:
        self._value = value
        self._val.setText(f"{value:+7.1f}°".replace(" ", ""))
        self._bar.set_value(value)


class _SignedBar(QWidget):
    """Thin centre-zero bar showing an angle relative to its full span."""

    def __init__(self, color: str, span: float, parent=None):
        super().__init__(parent)
        self._color = color
        self._span = span
        self._value = 0.0
        self.setFixedHeight(4)
        self.setStyleSheet("background: transparent; border: none;")

    def set_value(self, value: float) -> None:
        self._value = value
        self.update()

    def paintEvent(self, _event):
        from PyQt6.QtGui import QColor, QPainter

        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(PALETTE.bg_deep))

        mid = w / 2.0
        frac = max(-1.0, min(1.0, self._value / self._span))
        length = frac * mid
        x0, x1 = (mid, mid + length) if length >= 0 else (mid + length, mid)
        p.fillRect(int(x0), 0, max(1, int(x1 - x0)), h, QColor(self._color))
        p.fillRect(int(mid), 0, 1, h, QColor(PALETTE.border_bright))
        p.end()


# =====================================================================
# Main widget
# =====================================================================
class AttitudeIndicator(QWidget):
    """3D rocket attitude view plus raw roll / pitch / yaw numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # ---- 3D view -------------------------------------------------
        self._items: list[tuple[object, pg.Transform3D]] = []
        if OPENGL_AVAILABLE:
            self.view = self._build_view()
            root.addWidget(self.view, 3)
        else:
            self.view = None
            fallback = QLabel(
                "3D view unavailable\n\nInstall PyOpenGL:\n"
                "pip install PyOpenGL PyOpenGL-accelerate"
            )
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet(
                f"color:{PALETTE.text_faint}; background:{PALETTE.bg_deep};"
                f"border:1px solid {PALETTE.border}; font-size:11px;"
            )
            root.addWidget(fallback, 3)

        # ---- readouts ------------------------------------------------
        side = QVBoxLayout()
        side.setContentsMargins(0, 2, 6, 2)
        side.setSpacing(6)
        self.roll_out = _AxisReadout("ROLL", PALETTE.cyan, 180.0)
        self.pitch_out = _AxisReadout("PITCH", PALETTE.amber, 90.0)
        self.yaw_out = _AxisReadout("YAW", PALETTE.magenta, 180.0)
        side.addWidget(self.roll_out)
        side.addWidget(self.pitch_out)
        side.addWidget(self.yaw_out)

        self.tilt_out = _AxisReadout("TILT FROM VERT", PALETTE.green, 90.0)
        side.addWidget(self.tilt_out)
        side.addStretch(1)

        self.rate_label = QLabel("SPIN  —")
        self.rate_label.setStyleSheet(
            f"color:{PALETTE.text_dim}; font-family:{FONT_MONO}; font-size:10px;"
        )
        side.addWidget(self.rate_label)

        root.addLayout(side, 2)

    # -----------------------------------------------------------------
    def _build_view(self):
        view = gl.GLViewWidget()
        view.setCameraPosition(distance=11.0, elevation=14, azimuth=48)
        view.setBackgroundColor(pg.mkColor(PALETTE.bg_deep))

        # ground reference grid
        grid = gl.GLGridItem()
        grid.setSize(14, 14)
        grid.setSpacing(1, 1)
        grid.setColor(pg.mkColor(45, 62, 84, 110))
        grid.translate(0, 0, -2.6)
        view.addItem(grid)

        # world axis triad (X east / Y north / Z up)
        axis_len = 2.0
        for vec, color in (
            ((axis_len, 0, 0), PALETTE.red),
            ((0, axis_len, 0), PALETTE.green),
            ((0, 0, axis_len), PALETTE.cyan),
        ):
            line = gl.GLLinePlotItem(
                pos=np.array([[0, 0, -2.6], [vec[0], vec[1], -2.6 + vec[2]]]),
                color=_hex_to_rgba(color, 0.55),
                width=1.6,
                antialias=True,
            )
            view.addItem(line)

        # ---- rocket parts, all built nose-along +Z --------------------
        body_len, body_r = 3.15, 0.32
        nose_len = 1.30

        body_md = gl.MeshData.cylinder(rows=1, cols=36,
                                       radius=[body_r, body_r], length=body_len)
        body = gl.GLMeshItem(meshdata=body_md, smooth=True, shader="shaded",
                             color=_hex_to_rgba("#D9E2EC"), glOptions="opaque")
        self._add_part(view, body, translate=(0, 0, 0))

        nose_md = gl.MeshData.cylinder(rows=1, cols=36,
                                       radius=[body_r, 0.0], length=nose_len)
        nose = gl.GLMeshItem(meshdata=nose_md, smooth=True, shader="shaded",
                             color=_hex_to_rgba(PALETTE.cyan, 0.95), glOptions="opaque")
        self._add_part(view, nose, translate=(0, 0, body_len))

        # navy band -- Penn State livery
        band_md = gl.MeshData.cylinder(rows=1, cols=36,
                                       radius=[body_r * 1.03, body_r * 1.03], length=0.42)
        band = gl.GLMeshItem(meshdata=band_md, smooth=True, shader="shaded",
                             color=_hex_to_rgba(PALETTE.navy_light), glOptions="opaque")
        self._add_part(view, band, translate=(0, 0, body_len * 0.58))

        # motor nozzle
        noz_md = gl.MeshData.cylinder(rows=1, cols=24,
                                      radius=[0.16, 0.26], length=0.30)
        noz = gl.GLMeshItem(meshdata=noz_md, smooth=True, shader="shaded",
                            color=_hex_to_rgba("#5A6B80"), glOptions="opaque")
        self._add_part(view, noz, translate=(0, 0, -0.30))

        fin_v, fin_f = _fin_mesh(body_r=body_r)
        fins = gl.GLMeshItem(vertexes=fin_v, faces=fin_f, smooth=False,
                             shader="shaded", color=_hex_to_rgba(PALETTE.navy_light),
                             glOptions="opaque")
        self._add_part(view, fins, translate=(0, 0, 0))

        # body-axis reference line through the nose
        axis = gl.GLLinePlotItem(
            pos=np.array([[0, 0, -1.2], [0, 0, body_len + nose_len + 1.0]]),
            color=_hex_to_rgba(PALETTE.amber, 0.35), width=1.0, antialias=True,
        )
        self._add_part(view, axis, translate=(0, 0, 0))

        self._recenter_offset = -(body_len + nose_len) / 2.0
        return view

    def _add_part(self, view, item, translate=(0.0, 0.0, 0.0)) -> None:
        """Register a part with a base transform placing it in the body frame."""
        base = pg.Transform3D()
        base.translate(*translate)
        item.setTransform(base)
        view.addItem(item)
        self._items.append((item, base))

    # -----------------------------------------------------------------
    def set_attitude(self, roll: float, pitch: float, yaw: float) -> None:
        """Slew the model and update the numeric readouts."""
        sr, sp, sy = ATTITUDE_SIGNS
        roll, pitch, yaw = roll * sr, pitch * sp, yaw * sy

        self.roll_out.set_value(((roll + 180.0) % 360.0) - 180.0)
        self.pitch_out.set_value(pitch)
        self.yaw_out.set_value(yaw % 360.0)
        self.tilt_out.set_value(PITCH_OFFSET - pitch)

        if not OPENGL_AVAILABLE:
            return

        # Compose: spin about the body axis, tilt off vertical, then heading.
        # Transform3D.rotate() post-multiplies, so the last call is applied
        # to the model first.
        att = pg.Transform3D()
        att.rotate(-yaw, 0, 0, 1)                    # compass heading (CW +)
        att.rotate(pitch - PITCH_OFFSET, 1, 0, 0)    # elevation
        att.rotate(roll, 0, 0, 1)                    # roll about long axis
        att.translate(0, 0, self._recenter_offset)   # spin about the mid-body

        for item, base in self._items:
            item.setTransform(att * base)

    def set_spin_rate(self, dps: float) -> None:
        self.rate_label.setText(f"SPIN  {dps:6.1f} °/s")

    def reset_view(self) -> None:
        if OPENGL_AVAILABLE and self.view is not None:
            self.view.setCameraPosition(distance=11.0, elevation=14, azimuth=48)
