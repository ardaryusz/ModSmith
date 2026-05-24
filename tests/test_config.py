"""Unit tests for modsmith.config.

Covers:
- load_mod_config: happy path with full valid fixture
- load_mod_config: missing required fields
- load_mod_config: invalid mod_id values
- load_mod_config: invalid package values
- load_mod_config: explicit main_class vs derivation from mod_name
- load_mod_config: invalid explicit main_class
- load_mod_config: targets validation (empty, unsupported loader, bad structure)
- load_mod_config: file not found / invalid JSON
- load_template_descriptor: valid descriptor
- load_template_descriptor: missing descriptor returns None
- load_template_descriptor: descriptor defaults
"""

import json
import unittest
from pathlib import Path

from modsmith.config import (
    ConfigError,
    ModConfig,
    TargetConfig,
    TemplateDescriptor,
    load_mod_config,
    load_template_descriptor,
)

# Absolute path to the fixtures directory.
_FIXTURES = Path(__file__).parent / "fixtures"
_VALID_CONFIG = _FIXTURES / "modsmith.json"
_FAKE_TEMPLATE = _FIXTURES / "fake_template"


class TestLoadModConfigHappyPath(unittest.TestCase):
    """load_mod_config should parse the canonical fixture without errors."""

    def setUp(self):
        self.cfg = load_mod_config(_VALID_CONFIG)

    def test_returns_mod_config(self):
        self.assertIsInstance(self.cfg, ModConfig)

    def test_mod_id(self):
        self.assertEqual(self.cfg.mod_id, "easypeasygunpowder")

    def test_mod_name(self):
        self.assertEqual(self.cfg.mod_name, "Easy Peasy Gunpowder")

    def test_mod_version(self):
        self.assertEqual(self.cfg.mod_version, "1.1.0")

    def test_group(self):
        self.assertEqual(self.cfg.group, "com.ardaryusz.easypeasygunpowder")

    def test_package(self):
        self.assertEqual(self.cfg.package, "com.ardaryusz.easypeasygunpowder")

    def test_authors(self):
        self.assertEqual(self.cfg.authors, "ardaryusz")

    def test_license(self):
        self.assertEqual(self.cfg.license, "MIT")

    def test_output_repo_name(self):
        self.assertEqual(self.cfg.output_repo_name, "EasyPeasyGunpowder")

    def test_main_class_derived(self):
        # No explicit main_class in fixture; should be derived from mod_name.
        self.assertEqual(self.cfg.main_class, "EasyPeasyGunpowder")

    def test_target_count(self):
        self.assertEqual(len(self.cfg.targets), 4)

    def test_first_target_is_forge(self):
        t = self.cfg.targets[0]
        self.assertIsInstance(t, TargetConfig)
        self.assertEqual(t.loader, "forge")
        self.assertEqual(t.branch, "forge-1.20.1")
        self.assertEqual(t.mc_range, "1.20.1")
        self.assertEqual(t.minecraft_version, "1.20.1")
        self.assertEqual(t.minecraft_version_range, "[1.20.1,1.20.2)")

    def test_last_target_is_fabric(self):
        t = self.cfg.targets[-1]
        self.assertEqual(t.loader, "fabric")
        self.assertEqual(t.branch, "fabric-1.21.2-1.21.11")
        # Fabric targets may have no version range.
        self.assertEqual(t.minecraft_version_range, "")

    def test_optional_homepage_default(self):
        self.assertEqual(self.cfg.homepage, "")

    def test_optional_issue_tracker_default(self):
        self.assertEqual(self.cfg.issue_tracker, "")


class TestLoadModConfigFileErrors(unittest.TestCase):
    """load_mod_config should raise ConfigError for bad file states."""

    def test_file_not_found(self):
        with self.assertRaises(ConfigError) as ctx:
            load_mod_config(_FIXTURES / "nonexistent.json")
        self.assertIn("not found", str(ctx.exception))

    def test_invalid_json(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{ this is not valid json }")
            tmp = f.name
        try:
            with self.assertRaises(ConfigError) as ctx:
                load_mod_config(tmp)
            self.assertIn("Invalid JSON", str(ctx.exception))
        finally:
            os.unlink(tmp)

    def test_top_level_not_object(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("[1, 2, 3]")
            tmp = f.name
        try:
            with self.assertRaises(ConfigError):
                load_mod_config(tmp)
        finally:
            os.unlink(tmp)


class TestLoadModConfigMissingFields(unittest.TestCase):
    """Each required field omission should raise ConfigError."""

    def _load_with(self, overrides: dict) -> None:
        """Load the fixture, apply overrides (None value means delete the key)."""
        with open(_VALID_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in overrides.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v

        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            load_mod_config(tmp)
        finally:
            os.unlink(tmp)

    def test_missing_mod_id(self):
        with self.assertRaises(ConfigError):
            self._load_with({"mod_id": None})

    def test_missing_mod_name(self):
        with self.assertRaises(ConfigError):
            self._load_with({"mod_name": None})

    def test_missing_mod_version(self):
        with self.assertRaises(ConfigError):
            self._load_with({"mod_version": None})

    def test_missing_group(self):
        with self.assertRaises(ConfigError):
            self._load_with({"group": None})

    def test_missing_package(self):
        with self.assertRaises(ConfigError):
            self._load_with({"package": None})

    def test_missing_authors(self):
        with self.assertRaises(ConfigError):
            self._load_with({"authors": None})

    def test_missing_license(self):
        with self.assertRaises(ConfigError):
            self._load_with({"license": None})

    def test_missing_description(self):
        with self.assertRaises(ConfigError):
            self._load_with({"description": None})

    def test_missing_output_repo_name(self):
        with self.assertRaises(ConfigError):
            self._load_with({"output_repo_name": None})

    def test_missing_targets(self):
        with self.assertRaises(ConfigError):
            self._load_with({"targets": None})

    def test_empty_string_mod_id(self):
        with self.assertRaises(ConfigError):
            self._load_with({"mod_id": ""})


class TestLoadModConfigModIdValidation(unittest.TestCase):
    """mod_id field validation."""

    def _load_with_mod_id(self, mod_id: str) -> None:
        with open(_VALID_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        data["mod_id"] = mod_id

        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            load_mod_config(tmp)
        finally:
            os.unlink(tmp)

    def test_uppercase_mod_id(self):
        with self.assertRaises(ConfigError) as ctx:
            self._load_with_mod_id("EasyPeasyGunpowder")
        self.assertIn("mod_id", str(ctx.exception))

    def test_mod_id_with_spaces(self):
        with self.assertRaises(ConfigError):
            self._load_with_mod_id("easy peasy")

    def test_mod_id_with_hyphen(self):
        with self.assertRaises(ConfigError):
            self._load_with_mod_id("easy-peasy")

    def test_mod_id_starts_with_digit(self):
        with self.assertRaises(ConfigError):
            self._load_with_mod_id("1mymod")

    def test_mod_id_with_uppercase_mixed(self):
        with self.assertRaises(ConfigError):
            self._load_with_mod_id("myMod")

    def test_valid_mod_id_with_underscore(self):
        # Should NOT raise.
        self._load_with_mod_id("easy_peasy_gunpowder")

    def test_valid_mod_id_with_digits(self):
        self._load_with_mod_id("mymod2")


class TestLoadModConfigPackageValidation(unittest.TestCase):
    """package field validation."""

    def _load_with_package(self, package: str) -> None:
        with open(_VALID_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        data["package"] = package

        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            load_mod_config(tmp)
        finally:
            os.unlink(tmp)

    def test_single_segment_package(self):
        with self.assertRaises(ConfigError):
            self._load_with_package("mymod")

    def test_empty_package(self):
        with self.assertRaises(ConfigError):
            self._load_with_package("")

    def test_package_segment_starts_with_digit(self):
        with self.assertRaises(ConfigError):
            self._load_with_package("com.1example")

    def test_package_segment_with_hyphen(self):
        with self.assertRaises(ConfigError):
            self._load_with_package("com.my-mod")

    def test_package_keyword_segment(self):
        with self.assertRaises(ConfigError):
            self._load_with_package("com.class.mymod")

    def test_valid_two_segment_package(self):
        self._load_with_package("com.example")

    def test_valid_three_segment_package(self):
        self._load_with_package("com.example.mymod")


class TestLoadModConfigMainClass(unittest.TestCase):
    """main_class explicit override and derivation."""

    def _load_with(self, overrides: dict):
        with open(_VALID_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in overrides.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v

        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            return load_mod_config(tmp)
        finally:
            os.unlink(tmp)

    def test_explicit_main_class_used(self):
        cfg = self._load_with({"main_class": "EasyPeasyGunpowder"})
        self.assertEqual(cfg.main_class, "EasyPeasyGunpowder")

    def test_explicit_main_class_overrides_derivation(self):
        cfg = self._load_with({"main_class": "MyCustomClass"})
        self.assertEqual(cfg.main_class, "MyCustomClass")

    def test_explicit_main_class_invalid_java(self):
        with self.assertRaises(ConfigError) as ctx:
            self._load_with({"main_class": "123invalid"})
        self.assertIn("main_class", str(ctx.exception))

    def test_explicit_main_class_keyword(self):
        with self.assertRaises(ConfigError):
            self._load_with({"main_class": "class"})

    def test_derived_from_mod_name(self):
        # No explicit main_class; derived from "Easy Peasy Gunpowder".
        cfg = self._load_with({"main_class": None})
        self.assertEqual(cfg.main_class, "EasyPeasyGunpowder")

    def test_derivation_failure_requires_explicit(self):
        # A mod_name composed entirely of non-alphanumeric characters produces an
        # empty derived class name, which must fail with ConfigError.
        with self.assertRaises(ConfigError):
            self._load_with({"mod_name": "!!! --- ???", "main_class": None})


class TestLoadModConfigTargets(unittest.TestCase):
    """Targets array validation."""

    def _load_with(self, targets) -> ModConfig:
        with open(_VALID_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        data["targets"] = targets

        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            return load_mod_config(tmp)
        finally:
            os.unlink(tmp)

    def test_empty_targets_array(self):
        with self.assertRaises(ConfigError):
            self._load_with([])

    def test_targets_not_array(self):
        with self.assertRaises(ConfigError):
            self._load_with("not_an_array")

    def test_unsupported_loader(self):
        with self.assertRaises(ConfigError) as ctx:
            self._load_with([{
                "loader": "quilt",
                "template": "quilt-1.20.1",
                "branch": "quilt-1.20.1",
                "mc_range": "1.20.1",
                "minecraft_version": "1.20.1",
            }])
        self.assertIn("loader", str(ctx.exception))

    def test_target_missing_required_field(self):
        with self.assertRaises(ConfigError):
            self._load_with([{
                "loader": "forge",
                # 'template' is missing
                "branch": "forge-1.20.1",
                "mc_range": "1.20.1",
                "minecraft_version": "1.20.1",
            }])

    def test_single_valid_target(self):
        cfg = self._load_with([{
            "loader": "fabric",
            "template": "fabric-1.21",
            "branch": "fabric-1.21",
            "mc_range": "1.21",
            "minecraft_version": "1.21",
        }])
        self.assertEqual(len(cfg.targets), 1)
        self.assertEqual(cfg.targets[0].loader, "fabric")

    def test_all_three_loaders_accepted(self):
        targets = []
        for loader in ("forge", "neoforge", "fabric"):
            targets.append({
                "loader": loader,
                "template": f"{loader}-1.21",
                "branch": f"{loader}-1.21",
                "mc_range": "1.21",
                "minecraft_version": "1.21",
            })
        cfg = self._load_with(targets)
        loaders = [t.loader for t in cfg.targets]
        self.assertIn("forge", loaders)
        self.assertIn("neoforge", loaders)
        self.assertIn("fabric", loaders)


class TestLoadTemplateDescriptor(unittest.TestCase):
    """Tests for load_template_descriptor."""

    def test_loads_fake_template_descriptor(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertIsInstance(desc, TemplateDescriptor)

    def test_loader_field(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertEqual(desc.loader, "forge")

    def test_minecraft_version_field(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertEqual(desc.minecraft_version, "1.20.1")

    def test_recipe_folder_field(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertEqual(desc.recipe_folder, "recipes")

    def test_recipe_format_field(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertEqual(desc.recipe_format, "legacy_1_20")

    def test_metadata_files_field(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertIn("src/main/resources/META-INF/mods.toml", desc.metadata_files)

    def test_java_mod_import_field(self):
        desc = load_template_descriptor(_FAKE_TEMPLATE)
        self.assertEqual(desc.java_mod_import, "net.minecraftforge.fml.common.Mod")

    def test_missing_descriptor_returns_none(self):
        # A directory with no modsmith-template.json should return None.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = load_template_descriptor(tmp)
        self.assertIsNone(result)

    def test_defaults_on_minimal_descriptor(self):
        """A descriptor with only an empty JSON object should use all defaults."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            desc_path = Path(tmp) / "modsmith-template.json"
            desc_path.write_text("{}", encoding="utf-8")
            desc = load_template_descriptor(tmp)
        self.assertIsNotNone(desc)
        self.assertEqual(desc.recipe_folder, "recipe")       # default
        self.assertEqual(desc.recipe_format, "modern_1_21")  # default
        self.assertEqual(desc.metadata_files, [])            # default
        self.assertFalse(desc.uses_generated_metadata)       # default


if __name__ == "__main__":
    unittest.main()
