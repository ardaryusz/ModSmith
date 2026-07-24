"""Custom QComboBox subclass that ignores wheel events when closed."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QScrollArea, QWidget
from PySide6.QtGui import QWheelEvent
from PySide6.QtCore import QCoreApplication


class NoWheelComboBox(QComboBox):
    """QComboBox subclass that prevents accidental wheel scroll changes when closed."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.view().isVisible():
            super().wheelEvent(event)
            return

        event.ignore()

        # Find nearest QScrollArea parent to forward the event if needed
        parent: QWidget | None = self.parentWidget()
        target_viewport: QWidget | None = None
        while parent is not None:
            if isinstance(parent, QScrollArea):
                target_viewport = parent.viewport()
                break
            parent = parent.parentWidget()

        if target_viewport is not None:
            QCoreApplication.sendEvent(target_viewport, event)
