"""Tests for modsmith.home (home command group)."""

from __future__ import annotations

import argparse
import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modsmith.home import (
    get_effective_home,
    ensure_home_structure,
    set_user_home,
    unset_user_home,
    open_home,
)
from modsmith.cli import cmd_home
from tests.test_validate import _WorkspaceFactory, _VALID_CONFIG


class TestHomeCommands(unittest.TestCase):
    """Unit tests for modsmith home helper functions and CLI handler."""

    def test_1_home_show_reports_modsmith_home_when_set(self):
        """get_effective_home returns the MODSMITH_HOME env var value if set."""
        with patch.dict(os.environ, {"MODSMITH_HOME": "C:\\Users\\User\\CustomHome"}):
            self.assertEqual(get_effective_home(), "C:\\Users\\User\\CustomHome")

    def test_2_home_show_reports_relative_defaults_when_unset(self):
        """get_effective_home returns None if MODSMITH_HOME is unset."""
        with patch.dict(os.environ, {}):
            if "MODSMITH_HOME" in os.environ:
                del os.environ["MODSMITH_HOME"]
            self.assertIsNone(get_effective_home())

    def test_3_home_set_resolves_path_and_creates_folder_structure(self):
        """ensure_home_structure creates the standard directory skeleton."""
        with _WorkspaceFactory() as ws:
            custom_home = ws.root / "CustomHome"
            # Ensure folder structure created
            ensure_home_structure(custom_home)

            # Verify standard layout exists
            subdirs = [
                "WORKSPACE",
                "WORKSPACE/DETAILS",
                "WORKSPACE/RECIPES",
                "WORKSPACE/README",
                "WORKSPACE/DIST",
                "MODTEMPLATES",
                "MODS",
            ]
            for subdir in subdirs:
                self.assertTrue((custom_home / subdir).is_dir())

    @patch("sys.platform", "win32")
    @patch("modsmith.home.winreg", create=True)
    @patch("modsmith.home.ctypes", create=True)
    def test_4_home_set_writes_windows_user_env_using_mocked_winreg(self, mock_ctypes, mock_winreg):
        """set_user_home uses winreg to write the HKCU\\Environment key on Windows."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key

        with patch.dict(os.environ, {}):
            set_user_home("C:\\Users\\User\\NewHome")

            # Check winreg called correctly
            mock_winreg.OpenKey.assert_called_once_with(
                mock_winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                mock_winreg.KEY_SET_VALUE | mock_winreg.KEY_QUERY_VALUE,
            )
            mock_winreg.SetValueEx.assert_called_once_with(
                mock_key,
                "MODSMITH_HOME",
                0,
                mock_winreg.REG_SZ,
                str(Path("C:\\Users\\User\\NewHome").resolve()),
            )
            mock_winreg.CloseKey.assert_called_once_with(mock_key)

            # Check current process env updated
            self.assertEqual(os.environ["MODSMITH_HOME"], str(Path("C:\\Users\\User\\NewHome").resolve()))

            # Check broadcast SendMessageTimeoutW called
            mock_ctypes.windll.user32.SendMessageTimeoutW.assert_called_once()

    @patch("sys.platform", "win32")
    @patch("modsmith.home.winreg", create=True)
    @patch("modsmith.home.ctypes", create=True)
    def test_5_home_unset_removes_windows_user_env_using_mocked_winreg(self, mock_ctypes, mock_winreg):
        """unset_user_home uses winreg to delete MODSMITH_HOME registry variable on Windows."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key

        with patch.dict(os.environ, {"MODSMITH_HOME": "C:\\Users\\User\\NewHome"}):
            unset_user_home()

            mock_winreg.OpenKey.assert_called_once_with(
                mock_winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                mock_winreg.KEY_SET_VALUE | mock_winreg.KEY_QUERY_VALUE,
            )
            mock_winreg.DeleteValue.assert_called_once_with(mock_key, "MODSMITH_HOME")
            mock_winreg.CloseKey.assert_called_once_with(mock_key)

            # Check removed from current process env
            self.assertNotIn("MODSMITH_HOME", os.environ)
            mock_ctypes.windll.user32.SendMessageTimeoutW.assert_called_once()

    def test_6_home_unset_does_not_delete_folders(self):
        """unset_user_home cleans environment variables but leaves user directories untouched."""
        with _WorkspaceFactory() as ws:
            custom_home = ws.root / "CustomHome"
            ensure_home_structure(custom_home)

            with patch("sys.platform", "win32"), \
                 patch("modsmith.home.winreg", create=True), \
                 patch("modsmith.home.ctypes", create=True):
                unset_user_home()

            # Confirm directories still exist
            self.assertTrue(custom_home.is_dir())
            self.assertTrue((custom_home / "WORKSPACE").is_dir())

    def test_7_home_open_errors_if_folder_missing(self):
        """open_home raises SystemExit 1 if the target home folder does not exist."""
        with _WorkspaceFactory() as ws:
            missing_home = ws.root / "MissingFolder"

            with self.assertRaises(SystemExit) as cm:
                open_home(missing_home)
            self.assertEqual(cm.exception.code, 1)

    @patch("subprocess.run")
    def test_8_home_open_calls_explorer_open_xdg_open_using_mocked_subprocess(self, mock_run):
        """open_home runs appropriate system process explorer tool based on sys.platform."""
        with _WorkspaceFactory() as ws:
            home_dir = ws.root / "CustomHome"
            home_dir.mkdir(parents=True, exist_ok=True)

            # Test Windows
            with patch("sys.platform", "win32"):
                open_home(home_dir)
                mock_run.assert_called_with(["explorer", str(home_dir)], check=True)

            # Test macOS
            with patch("sys.platform", "darwin"):
                open_home(home_dir)
                mock_run.assert_called_with(["open", str(home_dir)], check=True)

            # Test Linux
            with patch("sys.platform", "linux"):
                open_home(home_dir)
                mock_run.assert_called_with(["xdg-open", str(home_dir)], check=True)

    @patch("modsmith.home.get_effective_home")
    def test_9_cli_returns_0_for_home_show(self, mock_get_home):
        """CLI home show executes successfully and exits 0."""
        mock_get_home.return_value = "C:\\Users\\User\\MockHome"

        args = argparse.Namespace(
            home_command="show",
            workspace="WORKSPACE",
            templates="MODTEMPLATES",
            mods="MODS"
        )

        with patch("builtins.print") as mock_print:
            exit_code = cmd_home(args)

        self.assertEqual(exit_code, 0)
        mock_print.assert_any_call("MODSMITH_HOME is set: C:\\Users\\User\\MockHome")

    @patch("modsmith.home.ensure_home_structure")
    @patch("modsmith.home.set_user_home")
    def test_10_cli_returns_0_for_home_set_success(self, mock_set_home, mock_ensure):
        """CLI home set executes successfully, creates directory, sets env, and exits 0."""
        args = argparse.Namespace(
            home_command="set",
            path="C:\\Users\\User\\CustomHome",
            workspace="WORKSPACE",
            templates="MODTEMPLATES",
            mods="MODS"
        )

        with patch("builtins.print") as mock_print:
            exit_code = cmd_home(args)

        self.assertEqual(exit_code, 0)
        mock_ensure.assert_called_once_with(Path("C:\\Users\\User\\CustomHome"))
        mock_set_home.assert_called_once_with(Path("C:\\Users\\User\\CustomHome"))
        mock_print.assert_any_call("[OK] Created/verified workspace folders")

    @patch("modsmith.home.unset_user_home")
    def test_11_cli_returns_0_for_home_unset_success(self, mock_unset):
        """CLI home unset executes successfully, unsets registry env, and exits 0."""
        args = argparse.Namespace(
            home_command="unset",
            workspace="WORKSPACE",
            templates="MODTEMPLATES",
            mods="MODS"
        )

        with patch("builtins.print") as mock_print:
            exit_code = cmd_home(args)

        self.assertEqual(exit_code, 0)
        mock_unset.assert_called_once()
        mock_print.assert_any_call("[OK] Removed MODSMITH_HOME from user environment.")

    def test_12_cli_returns_1_for_unsupported_non_windows_persistent_set_unset(self):
        """CLI home set/unset returns exit code 1 / SystemExit 1 when executed on non-Windows platforms."""
        # Test set on Linux
        with patch("sys.platform", "linux"):
            with self.assertRaises(SystemExit) as cm:
                set_user_home("C:\\Users\\User\\CustomHome")
            self.assertEqual(cm.exception.code, 1)

        # Test unset on Linux
        with patch("sys.platform", "linux"):
            with self.assertRaises(SystemExit) as cm:
                unset_user_home()
            self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
