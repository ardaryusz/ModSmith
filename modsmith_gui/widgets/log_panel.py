"""LogPanel — a flat, read-only log output widget with Clear and Copy buttons.

Designed to receive line-by-line log messages from background worker threads
via Qt signals. Thread-safe: callers should emit a signal that connects to
``append_line()``; calling ``append_line()`` directly from a non-GUI thread
is not safe.

Usage (in a screen widget)::

    log = LogPanel()
    layout.addWidget(log)

    # Connect a worker signal:
    worker.log_line.connect(log.append_line)
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton,
)
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtCore import Qt


class LogPanel(QWidget):
    """Read-only text panel for displaying log lines from background operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Text area ---
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # Use a plain monospace font — no system-theme magic needed
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(mono)

        self._text.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1e1e1e;"
            "  color: #d4d4d4;"
            "  border: 1px solid #444;"
            "  padding: 4px;"
            "}"
        )

        layout.addWidget(self._text)

        # --- Button row ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setMaximumWidth(70)
        self._btn_clear.clicked.connect(self.clear)

        self._btn_copy = QPushButton("Copy All")
        self._btn_copy.setMaximumWidth(80)
        self._btn_copy.clicked.connect(self._copy_all)

        btn_row.addStretch()
        btn_row.addWidget(self._btn_clear)
        btn_row.addWidget(self._btn_copy)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_line(self, line: str) -> None:
        """Append a single log line and scroll to the bottom.

        Safe to call from the GUI thread (e.g. from a signal connected
        to a QThread worker signal).
        """
        self._text.appendPlainText(line)
        # Auto-scroll to bottom
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text.setTextCursor(cursor)

    def clear(self) -> None:
        """Clear all log content."""
        self._text.clear()

    def text(self) -> str:
        """Return the full log contents as a string."""
        return self._text.toPlainText()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text.toPlainText())
