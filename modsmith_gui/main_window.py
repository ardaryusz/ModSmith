"""MainWindow — the top-level workbench window.

Layout
------
+-------+----------------------------------+
|       |                                  |
| Nav   |   Screen (QStackedWidget)        |
| list  |                                  |
|       |                                  |
+-------+------------ QSplitter -----------+
                (vertical, resizable)
         ┌── top content area above ──┐
         └── Output Log panel below  ──┘

The left nav list drives the QStackedWidget.  The LogPanel at the bottom
is shared across screens so that doctor output lands in one consistent place.

The vertical QSplitter between the main content area and the log panel lets
the user drag the separator to make the Output Log taller or shorter.

When the HomeScreen emits ``home_changed``, we call ``refresh()`` on every
screen that exposes that method so all displayed paths stay in sync.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
    QSizePolicy, QLabel, QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from modsmith_gui.resources import resolve_icon_path
from modsmith_gui.widgets.log_panel import LogPanel
from modsmith_gui.screens.dashboard import DashboardScreen
from modsmith_gui.screens.home import HomeScreen
from modsmith_gui.screens.templates import TemplatesScreen
from modsmith_gui.screens.recipes import RecipesScreen
from modsmith_gui.screens.workspace import WorkspaceScreen
from modsmith_gui.screens.generate_build import GenerateBuildScreen


# Navigation entries: (display label, screen widget class)
_NAV_ITEMS = [
    ("Dashboard", DashboardScreen),
    ("Home", HomeScreen),
    ("Templates", TemplatesScreen),
    ("Recipes", RecipesScreen),
    ("Workspace", WorkspaceScreen),
    ("Generate & Build", GenerateBuildScreen),
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
        self._log_panel.setMinimumHeight(60)
        # Remove fixed height so the splitter controls the size freely.
        self._log_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        # ------------------------------------------------------------------
        # Top content area: [nav sidebar | screen stack]
        # ------------------------------------------------------------------
        top_content = QWidget()
        top_content.setMinimumHeight(0)
        top_content.setMinimumSize(0, 0)
        top_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        top_layout = QHBoxLayout(top_content)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # --- Left sidebar nav ---
        self._nav = QListWidget()
        self._nav.setFixedWidth(160)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Ignored,
        )

        # --- Screen stack ---
        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(0)
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )

        # Build screens
        self._screens: list[QWidget] = []
        self._screen_objects: dict[str, QWidget] = {}

        for label, ScreenClass in _NAV_ITEMS:
            item = QListWidgetItem(label)
            self._nav.addItem(item)

            if ScreenClass is DashboardScreen:
                screen = DashboardScreen(log_panel=self._log_panel)
            elif ScreenClass is WorkspaceScreen:
                screen = WorkspaceScreen(log_panel=self._log_panel)
            elif ScreenClass is GenerateBuildScreen:
                screen = GenerateBuildScreen(log_panel=self._log_panel)
            else:
                screen = ScreenClass()

            self._screens.append(screen)
            self._screen_objects[label] = screen
            self._stack.addWidget(screen)

        # Wire home_changed → global refresh
        home_screen: HomeScreen = self._screen_objects["Home"]  # type: ignore[assignment]
        home_screen.home_changed.connect(self._on_home_changed)

        self._nav.currentRowChanged.connect(self._on_nav_changed)
        self._nav.setCurrentRow(0)

        top_layout.addWidget(self._nav)
        top_layout.addWidget(self._stack, stretch=1)

        # ------------------------------------------------------------------
        # Log area: label + panel, wrapped in a container widget
        # ------------------------------------------------------------------
        log_label = QLabel("  Output Log")
        log_label.setStyleSheet(
            "background-color: #d8d8d8; color: #555; font-size: 11px;"
            "padding: 2px 6px; border-top: 1px solid #bbb;"
        )

        log_container = QWidget()
        log_container_layout = QVBoxLayout(log_container)
        log_container_layout.setContentsMargins(0, 0, 0, 0)
        log_container_layout.setSpacing(0)
        log_container_layout.addWidget(log_label)
        log_container_layout.addWidget(self._log_panel)
        log_container.setMinimumHeight(60)

        # ------------------------------------------------------------------
        # Vertical QSplitter: top content above, log panel below
        # ------------------------------------------------------------------
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(top_content)
        self._splitter.addWidget(log_container)
        self._splitter.setCollapsible(0, True)
        self._splitter.setCollapsible(1, False)

        # Default sizes: top area gets ~460 px, log gets ~140 px.
        self._splitter.setSizes([460, 140])

        outer.addWidget(self._splitter)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_home_changed(self) -> None:
        """Propagate a home directory change to all screens that have refresh()."""
        for screen in self._screens:
            if hasattr(screen, "refresh"):
                screen.refresh()  # type: ignore[union-attr]

    def _on_nav_changed(self, index: int) -> None:
        """Handle screen changes and call refresh() on the selected screen if available."""
        self._stack.setCurrentIndex(index)
        screen = self._screens[index]
        if hasattr(screen, "refresh"):
            screen.refresh()
