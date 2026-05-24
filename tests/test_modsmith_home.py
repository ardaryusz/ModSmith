"""Tests for MODSMITH_HOME environment variable support in CLI defaults."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from modsmith.cli import _get_default_dir, _build_parser


class TestGetDefaultDir(unittest.TestCase):
    """Tests for the ``_get_default_dir`` helper."""

    def test_returns_bare_subdir_without_env(self):
        """Without MODSMITH_HOME, returns the plain subdir name."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_default_dir("WORKSPACE"), "WORKSPACE")
            self.assertEqual(_get_default_dir("MODTEMPLATES"), "MODTEMPLATES")
            self.assertEqual(_get_default_dir("MODS"), "MODS")

    def test_returns_joined_path_with_env(self):
        """With MODSMITH_HOME set, returns MODSMITH_HOME/subdir."""
        fake_home = r"C:\Users\Tester\Documents\ModSmith"
        with patch.dict(os.environ, {"MODSMITH_HOME": fake_home}, clear=False):
            result = _get_default_dir("WORKSPACE")
            expected = str(Path(fake_home) / "WORKSPACE")
            self.assertEqual(result, expected)

    def test_all_subdirs_respect_env(self):
        """All three default directories respect MODSMITH_HOME."""
        fake_home = r"C:\Users\Tester\Documents\ModSmith"
        with patch.dict(os.environ, {"MODSMITH_HOME": fake_home}, clear=False):
            for subdir in ("WORKSPACE", "MODTEMPLATES", "MODS"):
                result = _get_default_dir(subdir)
                self.assertEqual(result, str(Path(fake_home) / subdir))

    def test_empty_env_treated_as_unset(self):
        """An empty MODSMITH_HOME string falls back to bare subdir."""
        with patch.dict(os.environ, {"MODSMITH_HOME": ""}, clear=False):
            self.assertEqual(_get_default_dir("WORKSPACE"), "WORKSPACE")


class TestParserDefaults(unittest.TestCase):
    """Ensure the argparse defaults integrate with MODSMITH_HOME correctly."""

    def test_parser_defaults_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            # Force fresh parser build (defaults are evaluated at build time)
            parser = _build_parser()
            args = parser.parse_args(["validate"])
            self.assertEqual(args.workspace, "WORKSPACE")
            self.assertEqual(args.templates, "MODTEMPLATES")
            self.assertEqual(args.mods, "MODS")

    def test_parser_defaults_with_env(self):
        fake_home = r"C:\Users\Tester\Documents\ModSmith"
        with patch.dict(os.environ, {"MODSMITH_HOME": fake_home}, clear=False):
            parser = _build_parser()
            args = parser.parse_args(["validate"])
            self.assertEqual(args.workspace, str(Path(fake_home) / "WORKSPACE"))
            self.assertEqual(args.templates, str(Path(fake_home) / "MODTEMPLATES"))
            self.assertEqual(args.mods, str(Path(fake_home) / "MODS"))

    def test_explicit_flag_overrides_env(self):
        """--workspace explicit flag wins over MODSMITH_HOME."""
        fake_home = r"C:\Users\Tester\Documents\ModSmith"
        with patch.dict(os.environ, {"MODSMITH_HOME": fake_home}, clear=False):
            parser = _build_parser()
            args = parser.parse_args([
                "--workspace", r"D:\custom\WS",
                "--templates", r"D:\custom\TPL",
                "--mods", r"D:\custom\MODS",
                "validate",
            ])
            self.assertEqual(args.workspace, r"D:\custom\WS")
            self.assertEqual(args.templates, r"D:\custom\TPL")
            self.assertEqual(args.mods, r"D:\custom\MODS")


if __name__ == "__main__":
    unittest.main()
