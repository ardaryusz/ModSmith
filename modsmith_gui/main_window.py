"""MainWindow — the top-level workbench window.

Layout
------
+-------+----------------------------------+
|       |                                  |
| Nav   |   Screen (QStackedWidget)        |
| list  |                                  |
|       |                                  |
+-------+------ LogPanel (shared) ---------+

The left nav list drives the QStackedWidget.  The LogPanel at the bottom
is shared across screens so that doctor output lands in one consistent place.

When the HomeScreen emits ``home_changed``, we call ``refresh()`` on every
screen that exposes that method so all displayed paths stay in sync.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from modsmith_gui.resources import resolve_icon_path
from modsmith_gui.widgets.log_panel import LogPanel
from modsmith_gui.screens.dashboard import DashboardScreen
from modsmith_gui.screens.home import HomeScreen


# Navigation entries: (display label, screen widget class)
_NAV_ITEMS = [
    ("Dashboard", DashboardScreen),
    ("Home", HomeScreen),
]


class MainWindow(QMainWindow):
    """Top-level ModSmith workbench window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ModSmith Workbench")
        self.resize(900, 620)
        self.setMinimumSize(760, 520)

        # Set application / window icon
        icon_path = resolve_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        # ------------------------------------------------------------------
        # Central widget
        # ------------------------------------------------------------------
        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ------------------------------------------------------------------
        # Shared LogPanel (lives at the bottom, shared across all screens)
        # ------------------------------------------------------------------
        self._log_panel = LogPanel()
        self._log_panel.setMinimumHeight(120)
        self._log_panel.setMaximumHeight(240)
        self._log_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        # ------------------------------------------------------------------
        # Top content area: [nav sidebar | screen stack] using normal QHBoxLayout
        # ------------------------------------------------------------------
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # --- Left sidebar nav ---
        self._nav = QListWidget()
        self._nav.setFixedWidth(160)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # --- Screen stack ---
        self._stack = QStackedWidget()

        # Build screens
        self._screens: list[QWidget] = []
        self._screen_objects: dict[str, QWidget] = {}

        for label, ScreenClass in _NAV_ITEMS:
            item = QListWidgetItem(label)
            self._nav.addItem(item)

            if ScreenClass is DashboardScreen:
                screen = DashboardScreen(log_panel=self._log_panel)
            else:
                screen = ScreenClass()

            self._screens.append(screen)
            self._screen_objects[label] = screen
            self._stack.addWidget(screen)

        # Wire home_changed → global refresh
        home_screen: HomeScreen = self._screen_objects["Home"]  # type: ignore[assignment]
        home_screen.home_changed.connect(self._on_home_changed)

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        top_layout.addWidget(self._nav)
        top_layout.addWidget(self._stack, stretch=1)

        # ------------------------------------------------------------------
        # Log area separator label
        # ------------------------------------------------------------------
        log_label = QLabel("  Output Log")
        log_label.setStyleSheet(
            "background-color: #d8d8d8; color: #555; font-size: 11px;"
            "padding: 2px 6px; border-top: 1px solid #bbb;"
        )

        # ------------------------------------------------------------------
        # Compose outer layout: top layout on top, log at bottom
        # ------------------------------------------------------------------
        outer.addLayout(top_layout, stretch=1)
        outer.addWidget(log_label)
        outer.addWidget(self._log_panel)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_home_changed(self) -> None:
        """Propagate a home directory change to all screens that have refresh()."""
        for screen in self._screens:
            if hasattr(screen, "refresh"):
                screen.refresh()  # type: ignore[union-attr]
