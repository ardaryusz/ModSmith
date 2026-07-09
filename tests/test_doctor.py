"""Tests for modsmith.doctor (doctor command)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from tests.test_validate import _VALID_CONFIG, _WorkspaceFactory
from modsmith.doctor import DoctorResult, diagnose_environment
from modsmith.cli import cmd_doctor


class TestDoctorDiagnostics(unittest.TestCase):
    """Unit tests for the diagnose_environment function."""

    def _setup_valid_template_files(self, ws: _WorkspaceFactory, template_name: str) -> Path:
        """Create gradlew and gradle-wrapper.jar under the template folder."""
        tdir = ws.templates / template_name
        tdir.mkdir(parents=True, exist_ok=True)
        # Create gradlew
        (tdir / "gradlew").touch()
        # Create wrapper jar
        wrapper_dir = tdir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        (wrapper_dir / "gradle-wrapper.jar").touch()
        return tdir

    def test_doctor_succeeds_on_complete_fake_workspace(self):
        """Doctor command succeeds on a fully compliant workspace."""
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            # Add gradlew and gradle-wrapper.jar to targets
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            # Ensure DIST directory exists and contains a jar file
            (ws.workspace / "DIST").mkdir(parents=True, exist_ok=True)
            (ws.workspace / "DIST" / "testmod-1.0.0.jar").touch()

            # Mock git and java
            def mock_which(name: str):
                return f"/usr/bin/{name}"

            mock_run_res = MagicMock()
            mock_run_res.stdout = "version 1.2.3"
            mock_run_res.stderr = ""

            with patch("shutil.which", side_effect=mock_which), \
                 patch("subprocess.run", return_value=mock_run_res):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertTrue(result.ok, f"Expected ok but got errors: {result.errors}")
        self.assertEqual(len(result.errors), 0)

    def test_doctor_errors_when_modsmith_json_missing(self):
        """Doctor reports an error when modsmith.json is missing."""
        with _WorkspaceFactory() as ws:
            # Create workspace folders, recipes, and templates, but no config
            ws.write_recipe()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertFalse(result.ok)
        self.assertTrue(any("modsmith.json not found" in e for e in result.errors), result.errors)

    def test_doctor_errors_when_recipe_json_is_invalid(self):
        """Doctor reports an error when a recipe file contains invalid JSON."""
        with _WorkspaceFactory() as ws:
            ws.write_config()
            ws.write_recipe(name="bad_recipe.json", content="{ invalid json }")
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertFalse(result.ok)
        self.assertTrue(any("bad_recipe.json" in e for e in result.errors), result.errors)

    def test_doctor_errors_when_referenced_template_missing(self):
        """Doctor reports an error when a target template directory is missing."""
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            # Only set up the first template; leave the second template completely missing
            targets = _VALID_CONFIG["targets"]
            self._setup_valid_template_files(ws, targets[0]["template"])

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertFalse(result.ok)
        self.assertTrue(any(targets[1]["template"] in e for e in result.errors), result.errors)

    def test_doctor_errors_when_gradle_wrapper_jar_missing(self):
        """Doctor reports an error when gradle-wrapper.jar is missing from a template."""
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            # Setup templates with gradlew, but without gradle-wrapper.jar
            for t in _VALID_CONFIG["targets"]:
                tdir = ws.templates / t["template"]
                tdir.mkdir(parents=True, exist_ok=True)
                (tdir / "gradlew").touch()

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertFalse(result.ok)
        self.assertTrue(any("gradle-wrapper.jar is missing" in e for e in result.errors), result.errors)

    def test_doctor_warns_when_dist_has_no_jars_or_missing(self):
        """Doctor registers an info when WORKSPACE/DIST has no JAR files or is missing entirely."""
        # Case A: DIST exists but is empty
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])
            # Create empty DIST
            (ws.workspace / "DIST").mkdir(parents=True, exist_ok=True)

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertTrue(result.ok)
        self.assertTrue(any("contains no built JAR files yet" in inf for inf in result.infos), result.infos)

        # Case B: DIST does not exist
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])
            # DIST is deliberately not created

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertTrue(result.ok)
        self.assertTrue(any("directory does not exist yet" in inf for inf in result.infos), result.infos)

    def test_doctor_reports_generated_repo_exists_when_present(self):
        """Doctor accurately logs whether the output mod repo directory exists in MODS."""
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            # Create the output repo directory
            repo_name = _VALID_CONFIG["output_repo_name"]
            (ws.mods / repo_name).mkdir(parents=True, exist_ok=True)

            with patch("shutil.which", return_value="/usr/bin/mock"), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )

        self.assertTrue(result.ok)
        self.assertTrue(any("Generated repository exists" in info for info in result.infos), result.infos)

    def test_doctor_checks_git_java_using_mocks(self):
        """Doctor errors on missing Git or Java using shutil.which mock."""
        # Case A: Git missing, Java present
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            def mock_which_no_git(name: str):
                return None if name == "git" else "/usr/bin/java"

            with patch("shutil.which", side_effect=mock_which_no_git):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )
        self.assertFalse(result.ok)
        self.assertTrue(any("Git was not found on PATH" in e for e in result.errors), result.errors)

        # Case B: Git present, Java missing
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            def mock_which_no_java(name: str):
                return None if name == "java" else "/usr/bin/git"

            with patch("shutil.which", side_effect=mock_which_no_java):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=False,
                )
        self.assertFalse(result.ok)
        self.assertTrue(any("Java was not found on PATH" in e for e in result.errors), result.errors)

    def test_doctor_dev_checks_makensis_pyinstaller_using_mocks(self):
        """In --dev mode, missing pyinstaller or makensis are warnings, not errors."""
        with _WorkspaceFactory() as ws:
            ws.build_valid()
            for t in _VALID_CONFIG["targets"]:
                self._setup_valid_template_files(ws, t["template"])

            # Mock shutil.which to say git/java exist, but pyinstaller/makensis do not
            def mock_which_no_dev(name: str):
                if name in ("git", "java", "python", "py"):
                    return f"/usr/bin/{name}"
                return None

            with patch("shutil.which", side_effect=mock_which_no_dev), \
                 patch("subprocess.run"):
                result = diagnose_environment(
                    workspace_dir=ws.workspace,
                    templates_dir=ws.templates,
                    mods_dir=ws.mods,
                    dev_mode=True,
                )

        self.assertTrue(result.ok)  # should still be ok since dev tool issues are warnings
        self.assertTrue(any("pyinstaller was not found" in w for w in result.warnings), result.warnings)
        self.assertTrue(any("makensis was not found" in w for w in result.warnings), result.warnings)


class TestDoctorCliExitCodes(unittest.TestCase):
    """Tests the CLI handler for exit codes and formatting."""

    @patch("modsmith.doctor.diagnose_environment")
    def test_cli_returns_0_with_no_errors(self, mock_diagnose):
        """CLI returns exit code 0 when there are no errors."""
        mock_result = DoctorResult(
            errors=[],
            warnings=["Warn 1"],
            infos=["Info 1"]
        )
        mock_diagnose.return_value = mock_result

        args = argparse.Namespace(
            workspace="WORKSPACE",
            templates="MODTEMPLATES",
            mods="MODS",
            dev=False
        )

        with patch("builtins.print") as mock_print:
            exit_code = cmd_doctor(args)

        self.assertEqual(exit_code, 0)
        # Ensure we printed the warnings and infos
        mock_print.assert_any_call("  [INFO]  Info 1")
        mock_print.assert_any_call("  [WARN]  Warn 1")

    @patch("modsmith.doctor.diagnose_environment")
    def test_cli_returns_1_when_errors_exist(self, mock_diagnose):
        """CLI returns exit code 1 when errors are present."""
        mock_result = DoctorResult(
            errors=["Error 1"],
            warnings=[],
            infos=[]
        )
        mock_diagnose.return_value = mock_result

        args = argparse.Namespace(
            workspace="WORKSPACE",
            templates="MODTEMPLATES",
            mods="MODS",
            dev=False
        )

        with patch("builtins.print") as mock_print:
            exit_code = cmd_doctor(args)

        self.assertEqual(exit_code, 1)
        mock_print.assert_any_call("  [ERROR] Error 1")


if __name__ == "__main__":
    unittest.main()
