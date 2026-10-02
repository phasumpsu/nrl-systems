"""
Live GPS map and trajectory.

Primary path is a Leaflet map in a QWebEngineView (dark CartoDB basemap,
live trajectory polyline, heading-aware rocket marker). Leaflet itself is
vendored locally (widgets/vendor/) rather than pulled from a CDN, so the
map's markers, track and "NO GPS FIX" banner all work with zero network
access -- only the CartoDB tile imagery needs a connection. If
PyQt6-WebEngine is not installed, the widget falls back to a pyqtgraph
ground-track plot so the dashboard still runs and still shows the
trajectory.

Raw latitude / longitude are always shown numerically underneath, and the
last known GPS fix is kept in a copyable field (pastable straight into
Google Maps), so the map is never the only source of position truth.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from ..theme import FONT_MONO, PALETTE

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except Exception:                                     # noqa: BLE001
    QWebEngineView = None
    QWebEnginePage = None
    QWebEngineSettings = None
    WEBENGINE_AVAILABLE = False


if WEBENGINE_AVAILABLE:
    class _DiagnosticPage(QWebEnginePage):
        """Routes the map page's JS console to stderr.

        A broken map.html (bad script path, a thrown exception before
        Leaflet's globals are defined, ...) otherwise fails completely
        silently -- QWebEngineView shows nothing and Python never sees an
        exception, since runJavaScript() calls into an undefined function
        are just dropped.
        """

        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            print(f"[map.html:{line}] {message}", file=sys.stderr)


MAP_HTML_PATH = Path(__file__).with_name("map.html")


# =====================================================================
MAP_HTML = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="stylesheet" href="vendor/leaflet.css"/>
<script src="vendor/leaflet.js"></script>
<style>
  html, body {{ margin:0; padding:0; height:100%; background:{PALETTE.bg_deep}; }}
  #map {{ height:100%; width:100%; background:{PALETTE.bg_deep}; }}
  .leaflet-container {{ background:{PALETTE.bg_deep}; font-family:"Segoe UI",sans-serif; }}
  .leaflet-control-attribution {{
      background:rgba(0,0,0,.8)!important; color:{PALETTE.text_faint}!important; font-size:9px!important;
  }}
  .leaflet-control-attribution a {{ color:{PALETTE.cyan_dim}!important; }}
  .leaflet-control-zoom a {{
      background:{PALETTE.panel_alt}!important; color:{PALETTE.text}!important; border-color:{PALETTE.border_bright}!important;
  }}
  .leaflet-control-zoom a:hover {{ background:{PALETTE.navy_light}!important; }}
  .rocket-marker {{ width:26px; height:26px; }}
  .rocket-marker svg {{ display:block; filter:drop-shadow(0 0 5px {PALETTE.cyan}); }}
  .pad-marker {{
      width:12px; height:12px; border-radius:50%;
      background:{PALETTE.amber}; border:2px solid {PALETTE.bg_deep};
      box-shadow:0 0 7px {PALETTE.amber};
  }}
  #nofix {{
      position:absolute; z-index:900; top:8px; left:50%; transform:translateX(-50%);
      background:rgba(255,59,78,.16); border:1px solid {PALETTE.red}; color:{PALETTE.red};
      padding:3px 12px; font-size:10px; font-weight:700; letter-spacing:1px;
      border-radius:3px; display:none;
  }}
</style>
</head>
<body>
<div id="map"></div>
<div id="nofix">NO GPS FIX</div>
<script>
var PAD = [32.99025, -106.97500];
var map = L.map('map', {{ zoomControl: true, attributionControl: true }}).setView(PAD, 14);

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    maxZoom: 19,
    subdomains: 'abcd',
    attribution: '&copy; OpenStreetMap &copy; CARTO'
}}).addTo(map);

var padMarker = L.marker(PAD, {{
    icon: L.divIcon({{ className:'', html:'<div class="pad-marker"></div>', iconSize:[12,12], iconAnchor:[6,6] }})
}}).addTo(map).bindTooltip('LAUNCH SITE', {{permanent:false, direction:'right'}});

var track = L.polyline([], {{ color:'{PALETTE.cyan}', weight:2.5, opacity:0.9 }}).addTo(map);
var apogeeMarker = null;

function rocketIcon(heading) {{
    return L.divIcon({{
        className: 'rocket-marker',
        html: '<svg width="26" height="26" viewBox="0 0 26 26" style="transform:rotate(' + heading + 'deg)">' +
              '<polygon points="13,2 19,22 13,18 7,22" fill="{PALETTE.cyan}" stroke="#FFFFFF" stroke-width="1.1"/>' +
              '</svg>',
        iconSize: [26, 26], iconAnchor: [13, 13]
    }});
}}

var rocket = L.marker(PAD, {{ icon: rocketIcon(0), zIndexOffset: 1000 }}).addTo(map);
var follow = true;

function setLaunchSite(lat, lon) {{
    PAD = [lat, lon];
    padMarker.setLatLng(PAD);
    map.setView(PAD, 14);
}}

function updateRocket(lat, lon, alt, heading, fix) {{
    document.getElementById('nofix').style.display = fix ? 'none' : 'block';
    if (!fix) {{ return; }}
    var p = [lat, lon];
    rocket.setLatLng(p);
    rocket.setIcon(rocketIcon(heading));
    rocket.bindTooltip(
        alt.toFixed(0) + ' m MSL', {{permanent:false, direction:'top', offset:[0,-10]}}
    );
    track.addLatLng(p);
    if (follow) {{ map.panTo(p, {{ animate: true, duration: 0.4 }}); }}
}}

function markApogee(lat, lon, alt) {{
    if (apogeeMarker) {{ map.removeLayer(apogeeMarker); }}
    apogeeMarker = L.circleMarker([lat, lon], {{
        radius: 6, color:'{PALETTE.amber}', fillColor:'{PALETTE.amber}', fillOpacity:0.85, weight:2
    }}).addTo(map).bindTooltip('APOGEE ' + alt.toFixed(0) + ' m', {{direction:'top'}});
}}

function setFollow(on) {{ follow = on; }}
function clearTrack() {{
    track.setLatLngs([]);
    if (apogeeMarker) {{ map.removeLayer(apogeeMarker); apogeeMarker = null; }}
}}
function fitTrack() {{
    var pts = track.getLatLngs();
    if (pts.length > 1) {{ map.fitBounds(track.getBounds(), {{padding:[35,35]}}); }}
}}
</script>
</body>
</html>
"""


# =====================================================================
class _GroundTrackFallback(QWidget):
    """Offline ground-track plot used when QWebEngineView is unavailable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        banner = QLabel("OFFLINE GROUND TRACK  ·  install PyQt6-WebEngine for the live map")
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setStyleSheet(
            f"color:{PALETTE.amber}; background:{PALETTE.panel_alt}; font-size:10px;"
            f"font-weight:600; padding:4px; border-bottom:1px solid {PALETTE.border};"
        )
        lay.addWidget(banner)

        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("bottom", "East [m]")
        self.plot.setLabel("left", "North [m]")
        self.plot.setAspectLocked(True)
        lay.addWidget(self.plot, 1)

        self.track = self.plot.plot(pen=pg.mkPen(PALETTE.cyan, width=2))
        self.pad = pg.ScatterPlotItem(
            [0], [0], size=11, brush=pg.mkBrush(PALETTE.amber),
            pen=pg.mkPen(PALETTE.bg_deep, width=2), symbol="o",
        )
        self.plot.addItem(self.pad)
        self.rocket = pg.ScatterPlotItem(
            [0], [0], size=13, brush=pg.mkBrush(PALETTE.cyan),
            pen=pg.mkPen(PALETTE.white, width=1), symbol="t1",
        )
        self.plot.addItem(self.rocket)

        self._e: list[float] = []
        self._n: list[float] = []
        self._origin: tuple[float, float] | None = None

    def update_position(self, lat: float, lon: float) -> None:
        if self._origin is None:
            self._origin = (lat, lon)
        lat0, lon0 = self._origin
        north = (lat - lat0) * 111_320.0
        east = (lon - lon0) * 111_320.0 * math.cos(math.radians(lat0))
        self._e.append(east)
        self._n.append(north)
        self.track.setData(self._e, self._n)
        self.rocket.setData([east], [north])

    def set_origin(self, lat: float, lon: float) -> None:
        self._origin = (lat, lon)

    def clear(self) -> None:
        self._e.clear()
        self._n.clear()
        self.track.setData([], [])


# =====================================================================
class _Readout(QWidget):
    """Small labelled monospace value used in the GPS strip."""

    def __init__(self, label: str, color: str = PALETTE.text, parent=None):
        super().__init__(parent)
        self._color = color
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)

        self._name = QLabel(label)
        self._name.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700; letter-spacing:0.8px;"
        )
        self._value = QLabel("—")
        self._value.setStyleSheet(
            f"color:{color}; font-family:{FONT_MONO}; font-size:13px; font-weight:600;"
        )
        lay.addWidget(self._name)
        lay.addWidget(self._value)

    def set(self, text: str, color: str | None = None) -> None:
        self._value.setText(text)
        # Re-parsing a stylesheet forces a re-polish/repaint even when the
        # colour is unchanged -- skip it on the (common) unchanged case.
        if color and color != self._color:
            self._color = color
            self._value.setStyleSheet(
                f"color:{color}; font-family:{FONT_MONO}; font-size:13px; font-weight:600;"
            )


# =====================================================================
class MapView(QWidget):
    """Live map + raw GPS numerics."""

    def __init__(self, launch_site: tuple[float, float] = (32.99025, -106.97500), parent=None):
        super().__init__(parent)
        self._launch_site = launch_site
        self._ready = False
        self._pending: list[str] = []
        self._follow = True
        self._last_fix: tuple[float, float] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addLayout(self._build_toolbar())

        # ---- map / fallback ------------------------------------------
        if WEBENGINE_AVAILABLE:
            MAP_HTML_PATH.write_text(MAP_HTML, encoding="utf-8")
            self.web = QWebEngineView()
            self.web.setPage(_DiagnosticPage(self.web))
            # A page loaded via file:// is sandboxed by QtWebEngine by
            # default -- it can't even load sibling local files (vendored
            # Leaflet) let alone remote ones (the tile server) without these
            # explicitly opted in. Without this the whole map silently never
            # initializes: no tiles, no markers, no zoom control, nothing.
            settings = self.web.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            self.web.loadFinished.connect(self._on_load_finished)
            self.web.setUrl(QUrl.fromLocalFile(str(MAP_HTML_PATH)))
            self.fallback = None
            root.addWidget(self.web, 1)
        else:
            self.web = None
            self.fallback = _GroundTrackFallback()
            self.fallback.set_origin(*launch_site)
            root.addWidget(self.fallback, 1)

        root.addWidget(self._build_readout_strip())

    # -----------------------------------------------------------------
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(9, 6, 8, 6)
        bar.setSpacing(6)

        title = QLabel("GPS TRAJECTORY")
        title.setStyleSheet(
            f"color:{PALETTE.text}; font-size:11px; font-weight:700; letter-spacing:1.2px;"
        )
        bar.addWidget(title)
        bar.addStretch(1)

        self.follow_btn = QPushButton("FOLLOW")
        self.follow_btn.setCheckable(True)
        self.follow_btn.setChecked(True)
        self.follow_btn.setFixedHeight(22)
        self.follow_btn.toggled.connect(self._on_follow)
        bar.addWidget(self.follow_btn)

        fit = QPushButton("FIT")
        fit.setFixedHeight(22)
        fit.setToolTip("Zoom to the whole trajectory")
        fit.clicked.connect(lambda: self._js("fitTrack();"))
        bar.addWidget(fit)

        clear = QPushButton("CLEAR")
        clear.setFixedHeight(22)
        clear.clicked.connect(self.clear_track)
        bar.addWidget(clear)

        return bar

    def _build_readout_strip(self) -> QWidget:
        strip = QWidget()
        strip.setStyleSheet(
            f"background-color:{PALETTE.panel_alt}; border-top:1px solid {PALETTE.border};"
        )
        grid = QGridLayout(strip)
        grid.setContentsMargins(11, 7, 11, 8)
        grid.setHorizontalSpacing(18)

        self.lat_out = _Readout("LATITUDE", PALETTE.cyan)
        self.lon_out = _Readout("LONGITUDE", PALETTE.cyan)
        self.alt_out = _Readout("GPS ALT")
        self.spd_out = _Readout("GND SPEED")
        self.fix_out = _Readout("FIX")
        self.dist_out = _Readout("DOWNRANGE")

        for col, w in enumerate(
            (self.lat_out, self.lon_out, self.alt_out,
             self.spd_out, self.dist_out, self.fix_out)
        ):
            grid.addWidget(w, 0, col)
        grid.setColumnStretch(6, 1)

        grid.addLayout(self._build_last_fix_row(), 1, 0, 1, 7)
        return strip

    def _build_last_fix_row(self) -> QHBoxLayout:
        """Last confirmed GPS fix, kept live even after the fix is lost --
        recovery-ready and pastable straight into Google Maps' search box."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(8)

        label = QLabel("LAST KNOWN POSITION")
        label.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-size:9px; font-weight:700; letter-spacing:0.8px;"
        )
        row.addWidget(label)

        self.last_fix_field = QLineEdit("NO FIX YET")
        self.last_fix_field.setReadOnly(True)
        self.last_fix_field.setFixedHeight(22)
        self.last_fix_field.setStyleSheet(
            f"color:{PALETTE.cyan}; font-family:{FONT_MONO}; font-size:12px; font-weight:600;"
            f"background-color:{PALETTE.bg_deep}; border:1px solid {PALETTE.border_bright};"
            "padding:2px 6px;"
        )
        row.addWidget(self.last_fix_field, 1)

        self.last_fix_copy_btn = QPushButton("COPY")
        self.last_fix_copy_btn.setFixedHeight(22)
        self.last_fix_copy_btn.setEnabled(False)
        self.last_fix_copy_btn.setToolTip("Copy as \"lat, lon\" -- paste directly into Google Maps")
        self.last_fix_copy_btn.clicked.connect(self._copy_last_fix)
        row.addWidget(self.last_fix_copy_btn)

        return row

    def _copy_last_fix(self) -> None:
        if self._last_fix is None:
            return
        lat, lon = self._last_fix
        QGuiApplication.clipboard().setText(f"{lat:.6f}, {lon:.6f}")

    # -----------------------------------------------------------------
    def _on_load_finished(self, ok: bool) -> None:
        self._ready = bool(ok)
        if not ok:
            return
        lat, lon = self._launch_site
        self._js(f"setLaunchSite({lat},{lon});")
        for js in self._pending:
            self._js(js)
        self._pending.clear()

    def _js(self, code: str) -> None:
        if self.web is None:
            return
        if self._ready:
            self.web.page().runJavaScript(code)
        else:
            self._pending.append(code)

    def _on_follow(self, checked: bool) -> None:
        self._follow = checked
        self._js(f"setFollow({'true' if checked else 'false'});")

    # -----------------------------------------------------------------
    # public API
    # -----------------------------------------------------------------
    def set_launch_site(self, lat: float, lon: float) -> None:
        self._launch_site = (lat, lon)
        self._js(f"setLaunchSite({lat},{lon});")
        if self.fallback:
            self.fallback.set_origin(lat, lon)

    def update_position(self, frame) -> None:
        """Push one frame to the map and the numeric strip."""
        fix = frame.has_gps_fix
        lat, lon = frame.lat, frame.lon

        if fix:
            self._js(
                f"updateRocket({lat:.7f},{lon:.7f},{frame.gps_alt:.1f},"
                f"{frame.gps_heading:.1f},true);"
            )
            if self.fallback:
                self.fallback.update_position(lat, lon)
            self._last_fix = (lat, lon)
            self.last_fix_field.setText(f"{lat:.6f}, {lon:.6f}")
            self.last_fix_copy_btn.setEnabled(True)
        else:
            self._js("updateRocket(0,0,0,0,false);")

        # raw numerics -- always shown, fix or not
        self.lat_out.set(f"{lat:+.6f}°" if fix else "—")
        self.lon_out.set(f"{lon:+.6f}°" if fix else "—")
        self.alt_out.set(f"{frame.gps_alt:,.0f} m" if fix else "—")
        self.spd_out.set(f"{frame.gps_speed:,.1f} m/s" if fix else "—")
        self.dist_out.set(f"{self._downrange(lat, lon):,.0f} m" if fix else "—")

        if fix:
            self.fix_out.set(f"3D · {frame.gps_sats} SV", PALETTE.green)
        elif frame.gps_fix > 0:
            self.fix_out.set(f"{frame.gps_fix}D", PALETTE.amber)
        else:
            self.fix_out.set("NO FIX", PALETTE.red)

    def mark_apogee(self, frame) -> None:
        if frame.has_gps_fix:
            self._js(
                f"markApogee({frame.lat:.7f},{frame.lon:.7f},{frame.gps_alt:.1f});"
            )

    def clear_track(self) -> None:
        self._js("clearTrack();")
        if self.fallback:
            self.fallback.clear()

    # -----------------------------------------------------------------
    def _downrange(self, lat: float, lon: float) -> float:
        """Great-circle distance from the launch site, in metres."""
        lat0, lon0 = self._launch_site
        r = 6_371_000.0
        p0, p1 = math.radians(lat0), math.radians(lat)
        dp = p1 - p0
        dl = math.radians(lon - lon0)
        a = math.sin(dp / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(a)))
