"""Focused regression tests for ModSmith 2.1.4 GUI hotfix."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication, QScrollArea, QWidget, QVBoxLayout,
    QMessageBox, QTableWidget,
)

from modsmith_gui.widgets import NoWheelComboBox
from modsmith_gui.assets_utils import import_asset, AssetImportResult
from modsmith_gui.screens.workspace import WorkspaceScreen, WorkspaceExitDecision
from modsmith_gui.dialogs.template_descriptor_dialog import TemplateDescriptorDialog
from modsmith_gui.main_window import MainWindow
from modsmith_gui.widgets.log_panel import LogPanel


# ---------------------------------------------------------------------------
# Qt Application Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# 1. Dropdown Audit & Wheel Propagation Tests
# ---------------------------------------------------------------------------

class TestDropdownWheelFix:
    """Test NoWheelComboBox usage and wheel-event propagation."""

    def test_all_user_facing_combos_use_no_wheel(self, qapp, tmp_path):
        log = LogPanel()
        ws = WorkspaceScreen(log_panel=log)
        # Check target row combos
        for r in range(ws._table.rowCount()):
            for c in (0, 1, 4):
                widget = ws._table.cellWidget(r, c)
                assert isinstance(widget, NoWheelComboBox), f"Row {r} col {c} combo is not NoWheelComboBox"

        # Check TemplateDescriptorDialog combos
        dialog = TemplateDescriptorDialog(template_path=tmp_path)
        assert isinstance(dialog._cmb_loader, NoWheelComboBox)
        assert isinstance(dialog._cmb_recipe_format, NoWheelComboBox)
        assert isinstance(dialog._cmb_recipe_folder, NoWheelComboBox)

    def test_closed_combo_wheel_event_scrolls_parent_scroll_area(self, qapp):
        scroll = QScrollArea()
        scroll.setMinimumSize(300, 200)
        scroll.resize(300, 200)

        container = QWidget()
        layout = QVBoxLayout(container)

        combo = NoWheelComboBox()
        combo.addItems(["Option 1", "Option 2", "Option 3", "Option 4"])
        combo.setCurrentIndex(0)
        layout.addWidget(combo)

        # Add dummy tall spacing so scrollbar has range
        spacer = QWidget()
        spacer.setMinimumHeight(1000)
        layout.addWidget(spacer)

        scroll.setWidget(container)
        scroll.show()
        qapp.processEvents()

        assert scroll.verticalScrollBar().maximum() > 0, "ScrollArea vertical scrollbar should be active"

        initial_combo_idx = combo.currentIndex()
        initial_scroll_val = scroll.verticalScrollBar().value()

        from PySide6.QtCore import QPoint

        # Send downward wheel event over combo
        wheel_ev = QWheelEvent(
            QPointF(combo.rect().center()),
            QPointF(combo.mapToGlobal(combo.rect().center())),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        qapp.sendEvent(combo, wheel_ev)
        qapp.processEvents()

        # Closed combo index must NOT change
        assert combo.currentIndex() == initial_combo_idx
        # Parent scrollbar value MUST change (scrolled down)
        assert scroll.verticalScrollBar().value() > initial_scroll_val, "Parent scroll area should have scrolled"

    def test_combo_keyboard_and_click_selection(self, qapp):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        combo = NoWheelComboBox()
        combo.addItems(["Alpha", "Beta", "Gamma"])
        combo.setCurrentIndex(0)

        # Arrow down key
        key_ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(combo, key_ev)
        assert combo.currentIndex() in (0, 1)  # Keyboard interaction works



# ---------------------------------------------------------------------------
# 2. Asset Import Deduplication Tests
# ---------------------------------------------------------------------------

class TestAssetImportDeduplication:
    """Test import_asset logic and collision-only deduplication policy."""

    def test_import_asset_nested_inside_assets_dir(self, tmp_path):
        assets_dir = tmp_path / "ASSETS"
        sub_dir = assets_dir / "sub"
        sub_dir.mkdir(parents=True)
        img = sub_dir / "nested.png"
        img.write_bytes(b"NESTED_DATA")

        res = import_asset(img, assets_dir)
        assert not res.copied
        assert res.reused_existing
        assert res.relative_path == Path("ASSETS/sub/nested.png")
        assert res.absolute_path == img.resolve()

    def test_import_asset_reuses_identical_numbered_candidate(self, tmp_path):
        assets_dir = tmp_path / "ASSETS"
        assets_dir.mkdir()
        (assets_dir / "photo.png").write_bytes(b"V1")
        (assets_dir / "photo_1.png").write_bytes(b"TARGET_CONTENT")

        # External file with identical content to photo_1.png
        ext_src = tmp_path / "external" / "photo.png"
        ext_src.parent.mkdir()
        ext_src.write_bytes(b"TARGET_CONTENT")

        res = import_asset(ext_src, assets_dir)
        assert not res.copied
        assert res.reused_existing
        assert res.absolute_path == (assets_dir / "photo_1.png").resolve()
        assert res.relative_path == Path("ASSETS/photo_1.png")
        assert not (assets_dir / "photo_2.png").exists()

    def test_import_asset_collision_only_policy_does_not_dedup_different_names(self, tmp_path):
        assets_dir = tmp_path / "ASSETS"
        assets_dir.mkdir()
        (assets_dir / "existing.png").write_bytes(b"SHARED_BYTES")

        # External file with different name but same bytes
        ext_src = tmp_path / "external" / "other.png"
        ext_src.parent.mkdir()
        ext_src.write_bytes(b"SHARED_BYTES")

        res = import_asset(ext_src, assets_dir)
        assert res.copied
        assert not res.reused_existing
        assert res.absolute_path == (assets_dir / "other.png").resolve()
        assert res.relative_path == Path("ASSETS/other.png")
        assert (assets_dir / "other.png").exists()

    def test_import_asset_same_name_identical_content(self, tmp_path):
        assets_dir = tmp_path / "ASSETS"
        assets_dir.mkdir()
        (assets_dir / "icon.png").write_bytes(b"ICON_BYTES")

        ext_src = tmp_path / "external" / "icon.png"
        ext_src.parent.mkdir()
        ext_src.write_bytes(b"ICON_BYTES")

        res = import_asset(ext_src, assets_dir)
        assert not res.copied
        assert res.reused_existing
        assert res.absolute_path == (assets_dir / "icon.png").resolve()
        assert res.relative_path == Path("ASSETS/icon.png")

    def test_import_asset_same_name_different_content(self, tmp_path):
        assets_dir = tmp_path / "ASSETS"
        assets_dir.mkdir()
        (assets_dir / "icon.png").write_bytes(b"OLD_BYTES")

        ext_src = tmp_path / "external" / "icon.png"
        ext_src.parent.mkdir()
        ext_src.write_bytes(b"NEW_BYTES")

        res = import_asset(ext_src, assets_dir)
        assert res.copied
        assert not res.reused_existing
        assert res.absolute_path == (assets_dir / "icon_1.png").resolve()
        assert res.relative_path == Path("ASSETS/icon_1.png")
        assert (assets_dir / "icon_1.png").read_bytes() == b"NEW_BYTES"

    def test_import_asset_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_asset(tmp_path / "nonexistent.png", tmp_path / "ASSETS")


# ---------------------------------------------------------------------------
# 3. Unsaved Workspace Exit Guard & Navigation Signal Tests
# ---------------------------------------------------------------------------

class TestUnsavedWorkspaceGuards:
    """Test Workspace dirty state, confirmation dialogs, and navigation signals."""

    def test_clean_workspace_does_not_prompt_or_flag_dirty(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
        log = LogPanel()
        ws = WorkspaceScreen(log_panel=log)

        assert not ws.is_dirty()
        assert ws.confirm_workspace_exit() == WorkspaceExitDecision.DISCARD

    def test_workspace_dirty_state_clears_when_reverted(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
        log = LogPanel()
        ws = WorkspaceScreen(log_panel=log)

        original_name = ws._txt_mod_name.text()
        ws._txt_mod_name.setText("Temporary Edit")
        assert ws.is_dirty()

        ws._txt_mod_name.setText(original_name)
        assert not ws.is_dirty()

    def test_navigation_signal_recursion_prevention_on_cancel(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
        mw = MainWindow()

        # Navigate to Workspace (index 4)
        mw._nav.setCurrentRow(4)
        qapp.processEvents()
        assert mw._current_index == 4

        ws = mw._screen_objects["Workspace"]
        ws._txt_mod_name.setText("Dirty Mod Name Edit")
        assert ws.is_dirty()

        # User cancels navigation when prompted
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            mw._nav.setCurrentRow(0)  # Try switching to Dashboard
            qapp.processEvents()

            assert mw._nav.currentRow() == 4
            assert mw._stack.currentIndex() == 4
            assert mw._current_index == 4
            assert ws.is_dirty()

    def test_workspace_discard_restores_state_and_retains_assets(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
        log = LogPanel()
        ws = WorkspaceScreen(log_panel=log)

        # Import an asset into ASSETS
        assets_dir = tmp_path / "WORKSPACE" / "ASSETS"
        assets_dir.mkdir(parents=True, exist_ok=True)
        imported_img = assets_dir / "my_icon.png"
        imported_img.write_bytes(b"IMAGE_BYTES")

        ws._set_icon_state("ASSETS/my_icon.png")
        ws._txt_mod_name.setText("Dirty Edit Name")
        assert ws.is_dirty()

        ws.discard_changes()

        assert not ws.is_dirty()
        assert ws._txt_mod_name.text() != "Dirty Edit Name"
        # Imported image file remains on disk
        assert imported_img.exists()
        assert imported_img.read_bytes() == b"IMAGE_BYTES"

    def test_window_close_event_cancellation(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
        mw = MainWindow()
        ws = mw._screen_objects["Workspace"]
        ws._txt_mod_name.setText("Unsaved Work")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            from PySide6.QtGui import QCloseEvent
            ev = QCloseEvent()
            mw.closeEvent(ev)
            assert ev.isAccepted() is False


# ---------------------------------------------------------------------------
# 4. Packaging Script Cleanup & Preservation Tests
# ---------------------------------------------------------------------------

class TestPackagingScriptFix:
    """Test build_exe.ps1 and build_installer.ps1 clean and preservation semantics."""

    def test_build_exe_preserves_installer_dir_and_rebuilds_installer(self):
        project_root = Path(__file__).resolve().parent.parent
        dist_dir = project_root / "dist"
        installer_dir = dist_dir / "installer"
        modsmith_dir = dist_dir / "ModSmith"

        installer_dir.mkdir(parents=True, exist_ok=True)
        survivor_file = installer_dir / "survivor_test_file.txt"
        survivor_file.write_text("survived content", encoding="utf-8")

        try:
            # 1. Run build_exe.ps1
            cmd_exe = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(project_root / "scripts" / "build_exe.ps1"),
            ]
            res_exe = subprocess.run(
                cmd_exe, capture_output=True, text=True, cwd=str(project_root)
            )
            assert res_exe.returncode == 0, f"build_exe.ps1 failed:\n{res_exe.stderr}\n{res_exe.stdout}"

            # Verify existing file in dist/installer survived build_exe.ps1
            assert survivor_file.exists(), "survivor_test_file.txt in dist/installer was deleted by build_exe.ps1"
            assert survivor_file.read_text(encoding="utf-8") == "survived content"

            # Verify dist/ModSmith was rebuilt
            assert modsmith_dir.exists(), "dist/ModSmith was not created"
            assert (modsmith_dir / "modsmith.exe").exists(), "modsmith.exe was not created"
            assert (modsmith_dir / "modsmith_cli.exe").exists(), "modsmith_cli.exe was not created"

            # 2. Run build_installer.ps1
            cmd_inst = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(project_root / "scripts" / "build_installer.ps1"),
            ]
            res_inst = subprocess.run(
                cmd_inst, capture_output=True, text=True, cwd=str(project_root)
            )
            assert res_inst.returncode == 0, f"build_installer.ps1 failed:\n{res_inst.stderr}\n{res_inst.stdout}"

            setup_exe = installer_dir / "modsmith_2.1.4_x64-setup.exe"
            assert setup_exe.exists(), "modsmith_2.1.4_x64-setup.exe was not produced by build_installer.ps1"
            assert survivor_file.exists(), "survivor_test_file.txt in dist/installer was deleted by build_installer.ps1"
        finally:
            if survivor_file.exists():
                survivor_file.unlink()

