"""Unit tests for modsmith/builder.py (Phase 6 — build command)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modsmith.builder import (
    BuildError,
    BuildResult,
    build,
    collect_built_jars,
    find_gradle_wrapper,
    run_gradle_build,
)
from modsmith.git_ops import (
    git_add_all,
    git_commit,
    git_create_orphan_branch,
    git_init,
    git_current_branch,
    git_list_branches,
)


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_fake_repo_with_branches(repo_dir: Path, branches: list[str]) -> None:
    """Create a minimal Git repo with one commit per orphan branch."""
    if shutil.which("git") is None:
        return  # callers should skip if git is unavailable
    git_init(repo_dir)
    for branch in branches:
        git_create_orphan_branch(repo_dir, branch)
        # Write a placeholder file so Git has something to commit
        (repo_dir / f"placeholder-{branch}.txt").write_text(branch, encoding="utf-8")
        git_add_all(repo_dir)
        git_commit(repo_dir, f"init {branch}")


def _require_git(test: unittest.TestCase) -> None:
    """Skip the test if git is not on PATH."""
    if shutil.which("git") is None:
        test.skipTest("git not available on PATH")


# ---------------------------------------------------------------------------
# Tests — find_gradle_wrapper
# ---------------------------------------------------------------------------


class TestFindGradleWrapper(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_prefers_gradlew_bat_on_windows(self):
        (self.repo_dir / "gradlew.bat").write_text("@echo off", encoding="utf-8")
        (self.repo_dir / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
        with patch("sys.platform", "win32"):
            result = find_gradle_wrapper(self.repo_dir)
        self.assertEqual(result, self.repo_dir / "gradlew.bat")

    def test_prefers_gradlew_on_non_windows(self):
        (self.repo_dir / "gradlew.bat").write_text("@echo off", encoding="utf-8")
        (self.repo_dir / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
        with patch("sys.platform", "linux"):
            result = find_gradle_wrapper(self.repo_dir)
        self.assertEqual(result, self.repo_dir / "gradlew")

    def test_falls_back_to_gradlew_when_bat_missing(self):
        (self.repo_dir / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
        with patch("sys.platform", "win32"):
            result = find_gradle_wrapper(self.repo_dir)
        self.assertEqual(result, self.repo_dir / "gradlew")

    def test_falls_back_to_bat_when_gradlew_missing(self):
        (self.repo_dir / "gradlew.bat").write_text("@echo off", encoding="utf-8")
        with patch("sys.platform", "linux"):
            result = find_gradle_wrapper(self.repo_dir)
        self.assertEqual(result, self.repo_dir / "gradlew.bat")

    def test_raises_build_error_when_neither_exists(self):
        with self.assertRaises(BuildError):
            find_gradle_wrapper(self.repo_dir)


# ---------------------------------------------------------------------------
# Tests — collect_built_jars
# ---------------------------------------------------------------------------


class TestCollectBuiltJars(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo_dir = self.root / "repo"
        self.dist_dir = self.root / "DIST"
        self.libs_dir = self.repo_dir / "build" / "libs"
        self.libs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_jar(self, name: str) -> Path:
        p = self.libs_dir / name
        p.write_bytes(b"PK fake jar")
        return p

    def test_copies_normal_jar(self):
        self._write_jar("testmod-1.20.1-forge-1.0.0.jar")
        copied = collect_built_jars(self.repo_dir, self.dist_dir)
        self.assertEqual(len(copied), 1)
        self.assertTrue((self.dist_dir / "testmod-1.20.1-forge-1.0.0.jar").exists())

    def test_excludes_sources_jar(self):
        self._write_jar("testmod-1.0.0-sources.jar")
        with self.assertRaises(BuildError):
            collect_built_jars(self.repo_dir, self.dist_dir)

    def test_excludes_javadoc_jar(self):
        self._write_jar("testmod-1.0.0-javadoc.jar")
        with self.assertRaises(BuildError):
            collect_built_jars(self.repo_dir, self.dist_dir)

    def test_excludes_dev_jar(self):
        self._write_jar("testmod-1.0.0-dev.jar")
        with self.assertRaises(BuildError):
            collect_built_jars(self.repo_dir, self.dist_dir)

    def test_excludes_dev_shadow_jar(self):
        self._write_jar("testmod-1.0.0-dev-shadow.jar")
        with self.assertRaises(BuildError):
            collect_built_jars(self.repo_dir, self.dist_dir)

    def test_copies_release_jar_and_ignores_excluded(self):
        self._write_jar("testmod-1.0.0.jar")
        self._write_jar("testmod-1.0.0-sources.jar")
        self._write_jar("testmod-1.0.0-dev.jar")
        copied = collect_built_jars(self.repo_dir, self.dist_dir)
        names = [p.name for p in copied]
        self.assertEqual(names, ["testmod-1.0.0.jar"])
        self.assertFalse((self.dist_dir / "testmod-1.0.0-sources.jar").exists())

    def test_raises_when_libs_dir_missing(self):
        shutil.rmtree(self.libs_dir)
        with self.assertRaises(BuildError):
            collect_built_jars(self.repo_dir, self.dist_dir)

    def test_raises_when_no_valid_jar(self):
        self._write_jar("testmod-1.0.0-sources.jar")
        with self.assertRaises(BuildError):
            collect_built_jars(self.repo_dir, self.dist_dir)

    def test_preserves_jar_filename(self):
        self._write_jar("easypeasygunpowder-1.20.1-forge-1.1.0.jar")
        copied = collect_built_jars(self.repo_dir, self.dist_dir)
        self.assertEqual(copied[0].name, "easypeasygunpowder-1.20.1-forge-1.1.0.jar")


# ---------------------------------------------------------------------------
# Tests — build() orchestrator
# ---------------------------------------------------------------------------


class TestBuild(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.workspace, self.mods = _make_workspace(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    # ── error cases ───────────────────────────────────────────────────────────

    def test_fails_when_repo_missing(self):
        # Repo dir does not exist yet
        with self.assertRaises(BuildError) as ctx:
            build(self.workspace, self.mods)
        self.assertIn("Generated repo not found", str(ctx.exception))

    def test_fails_when_selected_branch_does_not_exist(self):
        _require_git(self)
        repo_dir = self.mods / "TestModRepo"
        _make_fake_repo_with_branches(repo_dir, ["forge-1.20.1"])

        with self.assertRaises(BuildError) as ctx:
            build(self.workspace, self.mods, branch="nonexistent-branch")
        self.assertIn("nonexistent-branch", str(ctx.exception))

    def test_fails_when_config_branch_missing_from_repo(self):
        """build() with no --branch fails if a config target branch is absent."""
        _require_git(self)
        repo_dir = self.mods / "TestModRepo"
        # Only create one of the two configured branches
        _make_fake_repo_with_branches(repo_dir, ["forge-1.20.1"])

        with self.assertRaises(BuildError) as ctx:
            build(self.workspace, self.mods)
        self.assertIn("fabric-1.21", str(ctx.exception))

    # ── dry-run ───────────────────────────────────────────────────────────────

    def test_dry_run_has_no_side_effects(self):
        """dry_run must not create DIST, not checkout branches, not run Gradle."""
        _require_git(self)
        repo_dir = self.mods / "TestModRepo"
        _make_fake_repo_with_branches(repo_dir, ["forge-1.20.1", "fabric-1.21"])

        dist_dir = self.workspace / "DIST"

        with patch("modsmith.builder.git_checkout") as mock_checkout, \
             patch("modsmith.builder.run_gradle_build") as mock_gradle:
            res = build(self.workspace, self.mods, dry_run=True)

        # No side effects
        mock_checkout.assert_not_called()
        mock_gradle.assert_not_called()
        self.assertFalse(dist_dir.exists())

        # Result is informative
        self.assertTrue(res.dry_run)
        self.assertEqual(res.copied_jars, [])
        self.assertIn("forge-1.20.1", res.built_branches)
        self.assertIn("fabric-1.21", res.built_branches)

    def test_dry_run_single_branch(self):
        _require_git(self)
        repo_dir = self.mods / "TestModRepo"
        _make_fake_repo_with_branches(repo_dir, ["forge-1.20.1", "fabric-1.21"])

        with patch("modsmith.builder.git_checkout"), \
             patch("modsmith.builder.run_gradle_build"):
            res = build(self.workspace, self.mods, branch="fabric-1.21", dry_run=True)

        self.assertEqual(res.built_branches, ["fabric-1.21"])
        self.assertTrue(res.dry_run)

    # ── real build (Gradle mocked) ─────────────────────────────────────────────

    def _setup_repo_with_gradle_output(
        self,
        branches: list[str],
        jar_name: str = "testmod-1.0.0.jar",
    ) -> Path:
        """Set up a fake repo and stub a build/libs with a release jar."""
        _require_git(self)
        repo_dir = self.mods / "TestModRepo"
        _make_fake_repo_with_branches(repo_dir, branches)

        # Write a fake gradlew.bat so find_gradle_wrapper is happy
        (repo_dir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
        (repo_dir / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

        # Write a fake release jar (simulating a successful Gradle run)
        libs_dir = repo_dir / "build" / "libs"
        libs_dir.mkdir(parents=True, exist_ok=True)
        (libs_dir / jar_name).write_bytes(b"PK fake jar")

        return repo_dir

    def test_build_all_target_branches(self):
        _require_git(self)
        repo_dir = self._setup_repo_with_gradle_output(
            ["forge-1.20.1", "fabric-1.21"]
        )

        with patch("modsmith.builder.run_gradle_build"):
            res = build(self.workspace, self.mods)

        self.assertFalse(res.dry_run)
        self.assertEqual(res.built_branches, ["forge-1.20.1", "fabric-1.21"])
        self.assertFalse(res.dry_run)

    def test_build_single_branch_with_flag(self):
        _require_git(self)
        self._setup_repo_with_gradle_output(["forge-1.20.1", "fabric-1.21"])

        with patch("modsmith.builder.run_gradle_build"):
            res = build(self.workspace, self.mods, branch="forge-1.20.1")

        self.assertEqual(res.built_branches, ["forge-1.20.1"])

    def test_jars_copied_to_dist(self):
        _require_git(self)
        self._setup_repo_with_gradle_output(
            ["forge-1.20.1", "fabric-1.21"],
            jar_name="testmod-1.0.0.jar",
        )
        dist_dir = self.workspace / "DIST"

        with patch("modsmith.builder.run_gradle_build"):
            res = build(self.workspace, self.mods, branch="forge-1.20.1")

        self.assertTrue(dist_dir.exists())
        self.assertTrue(any(j.name == "testmod-1.0.0.jar" for j in res.copied_jars))

    def test_first_branch_checked_out_after_all_builds(self):
        _require_git(self)
        repo_dir = self._setup_repo_with_gradle_output(
            ["forge-1.20.1", "fabric-1.21"]
        )

        with patch("modsmith.builder.run_gradle_build"):
            res = build(self.workspace, self.mods)

        current = git_current_branch(repo_dir)
        # After building both branches the first one (forge-1.20.1) should be active.
        self.assertEqual(current, "forge-1.20.1")

    def test_dist_not_created_on_dry_run(self):
        _require_git(self)
        self._setup_repo_with_gradle_output(["forge-1.20.1", "fabric-1.21"])

        with patch("modsmith.builder.run_gradle_build"), \
             patch("modsmith.builder.git_checkout"):
            build(self.workspace, self.mods, dry_run=True)

        self.assertFalse((self.workspace / "DIST").exists())


# ---------------------------------------------------------------------------
# Tests — CLI integration
# ---------------------------------------------------------------------------


class TestBuildCLI(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.workspace, self.mods = _make_workspace(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_cli(self, *extra_args: str) -> int:
        result = subprocess.run(
            [
                sys.executable, "-m", "modsmith",
                "--workspace", str(self.workspace),
                "--mods", str(self.mods),
                "build",
                *extra_args,
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode

    def test_cli_returns_1_on_build_error(self):
        # No repo → BuildError → exit 1
        rc = self._run_cli()
        self.assertEqual(rc, 1)

    def test_cli_returns_0_on_successful_build(self):
        _require_git(self)
        if shutil.which("git") is None:
            self.skipTest("git not available")

        repo_dir = self.mods / "TestModRepo"
        _make_fake_repo_with_branches(repo_dir, ["forge-1.20.1", "fabric-1.21"])
        (repo_dir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
        (repo_dir / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

        libs_dir = repo_dir / "build" / "libs"
        libs_dir.mkdir(parents=True, exist_ok=True)
        (libs_dir / "testmod-1.0.0.jar").write_bytes(b"PK")

        # Patch run_gradle_build at module level so the subprocess process
        # doesn't actually launch Gradle.
        with patch("modsmith.builder.run_gradle_build"):
            from modsmith.cli import main
            try:
                main([
                    "--workspace", str(self.workspace),
                    "--mods", str(self.mods),
                    "build",
                ])
            except SystemExit as exc:
                rc = exc.code
            else:
                rc = 0

        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
