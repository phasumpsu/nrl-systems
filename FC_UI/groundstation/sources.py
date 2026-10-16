"""Read-only telemetry source for GUI development."""
from __future__ import annotations

import time


from PyQt6.QtCore import QThread, pyqtSignal
from .telemetry import TelemetryFrame

class MockSource(QThread):
    frame = pyqtSignal(object)
    link = pyqtSignal(bool, str)
    event = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def run(self) -> None:
        self._running = True
        started = time.monotonic()
        self.link.emit(True, "SIMULATED DATA — NO HARDWARE")
        self.event.emit("info", "Read-only engine telemetry simulation started")

        while self._running:
            elapsed = time.monotonic() - started

            # Constant, clearly simulated values. These are UI test data,
            # not realistic test-fire data or acceptance limits.
            frame = TelemetryFrame(
                mcu_time_s=round(elapsed * 2) / 2,
                engine_thrust_n=0.0,
                nitrous_weight_lbs=0.0,
                run_tank_pressure_psi=0.0,
                cc_pressure_psi=0.0,
                top_cc_temp_c=0.0,
                bot_cc_temp_c=0.0,
                sv11_state=0,
                sv12_state=0,
                sv13_state=0,
                ignitor_state=0
            )
            self.frame.emit(frame)
            self.msleep(100)

        self.link.emit(False, "Simulation stopped")

    def stop(self) -> None:
        self._running = False
        if self.isRunning():
            self.wait(2000)