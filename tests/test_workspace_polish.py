from __future__ import annotations

import sys
import json
from pathlib import Path
import pytest

from modsmith_gui.workspace_utils import (
    derive_pascal_case,
    derive_mc_range,
    make_exact_patch_range,
    make_same_minor_range,
    make_inclusive_range,
    parse_version_range,
    infer_from_template,
)

# ---------------------------------------------------------------------------
# Pure unit tests (no Qt / GUI dependencies needed)
# ---------------------------------------------------------------------------

def test_derive_pascal_case() -> None:
    assert derive_pascal_case("Gunpowder Mod") == "GunpowderMod"
    assert derive_pascal_case("Easy Peasy Gunpowder") == "EasyPeasyGunpowder"
    assert derive_pascal_case("1 Cool Mod") == "CoolMod"
    assert derive_pascal_case("123") == "ExampleMod"
    assert derive_pascal_case("") == "ExampleMod"
    assert derive_pascal_case("!@#") == "ExampleMod"
    assert derive_pascal_case("cool_mod_2") == "CoolMod2"


def test_derive_mc_range() -> None:
    assert derive_mc_range("1.20.1") == "1.20"
    assert derive_mc_range("1.21.1") == "1.21"
    assert derive_mc_range("1.20") == "1.20"
    assert derive_mc_range("1") == "1"


def test_make_exact_patch_range() -> None:
    assert make_exact_patch_range("1.20.1") == "[1.20.1,1.20.2)"
    assert make_exact_patch_range("1.21") == "[1.21,1.21.1)"


def test_make_same_minor_range() -> None:
    assert make_same_minor_range("1.20.1") == "[1.20.1,1.21)"
    assert make_same_minor_range("1.21") == "[1.21,1.22)"


def test_make_inclusive_range() -> None:
    assert make_inclusive_range("1.20.1", "1.20.4") == "[1.20.1,1.20.4]"


def test_parse_version_range() -> None:
    # Exact patch case
    assert parse_version_range("[1.20.1,1.20.2)", "1.20.1") == ("Exact patch version only", "", "")
    # Same minor case
    assert parse_version_range("[1.20.1,1.21)", "1.20.1") == ("Same minor version", "", "")
    # Inclusive custom range cases
    assert parse_version_range("[1.20.1,1.20.4]", "1.20.1") == ("Inclusive custom range", "1.20.1", "1.20.4")
    # Clean bracket fallback cases
    assert parse_version_range("[1.20.1,1.20.4)", "1.20.1") == ("Inclusive custom range", "1.20.1", "1.20.4")
    assert parse_version_range("1.20.1", "1.20.1") == ("Inclusive custom range", "1.20.1", "1.20.1")
    assert parse_version_range("", "1.20.1") == ("Exact patch version only", "", "")


def test_infer_from_template(tmp_path: Path) -> None:
    # Inference from template name prefix & pattern
    res = infer_from_template("forge-1.20.1", tmp_path)
    assert res["loader"] == "forge"
    assert res["minecraft_version"] == "1.20.1"
    assert res["branch"] == "forge-1.20.1"
    assert res["mc_range"] == "1.20"

    # Fabric fallback
    res = infer_from_template("fabric-1.21.2-template", tmp_path)
    assert res["loader"] == "fabric"
    assert res["minecraft_version"] == "1.21.2"
    assert res["branch"] == "fabric-1.21.2"
    assert res["mc_range"] == "1.21"

    # Template with descriptor file
    t_dir = tmp_path / "custom-template"
    t_dir.mkdir()
    desc_path = t_dir / "modsmith-template.json"
    desc_data = {
        "loader": "neoforge",
        "minecraft_version": "1.20.4"
    }
    desc_path.write_text(json.dumps(desc_data), encoding="utf-8")

    res = infer_from_template("custom-template", tmp_path)
    assert res["loader"] == "neoforge"
    assert res["minecraft_version"] == "1.20.4"
    assert res["branch"] == "neoforge-1.20.4"
    assert res["mc_range"] == "1.20"


# ---------------------------------------------------------------------------
# PySide6 GUI Integration & Smoke tests (Skipped if GUI is unavailable)
# ---------------------------------------------------------------------------

try:
    from PySide6.QtWidgets import QApplication, QMessageBox, QComboBox
    from modsmith_gui.screens.workspace import WorkspaceScreen
    from modsmith_gui.widgets.log_panel import LogPanel
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 GUI packages are not installed or unavailable"
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def mock_qt_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )


def test_workspace_screen_columns(qt_app) -> None:
    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Verify column count and exact header labels list
    assert screen._table.columnCount() == 7
    headers = [
        screen._table.horizontalHeaderItem(i).text()
        for i in range(screen._table.columnCount())
    ]
    assert headers == ["Loader", "Template", "Branch", "MC Version", "Compatibility", "From", "Through"]

    screen.deleteLater()
    log_panel.deleteLater()


def test_workspace_screen_fields_hidden(qt_app) -> None:
    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Verify hidden/removed fields are not GUI attributes of WorkspaceScreen
    assert not hasattr(screen, "_txt_main_class")
    assert not hasattr(screen, "_txt_package")
    assert not hasattr(screen, "_txt_output_repo_name")

    screen.deleteLater()
    log_panel.deleteLater()


def test_workspace_defaults_and_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qt_app) -> None:
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    # Setup a mock templates directory
    tpl_dir = tmp_path / "MODTEMPLATES"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "forge-1.20.1").mkdir()

    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Fill out visible GUI forms
    screen._txt_mod_id.setText("powderplay")
    screen._txt_mod_name.setText("Gunpowder Mod")
    screen._txt_group.setText("com.example.powder")
    screen._txt_mod_version.setText("1.0.2")
    screen._txt_authors.setText("developer_name")
    screen._txt_description.setPlainText("This is a simple mod description.")

    # Set up target
    assert screen._table.rowCount() == 1
    # Loader
    loader_combo = screen._table.cellWidget(0, 0)
    assert isinstance(loader_combo, QComboBox)
    loader_combo.setCurrentText("forge")

    # Template (should auto-populate in dropdown list)
    tpl_combo = screen._table.cellWidget(0, 1)
    assert isinstance(tpl_combo, QComboBox)
    assert "forge-1.20.1" in [tpl_combo.itemText(i) for i in range(tpl_combo.count())]
    tpl_combo.setCurrentText("forge-1.20.1")

    # branch/mc_ver should be filled automatically via signals
    assert screen._table.item(0, 2).text() == "forge-1.20.1"
    assert screen._table.item(0, 3).text() == "1.20.1"

    # Compatibility combo
    compat_combo = screen._table.cellWidget(0, 4)
    assert isinstance(compat_combo, QComboBox)
    compat_combo.setCurrentText("Exact patch version only")

    # Verify From and Through are disabled/read-only initially
    from_item = screen._table.item(0, 5)
    through_item = screen._table.item(0, 6)
    from PySide6.QtCore import Qt
    assert not (from_item.flags() & Qt.ItemFlag.ItemIsEditable)
    assert not (through_item.flags() & Qt.ItemFlag.ItemIsEditable)

    # Toggle to custom range
    compat_combo.setCurrentText("Inclusive custom range")
    assert from_item.flags() & Qt.ItemFlag.ItemIsEditable
    assert through_item.flags() & Qt.ItemFlag.ItemIsEditable
    from_item.setText("1.20.1")
    through_item.setText("1.20.4")

    # Click Save Config
    screen._save_config()

    json_path = tmp_path / "WORKSPACE" / "DETAILS" / "modsmith.json"
    assert json_path.exists()

    # Read and parse config using core parser
    from modsmith.config import load_mod_config
    cfg = load_mod_config(json_path)

    # Core configuration verification
    assert cfg.mod_id == "powderplay"
    assert cfg.mod_name == "Gunpowder Mod"
    assert cfg.main_class == "GunpowderMod"
    assert cfg.package == "com.example.powder"
    assert cfg.output_repo_name == "GunpowderMod"

    assert len(cfg.targets) == 1
    t = cfg.targets[0]
    assert t.loader == "forge"
    assert t.template == "forge-1.20.1"
    assert t.branch == "forge-1.20.1"
    assert t.minecraft_version == "1.20.1"
    assert t.mc_range == "1.20"
    assert t.minecraft_version_range == "[1.20.1,1.20.4]"

    # Verify that Validate Config also passes
    screen._validate_config()

    screen.deleteLater()
    log_panel.deleteLater()


def test_loading_existing_custom_compatibility(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qt_app) -> None:
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    # Write existing modsmith.json
    config_dir = tmp_path / "WORKSPACE" / "DETAILS"
    config_dir.mkdir(parents=True)
    config_data = {
        "mod_id": "powderplay",
        "mod_name": "Gunpowder Mod",
        "main_class": "GunpowderMod",
        "mod_version": "1.0.2",
        "group": "com.example.powder",
        "package": "com.example.powder",
        "authors": "dev",
        "license": "MIT",
        "description": "test",
        "homepage": "",
        "issue_tracker": "",
        "output_repo_name": "GunpowderMod",
        "targets": [
            {
                "loader": "forge",
                "template": "forge-1.20.1",
                "branch": "forge-1.20.1",
                "mc_range": "1.20",
                "minecraft_version": "1.20.1",
                "minecraft_version_range": "[1.20.1,1.20.4]"
            }
        ]
    }
    (config_dir / "modsmith.json").write_text(json.dumps(config_data), encoding="utf-8")

    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Verify fields parsed on load
    assert screen._txt_mod_id.text() == "powderplay"
    assert screen._txt_group.text() == "com.example.powder"

    # Verify target row populated properly
    assert screen._table.rowCount() == 1
    loader_combo = screen._table.cellWidget(0, 0)
    assert loader_combo.currentText() == "forge"

    compat_combo = screen._table.cellWidget(0, 4)
    assert compat_combo.currentText() == "Inclusive custom range"

    assert screen._table.item(0, 5).text() == "1.20.1"
    assert screen._table.item(0, 6).text() == "1.20.4"

    screen.deleteLater()
    log_panel.deleteLater()
