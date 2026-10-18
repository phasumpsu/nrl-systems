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
os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

from groundstation.mainwindow import GroundStation           # noqa: E402
from groundstation.theme import build_stylesheet             # noqa: E402

from PyQt6.QtCore import Qt                                  # noqa: E402
from PyQt6.QtGui import QFont                                # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

# Belt-and-suspenders: also share the underlying GL contexts between the two
# widgets' surfaces.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nittany Rocket Labs Ground Station")
    parser.add_argument("--source", default="mock", help="telemetry source (default: mock)")
    parser.add_argument("--port", default="", help="serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud rate")
    parser.add_argument("--no-autostart", action="store_true", help="open the window without connecting the source")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    app = QApplication(sys.argv)
    app.setApplicationName("NRL Ground Station")
    app.setStyleSheet(build_stylesheet())

    font = QFont("Segoe UI", 9)
    app.setFont(font)

    window = GroundStation()
    window.show()

    if not args.no_autostart:
        window.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
