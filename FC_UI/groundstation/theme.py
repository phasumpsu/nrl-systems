"""
Visual theme for the NRL ground station -- black / white / pink, built around
the Nittany Rocket Labs wordmark (#C1489B). Status colours (green/amber/red)
are kept distinct from the brand accent on purpose -- they carry safety
meaning (armed/caution/fired) that has to stay readable regardless of the
brand palette.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # --- surfaces -------------------------------------------------------
    bg_deep: str = "#000000"      # window ground
    bg: str = "#0A0808"           # dock background
    panel: str = "#121012"        # card surface
    panel_alt: str = "#1C181B"    # raised / header surface
    border: str = "#2B2429"
    border_bright: str = "#4A3540"

    # --- type -----------------------------------------------------------
    text: str = "#FFFFFF"
    text_dim: str = "#C9C2C6"
    text_faint: str = "#7D747A"

    # --- brand ----------------------------------------------------------
    navy: str = "#1A0E16"         # deep brand black -- pressed / selected surfaces
    navy_light: str = "#7A3A61"   # structural brand border/underline

    # --- status ---------------------------------------------------------
    cyan: str = "#E8449E"         # primary accent / nominal -- brand pink
    cyan_dim: str = "#9A2F6C"
    green: str = "#00E676"        # armed / go
    amber: str = "#FFB627"        # caution
    red: str = "#FF3B4E"          # fired / abort
    magenta: str = "#C778FF"      # secondary trace (kept distinct from the primary pink)
    white: str = "#FFFFFF"
    grey: str = "#5A5158"         # disarmed / inert


PALETTE = Palette()

FONT_UI = '"Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Mono", Consolas, "Courier New", monospace'

# Series colours for the telemetry plots, in draw order.
SERIES_COLORS = (
    PALETTE.cyan,
    PALETTE.amber,
    PALETTE.magenta,
    PALETTE.green,
    PALETTE.red,
)


def build_stylesheet(p: Palette = PALETTE) -> str:
    """Global Qt stylesheet. Applied once to the QApplication."""
    return f"""
    QWidget {{
        background-color: {p.bg};
        color: {p.text};
        font-family: {FONT_UI};
        font-size: 12px;
    }}
    QMainWindow, QMainWindow > QWidget {{
        background-color: {p.bg_deep};
    }}
    QMainWindow::separator {{
        background-color: {p.bg_deep};
        width: 4px;
        height: 4px;
    }}
    QMainWindow::separator:hover {{
        background-color: {p.cyan_dim};
    }}

    /* ---------------- docks ---------------- */
    QDockWidget {{
        color: {p.text_dim};
        font-size: 11px;
        font-weight: 700;
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }}
    QDockWidget::title {{
        background-color: {p.panel_alt};
        border: 1px solid {p.border};
        border-bottom: 2px solid {p.navy_light};
        padding: 7px 10px;
        text-align: left;
    }}
    QDockWidget > QWidget {{
        background-color: {p.panel};
        border: 1px solid {p.border};
        border-top: none;
    }}

    /* ---------------- cards ---------------- */
    QGroupBox {{
        background-color: {p.panel};
        border: 1px solid {p.border};
        border-radius: 3px;
        margin-top: 16px;
        padding: 10px 8px 8px 8px;
        font-size: 10px;
        font-weight: 700;
        color: {p.text_faint};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 8px;
        padding: 0 5px;
        color: {p.text_faint};
    }}

    /* ---------------- controls ---------------- */
    QToolBar {{
        background-color: {p.panel_alt};
        border-bottom: 1px solid {p.border};
        spacing: 6px;
        padding: 5px 8px;
    }}
    QPushButton {{
        background-color: {p.panel_alt};
        border: 1px solid {p.border_bright};
        border-radius: 3px;
        padding: 6px 14px;
        font-size: 11px;
        font-weight: 600;
        color: {p.text};
    }}
    QPushButton:hover {{
        border-color: {p.cyan};
        color: {p.cyan};
    }}
    QPushButton:pressed {{
        background-color: {p.navy};
    }}
    QPushButton:disabled {{
        color: {p.text_faint};
        border-color: {p.border};
    }}
    QPushButton:checked {{
        background-color: {p.navy};
        border-color: {p.cyan};
        color: {p.cyan};
    }}

    QComboBox {{
        background-color: {p.panel_alt};
        border: 1px solid {p.border_bright};
        border-radius: 3px;
        padding: 5px 10px;
        min-width: 90px;
        color: {p.text};
    }}
    QComboBox:hover {{ border-color: {p.cyan}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background-color: {p.panel_alt};
        border: 1px solid {p.border_bright};
        selection-background-color: {p.navy};
        selection-color: {p.cyan};
        outline: none;
    }}

    QLineEdit {{
        background-color: {p.bg_deep};
        border: 1px solid {p.border_bright};
        border-radius: 3px;
        padding: 5px 8px;
        font-family: {FONT_MONO};
        color: {p.text};
    }}
    QLineEdit:focus {{ border-color: {p.cyan}; }}

    /* ---------------- log ---------------- */
    QPlainTextEdit {{
        background-color: {p.bg_deep};
        border: 1px solid {p.border};
        font-family: {FONT_MONO};
        font-size: 11px;
        color: {p.text_dim};
    }}

    /* ---------------- scrollbars ---------------- */
    QScrollBar:vertical {{
        background: {p.bg_deep};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border_bright};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.cyan_dim}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    QScrollBar:horizontal {{
        background: {p.bg_deep};
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.border_bright};
        border-radius: 5px;
        min-width: 24px;
    }}

    QToolTip {{
        background-color: {p.panel_alt};
        color: {p.text};
        border: 1px solid {p.cyan};
        padding: 4px 7px;
    }}

    QSplitter::handle {{ background-color: {p.bg_deep}; }}
    QSplitter::handle:hover {{ background-color: {p.cyan_dim}; }}
    """
