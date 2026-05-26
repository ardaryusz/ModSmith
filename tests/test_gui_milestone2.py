import sys
import pytest

try:
    from PySide6.QtWidgets import QApplication
    from modsmith_gui.screens.templates import TemplatesScreen
    from modsmith_gui.screens.recipes import RecipesScreen
    from modsmith_gui.main_window import MainWindow
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

# Skip entire test suite in this file if PySide6 is not installed
pytestmark = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 is not installed or unavailable"
)


def test_pyside6_imports() -> None:
    """Verify that all new GUI package screens import without exceptions."""
    from modsmith_gui.screens.templates import TemplatesScreen
    from modsmith_gui.screens.recipes import RecipesScreen

    assert TemplatesScreen is not None
    assert RecipesScreen is not None


def test_screens_instantiation() -> None:
    """Verify that GUI screens can be created and queried cleanly in a test event loop."""
    app = QApplication.instance()
    created_app = False
    if not app:
        app = QApplication([])
        created_app = True

    try:
        tpl_screen = TemplatesScreen()
        rec_screen = RecipesScreen()

        assert tpl_screen is not None
        assert rec_screen is not None

        # Basic properties
        assert tpl_screen.objectName() == ""
        assert rec_screen.objectName() == ""

        # Clean up widgets
        tpl_screen.deleteLater()
        rec_screen.deleteLater()
    finally:
        if created_app and app:
            app.processEvents()
