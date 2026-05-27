"""GUI smoke tests for Milestone 4: Generate & Build screen.

These tests verify that:
- The GenerateBuildScreen can be instantiated without error.
- All action buttons are present and enabled at startup.
- The worker classes (Validate/Generate/Build/Clean) can be instantiated
  without error (no actual backend calls are made).
- The MainWindow renders the "Generate & Build" nav entry.

All tests are skipped if PySide6 is not installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from modsmith_gui.screens.generate_build import GenerateBuildScreen
    from modsmith_gui.widgets.log_panel import LogPanel
    from modsmith_gui.workers import (
        ValidateWorker,
        GenerateWorker,
        BuildWorker,
        CleanWorker,
    )
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 is not installed or unavailable",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qt_app():
    """Provide a single QApplication instance for the entire module."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture()
def mock_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatically mock Qt modal dialogs."""
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        lambda *a, **kw: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.information",
        lambda *a, **kw: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.warning",
        lambda *a, **kw: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.critical",
        lambda *a, **kw: QMessageBox.StandardButton.Ok,
    )


# ---------------------------------------------------------------------------
# GenerateBuildScreen tests
# ---------------------------------------------------------------------------

class TestGenerateBuildScreen:
    """Smoke tests for the GenerateBuildScreen widget."""

    def test_instantiation(self, qt_app, mock_dialogs):
        """Screen should construct without raising."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen is not None

    def test_has_validate_button(self, qt_app, mock_dialogs):
        """Validate button should exist and be enabled at startup."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        btn = screen._btn_validate
        assert btn is not None
        assert btn.isEnabled()

    def test_has_generate_button(self, qt_app, mock_dialogs):
        """Generate button should exist and be enabled at startup."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen._btn_generate.isEnabled()

    def test_has_generate_force_button(self, qt_app, mock_dialogs):
        """Generate --force button should exist and be enabled at startup."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen._btn_generate_force.isEnabled()

    def test_has_build_button(self, qt_app, mock_dialogs):
        """Build button should exist and be enabled at startup."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen._btn_build.isEnabled()

    def test_has_clean_button(self, qt_app, mock_dialogs):
        """Clean button should exist and be enabled at startup."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen._btn_clean.isEnabled()

    def test_has_open_mods_button(self, qt_app, mock_dialogs):
        """Open MODS Folder button should exist."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen._btn_open_mods is not None

    def test_has_open_dist_button(self, qt_app, mock_dialogs):
        """Open DIST Folder button should exist."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        assert screen._btn_open_dist is not None

    def test_refresh_does_not_crash(self, qt_app, mock_dialogs):
        """refresh() should not raise even with no home set."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        screen.refresh()  # should be a no-op

    def test_buttons_disabled_while_busy(self, qt_app, mock_dialogs):
        """_set_busy() should disable all action buttons."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        screen._set_busy("Testing…")
        for btn in screen._action_buttons:
            assert not btn.isEnabled()

    def test_buttons_reenabled_after_idle(self, qt_app, mock_dialogs):
        """_set_idle() should re-enable all action buttons."""
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        screen._set_busy("Testing…")
        screen._set_idle(ok=True, message="Done")
        for btn in screen._action_buttons:
            assert btn.isEnabled()

    def test_clean_cancelled_when_no_confirmed(self, qt_app, monkeypatch, mock_dialogs):
        """Clicking Clean and answering No should leave buttons enabled."""
        # Override to return No for the confirmation dialog
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.question",
            lambda *a, **kw: QMessageBox.StandardButton.No,
        )
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        screen._on_clean()
        # Buttons should still be enabled (worker never started)
        assert screen._btn_clean.isEnabled()

    def test_generate_force_cancelled_when_no_confirmed(self, qt_app, monkeypatch, mock_dialogs):
        """Clicking Generate --force and answering No should leave buttons enabled."""
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.question",
            lambda *a, **kw: QMessageBox.StandardButton.No,
        )
        log_panel = LogPanel()
        screen = GenerateBuildScreen(log_panel=log_panel)
        screen._on_generate_force()
        assert screen._btn_generate_force.isEnabled()


# ---------------------------------------------------------------------------
# Worker instantiation tests (no backend calls)
# ---------------------------------------------------------------------------

class TestWorkerInstantiation:
    """Workers should construct without calling any backend."""

    def test_validate_worker_init(self, qt_app):
        tmp = Path("/tmp")
        w = ValidateWorker(
            workspace_dir=tmp / "WORKSPACE",
            templates_dir=tmp / "MODTEMPLATES",
            mods_dir=tmp / "MODS",
        )
        assert w is not None

    def test_generate_worker_init(self, qt_app):
        tmp = Path("/tmp")
        w = GenerateWorker(
            workspace_dir=tmp / "WORKSPACE",
            templates_dir=tmp / "MODTEMPLATES",
            mods_dir=tmp / "MODS",
            force=False,
        )
        assert w is not None

    def test_build_worker_init(self, qt_app):
        tmp = Path("/tmp")
        w = BuildWorker(
            workspace_dir=tmp / "WORKSPACE",
            mods_dir=tmp / "MODS",
        )
        assert w is not None

    def test_clean_worker_init(self, qt_app):
        tmp = Path("/tmp")
        w = CleanWorker(
            workspace_dir=tmp / "WORKSPACE",
            mods_dir=tmp / "MODS",
        )
        assert w is not None


# ---------------------------------------------------------------------------
# MainWindow navigation test
# ---------------------------------------------------------------------------

class TestMainWindowHasGenerateBuild:
    """Verify the MainWindow exposes Generate & Build in the nav."""

    def test_nav_item_present(self, qt_app, mock_dialogs):
        from modsmith_gui.main_window import MainWindow
        win = MainWindow()
        labels = [
            win._nav.item(i).text()
            for i in range(win._nav.count())
        ]
        assert "Generate & Build" in labels, (
            f"'Generate & Build' not found in nav items: {labels}"
        )
