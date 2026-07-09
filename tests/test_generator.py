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
    GenerateError,
)
from modsmith.git_ops import git_current_branch, git_list_branches, git_checkout
from modsmith.utils import run_subprocess


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
            "landing_branch": {
                "enabled": False,
                "name": "main"
            },
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


class TestLandingBranchGeneration(unittest.TestCase):
    """Landing branch generation and safety lifecycle tests."""

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
            "landing_branch": {
                "enabled": True,
                "name": "main"
            },
            "targets": [
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
            json.dumps(self.cfg_data, indent=2), encoding="utf-8"
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

        # Write template folders with all required verification stubs
        for t in self.cfg_data["targets"]:
            tdir = self.templates / t["template"]
            tdir.mkdir(parents=True, exist_ok=True)
            (tdir / "build.gradle").write_text("plugins { id 'java' }\n", encoding="utf-8")
            (tdir / "gradle.properties").write_text("mod_version=1.0.0\n", encoding="utf-8")
            
            desc_data = {
                "loader": t["loader"],
                "minecraft_version": t["minecraft_version"],
                "recipe_folder": "recipe",
                "recipe_format": "modern_1_21"
            }
            (tdir / "modsmith-template.json").write_text(
                json.dumps(desc_data), encoding="utf-8"
            )
            # Gradle wrapper stubs
            (tdir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
            (tdir / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
            wrapper_dir = tdir / "gradle" / "wrapper"
            wrapper_dir.mkdir(parents=True, exist_ok=True)
            (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"PK fake jar")
            (wrapper_dir / "gradle-wrapper.properties").write_text("", encoding="utf-8")
            # Loader metadata stubs
            res_dir = tdir / "src" / "main" / "resources"
            res_dir.mkdir(parents=True, exist_ok=True)
            (res_dir / "fabric.mod.json").write_text(
                '{"schemaVersion":1,"id":"placeholder","version":"1.0.0"}',
                encoding="utf-8",
            )

        # 2. Workspace README
        self.readme_dir = self.workspace / "README"
        self.readme_dir.mkdir(exist_ok=True)
        (self.readme_dir / "README.md").write_text("Hello from workspace README!", encoding="utf-8")

        # 3. Workspace LICENSE
        self.license_dir = self.workspace / "LICENSE"
        self.license_dir.mkdir(exist_ok=True)
        (self.license_dir / "LICENSE.md").write_text("License content", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_landing_branch_generation_enabled(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Configure an icon in modsmith.json
        cfg_path = self.workspace / "DETAILS" / "modsmith.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["icon"] = "ASSETS/icon.png"
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Create the icon file in workspace
        assets_dir = self.workspace / "ASSETS"
        assets_dir.mkdir()
        icon_file = assets_dir / "icon.png"
        icon_file.write_bytes(b"dummy icon bytes")

        res = generate(self.workspace, self.templates, self.mods)

        self.assertEqual(res.landing_branch, "main")
        self.assertEqual(res.checked_out_branch, "main")

        # Verify landing files exist in the repo
        repo_dir = res.repo_dir
        self.assertTrue((repo_dir / "README.md").exists())
        self.assertEqual((repo_dir / "README.md").read_text(encoding="utf-8"), "Hello from workspace README!\n")
        
        self.assertTrue((repo_dir / "LICENSE.md").exists())
        self.assertEqual((repo_dir / "LICENSE.md").read_text(encoding="utf-8"), "License content")

        self.assertTrue((repo_dir / "icon.png").exists())
        self.assertEqual((repo_dir / "icon.png").read_bytes(), b"dummy icon bytes")

        self.assertTrue((repo_dir / ".gitignore").exists())
        gitignore_text = (repo_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(gitignore_text.endswith("\n"))
        self.assertIn("# IDE", gitignore_text)

    def test_landing_branch_generation_disabled(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Disable in config
        cfg_path = self.workspace / "DETAILS" / "modsmith.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["landing_branch"] = {"enabled": False, "name": "main"}
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = generate(self.workspace, self.templates, self.mods)
        self.assertIsNone(res.landing_branch)
        self.assertEqual(res.checked_out_branch, "fabric-1.21")

        # Check main branch does not exist
        branches = git_list_branches(res.repo_dir)
        self.assertNotIn("main", branches)

    def test_landing_branch_fallback_readme(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Make workspace README empty
        (self.readme_dir / "README.md").write_text("   \n  \t ", encoding="utf-8")

        res = generate(self.workspace, self.templates, self.mods)
        repo_dir = res.repo_dir
        readme_content = (repo_dir / "README.md").read_text(encoding="utf-8")
        self.assertEqual(readme_content, "# Test Mod\n")

    def test_landing_branch_preflight_staged_changes_abort(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Run first generation
        res = generate(self.workspace, self.templates, self.mods)
        repo_dir = res.repo_dir

        # Let's stage a file manually in the repo on target branch
        # We can create a dummy file and stage it
        (repo_dir / "staged.txt").write_text("staged stuff", encoding="utf-8")
        run_subprocess(["git", "add", "staged.txt"], cwd=repo_dir)

        # Re-running generate should abort because staged changes exist
        from modsmith.generator import GenerateError
        with self.assertRaises(GenerateError) as ctx:
            generate(self.workspace, self.templates, self.mods, force=True)
        self.assertIn("Staged changes already exist in the generated repository", str(ctx.exception))

    def test_landing_branch_preflight_untracked_collision_abort(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # 1. Run first generation with landing branch DISABLED so repo is created but landing branch does not exist yet
        cfg_path = self.workspace / "DETAILS" / "modsmith.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["landing_branch"] = {"enabled": False, "name": "main"}
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        
        res = generate(self.workspace, self.templates, self.mods)
        repo_dir = res.repo_dir

        # 2. Put an UNTRACKED managed file (e.g. icon.png) in the repo directory on the current branch
        (repo_dir / "icon.png").write_text("untracked icon", encoding="utf-8")

        # 3. Put an UNTRACKED unrelated file in the repo (should NOT block creation)
        (repo_dir / "unrelated.txt").write_text("unrelated untracked", encoding="utf-8")

        # 4. Re-enable landing branch in config
        data["landing_branch"] = {"enabled": True, "name": "main"}
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # 5. Running generate should abort due to collision on icon.png
        from modsmith.generator import GenerateError
        with self.assertRaises(GenerateError) as ctx:
            generate(self.workspace, self.templates, self.mods, force=True)
        self.assertIn("untracked file 'icon.png' already exists", str(ctx.exception))

        # Delete the untracked icon.png and verify it now succeeds
        (repo_dir / "icon.png").unlink()
        res2 = generate(self.workspace, self.templates, self.mods, force=True)
        self.assertEqual(res2.landing_branch, "main")
        # Unrelated file survives
        self.assertTrue((repo_dir / "unrelated.txt").exists())

    def test_landing_branch_conflict_on_overwrite_abort(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Generate normally first time
        res = generate(self.workspace, self.templates, self.mods)
        repo_dir = res.repo_dir

        # Locally modify README.md on the landing branch (without committing)
        (repo_dir / "README.md").write_text("locally modified README!", encoding="utf-8")

        # Re-running generate should abort because of uncommitted changes on README.md
        from modsmith.generator import GenerateError
        with self.assertRaises(GenerateError) as ctx:
            generate(self.workspace, self.templates, self.mods, force=True)
        self.assertIn("Cannot update landing README.md because it contains uncommitted local changes", str(ctx.exception))

    def test_landing_branch_safe_stale_deletions(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Generate first time
        res = generate(self.workspace, self.templates, self.mods)
        repo_dir = res.repo_dir

        # We had LICENSE.md. Let's delete it from workspace LICENSE/ and add LICENSE.txt to simulate changing license types
        (self.license_dir / "LICENSE.md").unlink()
        (self.license_dir / "LICENSE.txt").write_text("new license txt", encoding="utf-8")

        # Re-run generation. It should safely delete the stale LICENSE.md and write LICENSE.txt instead.
        res = generate(self.workspace, self.templates, self.mods, force=True)
        self.assertFalse((repo_dir / "LICENSE.md").exists())
        self.assertTrue((repo_dir / "LICENSE.txt").exists())

        # Now, let's create a user-owned stale file (e.g. mock a LICENSE.html file, but commit it with a user commit message)
        git_checkout(repo_dir, "main")
        (repo_dir / "LICENSE.html").write_text("user custom license", encoding="utf-8")
        run_subprocess(["git", "add", "LICENSE.html"], cwd=repo_dir)
        # Commit as user
        run_subprocess(["git", "commit", "-m", "My custom license commit"], cwd=repo_dir)

        # Now re-run generate. ModSmith does not have LICENSE.html in workspace, so it's stale. But it is user-owned.
        # It should NOT delete it!
        res = generate(self.workspace, self.templates, self.mods, force=True)
        self.assertTrue((repo_dir / "LICENSE.html").exists())

    def test_landing_branch_failure_restoration(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tests")

        # Create a repo with a fabric branch first
        cfg_path = self.workspace / "DETAILS" / "modsmith.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["landing_branch"] = {"enabled": False, "name": "main"}
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        res = generate(self.workspace, self.templates, self.mods)
        repo_dir = res.repo_dir

        # Verify we are on fabric branch
        self.assertEqual(git_current_branch(repo_dir), "fabric-1.21")

        # Now enable landing branch but force a failure during writing (e.g., make icon unreadable)
        data["landing_branch"] = {"enabled": True, "name": "main"}
        data["icon"] = "ASSETS/icon.png"
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        assets_dir = self.workspace / "ASSETS"
        assets_dir.mkdir()
        icon_file = assets_dir / "icon.png"
        icon_file.write_bytes(b"dummy icon bytes")

        # Selective mock of shutil.copy2 to raise OSError only for landing branch files
        original_copy2 = shutil.copy2
        def mock_copy2(src, dst):
            if str(dst).endswith("icon.png") and "src" not in str(dst):
                raise OSError("Permission denied")
            return original_copy2(src, dst)

        with patch("shutil.copy2", side_effect=mock_copy2):
            with self.assertRaises(GenerateError):
                generate(self.workspace, self.templates, self.mods, force=True)

        # Restoration checks:
        # 1. We must be back on the original branch (fabric-1.21)
        self.assertEqual(git_current_branch(repo_dir), "fabric-1.21")
        # 2. Landing branch "main" was never committed, so the incomplete branch reference is deleted
        self.assertNotIn("main", git_list_branches(repo_dir))


if __name__ == "__main__":
    unittest.main()

