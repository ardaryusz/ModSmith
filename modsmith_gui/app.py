"""QApplication factory and global stylesheet for ModSmith GUI.

Keeps all application-level concerns (style, font, high-DPI settings)
in one place so ``__main__.py`` stays trivial.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon

from modsmith_gui.resources import resolve_icon_path


# ---------------------------------------------------------------------------
# Minimal flat stylesheet
# ---------------------------------------------------------------------------
# Goals:
#  - Readable, clean look on Windows 10/11 with default system theme.
#  - No animations, no gradients beyond the nav highlight.
#  - Practical workbench feel — neutral grays with clear contrast.
# ---------------------------------------------------------------------------

_STYLESHEET = """
QWidget {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
}

QMainWindow, QDialog {
    background-color: #f0f0f0;
}

/* Sidebar nav list */
QListWidget {
    background-color: #2b2b2b;
    color: #d4d4d4;
    border: none;
    outline: none;
    font-size: 12px;
}
QListWidget::item {
    padding: 10px 14px;
    border-bottom: 1px solid #3a3a3a;
}
QListWidget::item:selected {
    background-color: #3a5a8a;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #3d3d3d;
}

/* Content area */
QStackedWidget {
    background-color: #f5f5f5;
}

/* Group boxes */
QGroupBox {
    font-weight: bold;
    font-size: 12px;
    color: #111111;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 10px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    background-color: #ffffff;
    color: #111111;
}

/* Form labels */
QFormLayout QLabel {
    color: #555;
}

/* Plain value labels */
QLabel {
    color: #222;
}

/* Standard buttons */
QPushButton {
    background-color: #e0e0e0;
    color: #222;
    border: 1px solid #adadad;
    border-radius: 3px;
    padding: 4px 12px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #d0d0d0;
    border-color: #888;
}
QPushButton:pressed {
    background-color: #b8b8b8;
}
QPushButton:disabled {
    background-color: #e8e8e8;
    color: #aaa;
    border-color: #ccc;
}

/* Scrollbars — keep narrow and unobtrusive */
QScrollBar:vertical {
    width: 8px;
    background: #e8e8e8;
}
QScrollBar::handle:vertical {
    background: #b0b0b0;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Flat clean styling for editable inputs */
QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    border-radius: 2px;
    padding: 2px 4px;
    color: #111111;
    selection-background-color: #3a5a8a;
    selection-color: #ffffff;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: #3a5a8a;
}
QLineEdit[readOnly="true"], QPlainTextEdit[readOnly="true"], QTextEdit[readOnly="true"] {
    background-color: transparent;
    border: none;
    padding: 0px;
    color: #111111;
}

/* Combo boxes */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    border-radius: 2px;
    padding: 2px 6px;
    color: #111111;
    selection-background-color: #3a5a8a;
    selection-color: #ffffff;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #111111;
    selection-background-color: #3a5a8a;
    selection-color: #ffffff;
    border: 1px solid #c0c0c0;
}

/* Flat neutral table style */
QTableWidget {
    background-color: #ffffff;
    gridline-color: #e5e5e5;
    border: 1px solid #d0d0d0;
    color: #111111;
    font-size: 11px;
    selection-background-color: #3a5a8a;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item {
    color: #111111;
    background-color: #ffffff;
    padding: 4px 6px;
}
QTableWidget::item:selected {
    background-color: #3a5a8a;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #e0e0e0;
    color: #333;
    padding: 4px;
    border: 1px solid #ccc;
    font-weight: bold;
    font-size: 11px;
}
"""



def run_app() -> int:
    """Create and run the ModSmith GUI application.  Returns the exit code."""
    # Enable high-DPI scaling automatically on Qt 6
    app = QApplication(sys.argv)
    app.setApplicationName("ModSmith")
    app.setApplicationVersion("1.3.0")
    app.setOrganizationName("ModSmith Project")

    # Set application-wide icon if available
    icon_path = resolve_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # Apply global stylesheet
    app.setStyleSheet(_STYLESHEET)

    # Default font fallback (in case system font hints don't resolve)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Import here to keep Qt import cascade after QApplication is created
    from modsmith_gui.main_window import MainWindow  # noqa: PLC0415

    window = MainWindow()
    window.show()

    return app.exec()
