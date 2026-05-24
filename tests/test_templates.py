"""Unit tests for template discovery, copying, and entrypoint generation."""

import unittest
import tempfile
import shutil
from pathlib import Path

from modsmith.templates import (
    list_templates,
    copy_template,
    find_java_source_root,
    write_java_entrypoint,
)
from modsmith.context import ModContext, TargetContext
from modsmith.config import ModConfig, TargetConfig


class TestTemplates(unittest.TestCase):
    """Tests for templates discovery and manipulation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_templates(self):
        templates_dir = self.path / "templates"
        templates_dir.mkdir()
        (templates_dir / "forge_temp").mkdir()
        (templates_dir / "fabric_temp").mkdir()
        (templates_dir / "some_file.txt").write_text("hello", encoding="utf-8")

        templates = list_templates(templates_dir)
        self.assertEqual(templates, ["fabric_temp", "forge_temp"])

    def test_list_templates_non_existent(self):
        self.assertEqual(list_templates(self.path / "non_existent"), [])

    def test_copy_template(self):
        src_dir = self.path / "src"
        src_dir.mkdir()
        dest_dir = self.path / "dest"

        (src_dir / "gradlew").write_text("gradlew content", encoding="utf-8")
        (src_dir / "build.gradle").write_text("build content", encoding="utf-8")
        (src_dir / "some.jar").write_text("jar content", encoding="utf-8")

        (src_dir / ".git").mkdir()
        (src_dir / ".git" / "config").write_text("git config", encoding="utf-8")

        (src_dir / "build").mkdir()
        (src_dir / "build" / "some_file").write_text("build file", encoding="utf-8")

        copy_template(src_dir, dest_dir)

        self.assertTrue((dest_dir / "gradlew").exists())
        self.assertTrue((dest_dir / "build.gradle").exists())

        self.assertFalse((dest_dir / "some.jar").exists())
        self.assertFalse((dest_dir / ".git").exists())
        self.assertFalse((dest_dir / "build").exists())

    def test_copy_template_excludes_ordinary_jars(self):
        """Ordinary *.jar files (e.g. libs/example.jar) must NOT be copied."""
        src_dir = self.path / "src_jars"
        src_dir.mkdir()
        dest_dir = self.path / "dest_jars"

        # An ordinary jar in a libs directory
        (src_dir / "libs").mkdir()
        (src_dir / "libs" / "example.jar").write_bytes(b"fake jar content")
        # Another jar at root level
        (src_dir / "root.jar").write_bytes(b"another fake jar")

        copy_template(src_dir, dest_dir)

        self.assertFalse((dest_dir / "libs" / "example.jar").exists())
        self.assertFalse((dest_dir / "root.jar").exists())

    def test_copy_template_preserves_gradle_wrapper_jar(self):
        """gradle/wrapper/gradle-wrapper.jar must be preserved — it is required by gradlew."""
        src_dir = self.path / "src_wrapper"
        src_dir.mkdir()
        dest_dir = self.path / "dest_wrapper"

        wrapper_dir = src_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True)
        jar_content = b"PK fake gradle-wrapper jar bytes"
        (wrapper_dir / "gradle-wrapper.jar").write_bytes(jar_content)
        # Ordinary jar at root should still be excluded
        (src_dir / "ordinary.jar").write_bytes(b"should not be copied")

        copy_template(src_dir, dest_dir)

        preserved = dest_dir / "gradle" / "wrapper" / "gradle-wrapper.jar"
        self.assertTrue(preserved.exists(), "gradle-wrapper.jar must be copied from the template")
        self.assertEqual(preserved.read_bytes(), jar_content)
        self.assertFalse((dest_dir / "ordinary.jar").exists())

    def test_copy_template_gradle_wrapper_files_present(self):
        """A realistic template tree: gradlew, gradlew.bat, gradle-wrapper.properties,
        and gradle-wrapper.jar must all arrive in the destination."""
        src_dir = self.path / "src_full"
        src_dir.mkdir()
        dest_dir = self.path / "dest_full"

        wrapper_dir = src_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True)
        (src_dir / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        (src_dir / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
        (wrapper_dir / "gradle-wrapper.properties").write_text(
            "distributionUrl=https://services.gradle.org/distributions/gradle-8.0-bin.zip\n",
            encoding="utf-8",
        )
        (wrapper_dir / "gradle-wrapper.jar").write_bytes(b"PK\x03\x04 fake jar")

        copy_template(src_dir, dest_dir)

        self.assertTrue((dest_dir / "gradlew").exists())
        self.assertTrue((dest_dir / "gradlew.bat").exists())
        self.assertTrue((dest_dir / "gradle" / "wrapper" / "gradle-wrapper.properties").exists())
        self.assertTrue((dest_dir / "gradle" / "wrapper" / "gradle-wrapper.jar").exists())

    def test_find_java_source_root(self):

        repo_root = self.path / "repo"
        repo_root.mkdir()

        java_root = find_java_source_root(repo_root)
        self.assertEqual(java_root, repo_root / "src" / "main" / "java")
        self.assertTrue(java_root.exists())

    def test_write_java_entrypoint_forge(self):
        repo_root = self.path / "repo"
        repo_root.mkdir()

        java_root = repo_root / "src" / "main" / "java"
        (java_root / "com" / "example").mkdir(parents=True)
        (java_root / "examplemod").mkdir(parents=True)

        config = ModConfig(
            mod_id="testmod",
            mod_name="Test Mod",
            mod_version="1.0.0",
            group="com.test",
            package="com.test.my_pkg",
            authors="Author",
            license="MIT",
            description="Desc",
            output_repo_name="my_repo",
            targets=[],
            main_class="TestModMain",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="forge",
            template="some_template",
            branch="main",
            mc_range="1.20.1",
            minecraft_version="1.20.1"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

        warnings = write_java_entrypoint(repo_root, ctx)
        self.assertEqual(warnings, [])

        self.assertFalse((java_root / "com" / "example").exists())
        self.assertFalse((java_root / "examplemod").exists())

        java_file = java_root / "com" / "test" / "my_pkg" / "TestModMain.java"
        self.assertTrue(java_file.exists())
        content = java_file.read_text(encoding="utf-8")
        self.assertIn("package com.test.my_pkg;", content)
        self.assertIn("import net.minecraftforge.fml.common.Mod;", content)
        self.assertIn('@Mod("testmod")', content)
        self.assertIn("public class TestModMain", content)

    def test_write_java_entrypoint_neoforge(self):
        repo_root = self.path / "repo"
        repo_root.mkdir()

        config = ModConfig(
            mod_id="neomod",
            mod_name="Neo Mod",
            mod_version="1.0.0",
            group="com.test",
            package="com.test.neo_pkg",
            authors="Author",
            license="MIT",
            description="Desc",
            output_repo_name="my_repo",
            targets=[],
            main_class="NeoModMain",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="neoforge",
            template="some_template",
            branch="main",
            mc_range="1.21",
            minecraft_version="1.21"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

        warnings = write_java_entrypoint(repo_root, ctx)
        self.assertEqual(warnings, [])

        java_file = repo_root / "src" / "main" / "java" / "com" / "test" / "neo_pkg" / "NeoModMain.java"
        self.assertTrue(java_file.exists())
        content = java_file.read_text(encoding="utf-8")
        self.assertIn("import net.neoforged.fml.common.Mod;", content)

    def test_write_java_entrypoint_fabric_skips(self):
        repo_root = self.path / "repo"
        repo_root.mkdir()

        config = ModConfig(
            mod_id="fabmod",
            mod_name="Fabric Mod",
            mod_version="1.0.0",
            group="com.test",
            package="com.test.fab_pkg",
            authors="Author",
            license="MIT",
            description="Desc",
            output_repo_name="my_repo",
            targets=[],
            main_class="FabricModMain",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="fabric",
            template="some_template",
            branch="main",
            mc_range="1.20.1",
            minecraft_version="1.20.1"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

        warnings = write_java_entrypoint(repo_root, ctx)
        self.assertEqual(warnings, [])

        java_file = repo_root / "src" / "main" / "java" / "com" / "test" / "fab_pkg" / "FabricModMain.java"
        self.assertFalse(java_file.exists())

    def test_write_java_entrypoint_invalid_package_warnings(self):
        repo_root = self.path / "repo"
        repo_root.mkdir()

        config = ModConfig(
            mod_id="testmod",
            mod_name="Test Mod",
            mod_version="1.0.0",
            group="com.test",
            package="invalid-package-name",
            authors="Author",
            license="MIT",
            description="Desc",
            output_repo_name="my_repo",
            targets=[],
            main_class="TestModMain",
        )
        mod_ctx = ModContext(config=config)
        target = TargetConfig(
            loader="forge",
            template="some_template",
            branch="main",
            mc_range="1.20.1",
            minecraft_version="1.20.1"
        )
        ctx = TargetContext(mod_ctx=mod_ctx, target=target, descriptor=None)

        warnings = write_java_entrypoint(repo_root, ctx)
        self.assertTrue(any("Invalid Java package name" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
