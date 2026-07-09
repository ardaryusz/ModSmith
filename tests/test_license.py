import json
import shutil
import unittest
from pathlib import Path
import tempfile
import os

from modsmith.context import ModContext, TargetContext, discover_license_file
from modsmith.home import ensure_home_structure
from modsmith.generator import generate, template_has_license_file, clear_working_tree_selectively
from modsmith.doctor import diagnose_environment


class TestLicenseDiscovery(unittest.TestCase):
    """Test license file discovery logic."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.license_dir = Path(self.tmp.name) / "WORKSPACE" / "LICENSE"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_folder_returns_none(self):
        self.assertIsNone(discover_license_file(self.license_dir))

    def test_empty_folder_returns_none(self):
        self.license_dir.mkdir(parents=True)
        self.assertIsNone(discover_license_file(self.license_dir))

    def test_finds_license_md(self):
        self.license_dir.mkdir(parents=True)
        f = self.license_dir / "LICENSE.md"
        f.touch()
        selected = discover_license_file(self.license_dir)
        self.assertEqual(selected, f)

    def test_finds_license_txt(self):
        self.license_dir.mkdir(parents=True)
        f = self.license_dir / "LICENSE.txt"
        f.touch()
        selected = discover_license_file(self.license_dir)
        self.assertEqual(selected, f)

    def test_case_insensitive_stem_and_ext(self):
        self.license_dir.mkdir(parents=True)
        # Test lowercase stem and mixed-case extension
        f = self.license_dir / "license.Md"
        f.touch()
        selected = discover_license_file(self.license_dir)
        self.assertEqual(selected, f)

        f.unlink()
        f2 = self.license_dir / "License.TXT"
        f2.touch()
        selected2 = discover_license_file(self.license_dir)
        self.assertEqual(selected2, f2)

    def test_rejects_unrelated_filenames(self):
        self.license_dir.mkdir(parents=True)
        (self.license_dir / "MY_LICENSE.md").touch()
        (self.license_dir / "LICENSE-old.txt").touch()
        (self.license_dir / "COPYING.md").touch()
        (self.license_dir / "GPL.txt").touch()
        self.assertIsNone(discover_license_file(self.license_dir))

    def test_does_not_search_recursively(self):
        self.license_dir.mkdir(parents=True)
        subdir = self.license_dir / "sub"
        subdir.mkdir()
        (subdir / "LICENSE.md").touch()
        self.assertIsNone(discover_license_file(self.license_dir))

    def test_prefers_md_over_txt(self):
        self.license_dir.mkdir(parents=True)
        f_txt = self.license_dir / "LICENSE.txt"
        f_md = self.license_dir / "LICENSE.md"
        f_txt.touch()
        f_md.touch()
        selected = discover_license_file(self.license_dir)
        self.assertEqual(selected, f_md)

    def test_selection_is_deterministic(self):
        self.license_dir.mkdir(parents=True)
        f_lower = self.license_dir / "license.md"
        f_upper = self.license_dir / "LICENSE.md"
        f_lower.touch()
        f_upper.touch()
        
        selected = discover_license_file(self.license_dir)
        expected = sorted([f_lower, f_upper], key=lambda p: p.name)[0]
        self.assertEqual(selected, expected)


class TestWorkspaceInitialization(unittest.TestCase):
    """Test workspace structure initialization."""

    def test_license_folder_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            ensure_home_structure(home)
            license_dir = home / "WORKSPACE" / "LICENSE"
            self.assertTrue(license_dir.is_dir())
            # Verify no placeholders created
            self.assertEqual(list(license_dir.iterdir()), [])


class TestSelectiveClearingAndPreservation(unittest.TestCase):
    """Test clear_working_tree_selectively and generation file preservation."""

    def test_preserves_unrelated_files_and_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            template_dir = Path(tmp) / "template"
            repo_dir.mkdir()
            template_dir.mkdir()

            # Create files in template
            (template_dir / "build.gradle").touch()
            (template_dir / "src" / "main" / "java").mkdir(parents=True)
            (template_dir / "src" / "main" / "java" / "TemplateClass.java").touch()

            # Create files in repo (simulating previous run + user edits)
            (repo_dir / "build.gradle").write_text("modified", encoding="utf-8")
            (repo_dir / "src" / "main" / "java").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "main" / "java" / "TemplateClass.java").touch()
            # User added files
            (repo_dir / "CHANGELOG.md").write_text("version 2.0", encoding="utf-8")
            (repo_dir / "docs").mkdir()
            (repo_dir / "docs" / "manual.txt").touch()
            # Template provided license
            (repo_dir / "LICENSE.md").write_text("template license", encoding="utf-8")
            (template_dir / "LICENSE.md").touch() # In template too

            # Run selective clearing
            clear_working_tree_selectively(repo_dir, template_dir)

            # Template-provided files must be cleared
            self.assertFalse((repo_dir / "build.gradle").exists())
            self.assertFalse((repo_dir / "src" / "main" / "java" / "TemplateClass.java").exists())

            # User-added files/folders must survive
            self.assertTrue((repo_dir / "CHANGELOG.md").exists())
            self.assertEqual((repo_dir / "CHANGELOG.md").read_text(encoding="utf-8"), "version 2.0")
            self.assertTrue((repo_dir / "docs" / "manual.txt").exists())

            # Template-provided license must NOT be deleted
            self.assertTrue((repo_dir / "LICENSE.md").exists())


class TestLicenseGeneration(unittest.TestCase):
    """Test license generation, copy, and force stale-file cleanup."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        ensure_home_structure(self.home)
        self.workspace = self.home / "WORKSPACE"
        self.templates = self.home / "MODTEMPLATES"
        self.mods = self.home / "MODS"

        # Write minimum config
        cfg = {
            "mod_id": "testmod",
            "mod_name": "Test Mod",
            "mod_version": "1.0.0",
            "group": "com.example.testmod",
            "package": "com.example.testmod",
            "authors": "author",
            "license": "MIT",
            "description": "desc",
            "homepage": "",
            "issue_tracker": "",
            "output_repo_name": "TestModRepo",
            "targets": [
                {
                    "loader": "forge",
                    "template": "forge-1.20.1",
                    "branch": "forge-1.20.1",
                    "mc_range": "1.20.1",
                    "minecraft_version": "1.20.1"
                }
            ]
        }
        (self.workspace / "DETAILS" / "modsmith.json").write_text(json.dumps(cfg), encoding="utf-8")

        # Set up template stub
        tdir = self.templates / "forge-1.20.1"
        tdir.mkdir(parents=True)
        (tdir / "build.gradle").touch()
        (tdir / "gradle.properties").touch()
        (tdir / "gradlew").touch()
        (tdir / "gradlew.bat").touch()
        (tdir / "gradle" / "wrapper").mkdir(parents=True)
        (tdir / "gradle" / "wrapper" / "gradle-wrapper.jar").touch()
        (tdir / "gradle" / "wrapper" / "gradle-wrapper.properties").touch()
        (tdir / "src" / "main" / "resources" / "META-INF").mkdir(parents=True)
        (tdir / "src" / "main" / "resources" / "META-INF" / "mods.toml").write_text(
            'modLoader="javafml"\nlicense="MIT"\n[[mods]]\n    modId="testmod"\n', encoding="utf-8"
        )
        (tdir / "modsmith-template.json").write_text('{"loader":"forge","minecraft_version":"1.20.1","recipe_folder":"recipes"}', encoding="utf-8")

        # Recipes
        (self.workspace / "WORKSPACE" / "RECIPES").mkdir(parents=True, exist_ok=True)
        recipe = {
            "type": "minecraft:crafting_shaped",
            "key": {"C": "minecraft:charcoal"},
            "result": {"item": "minecraft:gunpowder"}
        }
        (self.workspace / "RECIPES" / "r.json").write_text(json.dumps(recipe), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_license_succeeds(self):
        res = generate(self.workspace, self.templates, self.mods, force=True)
        self.assertTrue((self.mods / "TestModRepo").exists())
        # No placeholder license created
        self.assertFalse((self.mods / "TestModRepo" / "LICENSE.md").exists())
        self.assertFalse((self.mods / "TestModRepo" / "LICENSE.txt").exists())

    def test_copies_license_md_and_normalizes_case(self):
        # Create a lowercase source license file
        src = self.workspace / "LICENSE" / "license.md"
        src.write_text("license md content", encoding="utf-8")

        generate(self.workspace, self.templates, self.mods, force=True)
        
        # Verify copied, normalized, and extension preserved
        dest = self.mods / "TestModRepo" / "LICENSE.md"
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(encoding="utf-8"), "license md content")

    def test_stale_alternate_handled_safely(self):
        # 1. Run with LICENSE.md
        src_md = self.workspace / "LICENSE" / "LICENSE.md"
        src_md.write_text("md content", encoding="utf-8")
        generate(self.workspace, self.templates, self.mods, force=True)
        self.assertTrue((self.mods / "TestModRepo" / "LICENSE.md").exists())

        # 2. Switch to LICENSE.txt
        src_md.unlink()
        src_txt = self.workspace / "LICENSE" / "LICENSE.txt"
        src_txt.write_text("txt content", encoding="utf-8")

        # Simulate user added unrelated files that must survive
        (self.mods / "TestModRepo" / "CHANGELOG.md").write_text("changelog", encoding="utf-8")

        generate(self.workspace, self.templates, self.mods, force=True)

        # LICENSE.md is stale and not in template, so it should be deleted.
        self.assertFalse((self.mods / "TestModRepo" / "LICENSE.md").exists())
        # LICENSE.txt is copied
        self.assertTrue((self.mods / "TestModRepo" / "LICENSE.txt").exists())
        # CHANGELOG.md must survive
        self.assertTrue((self.mods / "TestModRepo" / "CHANGELOG.md").exists())


class TestLicenseDoctor(unittest.TestCase):
    """Test doctor checks for license configuration."""

    def test_doctor_reports_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            ensure_home_structure(home)
            ws = home / "WORKSPACE"
            tpl = home / "MODTEMPLATES"
            mods = home / "MODS"

            # Create dummy files to satisfy diagnose_environment checks so res.ok is True
            cfg = {
                "mod_id": "testmod",
                "mod_name": "Test Mod",
                "mod_version": "1.0.0",
                "group": "com.example.testmod",
                "package": "com.example.testmod",
                "authors": "author",
                "license": "MIT",
                "description": "desc",
                "homepage": "",
                "issue_tracker": "",
                "output_repo_name": "TestModRepo",
                "targets": [
                    {
                        "loader": "forge",
                        "template": "forge-1.20.1",
                        "branch": "forge-1.20.1",
                        "mc_range": "1.20.1",
                        "minecraft_version": "1.20.1"
                    }
                ]
            }
            (ws / "DETAILS" / "modsmith.json").write_text(json.dumps(cfg), encoding="utf-8")
            (ws / "RECIPES" / "dummy.json").write_text("{}", encoding="utf-8")

            # Setup mock template directory structure
            tdir = tpl / "forge-1.20.1"
            tdir.mkdir(parents=True)
            (tdir / "gradlew").touch()
            (tdir / "gradle" / "wrapper").mkdir(parents=True)
            (tdir / "gradle" / "wrapper" / "gradle-wrapper.jar").touch()

            import unittest.mock
            with unittest.mock.patch("shutil.which", return_value="mock_bin"), \
                 unittest.mock.patch("subprocess.run") as mock_run:
                
                mock_run.return_value.stdout = "mock version"
                mock_run.return_value.stderr = "mock version"
                mock_run.return_value.returncode = 0

                # Scenario A: missing
                res = diagnose_environment(ws, tpl, mods)
                self.assertTrue(res.ok, f"Doctor check failed: {res.errors}")
                self.assertTrue(any("No workspace LICENSE, LICENSE.md, LICENSE.txt, LICENSE.html, or LICENSE.docx found" in inf for inf in res.infos))

                # Scenario B: LICENSE.md found
                (ws / "LICENSE" / "LICENSE.md").touch()
                res2 = diagnose_environment(ws, tpl, mods)
                self.assertTrue(any("Workspace license file found" in inf and "LICENSE.md" in inf for inf in res2.infos))

                # Scenario C: Both found
                (ws / "LICENSE" / "LICENSE.txt").touch()
                res3 = diagnose_environment(ws, tpl, mods)
                self.assertTrue(any("Multiple workspace license files exist" in inf and "Markdown file LICENSE.md was selected" in inf for inf in res3.infos))


class TestLicenseGUI(unittest.TestCase):
    """Test GUI dashboard fields defensively."""

    def test_dashboard_license_ui_fields(self):
        try:
            from PySide6.QtWidgets import QApplication
            from modsmith_gui.screens.dashboard import DashboardScreen
            from modsmith_gui.widgets.log_panel import LogPanel
            
            app = QApplication.instance() or QApplication([])
            log = LogPanel()
            screen = DashboardScreen(log_panel=log)
            self.assertIsNotNone(screen._lbl_summary_license)
            self.assertIsNotNone(screen._btn_open_license)
        except ImportError:
            pass


if __name__ == "__main__":
    unittest.main()
