"""Unit tests for modsmith/generator.py."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modsmith.config import load_template_descriptor
from modsmith.context import ModContext, TargetContext
from modsmith.generator import (
    GenerateResult,
    is_legacy_recipe_version,
    generate,
)
from modsmith.git_ops import git_current_branch, git_list_branches, git_checkout


class TestIsLegacyRecipeVersion(unittest.TestCase):
    """Test is_legacy_recipe_version version logic."""

    def test_legacy_versions(self):
        self.assertTrue(is_legacy_recipe_version("1.20"))
        self.assertTrue(is_legacy_recipe_version("1.20.1"))
        self.assertTrue(is_legacy_recipe_version("1.20.4"))
        self.assertTrue(is_legacy_recipe_version("1.19.4"))
        self.assertTrue(is_legacy_recipe_version("1.12.2"))

    def test_modern_versions(self):
        self.assertFalse(is_legacy_recipe_version("1.20.5"))
        self.assertFalse(is_legacy_recipe_version("1.20.6"))
        self.assertFalse(is_legacy_recipe_version("1.21"))
        self.assertFalse(is_legacy_recipe_version("1.21.1"))
        self.assertFalse(is_legacy_recipe_version("1.22"))

    def test_invalid_versions(self):
        self.assertFalse(is_legacy_recipe_version("invalid"))
        self.assertFalse(is_legacy_recipe_version("1"))


class TestGenerator(unittest.TestCase):
    """Integrative tests for modsmith.generator.generate command."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "WORKSPACE"
        self.details = self.workspace / "DETAILS"
        self.recipes = self.workspace / "RECIPES"
        self.templates = self.root / "MODTEMPLATES"
        self.mods = self.root / "MODS"

        # Write clean mock configurations and template folders
        self.details.mkdir(parents=True, exist_ok=True)
        self.recipes.mkdir(parents=True, exist_ok=True)
        self.templates.mkdir(parents=True, exist_ok=True)
        self.mods.mkdir(parents=True, exist_ok=True)

        self.cfg_data = {
            "mod_id": "testmod",
            "mod_name": "Test Mod",
            "mod_version": "1.0.0",
            "group": "com.example.testmod",
            "package": "com.example.testmod",
            "authors": "tester",
            "license": "MIT",
            "description": "A test mod.",
            "output_repo_name": "TestModRepo",
            "targets": [
                {
                    "loader": "forge",
                    "template": "forge-1.20.1",
                    "branch": "forge-1.20.1",
                    "mc_range": "1.20.1",
                    "minecraft_version": "1.20.1",
                    "minecraft_version_range": "[1.20.1,1.20.2)",
                },
                {
                    "loader": "fabric",
                    "template": "fabric-1.21",
                    "branch": "fabric-1.21",
                    "mc_range": "1.21",
                    "minecraft_version": "1.21",
                },
            ],
        }

        # Write config
        (self.details / "modsmith.json").write_text(
            json.dumps(self.cfg_data), encoding="utf-8"
        )

        # Write simple recipes
        recipe_data = {
            "type": "minecraft:crafting_shaped",
            "key": {"C": {"item": "minecraft:charcoal"}},
            "result": {"item": "minecraft:gunpowder", "count": 1},
        }
        (self.recipes / "recipe1.json").write_text(
            json.dumps(recipe_data), encoding="utf-8"
        )

        # Write template folders
        for t in self.cfg_data["targets"]:
            tdir = self.templates / t["template"]
            tdir.mkdir(parents=True, exist_ok=True)
            # Add basic files like build.gradle and gradle.properties
            (tdir / "build.gradle").write_text("plugins { id 'java' }\n", encoding="utf-8")
            (tdir / "gradle.properties").write_text("mod_version=1.0.0\n", encoding="utf-8")
            # Write modsmith-template.json
            desc_data = {
                "loader": t["loader"],
                "minecraft_version": t["minecraft_version"],
            }
            if t["minecraft_version"] == "1.20.1":
                desc_data["recipe_folder"] = "recipes"
                desc_data["recipe_format"] = "legacy_1_20"
            else:
                desc_data["recipe_folder"] = "recipe"
                desc_data["recipe_format"] = "modern_1_21"
            (tdir / "modsmith-template.json").write_text(
                json.dumps(desc_data), encoding="utf-8"
            )
            # Gradle wrapper stubs (required by verifier check 5)
            (tdir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
            (tdir / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
            wrapper_dir = tdir / "gradle" / "wrapper"
            wrapper_dir.mkdir(parents=True, exist_ok=True)
            (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"PK fake jar")
            (wrapper_dir / "gradle-wrapper.properties").write_text("", encoding="utf-8")
            # Loader metadata stubs (required by verifier check 4)
            loader = t["loader"].lower()
            if loader == "forge":
                meta_dir = tdir / "src" / "main" / "resources" / "META-INF"
                meta_dir.mkdir(parents=True, exist_ok=True)
                (meta_dir / "mods.toml").write_text(
                    'modLoader="javafml"\nlicense="MIT"\n[[mods]]\n    modId="placeholder"\n',
                    encoding="utf-8",
                )
            elif loader == "fabric":
                res_dir = tdir / "src" / "main" / "resources"
                res_dir.mkdir(parents=True, exist_ok=True)
                (res_dir / "fabric.mod.json").write_text(
                    '{"schemaVersion":1,"id":"placeholder","version":"1.0.0"}',
                    encoding="utf-8",
                )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validation_failure_raises_value_error(self):
        # Break validation by deleting recipes
        shutil.rmtree(self.recipes)

        with self.assertRaises(ValueError) as ctx:
            with patch("shutil.which", return_value="/usr/bin/mock"):
                generate(self.workspace, self.templates, self.mods)
        self.assertIn("Validation failed", str(ctx.exception))

    def test_dry_run_safety(self):
        with patch("shutil.which", return_value="/usr/bin/mock"):
            res = generate(
                self.workspace,
                self.templates,
                self.mods,
                dry_run=True,
            )

        # Result is correct
        self.assertEqual(res.repo_dir, self.mods / "TestModRepo")
        self.assertEqual(res.generated_branches, ["forge-1.20.1", "fabric-1.21"])
        self.assertTrue(res.dry_run)

        # No side effects!
        self.assertFalse((self.mods / "TestModRepo").exists())

    def test_simple_overwrite_fails_without_force(self):
        # Pre-create the output repo directory
        output_repo = self.mods / "TestModRepo"
        output_repo.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(ValueError) as ctx:
            with patch("shutil.which", return_value="/usr/bin/mock"):
                generate(self.workspace, self.templates, self.mods, force=False)
        self.assertIn("Output repo already exists", str(ctx.exception))

    def test_simple_overwrite_succeeds_with_force(self):
        output_repo = self.mods / "TestModRepo"
        output_repo.mkdir(parents=True, exist_ok=True)
        # Put a file inside to check that it survives
        (output_repo / "old.txt").write_text("old stuff", encoding="utf-8")

        if shutil.which("git") is None:
            self.skipTest("git is required for the full generate run")

        res = generate(self.workspace, self.templates, self.mods, force=True)
        self.assertTrue(output_repo.exists())
        # Unrelated files must survive generate --force
        self.assertTrue((output_repo / "old.txt").exists())
        self.assertEqual(res.generated_branches, ["forge-1.20.1", "fabric-1.21"])

    def test_target_branch_filtering(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for the full generate run")

        res = generate(
            self.workspace,
            self.templates,
            self.mods,
            target_branch="fabric-1.21",
        )

        # Only fabric branch is generated
        self.assertEqual(res.generated_branches, ["fabric-1.21"])
        branches = git_list_branches(res.repo_dir)
        self.assertEqual(branches, ["fabric-1.21"])

    def test_target_branch_filtering_invalid_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            generate(
                self.workspace,
                self.templates,
                self.mods,
                target_branch="invalid-branch",
            )
        self.assertIn("No target matches branch 'invalid-branch'", str(ctx.exception))

    def test_heuristic_fallback_when_no_descriptor(self):
        # Delete descriptor for 1.20.1 Forge template to trigger fallback
        desc_file = self.templates / "forge-1.20.1" / "modsmith-template.json"
        desc_file.unlink()

        if shutil.which("git") is None:
            self.skipTest("git is required for the full generate run")

        # Suppress missing descriptor warning
        with patch("shutil.which", return_value="/usr/bin/mock"):
            res = generate(
                self.workspace,
                self.templates,
                self.mods,
                target_branch="forge-1.20.1",
            )

        # Output folder should fall back to legacy 'recipes' since 1.20.1 is minor <= 20
        recipe_dest = (
            res.repo_dir
            / "src"
            / "main"
            / "resources"
            / "data"
            / "testmod"
            / "recipes"
            / "recipe1.json"
        )
        self.assertTrue(recipe_dest.exists())
        recipe_content = json.loads(recipe_dest.read_text(encoding="utf-8"))
        self.assertIn("item", recipe_content["result"])

    def test_full_real_generation(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for the full generate run")

        res = generate(self.workspace, self.templates, self.mods)

        # Repo dir exists
        self.assertTrue(res.repo_dir.exists())

        # Branches are generated
        branches = git_list_branches(res.repo_dir)
        self.assertEqual(branches, ["fabric-1.21", "forge-1.20.1"])

        # Current checked out branch is the first one
        current = git_current_branch(res.repo_dir)
        self.assertEqual(current, "forge-1.20.1")

        # Let's inspect the files in forge-1.20.1 branch
        # gitignore and README are present
        self.assertTrue((res.repo_dir / ".gitignore").exists())
        self.assertTrue((res.repo_dir / "README.md").exists())

        # Recipes are converted to legacy (1.20.1 uses recipes folder + legacy format)
        recipe_dest = (
            res.repo_dir
            / "src"
            / "main"
            / "resources"
            / "data"
            / "testmod"
            / "recipes"
            / "recipe1.json"
        )
        self.assertTrue(recipe_dest.exists())
        recipe_content = json.loads(recipe_dest.read_text(encoding="utf-8"))
        # Verify legacy result uses "item", not "id"
        self.assertIn("item", recipe_content["result"])
        self.assertNotIn("id", recipe_content["result"])

        # Now checkout fabric branch and check
        git_checkout(res.repo_dir, "fabric-1.21")
        # Recipes folder is "recipe" + modern format
        recipe_dest_fabric = (
            res.repo_dir
            / "src"
            / "main"
            / "resources"
            / "data"
            / "testmod"
            / "recipe"
            / "recipe1.json"
        )
        self.assertTrue(recipe_dest_fabric.exists())
        recipe_content_fabric = json.loads(recipe_dest_fabric.read_text(encoding="utf-8"))
        # Verify modern result uses "id", not "item"
        self.assertIn("id", recipe_content_fabric["result"])
        self.assertNotIn("item", recipe_content_fabric["result"])


if __name__ == "__main__":
    unittest.main()
