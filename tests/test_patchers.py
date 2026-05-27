"""Unit tests for mod loaders file patchers."""

import unittest
import tempfile
import json
from pathlib import Path

from modsmith.patchers import get_patcher, BasePatcher
from modsmith.patchers.base import BasePatcher as BasePatcherClass
from modsmith.patchers.forge import ForgePatcher
from modsmith.patchers.neoforge import NeoForgePatcher
from modsmith.patchers.fabric import FabricPatcher
from modsmith.context import ModContext, TargetContext
from modsmith.config import ModConfig, TargetConfig


class TestPatcherSelection(unittest.TestCase):
    """Tests for get_patcher loader selection."""

    def test_get_patcher_valid(self):
        self.assertIsInstance(get_patcher("forge"), ForgePatcher)
        self.assertIsInstance(get_patcher("neoforge"), NeoForgePatcher)
        self.assertIsInstance(get_patcher("fabric"), FabricPatcher)
        self.assertIsInstance(get_patcher("FORGE"), ForgePatcher)

    def test_get_patcher_invalid_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_patcher("invalid_loader")


class TestBasePatcherHelpers(unittest.TestCase):
    """Tests for BasePatcher shared helper methods."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_replace_in_file(self):
        test_file = self.path / "test.txt"
        test_file.write_text("hello examplemod world\nExample Mod is here", encoding="utf-8")
        
        replacements = {
            "examplemod": "my_mod_id",
            "Example Mod": "My Mod Name",
        }
        res = BasePatcherClass.replace_in_file(test_file, replacements)
        self.assertTrue(res)
        
        content = test_file.read_text(encoding="utf-8")
        self.assertEqual(content, "hello my_mod_id world\nMy Mod Name is here")

    def test_replace_in_file_missing_returns_false(self):
        res = BasePatcherClass.replace_in_file(self.path / "non_existent.txt", {"a": "b"})
        self.assertFalse(res)

    def test_set_or_replace_gradle_property(self):
        props_file = self.path / "gradle.properties"
        props_file.write_text("mod_id=old_id\n#some comment\nminecraft_version=1.20.1\n", encoding="utf-8")
        
        # Replace existing property
        res = BasePatcherClass.set_or_replace_gradle_property(props_file, "mod_id", "new_id")
        self.assertTrue(res)
        
        # Append new property
        res = BasePatcherClass.set_or_replace_gradle_property(props_file, "mod_license", "MIT")
        self.assertTrue(res)

        content = props_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertIn("mod_id=new_id", lines)
        self.assertIn("mod_license=MIT", lines)
        self.assertIn("#some comment", lines)

    def test_patch_build_gradle_archive_name_insert(self):
        bg = self.path / "build.gradle"
        bg.write_text("plugins {\n    id 'java'\n}\n", encoding="utf-8")
        
        res = BasePatcherClass.patch_build_gradle_archive_name(bg, "easypeasygunpowder-1.20.1-forge")
        self.assertTrue(res)
        
        content = bg.read_text(encoding="utf-8")
        self.assertIn('archivesName = "easypeasygunpowder-1.20.1-forge"', content)

    def test_patch_build_gradle_archive_name_replace(self):
        bg = self.path / "build.gradle"
        bg.write_text("base {\n    archivesName = 'old-name'\n}\n", encoding="utf-8")
        
        res = BasePatcherClass.patch_build_gradle_archive_name(bg, "new-name")
        self.assertTrue(res)
        
        content = bg.read_text(encoding="utf-8")
        self.assertIn('archivesName = "new-name"', content)


class TestForgePatcher(unittest.TestCase):
    """Tests for ForgePatcher."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_forge_patcher_success(self):
        # Setup files
        gradle_props = self.path / "gradle.properties"
        gradle_props.write_text("forge_version=47.1.0\nminecraft_version=1.20\n", encoding="utf-8")
        
        build_gradle = self.path / "build.gradle"
        build_gradle.write_text("version = '0.0.1'\ngroup = 'com.example'\nbase {\n    archivesName = 'examplemod'\n}\n", encoding="utf-8")
        
        mods_toml_dir = self.path / "src" / "main" / "resources" / "META-INF"
        mods_toml_dir.mkdir(parents=True)
        mods_toml = mods_toml_dir / "mods.toml"
        mods_toml.write_text("modId=\"examplemod\"\ndisplayName=\"Example Mod\"\nauthors=\"YourNameHere\"\ndescription=\"Example mod description...\"\n", encoding="utf-8")

        config = ModConfig(
            mod_id="easypeasygunpowder",
            mod_name="Easy Peasy Gunpowder",
            mod_version="1.2.3",
            group="com.ardaryusz.easypeasygunpowder",
            package="com.ardaryusz.easypeasygunpowder",
            authors="Ardaryusz",
            license="MIT",
            description="Allows crafting gunpowder easily",
            output_repo_name="easypeasygunpowder",
            targets=[],
            main_class="EasyPeasyGunpowder",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="forge",
            template="forge_template",
            branch="main",
            mc_range="1.20.1",
            minecraft_version="1.20.1",
            minecraft_version_range="[1.20, 1.21)"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)
        
        patcher = ForgePatcher()
        warnings = patcher.patch(self.path, ctx)
        
        self.assertEqual(warnings, [])
        
        # Check gradle.properties
        props = gradle_props.read_text(encoding="utf-8")
        self.assertIn("minecraft_version=1.20.1", props)
        self.assertIn("mod_id=easypeasygunpowder", props)
        self.assertIn("mod_authors=Ardaryusz", props)
        # Verify forge_version was untouched
        self.assertIn("forge_version=47.1.0", props)
        
        # Check build.gradle
        bg_content = build_gradle.read_text(encoding="utf-8")
        self.assertIn('archivesName = "easypeasygunpowder-1.20.1-forge"', bg_content)
        self.assertIn('version = "1.2.3"', bg_content)
        self.assertIn('group = "com.ardaryusz.easypeasygunpowder"', bg_content)
        
        # Check mods.toml
        toml_content = mods_toml.read_text(encoding="utf-8")
        self.assertIn('modId="easypeasygunpowder"', toml_content)
        self.assertIn('displayName="Easy Peasy Gunpowder"', toml_content)
        self.assertIn('authors="Ardaryusz"', toml_content)


class TestNeoForgePatcher(unittest.TestCase):
    """Tests for NeoForgePatcher."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_neoforge_patcher_success(self):
        gradle_props = self.path / "gradle.properties"
        gradle_props.write_text("neo_version=21.0.0\n", encoding="utf-8")
        
        build_gradle = self.path / "build.gradle"
        build_gradle.write_text("base {\n    archivesName = 'examplemod'\n}\n", encoding="utf-8")
        
        mods_toml_dir = self.path / "src" / "main" / "resources" / "META-INF"
        mods_toml_dir.mkdir(parents=True)
        mods_toml = mods_toml_dir / "neoforge.mods.toml"
        mods_toml.write_text("modId=\"examplemod\"\ndisplayName=\"Example Mod\"\n", encoding="utf-8")

        config = ModConfig(
            mod_id="easypeasygunpowder",
            mod_name="Easy Peasy Gunpowder",
            mod_version="1.2.3",
            group="com.ardaryusz.easypeasygunpowder",
            package="com.ardaryusz.easypeasygunpowder",
            authors="Ardaryusz",
            license="MIT",
            description="Allows crafting gunpowder easily",
            output_repo_name="easypeasygunpowder",
            targets=[],
            main_class="EasyPeasyGunpowder",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="neoforge",
            template="neoforge_template",
            branch="main",
            mc_range="1.21",
            minecraft_version="1.21"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)
        
        patcher = NeoForgePatcher()
        warnings = patcher.patch(self.path, ctx)
        self.assertEqual(warnings, [])
        
        # Check gradle.properties
        props = gradle_props.read_text(encoding="utf-8")
        self.assertIn("mod_id=easypeasygunpowder", props)
        self.assertIn("neo_version=21.0.0", props)
        
        # Check build.gradle
        bg_content = build_gradle.read_text(encoding="utf-8")
        self.assertIn('archivesName = "easypeasygunpowder-1.21-neoforge"', bg_content)
        
        # Check neoforge.mods.toml
        toml_content = mods_toml.read_text(encoding="utf-8")
        self.assertIn('modId="easypeasygunpowder"', toml_content)


class TestFabricPatcher(unittest.TestCase):
    """Tests for FabricPatcher."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fabric_patcher_success(self):
        gradle_props = self.path / "gradle.properties"
        gradle_props.write_text("archives_base_name=examplemod\n", encoding="utf-8")
        
        build_gradle = self.path / "build.gradle"
        build_gradle.write_text("archivesBaseName = 'examplemod'\n", encoding="utf-8")
        
        json_dir = self.path / "src" / "main" / "resources"
        json_dir.mkdir(parents=True)
        fabric_json = json_dir / "fabric.mod.json"
        
        initial_json = {
            "schemaVersion": 1,
            "id": "examplemod",
            "version": "0.1.0",
            "name": "Example Mod",
            "description": "desc",
            "authors": ["Me"],
            "contact": {
                "homepage": "http://example.com"
            },
            "license": "MIT",
            "environment": "*"
        }
        with open(fabric_json, "w", encoding="utf-8") as f:
            json.dump(initial_json, f)

        config = ModConfig(
            mod_id="easypeasygunpowder",
            mod_name="Easy Peasy Gunpowder",
            mod_version="1.2.3",
            group="com.ardaryusz.easypeasygunpowder",
            package="com.ardaryusz.easypeasygunpowder",
            authors="Ardaryusz",
            license="MIT",
            description="Allows crafting gunpowder easily",
            output_repo_name="easypeasygunpowder",
            targets=[],
            main_class="EasyPeasyGunpowder",
            homepage="http://homepage.com",
            issue_tracker="http://issues.com"
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="fabric",
            template="fabric_template",
            branch="main",
            mc_range="1.20.1",
            minecraft_version="1.20.1"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)
        
        patcher = FabricPatcher()
        warnings = patcher.patch(self.path, ctx)
        self.assertEqual(warnings, [])
        
        # Check gradle.properties
        props = gradle_props.read_text(encoding="utf-8")
        self.assertIn("archives_base_name=easypeasygunpowder-1.20.1-fabric", props)
        
        # Check build.gradle
        bg_content = build_gradle.read_text(encoding="utf-8")
        self.assertIn('archivesBaseName = "easypeasygunpowder-1.20.1-fabric"', bg_content)
        
        # Check fabric.mod.json
        with open(fabric_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.assertEqual(data["id"], "easypeasygunpowder")
        self.assertEqual(data["version"], "1.2.3")
        self.assertEqual(data["name"], "Easy Peasy Gunpowder")
        # Ensure unknown fields like environment are preserved
        self.assertEqual(data["environment"], "*")
        self.assertEqual(data["contact"]["homepage"], "http://homepage.com")
        self.assertEqual(data["contact"]["issues"], "http://issues.com")


class TestTargetContextVersionLabel(unittest.TestCase):
    """Tests for TargetContext.mc_version_label and archive_base_name."""

    def _make_ctx(self, mc_range: str, minecraft_version: str = "",
                  minecraft_version_range: str = "") -> TargetContext:
        config = ModConfig(
            mod_id="gunpowdermod",
            mod_name="Gunpowder Mod",
            mod_version="1.0.1",
            group="com.example",
            package="com.example",
            authors="Dev",
            license="MIT",
            description="Desc",
            output_repo_name="gunpowdermod",
            targets=[],
            main_class="GunpowderMod",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="forge",
            template="forge_template",
            branch="main",
            mc_range=mc_range,
            minecraft_version=minecraft_version,
            minecraft_version_range=minecraft_version_range,
        )
        return TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

    def test_exact_single_version(self):
        """Exact minecraft_version, no range → use minecraft_version verbatim."""
        ctx = self._make_ctx(
            mc_range="1.20",
            minecraft_version="1.20.1",
            minecraft_version_range="[1.20.1,1.20.1]",
        )
        self.assertEqual(ctx.mc_version_label, "1.20.1")

    def test_exact_version_no_range_field(self):
        """minecraft_version set, no minecraft_version_range → use minecraft_version."""
        ctx = self._make_ctx(
            mc_range="1.20",
            minecraft_version="1.20.1",
            minecraft_version_range="",
        )
        self.assertEqual(ctx.mc_version_label, "1.20.1")

    def test_inclusive_custom_range(self):
        """[from,through] inclusive range → 'from-through'."""
        ctx = self._make_ctx(
            mc_range="1.21",
            minecraft_version="1.21.2",
            minecraft_version_range="[1.21.2,1.21.11]",
        )
        self.assertEqual(ctx.mc_version_label, "1.21.2-1.21.11")

    def test_exclusive_range_falls_back_to_minecraft_version(self):
        """Maven half-open range like [1.20,1.21) → not inclusive, use minecraft_version."""
        ctx = self._make_ctx(
            mc_range="1.20",
            minecraft_version="1.20.4",
            minecraft_version_range="[1.20,1.21)",
        )
        # Does not end with ']', so falls back to minecraft_version
        self.assertEqual(ctx.mc_version_label, "1.20.4")

    def test_fallback_to_mc_range_when_no_minecraft_version(self):
        """No minecraft_version set → fall back to mc_range."""
        ctx = self._make_ctx(mc_range="1.21", minecraft_version="")
        self.assertEqual(ctx.mc_version_label, "1.21")

    def test_archive_base_name_uses_version_label(self):
        """archive_base_name must include the full version label, not truncated mc_range."""
        ctx = self._make_ctx(
            mc_range="1.20",
            minecraft_version="1.20.1",
            minecraft_version_range="",
        )
        self.assertEqual(ctx.archive_base_name, "gunpowdermod-1.20.1-forge")

    def test_expected_jar_name(self):
        """expected_jar_name combines archive_base_name with mod_version."""
        ctx = self._make_ctx(
            mc_range="1.20",
            minecraft_version="1.20.1",
            minecraft_version_range="",
        )
        self.assertEqual(ctx.expected_jar_name, "gunpowdermod-1.20.1-forge-1.0.1.jar")

    def test_range_archive_base_name(self):
        """Inclusive range produces 'from-through' segment in archive_base_name."""
        ctx = self._make_ctx(
            mc_range="1.21",
            minecraft_version="1.21.2",
            minecraft_version_range="[1.21.2,1.21.11]",
        )
        self.assertEqual(ctx.archive_base_name, "gunpowdermod-1.21.2-1.21.11-forge")


if __name__ == "__main__":
    unittest.main()
