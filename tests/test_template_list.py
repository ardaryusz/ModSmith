"""Unit and integration tests for template listing and validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modsmith.template_listing import list_templates, TemplateListResult
from modsmith.cli import main


class TestTemplateListing(unittest.TestCase):
    """Tests for the list_templates logic in template_listing.py."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _create_fake_template(
        self,
        name: str,
        descriptor_content: dict | str | None = None,
        has_gradlew: bool = True,
        has_gradlew_bat: bool = True,
        has_gradle_wrapper_jar: bool = True,
    ) -> Path:
        t_dir = self.tmp_path / name
        t_dir.mkdir(parents=True, exist_ok=True)

        if descriptor_content is not None:
            desc_file = t_dir / "modsmith-template.json"
            if isinstance(descriptor_content, dict):
                desc_file.write_text(json.dumps(descriptor_content), encoding="utf-8")
            else:
                desc_file.write_text(descriptor_content, encoding="utf-8")

        if has_gradlew:
            (t_dir / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        if has_gradlew_bat:
            (t_dir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")

        if has_gradle_wrapper_jar:
            wrapper_dir = t_dir / "gradle" / "wrapper"
            wrapper_dir.mkdir(parents=True, exist_ok=True)
            (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"fake jar bytes")

        return t_dir

    def test_missing_templates_dir(self):
        """Missing templates directory returns ok=False and has errors."""
        missing_dir = self.tmp_path / "non_existent"
        res = list_templates(missing_dir)
        self.assertFalse(res.ok)
        self.assertEqual(len(res.templates), 0)
        self.assertTrue(any("does not exist" in err for err in res.errors))

    def test_templates_dir_is_not_a_dir(self):
        """Templates path pointing to a file returns ok=False and has errors."""
        file_path = self.tmp_path / "some_file.txt"
        file_path.write_text("hello", encoding="utf-8")
        res = list_templates(file_path)
        self.assertFalse(res.ok)
        self.assertEqual(len(res.templates), 0)
        self.assertTrue(any("not a directory" in err for err in res.errors))

    def test_empty_templates_dir(self):
        """Empty templates directory returns ok=True and has warning."""
        empty_dir = self.tmp_path / "empty_dir"
        empty_dir.mkdir()
        res = list_templates(empty_dir)
        self.assertTrue(res.ok)
        self.assertEqual(len(res.templates), 0)
        self.assertTrue(any("no template folders" in w for w in res.warnings))

    def test_valid_template(self):
        """A fully valid template is parsed correctly with no errors or warnings."""
        descriptor = {
            "loader": "forge",
            "minecraft_version": "1.20.1",
            "recipe_folder": "recipes",
            "recipe_format": "legacy_1_20",
            "jar_loader_suffix": "forge",
        }
        self._create_fake_template("forge-1.20.1", descriptor_content=descriptor)

        res = list_templates(self.tmp_path)
        self.assertTrue(res.ok)
        self.assertEqual(len(res.templates), 1)

        t = res.templates[0]
        self.assertEqual(t.name, "forge-1.20.1")
        self.assertTrue(t.has_descriptor)
        self.assertTrue(t.descriptor_valid)
        self.assertEqual(t.loader, "forge")
        self.assertEqual(t.minecraft_version, "1.20.1")
        self.assertEqual(t.recipe_folder, "recipes")
        self.assertEqual(t.recipe_format, "legacy_1_20")
        self.assertEqual(t.jar_loader_suffix, "forge")
        self.assertTrue(t.has_gradlew)
        self.assertTrue(t.has_gradlew_bat)
        self.assertTrue(t.has_gradle_wrapper_jar)

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.warnings), 0)

    def test_missing_descriptor(self):
        """Template missing modsmith-template.json yields errors and ok=False."""
        self._create_fake_template("missing-desc", descriptor_content=None)

        res = list_templates(self.tmp_path)
        self.assertFalse(res.ok)
        self.assertEqual(len(res.templates), 1)
        t = res.templates[0]
        self.assertFalse(t.has_descriptor)
        self.assertFalse(t.descriptor_valid)
        self.assertTrue(any("missing modsmith-template.json" in err for err in res.errors))

    def test_invalid_descriptor(self):
        """Template with malformed JSON in modsmith-template.json yields errors and ok=False."""
        self._create_fake_template("invalid-desc", descriptor_content="invalid json { [")

        res = list_templates(self.tmp_path)
        self.assertFalse(res.ok)
        self.assertEqual(len(res.templates), 1)
        t = res.templates[0]
        self.assertTrue(t.has_descriptor)
        self.assertFalse(t.descriptor_valid)
        self.assertIsNotNone(t.error_message)
        self.assertTrue(any("invalid descriptor" in err or "failed to parse" in err for err in res.errors))

    def test_missing_gradle_wrapper_jar(self):
        """Template missing gradle-wrapper.jar yields errors and ok=False."""
        self._create_fake_template("missing-wrapper", descriptor_content={}, has_gradle_wrapper_jar=False)

        res = list_templates(self.tmp_path)
        self.assertFalse(res.ok)
        self.assertEqual(len(res.templates), 1)
        t = res.templates[0]
        self.assertFalse(t.has_gradle_wrapper_jar)
        self.assertTrue(any("missing gradle/wrapper/gradle-wrapper.jar" in err for err in res.errors))

    def test_missing_gradlew_warning(self):
        """Template missing gradlew or gradlew.bat yields warnings but ok=True."""
        # Missing both
        self._create_fake_template("missing-both-gradlew", descriptor_content={}, has_gradlew=False, has_gradlew_bat=False)
        res = list_templates(self.tmp_path)
        self.assertTrue(res.ok)
        self.assertTrue(any("missing both gradlew and gradlew.bat" in w for w in res.warnings))

        # Reset temp directory
        self._tmp.cleanup()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

        # Missing gradlew only
        self._create_fake_template("missing-gradlew", descriptor_content={}, has_gradlew=False, has_gradlew_bat=True)
        res = list_templates(self.tmp_path)
        self.assertTrue(res.ok)
        self.assertTrue(any(w.endswith("is missing gradlew") for w in res.warnings))
        self.assertFalse(any(w.endswith("is missing gradlew.bat") for w in res.warnings))

        # Reset temp directory again
        self._tmp.cleanup()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

        # Missing gradlew.bat only
        self._create_fake_template("missing-gradlew-bat", descriptor_content={}, has_gradlew=True, has_gradlew_bat=False)
        res = list_templates(self.tmp_path)
        self.assertTrue(res.ok)
        self.assertTrue(any(w.endswith("is missing gradlew.bat") for w in res.warnings))
        self.assertFalse(any(w.endswith("is missing gradlew") for w in res.warnings))


class TestTemplateListCLI(unittest.TestCase):
    """Integration/CLI tests for 'modsmith template list'."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_missing_templates_dir_exits_1(self):
        """CLI exits 1 if templates directory does not exist."""
        missing_dir = self.tmp_path / "non_existent"
        with patch("sys.argv", [
            "modsmith",
            "--templates", str(missing_dir),
            "template",
            "list"
        ]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_cli_empty_templates_dir_exits_0(self):
        """CLI exits 0 if templates directory is empty (warns but ok)."""
        empty_dir = self.tmp_path / "empty_dir"
        empty_dir.mkdir()
        with patch("sys.argv", [
            "modsmith",
            "--templates", str(empty_dir),
            "template",
            "list"
        ]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_cli_all_valid_templates_exits_0(self):
        """CLI exits 0 if all templates are valid."""
        t_dir = self.tmp_path / "valid-template"
        t_dir.mkdir()
        (t_dir / "modsmith-template.json").write_text("{}", encoding="utf-8")
        (t_dir / "gradlew").write_text("#!", encoding="utf-8")
        (t_dir / "gradlew.bat").write_text("@", encoding="utf-8")
        wrapper_dir = t_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True)
        (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"")

        with patch("sys.argv", [
            "modsmith",
            "--templates", str(self.tmp_path),
            "template",
            "list"
        ]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_cli_any_template_error_exits_1(self):
        """CLI exits 1 if any template has a validation error (e.g. missing descriptor)."""
        t_dir = self.tmp_path / "error-template"
        t_dir.mkdir()
        # No modsmith-template.json written
        (t_dir / "gradlew").write_text("#!", encoding="utf-8")
        (t_dir / "gradlew.bat").write_text("@", encoding="utf-8")
        wrapper_dir = t_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True)
        (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"")

        with patch("sys.argv", [
            "modsmith",
            "--templates", str(self.tmp_path),
            "template",
            "list"
        ]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
