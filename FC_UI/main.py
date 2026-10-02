"""
NRL Ground Station — entry point.

    python main.py                       # mock flight (no hardware needed)
    python main.py --source mock --speed 4
    python main.py --source serial --port COM5 --baud 115200
    python main.py --source udp --udp-port 5005

The mock source flies a complete synthetic mission through all seven flight
phases from config.h, so the whole dashboard can be exercised before the
radio link exists.
"""

from __future__ import annotations

import argparse
import os
import sys

# The map (QWebEngineView, backed internally by a QQuickWidget/RHI surface)
# and the 3D attitude indicator (QOpenGLWidget, via pyqtgraph.opengl) both
# live in the same top-level window and both need a graphics API. On Windows
# Qt Quick's RHI defaults to Direct3D11, which conflicts with the desktop
# OpenGL context the attitude indicator forces onto that window -- the web
# view's QQuickWidget then fails to get a QRhi and renders nothing (silently
# black, no exception). Forcing both onto OpenGL fixes the mismatch. This
# must be set before any Qt module initializes, so it comes before every
# other import.
#
# setdefault() means an env var set before launch always wins, so if the
# whole app feels sluggish (not just the map/3D panes) on a given machine,
# that's worth A/B testing -- e.g. in PowerShell:
#   $env:QSG_RHI_BACKEND="software"; python main.py   # slower GPU path but
#                                                      # sidesteps flaky GL
#                                                      # drivers entirely
# ("d3d11", Qt Quick's own default, will bring back the black map -- it's
# only useful here to confirm whether "opengl" itself is the slow part.)
os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

# QtWebEngine must be imported before the QApplication is constructed, so the
# widgets package (which pulls in the map view) is imported up here.
from groundstation.mainwindow import GroundStation           # noqa: E402
from groundstation.theme import build_stylesheet             # noqa: E402

from PyQt6.QtCore import Qt                                  # noqa: E402
from PyQt6.QtGui import QFont                                # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

# Belt-and-suspenders: also share the underlying GL contexts between the two
# widgets' surfaces.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nittany Rocket Labs ground station")
    parser.add_argument(
        "--source", choices=("mock", "serial", "udp"), default="mock",
        help="telemetry source (default: mock)",
    )
    parser.add_argument("--port", default="", help="serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud rate")
    parser.add_argument("--udp-port", type=int, default=5005, help="UDP listen port")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="mock playback speed multiplier")
    parser.add_argument("--no-autostart", action="store_true",
                        help="open the window without connecting the source")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    app = QApplication(sys.argv)
    app.setApplicationName("NRL Ground Station")
    app.setStyleSheet(build_stylesheet())

    font = QFont("Segoe UI", 9)
    app.setFont(font)

    source_arg = {
        "mock": f"{args.speed:g}",
        "serial": args.port,
        "udp": str(args.udp_port),
    }[args.source]

    window = GroundStation(
        source_kind=args.source,
        source_arg=source_arg,
        baud=args.baud,
        speed=args.speed,
    )
    window.show()

    if not args.no_autostart:
        window.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
