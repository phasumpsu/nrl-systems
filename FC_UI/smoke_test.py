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

# See main.py -- must be set before any Qt module initializes so the map's
# QWebEngineView (RHI-backed QQuickWidget) and the 3D attitude indicator's
# QOpenGLWidget agree on a graphics API, or the map renders fully black.
os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

from groundstation.mainwindow import GroundStation
from groundstation.telemetry import FlightPhase
from groundstation.theme import build_stylesheet

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

    # Hook the frame signal rather than polling: short-lived phases such as
    # APOGEE (0.4 s of sim time) would otherwise be missed by a sampler.
    seen: set[FlightPhase] = set()
    win.source.frame.connect(lambda f: seen.add(f.flight_phase))

    # The 167 s mock mission plays back at roughly 6x real time (queued
    # signal delivery, not the sleep, is the ceiling), so allow ~32 s.
    DURATION_MS = 32000
    started = time.perf_counter()
    QTimer.singleShot(DURATION_MS, app.quit)
    app.exec()
    elapsed = time.perf_counter() - started
    win.close()

    print("phases observed :", ", ".join(p.label for p in sorted(seen)))
    print("packets         : %d  (%.0f Hz delivered)"
          % (win.status.packet_count, win.status.packet_count / max(elapsed, 1e-3)))
    print("apogee          : %.0f m" % win.status.max_altitude)
    print("peak accel      : %.1f g" % win.status.max_accel)
    print("webengine map   :", win.map.web is not None)
    print("opengl 3d       :", win.attitude.view is not None)
    print("apogee marked   :", win._apogee_marked)
    print("event markers   :", len(win.graphs.altitude._markers))

    missing = set(FlightPhase) - seen
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
