"""Tests for Template Descriptor Editor — GUI polish.

Structure:
  TestInferDefaults          — pure helper tests, no PySide6 needed
  TestRecipeFormatHelper     — pure helper tests, no PySide6 needed
  TestDescriptorDialog       — GUI tests, skipped if PySide6 unavailable
  TestDescriptorDialogSave   — GUI tests, skipped if PySide6 unavailable
  TestTemplatesScreenDescriptor — GUI smoke tests, skipped if PySide6 unavailable
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Pure helper tests (no PySide6 required)
# ---------------------------------------------------------------------------

from modsmith_gui.template_descriptor_utils import (
    infer_template_descriptor_defaults,
    recipe_format_for_minecraft_version,
    RECIPE_FORMAT_LEGACY,
    RECIPE_FORMAT_TRANSITIONAL,
    RECIPE_FORMAT_MODERN,
)


class TestRecipeFormatHelper:
    """Tests for recipe_format_for_minecraft_version."""

    def test_1_20_is_legacy(self):
        assert recipe_format_for_minecraft_version("1.20") == RECIPE_FORMAT_LEGACY

    def test_1_20_1_is_legacy(self):
        assert recipe_format_for_minecraft_version("1.20.1") == RECIPE_FORMAT_LEGACY

    def test_1_20_4_is_legacy(self):
        assert recipe_format_for_minecraft_version("1.20.4") == RECIPE_FORMAT_LEGACY

    def test_1_21_is_modern(self):
        assert recipe_format_for_minecraft_version("1.21") == RECIPE_FORMAT_TRANSITIONAL

    def test_1_21_1_is_modern(self):
        assert recipe_format_for_minecraft_version("1.21.1") == RECIPE_FORMAT_TRANSITIONAL

    def test_1_21_4_is_modern(self):
        assert recipe_format_for_minecraft_version("1.21.4") == RECIPE_FORMAT_MODERN

    def test_empty_string_returns_modern(self):
        assert recipe_format_for_minecraft_version("") == RECIPE_FORMAT_MODERN

    def test_unparseable_returns_modern(self):
        assert recipe_format_for_minecraft_version("unknown") == RECIPE_FORMAT_MODERN


class TestInferDefaults:
    """Tests for infer_template_descriptor_defaults."""

    def _infer(self, name: str) -> dict:
        return infer_template_descriptor_defaults(name)

    # --- Forge ---

    def test_forge_1_20_1(self):
        d = self._infer("forge-1.20.1")
        assert d["loader"] == "forge"
        assert d["minecraft_version"] == "1.20.1"
        assert d["recipe_format"] == RECIPE_FORMAT_LEGACY
        assert d["recipe_folder"] == "recipes"
        assert d["jar_loader_suffix"] == "forge"

    def test_forge_1_21_1(self):
        d = self._infer("forge-1.21.1")
        assert d["loader"] == "forge"
        assert d["minecraft_version"] == "1.21.1"
        assert d["recipe_format"] == RECIPE_FORMAT_TRANSITIONAL
        assert d["jar_loader_suffix"] == "forge"

    def test_forge_uppercase_case_insensitive(self):
        """Inference is case-insensitive: 'FORGE-1.20.1' matches 'forge'."""
        d = self._infer("FORGE-1.20.1")
        assert d["loader"] == "forge"
        assert d["minecraft_version"] == "1.20.1"

    # --- Fabric ---

    def test_fabric_1_21_1(self):
        d = self._infer("fabric-1.21.1")
        assert d["loader"] == "fabric"
        assert d["minecraft_version"] == "1.21.1"
        assert d["recipe_format"] == RECIPE_FORMAT_TRANSITIONAL
        assert d["jar_loader_suffix"] == "fabric"

    def test_fabric_1_20_1(self):
        d = self._infer("fabric-1.20.1")
        assert d["loader"] == "fabric"
        assert d["recipe_format"] == RECIPE_FORMAT_LEGACY

    # --- NeoForge ---

    def test_neoforge_1_21_1(self):
        d = self._infer("neoforge-1.21.1")
        assert d["loader"] == "neoforge"
        assert d["minecraft_version"] == "1.21.1"
        assert d["recipe_format"] == RECIPE_FORMAT_TRANSITIONAL
        assert d["jar_loader_suffix"] == "neoforge"

    def test_neoforge_1_21_4(self):
        d = self._infer("neoforge-1.21.4")
        assert d["loader"] == "neoforge"
        assert d["jar_loader_suffix"] == "neoforge"

    # --- Unknown folder names ---

    def test_unknown_name_empty_loader(self):
        d = self._infer("my-template")
        assert d["loader"] == ""
        assert d["minecraft_version"] == ""
        assert d["recipe_folder"] == "recipe"

    def test_bare_name_no_dash(self):
        d = self._infer("mytpl")
        assert d["loader"] == ""
        assert d["minecraft_version"] == ""
        assert d["recipe_folder"] == "recipe"

    def test_loader_no_version(self):
        """'forge' alone (no version) should not match."""
        d = self._infer("forge")
        assert d["loader"] == ""

    def test_loader_non_numeric_version(self):
        """'forge-abc' should not match because version is not numeric."""
        d = self._infer("forge-abc")
        assert d["loader"] == ""

    # --- Path stripping ---

    def test_full_path_stripped_to_name(self):
        d = self._infer("MODTEMPLATES/forge-1.20.1")
        assert d["loader"] == "forge"
        assert d["minecraft_version"] == "1.20.1"

    def test_backslash_path_stripped(self):
        d = self._infer("MODTEMPLATES\\neoforge-1.21.1")
        assert d["loader"] == "neoforge"

    # --- Version-dependent recipe_folder defaults ---

    def test_recipe_folder_defaults_by_version(self):
        assert self._infer("forge-1.20.1")["recipe_folder"] == "recipes"
        assert self._infer("forge-1.21")["recipe_folder"] == "recipe"
        assert self._infer("forge-1.21.1")["recipe_folder"] == "recipe"
        assert self._infer("fabric-1.21.11")["recipe_folder"] == "recipe"


# ---------------------------------------------------------------------------
# GUI tests — skipped if PySide6 unavailable
# ---------------------------------------------------------------------------

try:
    from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
    from modsmith_gui.dialogs.template_descriptor_dialog import TemplateDescriptorDialog
    from modsmith_gui.screens.templates import TemplatesScreen
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

pytestmark_gui = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 is not installed or unavailable",
)


@pytest.fixture(scope="module")
def qt_app():
    """Provide a single QApplication instance for the module."""
    if not PYSIDE6_AVAILABLE:
        pytest.skip("PySide6 not available")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture()
def mock_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suppress Qt modal dialogs."""
    if not PYSIDE6_AVAILABLE:
        return
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question",
                        lambda *a, **kw: QMessageBox.StandardButton.No)
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information",
                        lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning",
                        lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical",
                        lambda *a, **kw: QMessageBox.StandardButton.Ok)


@pytestmark_gui
class TestDescriptorDialog:
    """Smoke tests for TemplateDescriptorDialog instantiation."""

    def test_dialog_instantiation_new(self, qt_app, tmp_path):
        """Dialog should construct for a folder with no descriptor."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg is not None

    def test_dialog_instantiation_existing(self, qt_app, tmp_path):
        """Dialog should construct when descriptor already exists."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        desc = tpl / "modsmith-template.json"
        desc.write_text(
            json.dumps({
                "loader": "forge",
                "minecraft_version": "1.20.1",
                "recipe_format": "legacy_1_20",
                "recipe_folder": "recipes",
                "jar_loader_suffix": "forge",
            }),
            encoding="utf-8",
        )
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg is not None

    def test_inferred_loader_set_in_form(self, qt_app, tmp_path):
        """Creating dialog for 'forge-1.20.1' should pre-select 'forge'."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._cmb_loader.currentText() == "forge"

    def test_inferred_mc_version_set_in_form(self, qt_app, tmp_path):
        """Creating dialog for 'neoforge-1.21.4' should fill '1.21.4'."""
        tpl = tmp_path / "neoforge-1.21.4"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._txt_mc_version.text() == "1.21.4"

    def test_inferred_modern_recipe_format(self, qt_app, tmp_path):
        """1.21.2+ templates should default to modern recipe format."""
        tpl = tmp_path / "fabric-1.21.2"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._cmb_recipe_format.currentText() == "Modern (>= 1.21.2)"

    def test_inferred_legacy_recipe_format(self, qt_app, tmp_path):
        """1.20.x templates should default to legacy_1_20 recipe format."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._cmb_recipe_format.currentText() == "Legacy (<= 1.20.4)"

    def test_existing_values_loaded(self, qt_app, tmp_path):
        """Editing an existing descriptor should populate all form fields."""
        tpl = tmp_path / "mymod-template"
        tpl.mkdir()
        data = {
            "loader": "neoforge",
            "minecraft_version": "1.21.2",
            "recipe_format": "modern_1_21",
            "recipe_folder": "recipe",
            "jar_loader_suffix": "neoforge-custom",
        }
        (tpl / "modsmith-template.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._cmb_loader.currentText() == "neoforge"
        assert dlg._txt_mc_version.text() == "1.21.2"
        assert dlg._cmb_recipe_format.currentText() == "Modern (>= 1.21.2)"
        assert dlg._cmb_recipe_folder.currentText() == "recipe"
        assert dlg._txt_jar_suffix.text() == "neoforge-custom"

    def test_existing_values_loaded_recipes(self, qt_app, tmp_path):
        """Editing an existing descriptor with recipe_folder 'recipes' loads 'recipes'."""
        tpl = tmp_path / "mymod-template-recipes"
        tpl.mkdir()
        data = {
            "loader": "forge",
            "minecraft_version": "1.20.1",
            "recipe_format": "legacy_1_20",
            "recipe_folder": "recipes",
            "jar_loader_suffix": "forge",
        }
        (tpl / "modsmith-template.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._cmb_recipe_folder.currentText() == "recipes"

    def test_editing_mc_version_updates_defaults(self, qt_app, tmp_path):
        """Editing the Minecraft Version field updates recipe format and recipe folder defaults."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg._cmb_recipe_format.currentText() == "Legacy (<= 1.20.4)"
        assert dlg._cmb_recipe_folder.currentText() == "recipes"

        # Change version to a 1.21.4 version and trigger editing finished
        dlg._txt_mc_version.setText("1.21.4")
        dlg._on_mc_version_editing_finished()

        assert dlg._cmb_recipe_format.currentText() == "Modern (>= 1.21.2)"
        assert dlg._cmb_recipe_folder.currentText() == "recipe"

    def test_descriptor_path_property(self, qt_app, tmp_path):
        """descriptor_path should point to modsmith-template.json inside template folder."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        assert dlg.descriptor_path == tpl / "modsmith-template.json"


@pytestmark_gui
class TestDescriptorDialogSave:
    """Test that _on_save writes a valid JSON descriptor."""

    def test_save_writes_json(self, qt_app, tmp_path):
        """Calling _on_save with valid fields should create the descriptor JSON."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)

        # Fields are already pre-populated by inference; call save directly
        dlg._on_save()

        desc = tpl / "modsmith-template.json"
        assert desc.exists(), "descriptor file was not written"
        data = json.loads(desc.read_text(encoding="utf-8"))
        assert data["loader"] == "forge"
        assert data["minecraft_version"] == "1.20.1"
        assert data["recipe_format"] == RECIPE_FORMAT_LEGACY
        assert data["recipe_folder"] == "recipes"
        assert data["jar_loader_suffix"] == "forge"

    def test_save_preserves_advanced_fields(self, qt_app, tmp_path):
        """Saving via dialog should not delete advanced fields like metadata_files."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        existing = {
            "loader": "forge",
            "minecraft_version": "1.20.1",
            "recipe_format": "legacy_1_20",
            "recipe_folder": "recipes",
            "jar_loader_suffix": "forge",
            "metadata_files": ["src/main/resources/META-INF/mods.toml"],
            "java_mod_import": "net.minecraftforge.fml.common.Mod",
            "uses_generated_metadata": False,
        }
        (tpl / "modsmith-template.json").write_text(json.dumps(existing), encoding="utf-8")

        dlg = TemplateDescriptorDialog(template_path=tpl)
        dlg._on_save()

        data = json.loads((tpl / "modsmith-template.json").read_text(encoding="utf-8"))
        # Advanced fields must be preserved
        assert data.get("metadata_files") == ["src/main/resources/META-INF/mods.toml"]
        assert data.get("java_mod_import") == "net.minecraftforge.fml.common.Mod"
        assert data.get("uses_generated_metadata") is False

    def test_save_produces_indent2_json(self, qt_app, tmp_path):
        """Written JSON must use 2-space indentation."""
        tpl = tmp_path / "fabric-1.21.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        dlg._on_save()

        raw = (tpl / "modsmith-template.json").read_text(encoding="utf-8")
        assert '  "loader"' in raw, "Expected 2-space indented JSON"

    def test_descriptor_loadable_by_backend(self, qt_app, tmp_path):
        """Written descriptor must be loadable by load_template_descriptor."""
        from modsmith.config import load_template_descriptor

        tpl = tmp_path / "neoforge-1.21.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        dlg._on_save()

        desc = load_template_descriptor(tpl)
        assert desc is not None
        assert desc.loader == "neoforge"
        assert desc.minecraft_version == "1.21.1"
        assert desc.recipe_format == "transitional_1_20_5_to_1_21_1"

    def test_validation_blocks_empty_minecraft_version(self, qt_app, tmp_path, monkeypatch):
        """Save with blank Minecraft Version should be blocked (warning shown)."""
        tpl = tmp_path / "forge-1.20.1"
        tpl.mkdir()
        dlg = TemplateDescriptorDialog(template_path=tpl)
        dlg._txt_mc_version.setText("")  # clear version

        warned = []
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.warning",
            lambda *a, **kw: warned.append(True) or QMessageBox.StandardButton.Ok,
        )
        dlg._on_save()

        assert warned, "Expected a warning dialog when minecraft_version is empty"
        assert not (tpl / "modsmith-template.json").exists(), (
            "Descriptor should NOT be written when validation fails"
        )


@pytestmark_gui
class TestTemplatesScreenDescriptor:
    """Smoke tests for Templates screen descriptor integration."""

    def test_screen_instantiation(self, qt_app, mock_dialogs):
        """TemplatesScreen should construct without raising."""
        screen = TemplatesScreen()
        assert screen is not None

    def test_create_descriptor_button_present(self, qt_app, mock_dialogs):
        """Create/Edit Descriptor button should exist."""
        screen = TemplatesScreen()
        assert hasattr(screen, "_btn_descriptor")
        assert screen._btn_descriptor is not None

    def test_open_descriptor_json_button_present(self, qt_app, mock_dialogs):
        """Open Descriptor JSON button should exist."""
        screen = TemplatesScreen()
        assert hasattr(screen, "_btn_open_descriptor_json")
        assert screen._btn_open_descriptor_json is not None

    def test_initial_button_label_is_create(self, qt_app, mock_dialogs):
        """Without a selection the button should read 'Create Descriptor'."""
        screen = TemplatesScreen()
        assert screen._btn_descriptor.text() == "Create Descriptor"

    def test_descriptor_detail_path_field_exists(self, qt_app, mock_dialogs):
        """Detail area should include a descriptor path field."""
        screen = TemplatesScreen()
        assert hasattr(screen, "_txt_detail_descriptor_path")

    def test_no_selection_warning_on_descriptor_click(
        self, qt_app, mock_dialogs, monkeypatch
    ):
        """Clicking Create Descriptor with no row selected should warn."""
        screen = TemplatesScreen()
        warned = []
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.warning",
            lambda *a, **kw: warned.append(True) or QMessageBox.StandardButton.Ok,
        )
        screen._on_descriptor()
        assert warned, "Expected a warning when no template is selected"

    def test_no_selection_warning_on_open_json_click(
        self, qt_app, mock_dialogs, monkeypatch
    ):
        """Clicking Open Descriptor JSON with no row selected should warn."""
        screen = TemplatesScreen()
        warned = []
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.warning",
            lambda *a, **kw: warned.append(True) or QMessageBox.StandardButton.Ok,
        )
        screen._on_open_descriptor_json()
        assert warned, "Expected a warning when no template is selected"

    def test_refresh_after_descriptor_create(self, qt_app, mock_dialogs, tmp_path, monkeypatch):
        """Creating a descriptor via dialog should cause the screen to refresh."""
        # Point MODTEMPLATES at tmp_path
        tpl_dir = tmp_path / "MODTEMPLATES"
        tpl_dir.mkdir()
        tpl = tpl_dir / "forge-1.20.1"
        tpl.mkdir()
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

        screen = TemplatesScreen()
        # The table should have 1 row (missing descriptor → ERROR)
        assert screen._table.rowCount() == 1
        status_item = screen._table.item(0, 6)  # Status column
        assert status_item.text() == "ERROR"

        # Simulate creating the descriptor manually (as dialog would)
        desc = tpl / "modsmith-template.json"
        desc.write_text(
            json.dumps({
                "loader": "forge",
                "minecraft_version": "1.20.1",
                "recipe_format": "legacy_1_20",
                "recipe_folder": "recipes",
                "jar_loader_suffix": "forge",
            }),
            encoding="utf-8",
        )

        # Also create a fake gradle-wrapper.jar so the template clears all errors
        wrapper_dir = tpl / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True)
        (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"fake")
        (tpl / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        (tpl / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")

        screen.refresh()

        status_item = screen._table.item(0, 6)
        assert status_item.text() == "OK", (
            f"Expected OK after descriptor creation, got: {status_item.text()}"
        )

    def test_templates_screen_empty_state_and_disabled_controls(self, qt_app, mock_dialogs, tmp_path, monkeypatch):
        """When MODTEMPLATES is empty, the table, detail group, and descriptor buttons should be hidden, and the empty state label shown."""
        tpl_dir = tmp_path / "MODTEMPLATES"
        tpl_dir.mkdir()
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

        screen = TemplatesScreen()

        # Verify hidden widgets
        assert screen._table.isHidden()
        assert screen._detail_group.isHidden()
        assert screen._btn_descriptor.isHidden()
        assert screen._btn_open_descriptor_json.isHidden()

        # Verify empty state label is visible and contains expected text
        assert not screen._lbl_empty_state.isHidden()
        assert "No templates found in:" in screen._lbl_empty_state.text()
        assert "Use Add Template to import a template folder." in screen._lbl_empty_state.text()

    def test_templates_screen_missing_state(self, qt_app, mock_dialogs, tmp_path, monkeypatch):
        """When MODTEMPLATES does not exist, the screen should show missing state warning."""
        # MODTEMPLATES does not exist
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

        screen = TemplatesScreen()

        # Verify hidden widgets
        assert screen._table.isHidden()
        assert screen._detail_group.isHidden()
        assert screen._btn_descriptor.isHidden()
        assert screen._btn_open_descriptor_json.isHidden()

        # Verify missing state label is visible and contains expected text
        assert not screen._lbl_empty_state.isHidden()
        assert "Templates folder does not exist:" in screen._lbl_empty_state.text()

    def test_templates_screen_non_empty_shows_controls_and_disabled_initially(self, qt_app, mock_dialogs, tmp_path, monkeypatch):
        """When MODTEMPLATES is non-empty, the table, details, and buttons are visible but disabled initially."""
        tpl_dir = tmp_path / "MODTEMPLATES"
        tpl_dir.mkdir()
        tpl = tpl_dir / "forge-1.20.1"
        tpl.mkdir()
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

        screen = TemplatesScreen()

        # Verify visible widgets
        assert not screen._table.isHidden()
        assert not screen._detail_group.isHidden()
        assert not screen._btn_descriptor.isHidden()
        assert not screen._btn_open_descriptor_json.isHidden()
        assert screen._lbl_empty_state.isHidden()

        # Verify buttons and detail group are disabled initially (no selection)
        assert not screen._btn_descriptor.isEnabled()
        assert not screen._btn_open_descriptor_json.isEnabled()
        assert not screen._detail_group.isEnabled()
