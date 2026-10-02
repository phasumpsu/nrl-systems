"""
Raw serial/UDP byte monitor -- shows exactly what's on the wire, undecoded.

Bytes arrive on the source's worker thread at up to hundreds of times a
second; rather than touching the QPlainTextEdit per-chunk, `feed()` just
appends to a buffer and the owning window flushes it to screen on the
regular UI timer, matching how frames/graphs are throttled.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..theme import FONT_MONO, PALETTE

BYTES_PER_HEX_LINE = 16


class RawMonitor(QWidget):
    """Live view of the unparsed byte stream, in hex or ASCII."""

    def __init__(self, max_lines: int = 4000, parent=None):
        super().__init__(parent)

        self._paused = False
        self._pending = bytearray()
        self._hex_line = bytearray()
        self._offset = 0
        self._total_bytes = 0
        self._t0 = time.time()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 6, 6, 6)
        bar.setSpacing(6)

        bar.addWidget(QLabel("MODE"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["HEX", "ASCII"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        bar.addWidget(self.mode_combo)

        self.pause_btn = QPushButton("PAUSE")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause_toggled)
        bar.addWidget(self.pause_btn)

        clear_btn = QPushButton("CLEAR")
        clear_btn.clicked.connect(self.clear)
        bar.addWidget(clear_btn)

        bar.addStretch(1)

        self.stats_label = QLabel("0 B")
        self.stats_label.setStyleSheet(
            f"color:{PALETTE.text_faint}; font-family:{FONT_MONO}; font-size:11px;"
        )
        bar.addWidget(self.stats_label)

        lay.addLayout(bar)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(max_lines)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setStyleSheet(f"color:{PALETTE.text_dim};")
        lay.addWidget(self.view)

    # -----------------------------------------------------------------
    def _on_pause_toggled(self, checked: bool) -> None:
        self._paused = checked
        self.pause_btn.setText("RESUME" if checked else "PAUSE")

    def _on_mode_changed(self, _index: int) -> None:
        self._hex_line.clear()

    # -----------------------------------------------------------------
    def feed(self, data: bytes) -> None:
        """Called from the GUI thread (connected to the source's `raw` signal)."""
        self._total_bytes += len(data)
        if not self._paused:
            self._pending.extend(data)

    def flush(self) -> None:
        """Render whatever has accumulated since the last flush. Call on a timer."""
        if not self._pending:
            return
        chunk, self._pending = bytes(self._pending), bytearray()

        if self.mode_combo.currentText() == "HEX":
            text = self._format_hex(chunk)
        else:
            text = chunk.decode("ascii", errors="replace").replace("\r", "")

        if text:
            cursor = self.view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText(text)
            self.view.setTextCursor(cursor)
            self.view.ensureCursorVisible()

        elapsed = time.time() - self._t0
        rate = self._total_bytes / elapsed if elapsed > 0 else 0.0
        self.stats_label.setText(f"{self._total_bytes:,} B   ({rate:,.0f} B/s)")

    # -----------------------------------------------------------------
    def _format_hex(self, chunk: bytes) -> str:
        self._hex_line.extend(chunk)
        lines = []
        while len(self._hex_line) >= BYTES_PER_HEX_LINE:
            row, self._hex_line = (
                bytes(self._hex_line[:BYTES_PER_HEX_LINE]),
                self._hex_line[BYTES_PER_HEX_LINE:],
            )
            lines.append(self._hex_row(row))
            self._offset += len(row)
        return "\n".join(lines) + ("\n" if lines else "")

    def _hex_row(self, row: bytes) -> str:
        hex_part = " ".join(f"{b:02X}" for b in row)
        hex_part = hex_part.ljust(BYTES_PER_HEX_LINE * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        return f"{self._offset:08X}  {hex_part}  |{ascii_part}|"

    # -----------------------------------------------------------------
    def clear(self) -> None:
        self.view.clear()
        self._pending.clear()
        self._hex_line.clear()
        self._offset = 0
        self._total_bytes = 0
        self._t0 = time.time()
        self.stats_label.setText("0 B")
