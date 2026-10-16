"""
Headless-ish smoke test: build the real window, run the mock flight at high
speed through every phase, and fail loudly on any exception raised inside a
Qt slot (which Qt would otherwise swallow).

    python smoke_test.py
"""

from __future__ import annotations

import os
import sys
import time
import traceback

os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

from groundstation.mainwindow import GroundStation
from groundstation.theme import build_stylesheet
from groundstation.telemetry import (ObservedState,TestPhase,OperatorRequest)

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

ERRORS: list[str] = []


def _hook(exc_type, exc, tb):
    ERRORS.append("".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = _hook


def main() -> int:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())

    win = GroundStation(source_kind="mock", source_arg="60", speed=60.0)
    win.show()
    win.start()

    seen: set[SystemPhase] = set()
    win.source.frame.connect(lambda f: seen.add(f.flight_phase))

    DURATION_MS = 32000
    started = time.perf_counter()
    QTimer.singleShot(DURATION_MS, app.quit)
    app.exec()
    elapsed = time.perf_counter() - started
    win.close()

    missing = set(SystemPhase) - seen
    if missing:
        print("\nFAIL: phases never seen:", ", ".join(p.label for p in sorted(missing)))
        return 1

    if ERRORS:
        print("\n=== %d EXCEPTION(S) ===" % len(ERRORS))
        for e in ERRORS:
            print(e)
        return 1

    if win.status.packet_count == 0:
        print("\nFAIL: no telemetry frames reached the UI")
        return 1

    print("\nSMOKE TEST PASSED — no exceptions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
