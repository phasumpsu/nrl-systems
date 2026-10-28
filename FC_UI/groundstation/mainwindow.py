from __future__ import annotations

import os

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from .sources import CTelemetrySource, MockSource
from .theme import PALETTE
from .widgets import EventLog, GraphStack, StatusPanel

STATE_NAMES = {0: "UNKNOWN", 1: "OPEN", 2: "CLOSED", 3: "FAULT"}
ARMED_NAMES = {0: "UNKNOWN", 1: "ARMED", 2: "DISARMED", 3: "FAULT"}
ROUTINE_NAMES = {0: "NONE", 1: "FIRE", 2: "LONG_FILL", 3: "SHORT_FILL",
                 4: "ROUTINE_4", 5: "ROUTINE_5"}


class GroundStation(QMainWindow):
    """Ground-station dashboard; requests go through the Pi, never local CAN."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nittany Rocket Labs · Ground Station")
        self.resize(1860, 1020)
        self.source = None
        self.latest = None
        self.live_fresh = False

        # Until the STM32 mapping is confirmed, expose raw DBC bits rather than
        # guessing which bit opens a valve. Selection works in either case.
        open_value = os.environ.get("GS_VALVE_OPEN_VALUE")
        self.valve_open_value = int(open_value) if open_value in ("0", "1") else None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

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
        self.probe_button = QPushButton("CHECK PI LINK")
        self.probe_button.setEnabled(False)
        self.probe_button.clicked.connect(self._probe_pi)
        controls.addWidget(self.probe_button)
        layout.addLayout(controls)
        self.source_selector.currentIndexChanged.connect(self._update_source_label)
        self._update_source_label()

        main_area = QHBoxLayout()
        main_area.setSpacing(8)
        left = QFrame()
        left.setStyleSheet(
            f"QFrame {{background-color:{PALETTE.panel}; border:1px solid {PALETTE.border};}}"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(9, 7, 9, 7)
        left_layout.setSpacing(5)
        left_layout.addWidget(QLabel("ENGINE STATE / OPERATOR REQUESTS"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(3)
        self.state_labels = {}
        self.valve_selectors = {}
        valve_names = (("sv11", "SV11 — Ground Tank"),
                       ("sv12", "SV12 — Release Vent"),
                       ("sv13", "SV13 — Run Tank"))
        for i, (key, name) in enumerate(valve_names):
            state = QLabel("—")
            state.setStyleSheet(f"color:{PALETTE.text_dim};")
            self.state_labels[f"{key}_state"] = state
            selector = QComboBox()
            selector.addItem("No request", None)
            if self.valve_open_value is None:
                selector.addItem("REQUEST BIT 0", 0)
                selector.addItem("REQUEST BIT 1", 1)
            else:
                selector.addItem("OPEN", self.valve_open_value)
                selector.addItem("CLOSE", 1 - self.valve_open_value)
            self.valve_selectors[key] = selector
            grid.addWidget(QLabel(name), 2 * i, 0)
            grid.addWidget(state, 2 * i + 1, 0)
            grid.addWidget(selector, 2 * i, 1, 2, 1)

        grid.setColumnStretch(0, 1)
        left_layout.addLayout(grid)
        if self.valve_open_value is None:
            warning = QLabel("Valve requests use raw bits; OPEN/CLOSE meaning is unverified.")
            warning.setWordWrap(True)
            warning.setStyleSheet(f"color:{PALETTE.amber};")
            left_layout.addWidget(warning)

        routine_header = QHBoxLayout()
        routine_header.addWidget(QLabel("ROUTINE SEQUENCE"))
        routine_header.addStretch(1)
        self.state_labels["routine_sequence"] = QLabel("—")
        routine_header.addWidget(self.state_labels["routine_sequence"])
        left_layout.addLayout(routine_header)

        self.routine_selector = QComboBox()
        for label, value in (("No routine request", None), ("NONE", 0),
                             ("SHORT FILL", 3), ("LONG FILL", 2), ("FIRE", 1)):
            self.routine_selector.addItem(label, value)
        left_layout.addWidget(self.routine_selector)
        self.full_state = QCheckBox("FULL STATE — required to clear Pi forced-safe latch")
        self.full_state.setToolTip("Requires explicit choices for all three valves, armed, routine, and fire delay. Never filled from old telemetry.")
        left_layout.addWidget(self.full_state)
        self.full_state.toggled.connect(self._full_state_toggled)

        other_states = QHBoxLayout()
        other_states.addWidget(QLabel("IGNITOR:"))
        self.state_labels["ignitor_state"] = QLabel("—")
        other_states.addWidget(self.state_labels["ignitor_state"])
        other_states.addStretch(1)
        other_states.addWidget(QLabel("ARMED:"))
        self.state_labels["armed_status"] = QLabel("—")
        other_states.addWidget(self.state_labels["armed_status"])
        left_layout.addLayout(other_states)

        self.more_button = QToolButton()
        self.more_button.setText("MORE REQUESTS: ARMED / DELAY / TARE")
        self.more_button.setCheckable(True)
        left_layout.addWidget(self.more_button)
        self.more_box = QWidget()
        more = QGridLayout(self.more_box)
        more.setContentsMargins(0, 0, 0, 0)
        self.armed_selector = QComboBox()
        self.armed_selector.addItem("No armed request", None)
        self.armed_selector.addItem("Request bit 0", 0)
        self.armed_selector.addItem("Request bit 1", 1)
        more.addWidget(self.armed_selector, 0, 0, 1, 2)
        self.include_delay = QCheckBox("Include fire delay")
        more.addWidget(self.include_delay, 1, 0)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 65535)
        self.delay_spin.setValue(5000)
        self.delay_spin.setSuffix(" ms")
        more.addWidget(self.delay_spin, 1, 1)
        self.tare_selector = QComboBox()
        for text, value in (("No tare request", None), ("LC1", 1),
                            ("LC2", 2), ("BOTH", 3)):
            self.tare_selector.addItem(text, value)
        more.addWidget(self.tare_selector, 2, 0, 1, 2)
        self.more_box.setVisible(False)
        left_layout.addWidget(self.more_box)
        self.more_button.toggled.connect(self._toggle_more)
        self.include_delay.toggled.connect(lambda _: self._set_requests_enabled(self._commands_ready()))
        self.more_button.toggled.connect(lambda _: self._set_requests_enabled(self._commands_ready()))

        self.send_button = QPushButton("SEND REQUEST TO PI")
        self.send_button.clicked.connect(self._send_command)
        left_layout.addWidget(self.send_button)
        note = QLabel("Pi heartbeat ACK enables testing this request path. Without STM32 telemetry the Pi should REJECT actuator requests; acceptance never proves actuation.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{PALETTE.text_dim};")
        left_layout.addWidget(note)
        left_layout.addStretch(1)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setMinimumWidth(365)
        left_scroll.setMaximumWidth(425)
        left_scroll.setWidget(left)
        main_area.addWidget(left_scroll)

        self.graphs = GraphStack()
        main_area.addWidget(self.graphs, 1)
        layout.addLayout(main_area, 1)
        self.numeric_status = StatusPanel(kind="numbers")
        layout.addWidget(self.numeric_status)
        self.log = EventLog()
        self.log.setFixedHeight(105)
        layout.addWidget(self.log)
        self.setCentralWidget(central)
        self._set_requests_enabled(False)

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh)
        self._ui_timer.start(50)

    def _full_state_toggled(self, checked: bool) -> None:
        if checked:
            self.more_button.setChecked(True)
            self.include_delay.setChecked(True)

    def _toggle_more(self, visible: bool) -> None:
        if not visible:
            if self.full_state.isChecked():
                self.full_state.setChecked(False)
            # Hidden fields must not be sent as surprise commands.
            self.armed_selector.setCurrentIndex(0)
            self.include_delay.setChecked(False)
            self.tare_selector.setCurrentIndex(0)
        self.more_box.setVisible(visible)

    def _commands_ready(self) -> bool:
        # A confirmed Pi heartbeat is enough to test delivery; the Pi can
        # reject the request if this session is inactive or MCU data is stale.
        return (isinstance(self.source, CTelemetrySource)
                and self.source.command_available())

    def _set_requests_enabled(self, enabled: bool) -> None:
        # Keep choices selectable while a live Pi link is being established.
        choosing = isinstance(self.source, CTelemetrySource) and self.source.isRunning()
        for selector in self.valve_selectors.values():
            selector.setEnabled(choosing)
        self.routine_selector.setEnabled(choosing)
        self.more_button.setEnabled(choosing)
        self.armed_selector.setEnabled(choosing)
        self.include_delay.setEnabled(choosing)
        self.delay_spin.setEnabled(choosing and self.include_delay.isChecked())
        self.tare_selector.setEnabled(choosing)
        self.full_state.setEnabled(choosing)
        self.send_button.setEnabled(enabled)

    def _send_command(self) -> None:
        if not self._commands_ready():
            self.log.log("warn", "Request blocked: Pi heartbeat not acknowledged or TCP disconnected")
            return
        fields = {}
        for key, selector in self.valve_selectors.items():
            value = selector.currentData()
            if value is not None:
                fields[key] = value
        routine = self.routine_selector.currentData()
        if routine is not None:
            fields["routine"] = routine
        if self.more_button.isChecked():
            if self.armed_selector.currentData() is not None:
                fields["armed"] = self.armed_selector.currentData()
            if self.include_delay.isChecked():
                fields["fire_delay_ms"] = self.delay_spin.value()
            if self.tare_selector.currentData() is not None:
                fields["tare"] = self.tare_selector.currentData()
        if not fields:
            self.log.log("warn", "Choose at least one request before sending")
            return
        required = {"sv11", "sv12", "sv13", "armed", "routine", "fire_delay_ms"}
        missing = required - fields.keys()
        if self.full_state.isChecked() and missing:
            self.log.log("warn", f"FULL STATE requires explicit values for: {', '.join(sorted(missing))}")
            return
        # Pi treats a request containing all six keys as FULL STATE even if
        # the checkbox is off. Never bypass confirmation in that case.
        if not missing:
            choice = QMessageBox.warning(
                self, "Confirm complete state request",
                f"Send this COMPLETE command state to the Pi?\n\n{fields}\n\n"
                "This can command physical outputs if an STM32 is attached. "
                "Pi acceptance is not confirmation of actuation.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes or not self._commands_ready():
                return
        try:
            queued = self.source.request(**fields)
        except ValueError as exc:
            self.log.log("error", f"Invalid request: {exc}")
            return
        if not queued:
            self.log.log("warn", "Request not queued: connection stale, closed, or busy")
            return
        self.log.log("info", f"Queued request {fields}; not acknowledged by Pi or MCU")
        for selector in self.valve_selectors.values():
            selector.setCurrentIndex(0)
        self.routine_selector.setCurrentIndex(0)
        self.armed_selector.setCurrentIndex(0)
        self.include_delay.setChecked(False)
        self.tare_selector.setCurrentIndex(0)
        self.full_state.setChecked(False)

    def _probe_pi(self) -> None:
        if isinstance(self.source, CTelemetrySource) and self.source.probe():
            self.log.log("info", "Pi link check sent; waiting for Pi response")
        else:
            self.log.log("warn", "Pi link check unavailable")

    def _on_bridge_status(self, detail: str) -> None:
        self.log.log("info", detail)
        if not self.live_fresh:
            self.mode_label.setText("LIVE PI — LINK OK; NO FRESH ENGINE TELEMETRY")

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
        self._reset_states()
        self._set_requests_enabled(False)
        if self.source_selector.currentData() == "live":
            host = os.environ.get("GROUND_STATION_HOST", "10.42.0.1")
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
        if isinstance(source, CTelemetrySource):
            source.bridge_status.connect(
                lambda detail, s=source: self._on_bridge_status(detail) if self.source is s else None
            )
        source.start()
        self.source_selector.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.probe_button.setEnabled(isinstance(source, CTelemetrySource))

    def _source_finished(self, source) -> None:
        if self.source is source:
            self.stop()

    def _on_frame(self, frame) -> None:
        self.latest = frame
        self.graphs.append(frame)
        self.numeric_status.note_packet()

    def _reset_states(self) -> None:
        for label in self.state_labels.values():
            label.setText("—")

    def _on_link(self, connected: bool, detail: str) -> None:
        self.log.log("info" if connected else "warn", detail)
        if self.source_selector.currentData() == "live":
            self.live_fresh = connected
            self._set_requests_enabled(False)
            self.mode_label.setText("LIVE PI — TELEMETRY RECEIVED" if connected else
                                    "LIVE PI — NO FRESH TELEMETRY")
            if not connected:
                self.latest = None
                self.numeric_status.reset()
                self._reset_states()

    def _refresh(self) -> None:
        if isinstance(self.source, CTelemetrySource):
            ready = self._commands_ready()
            self._set_requests_enabled(ready)
            if ready:
                if not self.source.mcu_telemetry_available():
                    self.mode_label.setText("LIVE PI — TRANSPORT TEST ONLY; MCU OFFLINE")
                elif not self.source.active_session_available():
                    self.mode_label.setText("LIVE PI — STANDBY; REQUESTS MAY BE REJECTED")
                else:
                    self.mode_label.setText("LIVE PI — ACTIVE; MCU TELEMETRY FRESH")
            elif self.source.isRunning():
                self.mode_label.setText("LIVE PI — WAITING FOR HEARTBEAT ACK")
        if self.latest is None:
            return
        self.graphs.redraw()
        self.numeric_status.update_frame(self.latest)
        for key, label in self.state_labels.items():
            mapping = (ROUTINE_NAMES if key == "routine_sequence" else
                       ARMED_NAMES if key == "armed_status" else STATE_NAMES)
            label.setText(mapping.get(getattr(self.latest, key), "UNKNOWN"))

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
        self.probe_button.setEnabled(False)
        self._update_source_label()
        self.graphs.clear()
        self.numeric_status.reset()
        self._reset_states()

    def closeEvent(self, event) -> None:
        self._ui_timer.stop()
        self.stop()
        super().closeEvent(event)
