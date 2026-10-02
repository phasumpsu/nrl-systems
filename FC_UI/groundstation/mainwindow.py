"""
Ground station main window.

Layout is dock-based so the operator can rearrange panels during a launch:

    +--------------------------------------------------------------+
    |  toolbar: source / connect / link state                       |
    +-----------+--------------------------------+-----------------+
    | ATTITUDE  |  FLIGHT PHASE banner           |  GPS MAP        |
    | (3D)      |--------------------------------|                 |
    |-----------|  ALTITUDE / ACCEL / VELOCITY   |-----------------|
    | PYRO      |  (crosshair plots)             |  VEHICLE STATUS |
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

from .sources import (
    LAUNCH_SITE,
    LAUNCH_SITE_NAME,
    MockSource,
    SerialSource,
    TelemetrySource,
    UdpSource,
    available_serial_ports,
)
from .telemetry import FlightPhase, TelemetryFrame
from .theme import FONT_MONO, PALETTE
from .widgets import (
    AttitudeIndicator,
    EventLog,
    GraphStack,
    MapView,
    PhaseDisplay,
    PyroPanel,
    RawMonitor,
    StatusPanel,
)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "NRL S2 W&P.png"

UI_REFRESH_HZ = 20
MAP_REFRESH_HZ = 4


class GroundStation(QMainWindow):
    """Top-level dashboard window."""

    def __init__(self, source_kind: str = "mock", source_arg: str = "",
                 baud: int = 115200, speed: float = 1.0):
        super().__init__()

        self.setWindowTitle("Nittany Rocket Labs · Ground Station")
        self.resize(1860, 1020)

        self.source: TelemetrySource | None = None
        self.latest: TelemetryFrame | None = None
        self._pending: list[TelemetryFrame] = []
        self._last_phase = FlightPhase.IDLE
        self._phase_entered_t = 0.0
        self._last_t = 0.0
        self._apogee_marked = False
        self._default_speed = speed

        self._build_ui()
        self._build_toolbar(source_kind, source_arg, baud)

        # --- repaint timers ------------------------------------------
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh)
        self._ui_timer.start(int(1000 / UI_REFRESH_HZ))

        self._map_timer = QTimer(self)
        self._map_timer.timeout.connect(self._refresh_map)
        self._map_timer.start(int(1000 / MAP_REFRESH_HZ))

        self.log.log("info", f"Ground station ready — site {LAUNCH_SITE_NAME}")
        self.log.log("info", "Radio downlink carries altitude/velocity/phase only "
                             "— attitude, GPS and accel need the extended packet.")

    # =================================================================
    # construction
    # =================================================================
    def _build_ui(self) -> None:
        # ---- central column: phase banner + plots --------------------
        central = QWidget()
        col = QVBoxLayout(central)
        col.setContentsMargins(6, 6, 6, 6)
        col.setSpacing(6)

        self.phase_display = PhaseDisplay()
        col.addWidget(self.phase_display)

        self.graphs = GraphStack()
        col.addWidget(self.graphs, 1)

        self.setCentralWidget(central)

        # ---- docks ----------------------------------------------------
        self.attitude = AttitudeIndicator()
        self._add_dock("ATTITUDE · 3D", self.attitude,
                       Qt.DockWidgetArea.LeftDockWidgetArea, min_size=(430, 300))

        self.pyro = PyroPanel()
        self._add_dock("PYRO CHANNELS", self.pyro,
                       Qt.DockWidgetArea.LeftDockWidgetArea, min_size=(430, 240))

        self.map = MapView(launch_site=LAUNCH_SITE)
        self._add_dock("GPS TRAJECTORY", self.map,
                       Qt.DockWidgetArea.RightDockWidgetArea, min_size=(470, 360))

        self.status = StatusPanel()
        self._add_dock("VEHICLE STATUS", self.status,
                       Qt.DockWidgetArea.RightDockWidgetArea, min_size=(470, 200))

        self.log = EventLog()
        log_dock = self._add_dock("EVENT LOG", self.log,
                                  Qt.DockWidgetArea.BottomDockWidgetArea, min_size=(400, 130))

        self.raw_monitor = RawMonitor()
        raw_dock = self._add_dock("RAW SERIAL", self.raw_monitor,
                                  Qt.DockWidgetArea.BottomDockWidgetArea, min_size=(400, 130))
        self.tabifyDockWidget(log_dock, raw_dock)

    def _add_dock(self, title: str, widget: QWidget,
                  area: Qt.DockWidgetArea, min_size=(300, 200)) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        widget.setMinimumSize(*min_size)
        self.addDockWidget(area, dock)
        return dock

    # -----------------------------------------------------------------
    def _build_toolbar(self, source_kind: str, source_arg: str, baud: int) -> None:
        bar = QToolBar("Mission")
        bar.setMovable(False)
        self.addToolBar(bar)

        brand = QLabel()
        brand.setStyleSheet(
            f"background-color:#000000; border:1px solid {PALETTE.navy_light};"
            "padding:5px 10px;"
        )
        logo = QPixmap(str(LOGO_PATH))
        if not logo.isNull():
            logo.setDevicePixelRatio(self.devicePixelRatioF())
            scaled = logo.scaledToHeight(
                int(30 * self.devicePixelRatioF()),
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(self.devicePixelRatioF())
            brand.setPixmap(scaled)
        else:
            brand.setText("  NRL  ")
            brand.setStyleSheet(
                brand.styleSheet()
                + f"color:{PALETTE.white}; font-size:15px; font-weight:800;"
                "letter-spacing:3px;"
            )
        bar.addWidget(brand)

        title = QLabel("  GROUND STATION  ")
        title.setStyleSheet(
            f"color:{PALETTE.text}; font-size:13px; font-weight:700; letter-spacing:2.5px;"
        )
        bar.addWidget(title)
        bar.addSeparator()

        # ---- source selection -----------------------------------------
        bar.addWidget(QLabel(" SOURCE "))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["MOCK FLIGHT", "SERIAL", "UDP"])
        self.source_combo.setCurrentIndex({"mock": 0, "serial": 1, "udp": 2}.get(source_kind, 0))
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        bar.addWidget(self.source_combo)

        self.arg_field = QLineEdit(source_arg)
        self.arg_field.setFixedWidth(150)
        bar.addWidget(self.arg_field)

        self._baud = baud
        self._on_source_changed(self.source_combo.currentIndex())

        self.connect_btn = QPushButton("CONNECT")
        self.connect_btn.setCheckable(True)
        self.connect_btn.toggled.connect(self._on_connect_toggled)
        bar.addWidget(self.connect_btn)

        bar.addSeparator()

        clear = QPushButton("CLEAR SESSION")
        clear.clicked.connect(self._clear_session)
        bar.addWidget(clear)

        reset_view = QPushButton("RESET 3D")
        reset_view.clicked.connect(self.attitude.reset_view)
        bar.addWidget(reset_view)

        # ---- link state ------------------------------------------------
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        self.link_label = QLabel("● NO LINK")
        self.link_label.setStyleSheet(
            f"color:{PALETTE.red}; font-family:{FONT_MONO}; font-size:12px;"
            "font-weight:700; padding-right:10px;"
        )
        bar.addWidget(self.link_label)

    def _on_source_changed(self, index: int) -> None:
        """Retarget the argument field for the selected source."""
        if index == 0:
            self.arg_field.setPlaceholderText("speed ×  (e.g. 1.0)")
            self.arg_field.setToolTip("Playback speed multiplier for the mock flight")
            if not self.arg_field.text():
                self.arg_field.setText(f"{self._default_speed:g}")
        elif index == 1:
            ports = available_serial_ports()
            self.arg_field.setPlaceholderText(ports[0] if ports else "COM5")
            self.arg_field.setToolTip(
                "Serial port. Detected: " + (", ".join(ports) if ports else "none")
            )
        else:
            self.arg_field.setPlaceholderText("5005")
            self.arg_field.setToolTip("UDP listen port")

    # =================================================================
    # source lifecycle
    # =================================================================
    def _on_connect_toggled(self, checked: bool) -> None:
        if checked:
            self._start_source()
        else:
            self._stop_source()

    def start(self) -> None:
        """Kick off the configured source (called once at launch)."""
        self.connect_btn.setChecked(True)

    def _start_source(self) -> None:
        self._stop_source()

        index = self.source_combo.currentIndex()
        arg = self.arg_field.text().strip() or self.arg_field.placeholderText()

        if index == 0:
            try:
                speed = float(arg)
            except ValueError:
                speed = 1.0
            self.source = MockSource(speed=speed)
        elif index == 1:
            if arg.isdigit():
                arg = f"COM{arg}"
            self.source = SerialSource(arg, self._baud)
        else:
            try:
                port = int(arg)
            except ValueError:
                port = 5005
            self.source = UdpSource(port=port)

        self.source.frame.connect(self._on_frame)
        self.source.link.connect(self._on_link)
        self.source.event.connect(self.log.log)
        self.source.raw.connect(self.raw_monitor.feed)
        self.source.start()

        self.connect_btn.setText("DISCONNECT")
        self.source_combo.setEnabled(False)
        self.arg_field.setEnabled(False)

    def _stop_source(self) -> None:
        if self.source is not None:
            self.source.stop()
            self.source = None
        self.connect_btn.setText("CONNECT")
        self.source_combo.setEnabled(True)
        self.arg_field.setEnabled(True)
        self._set_link(False, "no link")

    # =================================================================
    # data path
    # =================================================================
    def _on_frame(self, frame: TelemetryFrame) -> None:
        """Worker-thread frames land here (queued to the GUI thread by Qt)."""
        # A large backwards jump means the source restarted (mock recycle,
        # or the vehicle rebooted) -- start a fresh session.
        if frame.t_seconds < self._last_t - 1.0:
            self._clear_session()
        self._last_t = frame.t_seconds

        self.latest = frame
        self._pending.append(frame)
        self.graphs.append(frame)
        self.status.note_packet()

        if frame.flight_phase != self._last_phase:
            self._on_phase_change(frame)

    def _on_phase_change(self, frame: TelemetryFrame) -> None:
        phase = frame.flight_phase
        self._last_phase = phase
        self._phase_entered_t = frame.t_seconds

        severity = "warn" if phase in (FlightPhase.BOOST, FlightPhase.APOGEE) else "event"
        self.log.log(
            severity,
            f"PHASE → {phase.label:<8} alt {frame.filtered_altitude:8.1f} m   "
            f"vz {frame.vertical_velocity:+7.1f} m/s",
        )
        self.graphs.add_marker(frame.t_seconds, phase.label, phase.color)

        if phase == FlightPhase.APOGEE and not self._apogee_marked:
            self._apogee_marked = True
            self.map.mark_apogee(frame)

    def _on_link(self, connected: bool, detail: str) -> None:
        self._set_link(connected, detail)
        self.log.log("info" if connected else "warn",
                     f"Link {'up' if connected else 'down'} — {detail}")

    def _set_link(self, connected: bool, detail: str) -> None:
        color = PALETTE.green if connected else PALETTE.red
        text = f"● {detail.upper()}" if connected else "● NO LINK"
        self.link_label.setText(text)
        self.link_label.setStyleSheet(
            f"color:{color}; font-family:{FONT_MONO}; font-size:12px;"
            "font-weight:700; padding-right:10px;"
        )

    # =================================================================
    # rendering
    # =================================================================
    def _refresh(self) -> None:
        self.raw_monitor.flush()

        frame = self.latest
        if frame is None:
            return

        self.attitude.set_attitude(frame.roll, frame.pitch, frame.yaw)
        self.attitude.set_spin_rate(frame.gz)
        self.phase_display.set_phase(frame.flight_phase)
        self.phase_display.set_clock(
            frame.t_seconds, frame.t_seconds - self._phase_entered_t
        )
        self.pyro.update_frame(frame)
        self.status.update_frame(frame)
        self.graphs.redraw()
        self._pending.clear()

    def _refresh_map(self) -> None:
        if self.latest is not None:
            self.map.update_position(self.latest)

    # =================================================================
    def _clear_session(self) -> None:
        self.graphs.clear()
        self.map.clear_track()
        self.status.reset()
        self._last_phase = FlightPhase.IDLE
        self._phase_entered_t = 0.0
        self._last_t = 0.0
        self._apogee_marked = False
        self.raw_monitor.clear()
        self.log.log("info", "Session cleared")

    def closeEvent(self, event):
        self._ui_timer.stop()
        self._map_timer.stop()
        self._stop_source()
        super().closeEvent(event)
