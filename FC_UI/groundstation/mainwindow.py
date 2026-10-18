from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from .sources import MockSource, CTelemetrySource
from .theme import PALETTE
from .widgets import EventLog, GraphStack, StatusPanel

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "NRL S2 W&P.png"


class GroundStation(QMainWindow):
    """Ground-station dashboard; requests go through the Pi, never local CAN."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nittany Rocket Labs · Ground Station")
        self.resize(1860, 1020)
        self.source = None
        self.latest = None
        self.live_fresh = False

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        self.mode_label = QLabel("SIMULATED DATA — NO HARDWARE CONNECTED")
        controls.addWidget(self.mode_label, 1)
        self.source_selector = QComboBox()
        self.source_selector.addItem("Simulated", "mock")
        self.source_selector.addItem("Live Pi", "live")
        controls.addWidget(self.source_selector)
        self.start_button = QPushButton()
        self.start_button.clicked.connect(self.start)
        controls.addWidget(self.start_button)
        self.stop_button = QPushButton("STOP / DISCONNECT")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        self.source_selector.currentIndexChanged.connect(self._update_source_label)
        self._update_source_label()

        main_area = QHBoxLayout()
        main_area.setSpacing(6)
        left_column = QVBoxLayout()
        self.state_status = StatusPanel(kind="states")
        left_column.addWidget(self.state_status)
        request_box = QFrame()
        request_box.setStyleSheet(
            f"background-color:{PALETTE.panel};border:1px solid {PALETTE.border};"
        )
        request_layout = QVBoxLayout(request_box)
        request_layout.addWidget(QLabel("OPERATOR REQUESTS — NOT ACKNOWLEDGED"))

        self.routine_selector = QComboBox()
        for label, value in (("Select routine…", None), ("NONE", 0),
                             ("FIRE", 1), ("LONG_FILL", 2), ("SHORT_FILL", 3)):
            self.routine_selector.addItem(label, value)
        request_layout.addWidget(self.routine_selector)
        self.request_button = QPushButton("REQUEST ROUTINE")
        self.request_button.clicked.connect(self._request_routine)
        request_layout.addWidget(self.request_button)

        self.valve_selectors = {}
        for name, label in (("sv11", "SV11"), ("sv12", "SV12"), ("sv13", "SV13")):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            selector = QComboBox()
            selector.addItem("Choose…", None)
            selector.addItem("0 (request)", 0)
            selector.addItem("1 (request)", 1)
            row.addWidget(selector)
            button = QPushButton("SEND")
            button.clicked.connect(lambda _checked=False, k=name, cb=selector: self._request_selected(k, cb))
            row.addWidget(button)
            request_layout.addLayout(row)
            self.valve_selectors[name] = (selector, button)
        self.armed_selector = QComboBox()
        for text, value in (("Choose armed request…", None), ("0 (request)", 0),
                            ("1 (request)", 1)):
            self.armed_selector.addItem(text, value)
        request_layout.addWidget(self.armed_selector)
        self.armed_button = QPushButton("SEND ARMED REQUEST")
        self.armed_button.clicked.connect(lambda: self._request_selected("armed", self.armed_selector))
        request_layout.addWidget(self.armed_button)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 65535)
        self.delay_spin.setSuffix(" ms fire delay")
        self.delay_spin.setValue(5000)
        request_layout.addWidget(self.delay_spin)
        self.delay_button = QPushButton("SEND FIRE DELAY")
        self.delay_button.clicked.connect(lambda: self._request(fire_delay_ms=self.delay_spin.value()))
        request_layout.addWidget(self.delay_button)
        self.tare_selector = QComboBox()
        for text, value in (("Choose tare…", None), ("LC1", 1), ("LC2", 2), ("BOTH", 3)):
            self.tare_selector.addItem(text, value)
        request_layout.addWidget(self.tare_selector)
        self.tare_button = QPushButton("REQUEST TARE")
        self.tare_button.clicked.connect(lambda: self._request_selected("tare", self.tare_selector))
        request_layout.addWidget(self.tare_button)

        self.command_widgets = [self.routine_selector, self.request_button,
                                self.armed_selector, self.armed_button,
                                self.delay_spin, self.delay_button,
                                self.tare_selector, self.tare_button]
        for selector, button in self.valve_selectors.values():
            self.command_widgets.extend((selector, button))
        self._set_requests_enabled(False)
        left_column.addWidget(request_box)
        left_column.addStretch(1)
        main_area.addLayout(left_column)
        self.graphs = GraphStack()
        main_area.addWidget(self.graphs, 1)
        layout.addLayout(main_area, 1)
        self.numeric_status = StatusPanel(kind="numbers")
        layout.addWidget(self.numeric_status)
        self.log = EventLog()
        self.log.setFixedHeight(105)
        layout.addWidget(self.log)
        self.setCentralWidget(central)
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh)
        self._ui_timer.start(50)

    def _set_requests_enabled(self, enabled: bool) -> None:
        for widget in self.command_widgets:
            widget.setEnabled(enabled)

    def _request_selected(self, key: str, selector: QComboBox) -> None:
        value = selector.currentData()
        if value is not None:
            self._request(**{key: value})

    def _request_routine(self) -> None:
        self._request_selected("routine", self.routine_selector)

    def _request(self, **fields: int) -> None:
        if (not self.live_fresh or not isinstance(self.source, CTelemetrySource)
                or not self.source.command_available()):
            self.log.log("warn", "Request blocked: live Pi telemetry is not fresh")
            return
        try:
            queued = self.source.request(**fields)
        except ValueError as exc:
            self.log.log("error", f"Invalid request: {exc}")
            return
        if not queued:
            self.log.log("warn", "Request not queued: connection stale, closed, or busy")
        else:
            self.log.log("info", f"Queued request {fields}; not acknowledged by Pi or MCU")

    def _update_source_label(self) -> None:
        if self.source_selector.currentData() == "live":
            self.mode_label.setText("LIVE PI — NOT CONNECTED")
            self.start_button.setText("CONNECT")
        else:
            self.mode_label.setText("SIMULATED DATA — NOT STARTED")
            self.start_button.setText("START SIMULATION")

    def start(self) -> None:
        if self.source is not None:
            return
        self.graphs.clear()
        self.latest = None
        self.live_fresh = False
        self._set_requests_enabled(False)
        if self.source_selector.currentData() == "live":
            host = os.environ.get("GROUND_STATION_HOST", "127.0.0.1")
            port = int(os.environ.get("GROUND_STATION_PORT", "5555"))
            self.source = CTelemetrySource(host=host, port=port, parent=self)
        else:
            self.source = MockSource(self)
        source = self.source
        source.frame.connect(lambda frame, s=source: self._on_frame(frame) if self.source is s else None)
        source.link.connect(lambda connected, detail, s=source:
                            self._on_link(connected, detail) if self.source is s else None)
        source.event.connect(lambda severity, message, s=source:
                             self.log.log(severity, message) if self.source is s else None)
        source.finished.connect(lambda s=source: self._source_finished(s))
        source.start()
        self.source_selector.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)


    def _source_finished(self, source) -> None:
        if self.source is source:
            self.stop()

    def _sync_command_gate(self) -> None:
        if isinstance(self.source, CTelemetrySource) and self.live_fresh:
            ready = self.source.command_available()
            self._set_requests_enabled(ready)
            self.mode_label.setText("LIVE PI — COMMANDS AVAILABLE (NOT ACKNOWLEDGED)" if ready else
                                    "LIVE PI — TELEMETRY STALE FOR COMMANDS")

    def _on_frame(self, frame) -> None:
        self.latest = frame
        self.graphs.append(frame)
        self.numeric_status.note_packet()

    def _on_link(self, connected: bool, detail: str) -> None:
        self.log.log("info" if connected else "warn", detail)
        if self.source_selector.currentData() == "live":
            self.live_fresh = connected
            self._set_requests_enabled(False)
            self.mode_label.setText("LIVE PI — TELEMETRY RECEIVED" if connected else
                                    "LIVE PI — NO FRESH TELEMETRY")
            if connected:
                self._sync_command_gate()
            if not connected:
                self.latest = None
                self.numeric_status.reset()
                self.state_status.reset()

    def _refresh(self) -> None:
        self._sync_command_gate()
        if self.latest is None:
            return
        self.graphs.redraw()
        self.numeric_status.update_frame(self.latest)
        self.state_status.update_frame(self.latest)

    def stop(self) -> None:
        if self.source is None:
            return
        self.live_fresh = False
        self._set_requests_enabled(False)
        self.source.stop()
        self.source = None
        self.latest = None
        self.source_selector.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._update_source_label()
        self.graphs.clear()
        self.numeric_status.reset()
        self.state_status.reset()

    def closeEvent(self, event) -> None:
        self._ui_timer.stop()
        self.stop()
        super().closeEvent(event)
