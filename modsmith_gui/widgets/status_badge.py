"""StatusBadge — a small, flat, color-coded status indicator widget.

Renders a solid filled circle with a label alongside it.
No animations, no custom painting tricks — uses a QLabel with a
stylesheet-based border-radius trick for the circle, which works
reliably with standard Qt style on all Windows themes.

Usage::

    badge = StatusBadge()
    badge.set_ok("Workspace ready")
    badge.set_warning("MODSMITH_HOME unset")
    badge.set_error("Config file missing")
    badge.set_neutral("Not checked")
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


# Palette — plain solid colours, no gradients
_COLOR_OK = "#3a8c3a"        # muted green
_COLOR_WARNING = "#b87800"   # amber
_COLOR_ERROR = "#b83232"     # muted red
_COLOR_NEUTRAL = "#787878"   # grey

_CIRCLE_STYLE = (
    "border-radius: 5px;"
    "min-width: 10px; max-width: 10px;"
    "min-height: 10px; max-height: 10px;"
)


class StatusBadge(QWidget):
    """A small colored dot followed by a text label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._text = QLabel()
        self._text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._dot)
        layout.addWidget(self._text)

        self.set_neutral("")

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------

    def set_ok(self, message: str) -> None:
        """Display a green dot with *message*."""
        self._apply(_COLOR_OK, message)

    def set_warning(self, message: str) -> None:
        """Display an amber dot with *message*."""
        self._apply(_COLOR_WARNING, message)

    def set_error(self, message: str) -> None:
        """Display a red dot with *message*."""
        self._apply(_COLOR_ERROR, message)

    def set_neutral(self, message: str) -> None:
        """Display a grey dot with *message*."""
        self._apply(_COLOR_NEUTRAL, message)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply(self, color: str, message: str) -> None:
        self._dot.setStyleSheet(
            f"background-color: {color}; {_CIRCLE_STYLE}"
        )
        self._text.setText(message)
