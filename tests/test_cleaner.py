"""Unit and integration tests for modsmith/cleaner.py (Phase 7 — clean command)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modsmith.cleaner import CleanError, CleanResult, clean
from modsmith.config import ConfigError


_VALID_CONFIG = {
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
        }
    ],
}


def _make_workspace(root: Path, cfg: dict | None = None) -> tuple[Path, Path]:
    """Return (workspace_dir, mods_dir) with a written modsmith.json."""
    workspace = root / "WORKSPACE"
    (workspace / "DETAILS").mkdir(parents=True, exist_ok=True)
    (workspace / "DETAILS" / "modsmith.json").write_text(
        json.dumps(cfg or _VALID_CONFIG), encoding="utf-8"
    )
    mods = root / "MODS"
    mods.mkdir(parents=True, exist_ok=True)
    return workspace, mods


class TestCleaner(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.workspace, self.mods = _make_workspace(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    # 1. clean exits successfully when repo does not exist
    def test_clean_repo_does_not_exist(self):
        repo_dir = self.mods / "TestModRepo"
        self.assertFalse(repo_dir.exists())

        res = clean(self.workspace, self.mods)
        self.assertFalse(res.deleted)
        self.assertFalse(res.dry_run)
        self.assertIn("No generated repository found", res.message)

    # 2. clean --force deletes existing repo
    def test_clean_force_deletes_existing_repo(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "some_file.txt").write_text("content", encoding="utf-8")
        self.assertTrue(repo_dir.exists())

        res = clean(self.workspace, self.mods, force=True)
        self.assertTrue(res.deleted)
        self.assertFalse(repo_dir.exists())
        self.assertIn("Successfully deleted", res.message)

    # 3. clean without --force prompts and deletes on y
    def test_clean_prompt_y(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        confirm_mock = MagicMock(return_value="y")
        res = clean(self.workspace, self.mods, force=False, confirm_fn=confirm_mock)

        confirm_mock.assert_called_once()
        self.assertTrue(res.deleted)
        self.assertFalse(repo_dir.exists())
        self.assertIn("Successfully deleted", res.message)

    # 4. clean without --force prompts and deletes on yes
    def test_clean_prompt_yes(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        confirm_mock = MagicMock(return_value="yEs")
        res = clean(self.workspace, self.mods, force=False, confirm_fn=confirm_mock)

        confirm_mock.assert_called_once()
        self.assertTrue(res.deleted)
        self.assertFalse(repo_dir.exists())

    # 5. clean without --force cancels on empty input
    def test_clean_prompt_empty_cancels(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        confirm_mock = MagicMock(return_value="  ")
        res = clean(self.workspace, self.mods, force=False, confirm_fn=confirm_mock)

        confirm_mock.assert_called_once()
        self.assertFalse(res.deleted)
        self.assertTrue(repo_dir.exists())
        self.assertIn("cancelled", res.message)

    # 6. clean without --force cancels on n
    def test_clean_prompt_n_cancels(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        confirm_mock = MagicMock(return_value="n")
        res = clean(self.workspace, self.mods, force=False, confirm_fn=confirm_mock)

        confirm_mock.assert_called_once()
        self.assertFalse(res.deleted)
        self.assertTrue(repo_dir.exists())

    # 7. dry-run does not delete and does not prompt
    def test_clean_dry_run(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        confirm_mock = MagicMock()
        res = clean(self.workspace, self.mods, dry_run=True, force=False, confirm_fn=confirm_mock)

        confirm_mock.assert_not_called()
        self.assertFalse(res.deleted)
        self.assertTrue(res.dry_run)
        self.assertTrue(repo_dir.exists())
        self.assertIn("Would delete", res.message)

    # 8. clean only deletes MODS/<output_repo_name>, not WORKSPACE or MODTEMPLATES
    def test_clean_safety_bounds(self):
        # Create other sibling dirs
        templates_dir = self.root / "MODTEMPLATES"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "template_file.txt").write_text("template", encoding="utf-8")

        dist_dir = self.workspace / "DIST"
        dist_dir.mkdir(parents=True, exist_ok=True)
        (dist_dir / "jar.jar").write_bytes(b"jar")

        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        res = clean(self.workspace, self.mods, force=True)

        self.assertTrue(res.deleted)
        self.assertFalse(repo_dir.exists())
        # Workspace and templates must still exist
        self.assertTrue(self.workspace.exists())
        self.assertTrue((self.workspace / "DETAILS" / "modsmith.json").exists())
        self.assertTrue(dist_dir.exists())
        self.assertTrue(templates_dir.exists())

    # 9. clean uses safe_delete_tree
    def test_clean_uses_safe_delete_tree(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        with patch("modsmith.cleaner.safe_delete_tree") as mock_safe_delete:
            clean(self.workspace, self.mods, force=True)
            mock_safe_delete.assert_called_once_with(repo_dir)

    # 10. clean surfaces deletion errors cleanly
    def test_clean_surfaces_deletion_errors(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        with patch("modsmith.cleaner.safe_delete_tree", side_effect=OSError("Permission denied")):
            with self.assertRaises(CleanError) as ctx:
                clean(self.workspace, self.mods, force=True)
            self.assertIn("Failed to delete repository", str(ctx.exception))
            self.assertIn("Permission denied", str(ctx.exception))


class TestCleanerCLI(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.workspace, self.mods = _make_workspace(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    # 11. CLI returns 0 when no repo exists
    def test_cli_returns_0_when_no_repo_exists(self):
        from modsmith.cli import main
        with patch("sys.argv", [
            "modsmith",
            "--workspace", str(self.workspace),
            "--mods", str(self.mods),
            "clean",
        ]):
            try:
                main()
                rc = 0
            except SystemExit as exc:
                rc = exc.code

        self.assertEqual(rc, 0)

    # 12. CLI returns 0 after successful deletion
    def test_cli_returns_0_after_successful_deletion(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        from modsmith.cli import main
        with patch("sys.argv", [
            "modsmith",
            "--workspace", str(self.workspace),
            "--mods", str(self.mods),
            "clean",
            "--force",
        ]):
            try:
                main()
                rc = 0
            except SystemExit as exc:
                rc = exc.code

        self.assertEqual(rc, 0)
        self.assertFalse(repo_dir.exists())

    # 13. CLI returns 1 on CleanError
    def test_cli_returns_1_on_clean_error(self):
        repo_dir = self.mods / "TestModRepo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        from modsmith.cli import main
        with patch("modsmith.cleaner.safe_delete_tree", side_effect=OSError("Access denied")), \
             patch("sys.argv", [
                 "modsmith",
                 "--workspace", str(self.workspace),
                 "--mods", str(self.mods),
                 "clean",
                 "--force",
             ]):
            try:
                main()
                rc = 0
            except SystemExit as exc:
                rc = exc.code

        self.assertEqual(rc, 1)
