"""
Ground station main window.

Layout is dock-based so the operator can rearrange panels during a launch:

    +--------------------------------------------------------------+
    |  toolbar: source / connect / link state                       |
    +-----------+--------------------------------+-----------------+
    | ATTITUDE  |  FLIGHT PHASE banner           |  GPS MAP        |
    | (3D)      |--------------------------------|                 |
    |-----------|  TEMP/PRESSURE/THRUST/WEIGHT   |-----------------|
    | PYRO      |  (crosshair plots)             |  ENGINE STATUS  |
    +-----------+--------------------------------+-----------------+
    |  EVENT LOG                                                   |
    +--------------------------------------------------------------+

Frames arrive on a worker thread at up to 50 Hz. They are buffered on
arrival but the widgets are only repainted on a 20 Hz timer (4 Hz for the
map), which keeps the UI responsive at full telemetry rate.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .sources import (MockSource)
from .telemetry import TelemetryFrame
from .theme import FONT_MONO, PALETTE
from .widgets import (EventLog,GraphStack,StatusPanel)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "NRL S2 W&P.png"

UI_REFRESH_HZ = 20
MAP_REFRESH_HZ = 4


class GroundStation(QMainWindow):
    """Top-level dashboard window."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Nittany Rocket Labs · Ground Station")
        self.resize(1860, 1020)

        self.source = None
        self.latest = None

        central = QWidget()
        layout = QVBoxLayout(central)

        self.mode_label = QLabel("SIMULATED DATA — NO HARDWARE CONNECTED")
        layout.addWidget(self.mode_label)

        self.start_button = QPushButton("START SIMULATION")
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)

        self.graphs = GraphStack()
        layout.addWidget(self.graphs, 1)

        self.status = StatusPanel()
        layout.addWidget(self.status)

        self.log = EventLog()
        layout.addWidget(self.log)

        self.setCentralWidget(central)

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh)
        self._ui_timer.start(50)

    # =================================================================
    # construction
    # =================================================================
    def start(self) -> None:
        if self.source is not None:
            return
        
        self.source = MockSource(self)
        self.source.frame.connect(self._on_frame)
        self.source.link.connect(self._on_link)
        self.source.event.connect(self.log.log)
        self.source.start()

        self.start_button.setEnabled(False)

    def _on_frame(self, frame) -> None:
        self.latest = frame
        self.graphs.append(frame)
        self.status.note_packet()

    def _on_link(self, connected: bool, detail: str) -> None:
        self.log.log("info" if connected else "warn", detail)

    def _refresh(self) -> None:
        if self.latest is None:
            return
        self.graphs.redraw()
        self.status.update_frame(self.latest)

    def closeEvent(self, event) -> None:
        self._ui_timer.stop()
        if self.source is not None:
            self.source.stop()
        super().closeEvent(event)
