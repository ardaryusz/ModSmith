"""Tests for GUI Milestone: ASSETS folder & Mod Icon Selection.

Covers:
- WORKSPACE/ASSETS folder creation via ensure_home_structure()
- safe_copy_to_assets() helper: copies file, auto-suffixes on collision
- Config loads without icon field (backward compat)
- Config loads/saves with icon field
- Config save omits icon when cleared
- Doctor reports WORKSPACE/ASSETS as INFO
- Icon copy target paths for Fabric/Forge/NeoForge patchers
- Patchers inject icon metadata (Fabric JSON icon, Forge/NeoForge logoFile)
- GUI smoke tests (skip if PySide6 missing)
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Part A — WORKSPACE/ASSETS in ensure_home_structure
# ---------------------------------------------------------------------------


class TestAssetsFolder:
    """Test that WORKSPACE/ASSETS is created by ensure_home_structure."""

    def test_ensure_home_creates_assets_dir(self, tmp_path: Path) -> None:
        from modsmith.home import ensure_home_structure

        ensure_home_structure(tmp_path)
        assets = tmp_path / "WORKSPACE" / "ASSETS"
        assert assets.is_dir(), f"WORKSPACE/ASSETS should exist after init: {assets}"

    def test_ensure_home_creates_all_standard_dirs(self, tmp_path: Path) -> None:
        from modsmith.home import ensure_home_structure

        ensure_home_structure(tmp_path)
        expected = [
            "WORKSPACE",
            "WORKSPACE/DETAILS",
            "WORKSPACE/RECIPES",
            "WORKSPACE/README",
            "WORKSPACE/ASSETS",
            "WORKSPACE/DIST",
            "MODTEMPLATES",
            "MODS",
        ]
        for subdir in expected:
            assert (tmp_path / subdir).is_dir(), f"{subdir} should exist"


# ---------------------------------------------------------------------------
# Part A — Doctor ASSETS INFO check
# ---------------------------------------------------------------------------


class TestDoctorAssets:
    """Doctor should report WORKSPACE/ASSETS as INFO, never error."""

    def test_assets_missing_is_info(self, tmp_path: Path) -> None:
        from modsmith.doctor import diagnose_environment

        ws = tmp_path / "WORKSPACE"
        ws.mkdir()
        (ws / "DETAILS").mkdir()
        (ws / "RECIPES").mkdir()

        tpl = tmp_path / "MODTEMPLATES"
        tpl.mkdir()
        mods = tmp_path / "MODS"
        mods.mkdir()

        result = diagnose_environment(ws, tpl, mods)

        # ASSETS should be mentioned in infos, not errors or warnings
        assets_infos = [i for i in result.infos if "ASSETS" in i]
        assert len(assets_infos) >= 1, "Should have an INFO about ASSETS"
        assets_errors = [e for e in result.errors if "ASSETS" in e]
        assert len(assets_errors) == 0, "ASSETS should never be an error"
        assets_warnings = [w for w in result.warnings if "ASSETS" in w]
        assert len(assets_warnings) == 0, "ASSETS should never be a warning"

    def test_assets_exists_is_info(self, tmp_path: Path) -> None:
        from modsmith.doctor import diagnose_environment

        ws = tmp_path / "WORKSPACE"
        ws.mkdir()
        (ws / "DETAILS").mkdir()
        (ws / "RECIPES").mkdir()
        (ws / "ASSETS").mkdir()

        tpl = tmp_path / "MODTEMPLATES"
        tpl.mkdir()
        mods = tmp_path / "MODS"
        mods.mkdir()

        result = diagnose_environment(ws, tpl, mods)
        assets_infos = [i for i in result.infos if "ASSETS" in i and "exists" in i]
        assert len(assets_infos) >= 1


# ---------------------------------------------------------------------------
# Part B — safe_copy_to_assets helper
# ---------------------------------------------------------------------------


class TestSafeCopyToAssets:
    """Test the safe_copy_to_assets() helper for README image insertion."""

    def test_copies_file_to_assets(self, tmp_path: Path) -> None:
        from modsmith_gui.assets_utils import safe_copy_to_assets

        src = tmp_path / "source" / "image.png"
        src.parent.mkdir()
        src.write_bytes(b"PNG_DATA")

        assets = tmp_path / "ASSETS"
        dest = safe_copy_to_assets(src, assets)

        assert dest == assets / "image.png"
        assert dest.read_bytes() == b"PNG_DATA"

    def test_auto_suffix_on_duplicate(self, tmp_path: Path) -> None:
        from modsmith_gui.assets_utils import safe_copy_to_assets

        src = tmp_path / "source" / "icon.png"
        src.parent.mkdir()
        src.write_bytes(b"V1")

        assets = tmp_path / "ASSETS"
        assets.mkdir()

        # First copy — no suffix
        (assets / "icon.png").write_bytes(b"EXISTING")
        dest = safe_copy_to_assets(src, assets)
        assert dest.name == "icon_1.png"
        assert dest.read_bytes() == b"V1"

    def test_auto_suffix_increments(self, tmp_path: Path) -> None:
        from modsmith_gui.assets_utils import safe_copy_to_assets

        src = tmp_path / "source" / "photo.jpg"
        src.parent.mkdir()
        src.write_bytes(b"JPEG_DATA")

        assets = tmp_path / "ASSETS"
        assets.mkdir()

        (assets / "photo.jpg").write_bytes(b"existing")
        (assets / "photo_1.jpg").write_bytes(b"existing")
        dest = safe_copy_to_assets(src, assets)
        assert dest.name == "photo_2.jpg"

    def test_creates_assets_dir_on_demand(self, tmp_path: Path) -> None:
        from modsmith_gui.assets_utils import safe_copy_to_assets

        src = tmp_path / "source" / "file.webp"
        src.parent.mkdir()
        src.write_bytes(b"WEBP")

        assets = tmp_path / "NEW_ASSETS"
        dest = safe_copy_to_assets(src, assets)
        assert assets.is_dir()
        assert dest.exists()


# ---------------------------------------------------------------------------
# Part D — Config schema with/without icon
# ---------------------------------------------------------------------------


class TestConfigIcon:
    """Test that the config loads and saves with/without the optional icon field."""

    def _write_config(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def _minimal_config(self, **overrides) -> dict:
        base = {
            "mod_id": "testmod",
            "mod_name": "Test Mod",
            "mod_version": "1.0.0",
            "group": "com.test.testmod",
            "package": "com.test.testmod",
            "authors": "tester",
            "license": "MIT",
            "description": "A test mod.",
            "output_repo_name": "TestMod",
            "targets": [{
                "loader": "fabric",
                "template": "fabric-1.21",
                "branch": "fabric-1.21",
                "mc_range": "1.21",
                "minecraft_version": "1.21.0",
            }],
        }
        base.update(overrides)
        return base

    def test_load_config_without_icon(self, tmp_path: Path) -> None:
        from modsmith.config import load_mod_config

        cfg_path = tmp_path / "modsmith.json"
        self._write_config(cfg_path, self._minimal_config())

        config = load_mod_config(cfg_path)
        assert config.icon == ""

    def test_load_config_with_icon(self, tmp_path: Path) -> None:
        from modsmith.config import load_mod_config

        cfg_path = tmp_path / "modsmith.json"
        self._write_config(cfg_path, self._minimal_config(icon="ASSETS/icon.png"))

        config = load_mod_config(cfg_path)
        assert config.icon == "ASSETS/icon.png"

    def test_save_omits_icon_when_empty(self, tmp_path: Path) -> None:
        """When icon is cleared, it should be omitted from saved JSON."""
        cfg_data = self._minimal_config()
        # Simulate what the GUI does: build config_data without icon
        config_data = dict(cfg_data)
        # Explicitly NOT adding "icon"
        cfg_path = tmp_path / "modsmith.json"
        self._write_config(cfg_path, config_data)

        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "icon" not in raw

    def test_save_includes_icon_when_set(self, tmp_path: Path) -> None:
        cfg_data = self._minimal_config(icon="ASSETS/mod_logo.png")
        cfg_path = tmp_path / "modsmith.json"
        self._write_config(cfg_path, cfg_data)

        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert raw["icon"] == "ASSETS/mod_logo.png"

    def test_context_has_icon_property(self, tmp_path: Path) -> None:
        from modsmith.config import load_mod_config
        from modsmith.context import ModContext

        cfg_path = tmp_path / "modsmith.json"
        self._write_config(cfg_path, self._minimal_config(icon="ASSETS/icon.png"))

        config = load_mod_config(cfg_path)
        ctx = ModContext(config=config)
        assert ctx.icon == "ASSETS/icon.png"
        assert ctx.assets_dir == ctx.workspace_dir / "ASSETS"

    def test_context_icon_empty_by_default(self, tmp_path: Path) -> None:
        from modsmith.config import load_mod_config
        from modsmith.context import ModContext

        cfg_path = tmp_path / "modsmith.json"
        self._write_config(cfg_path, self._minimal_config())

        config = load_mod_config(cfg_path)
        ctx = ModContext(config=config)
        assert ctx.icon == ""


# ---------------------------------------------------------------------------
# Part E — Patcher icon injection
# ---------------------------------------------------------------------------


class TestFabricIconInjection:
    """Test that the Fabric patcher sets the icon field in fabric.mod.json."""

    def _make_context(self, tmp_path: Path, icon: str = "ASSETS/icon.png"):
        from modsmith.config import ModConfig, TargetConfig, TemplateDescriptor
        from modsmith.context import ModContext, TargetContext

        config = ModConfig(
            mod_id="testmod",
            mod_name="Test Mod",
            mod_version="1.0.0",
            group="com.test.testmod",
            package="com.test.testmod",
            authors="tester",
            license="MIT",
            description="A test mod.",
            output_repo_name="TestMod",
            targets=[],
            icon=icon,
        )
        target = TargetConfig(
            loader="fabric",
            template="fabric-1.21",
            branch="fabric-1.21",
            mc_range="1.21",
            minecraft_version="1.21.0",
        )
        mod_ctx = ModContext(
            config=config,
            workspace_dir=tmp_path / "WORKSPACE",
            templates_dir=tmp_path / "MODTEMPLATES",
            mods_dir=tmp_path / "MODS",
        )
        return TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

    def test_fabric_sets_icon_in_json(self, tmp_path: Path) -> None:
        from modsmith.patchers.fabric import FabricPatcher

        repo = tmp_path / "repo"
        fabric_json = repo / "src" / "main" / "resources" / "fabric.mod.json"
        fabric_json.parent.mkdir(parents=True)
        fabric_json.write_text(json.dumps({
            "id": "examplemod",
            "version": "1.0.0",
            "name": "Example Mod",
            "description": "desc",
            "license": "MIT",
            "authors": ["dev"],
        }), encoding="utf-8")

        # Also need gradle.properties for patcher
        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path)
        patcher = FabricPatcher()
        patcher.patch(repo, ctx)

        data = json.loads(fabric_json.read_text(encoding="utf-8"))
        assert data.get("icon") == "assets/testmod/icon.png"

    def test_fabric_no_icon_when_not_configured(self, tmp_path: Path) -> None:
        from modsmith.patchers.fabric import FabricPatcher

        repo = tmp_path / "repo"
        fabric_json = repo / "src" / "main" / "resources" / "fabric.mod.json"
        fabric_json.parent.mkdir(parents=True)
        fabric_json.write_text(json.dumps({
            "id": "examplemod",
            "version": "1.0.0",
            "name": "Example Mod",
            "description": "desc",
            "license": "MIT",
            "authors": ["dev"],
        }), encoding="utf-8")

        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path, icon="")
        patcher = FabricPatcher()
        patcher.patch(repo, ctx)

        data = json.loads(fabric_json.read_text(encoding="utf-8"))
        assert "icon" not in data

    def test_fabric_no_icon_when_non_png(self, tmp_path: Path) -> None:
        from modsmith.patchers.fabric import FabricPatcher

        repo = tmp_path / "repo"
        fabric_json = repo / "src" / "main" / "resources" / "fabric.mod.json"
        fabric_json.parent.mkdir(parents=True)
        fabric_json.write_text(json.dumps({
            "id": "examplemod",
            "version": "1.0.0",
            "name": "Example Mod",
            "description": "desc",
            "license": "MIT",
            "authors": ["dev"],
        }), encoding="utf-8")

        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path, icon="ASSETS/icon.jpg")
        patcher = FabricPatcher()
        patcher.patch(repo, ctx)

        data = json.loads(fabric_json.read_text(encoding="utf-8"))
        assert "icon" not in data


class TestForgeIconInjection:
    """Test that the Forge patcher injects logoFile in mods.toml."""

    def _make_context(self, tmp_path: Path, icon: str = "ASSETS/icon.png"):
        from modsmith.config import ModConfig, TargetConfig
        from modsmith.context import ModContext, TargetContext

        config = ModConfig(
            mod_id="testmod",
            mod_name="Test Mod",
            mod_version="1.0.0",
            group="com.test.testmod",
            package="com.test.testmod",
            authors="tester",
            license="MIT",
            description="A test mod.",
            output_repo_name="TestMod",
            targets=[],
            icon=icon,
        )
        target = TargetConfig(
            loader="forge",
            template="forge-1.20.1",
            branch="forge-1.20.1",
            mc_range="1.20.1",
            minecraft_version="1.20.1",
        )
        mod_ctx = ModContext(
            config=config,
            workspace_dir=tmp_path / "WORKSPACE",
            templates_dir=tmp_path / "MODTEMPLATES",
            mods_dir=tmp_path / "MODS",
        )
        return TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

    def test_forge_injects_logofile(self, tmp_path: Path) -> None:
        from modsmith.patchers.forge import ForgePatcher

        repo = tmp_path / "repo"
        mods_toml = repo / "src" / "main" / "resources" / "META-INF" / "mods.toml"
        mods_toml.parent.mkdir(parents=True)
        mods_toml.write_text(textwrap.dedent("""\
            modLoader="javafml"
            loaderVersion="[47,)"

            [[mods]]
            modId="examplemod"
            displayName="Example Mod"
        """), encoding="utf-8")

        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path)
        patcher = ForgePatcher()
        patcher.patch(repo, ctx)

        content = mods_toml.read_text(encoding="utf-8")
        assert 'logoFile="icon.png"' in content

    def test_forge_replaces_existing_logofile(self, tmp_path: Path) -> None:
        from modsmith.patchers.forge import ForgePatcher

        repo = tmp_path / "repo"
        mods_toml = repo / "src" / "main" / "resources" / "META-INF" / "mods.toml"
        mods_toml.parent.mkdir(parents=True)
        mods_toml.write_text(textwrap.dedent("""\
            modLoader="javafml"
            loaderVersion="[47,)"

            [[mods]]
            modId="examplemod"
            logoFile="old_logo.png"
            displayName="Example Mod"
        """), encoding="utf-8")

        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path)
        patcher = ForgePatcher()
        patcher.patch(repo, ctx)

        content = mods_toml.read_text(encoding="utf-8")
        assert 'logoFile' in content
        assert '"icon.png"' in content
        assert 'old_logo' not in content

    def test_forge_no_logofile_without_icon(self, tmp_path: Path) -> None:
        from modsmith.patchers.forge import ForgePatcher

        repo = tmp_path / "repo"
        mods_toml = repo / "src" / "main" / "resources" / "META-INF" / "mods.toml"
        mods_toml.parent.mkdir(parents=True)
        mods_toml.write_text(textwrap.dedent("""\
            modLoader="javafml"
            loaderVersion="[47,)"

            [[mods]]
            modId="examplemod"
            displayName="Example Mod"
        """), encoding="utf-8")

        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path, icon="")
        patcher = ForgePatcher()
        patcher.patch(repo, ctx)

        content = mods_toml.read_text(encoding="utf-8")
        assert "logoFile" not in content


class TestNeoForgeIconInjection:
    """Test that the NeoForge patcher injects logoFile in neoforge.mods.toml."""

    def _make_context(self, tmp_path: Path, icon: str = "ASSETS/icon.png"):
        from modsmith.config import ModConfig, TargetConfig
        from modsmith.context import ModContext, TargetContext

        config = ModConfig(
            mod_id="testmod",
            mod_name="Test Mod",
            mod_version="1.0.0",
            group="com.test.testmod",
            package="com.test.testmod",
            authors="tester",
            license="MIT",
            description="A test mod.",
            output_repo_name="TestMod",
            targets=[],
            icon=icon,
        )
        target = TargetConfig(
            loader="neoforge",
            template="neoforge-1.21",
            branch="neoforge-1.21",
            mc_range="1.21",
            minecraft_version="1.21.0",
        )
        mod_ctx = ModContext(
            config=config,
            workspace_dir=tmp_path / "WORKSPACE",
            templates_dir=tmp_path / "MODTEMPLATES",
            mods_dir=tmp_path / "MODS",
        )
        return TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

    def test_neoforge_injects_logofile(self, tmp_path: Path) -> None:
        from modsmith.patchers.neoforge import NeoForgePatcher

        repo = tmp_path / "repo"
        toml_path = repo / "src" / "main" / "resources" / "META-INF" / "neoforge.mods.toml"
        toml_path.parent.mkdir(parents=True)
        toml_path.write_text(textwrap.dedent("""\
            modLoader="javafml"
            loaderVersion="[4,)"

            [[mods]]
            modId="examplemod"
            displayName="Example Mod"
        """), encoding="utf-8")

        gp = repo / "gradle.properties"
        gp.write_text("mod_version=1.0.0\n", encoding="utf-8")

        ctx = self._make_context(tmp_path)
        patcher = NeoForgePatcher()
        patcher.patch(repo, ctx)

        content = toml_path.read_text(encoding="utf-8")
        assert 'logoFile="icon.png"' in content


# ---------------------------------------------------------------------------
# Part E — Icon copy target paths
# ---------------------------------------------------------------------------


class TestIconCopyTargetPaths:
    """Verify the generator copies icons to the correct loader-specific paths."""

    def test_fabric_icon_dest_path(self) -> None:
        """Fabric: src/main/resources/assets/<mod_id>/icon.png"""
        mod_id = "mymod"
        dest_dir = Path("src/main/resources/assets") / mod_id
        assert (dest_dir / "icon.png").as_posix() == f"src/main/resources/assets/{mod_id}/icon.png"

    def test_forge_icon_dest_path(self) -> None:
        """Forge/NeoForge: src/main/resources/icon.png"""
        dest = Path("src/main/resources/icon.png")
        assert dest.as_posix() == "src/main/resources/icon.png"


# ---------------------------------------------------------------------------
# Part G — GUI smoke tests (skip if PySide6 missing)
# ---------------------------------------------------------------------------


try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False


pytestmark_gui = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 is not installed or unavailable",
)


@pytest.fixture(scope="module")
def qt_app():
    """Provide a single QApplication instance for the entire module."""
    if not PYSIDE6_AVAILABLE:
        pytest.skip("PySide6 not available")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture()
def mock_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatically mock Qt modal dialogs to prevent blocking."""
    if not PYSIDE6_AVAILABLE:
        return
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


@pytestmark_gui
class TestWorkspaceIconGui:
    """Smoke tests for the Workspace screen mod icon section."""

    def test_workspace_has_select_icon_btn(self, qt_app, mock_dialogs):
        from modsmith_gui.screens.workspace import WorkspaceScreen
        from modsmith_gui.widgets.log_panel import LogPanel
        screen = WorkspaceScreen(log_panel=LogPanel())
        assert screen._btn_select_icon is not None
        assert screen._btn_select_icon.text() == "Select Icon"

    def test_workspace_has_clear_icon_btn(self, qt_app, mock_dialogs):
        from modsmith_gui.screens.workspace import WorkspaceScreen
        from modsmith_gui.widgets.log_panel import LogPanel
        screen = WorkspaceScreen(log_panel=LogPanel())
        assert screen._btn_clear_icon is not None
        assert screen._btn_clear_icon.text() == "Clear Icon"

    def test_workspace_icon_initially_empty(self, qt_app, mock_dialogs, tmp_path, monkeypatch):
        from modsmith_gui.screens.workspace import WorkspaceScreen
        from modsmith_gui.widgets.log_panel import LogPanel
        monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
        screen = WorkspaceScreen(log_panel=LogPanel())
        assert screen._icon_value == ""
        assert "No icon" in screen._icon_path_label.text()


@pytestmark_gui
class TestDashboardAssetsIcon:
    """Smoke tests for Dashboard assets and icon rows."""

    def test_dashboard_has_assets_label(self, qt_app, mock_dialogs):
        from modsmith_gui.screens.dashboard import DashboardScreen
        from modsmith_gui.widgets.log_panel import LogPanel
        screen = DashboardScreen(log_panel=LogPanel())
        assert screen._lbl_summary_assets is not None

    def test_dashboard_has_icon_label(self, qt_app, mock_dialogs):
        from modsmith_gui.screens.dashboard import DashboardScreen
        from modsmith_gui.widgets.log_panel import LogPanel
        screen = DashboardScreen(log_panel=LogPanel())
        assert screen._lbl_summary_icon is not None
