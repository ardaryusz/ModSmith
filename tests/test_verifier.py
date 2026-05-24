"""Unit tests for modsmith/verifier.py — post-generation project verification."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modsmith.config import ModConfig, TargetConfig, TemplateDescriptor
from modsmith.context import ModContext, TargetContext
from modsmith.verifier import VerificationResult, verify_generated_project


# ---------------------------------------------------------------------------
# Helpers for building test fixture contexts and trees
# ---------------------------------------------------------------------------

_BASE_CFG = dict(
    mod_id="mymod",
    mod_name="My Mod",
    mod_version="1.0.0",
    group="com.mymod.core",
    package="com.mymod.core",  # deliberately not 'com.example.*'
    main_class="MyMod",        # must match the .java filename written by builder
    authors="tester",
    license="MIT",
    description="Test",
    output_repo_name="MyModRepo",
    targets=[],
)

_FORGE_TARGET = dict(
    loader="forge",
    template="forge-1.20.1",
    branch="forge-1.20.1",
    mc_range="1.20.1",
    minecraft_version="1.20.1",
    minecraft_version_range="[1.20.1,1.20.2)",
)

_FABRIC_TARGET = dict(
    loader="fabric",
    template="fabric-1.21",
    branch="fabric-1.21",
    mc_range="1.21",
    minecraft_version="1.21",
)


def _make_ctx(
    root: Path,
    target_dict: dict | None = None,
    descriptor: TemplateDescriptor | None = None,
) -> TargetContext:
    """Construct a minimal TargetContext pointing to *root* as the output repo."""
    td = target_dict or _FORGE_TARGET
    cfg = ModConfig(**{**_BASE_CFG, "targets": [TargetConfig(**td)]})
    # Override mods_dir so output_repo_dir == root
    mod_ctx = ModContext(
        config=cfg,
        workspace_dir=root.parent / "WORKSPACE",
        templates_dir=root.parent / "MODTEMPLATES",
        mods_dir=root.parent,
    )
    # output_repo_name == "MyModRepo", mods_dir == root.parent  → output_repo_dir == root
    assert mod_ctx.output_repo_dir == root
    return TargetContext(
        mod_ctx=mod_ctx,
        target=TargetConfig(**td),
        descriptor=descriptor,
    )


def _forge_descriptor(recipe_folder: str = "recipes") -> TemplateDescriptor:
    return TemplateDescriptor(
        loader="forge",
        minecraft_version="1.20.1",
        recipe_folder=recipe_folder,
        recipe_format="legacy_1_20",
    )


def _modern_descriptor() -> TemplateDescriptor:
    return TemplateDescriptor(
        loader="fabric",
        minecraft_version="1.21",
        recipe_folder="recipe",
        recipe_format="modern_1_21",
    )


def _legacy_recipe(name: str = "minecraft:gunpowder") -> dict:
    return {
        "type": "minecraft:crafting_shaped",
        "pattern": ["CCC"],
        "key": {"C": {"item": "minecraft:charcoal"}},
        "result": {"item": name, "count": 1},
    }


def _modern_recipe(name: str = "minecraft:gunpowder") -> dict:
    return {
        "type": "minecraft:crafting_shaped",
        "pattern": ["CCC"],
        "key": {"C": "minecraft:charcoal"},
        "result": {"id": name, "count": 1},
    }


MINIMAL_FORGE_JAVA = """\
package com.mymod.core;

import net.minecraftforge.fml.common.Mod;

@Mod("mymod")
public class MyMod {
    public MyMod() {
        // Entrypoint
    }
}
"""

MINIMAL_FORGE_MODS_TOML = """\
modLoader="javafml"
loaderVersion="[47,)"
license="MIT"

[[dependencies.mymod]]
    modId="forge"
    type="required"
    versionRange="[47,)"
    ordering="NONE"
    side="BOTH"

[[mods]]
    modId="mymod"
    version="1.0.0"
    displayName="My Mod"
"""


class _ForgeProjectBuilder:
    """Fluent builder that constructs a minimal but valid Forge 1.20.1 project tree."""

    def __init__(self, root: Path):
        self.root = root

    # --- Gradle wrapper -------------------------------------------------------

    def with_gradle_wrapper(self) -> "_ForgeProjectBuilder":
        (self.root / "gradlew.bat").write_text("@echo off\n", encoding="utf-8")
        (self.root / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        jar_dir = self.root / "gradle" / "wrapper"
        jar_dir.mkdir(parents=True, exist_ok=True)
        (jar_dir / "gradle-wrapper.jar").write_bytes(b"PK fake jar")
        (jar_dir / "gradle-wrapper.properties").write_text("", encoding="utf-8")
        return self

    # --- Recipe ---------------------------------------------------------------

    def with_recipe(
        self,
        folder: str = "recipes",
        recipe: dict | None = None,
        filename: str = "recipe1.json",
    ) -> "_ForgeProjectBuilder":
        d = self.root / "src/main/resources/data/mymod" / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text(
            json.dumps(recipe or _legacy_recipe()), encoding="utf-8"
        )
        return self

    # --- Java entrypoint ------------------------------------------------------

    def with_java(
        self,
        content: str = MINIMAL_FORGE_JAVA,
        pkg: str = "com/mymod/core",
        filename: str = "MyMod.java",
    ) -> "_ForgeProjectBuilder":
        d = self.root / "src/main/java" / pkg
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text(content, encoding="utf-8")
        return self

    # --- Metadata -------------------------------------------------------------

    def with_mods_toml(
        self, content: str = MINIMAL_FORGE_MODS_TOML
    ) -> "_ForgeProjectBuilder":
        d = self.root / "src/main/resources/META-INF"
        d.mkdir(parents=True, exist_ok=True)
        (d / "mods.toml").write_text(content, encoding="utf-8")
        return self

    def build_valid(self) -> "_ForgeProjectBuilder":
        return (
            self.with_gradle_wrapper()
            .with_recipe()
            .with_java()
            .with_mods_toml()
        )


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------


class VerifierTestBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # output_repo_dir == tmp/MyModRepo
        self.repo_dir = Path(self._tmp.name) / "MyModRepo"
        self.repo_dir.mkdir()
        self.builder = _ForgeProjectBuilder(self.repo_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def ctx(
        self,
        target_dict: dict | None = None,
        descriptor: TemplateDescriptor | None = None,
    ) -> TargetContext:
        return _make_ctx(
            self.repo_dir,
            target_dict=target_dict,
            descriptor=descriptor or _forge_descriptor(),
        )

    def run_verify(
        self,
        target_dict: dict | None = None,
        descriptor: TemplateDescriptor | None = None,
    ) -> VerificationResult:
        return verify_generated_project(
            self.repo_dir, self.ctx(target_dict=target_dict, descriptor=descriptor)
        )


# ---------------------------------------------------------------------------
# Test 1 — valid Forge 1.20.1 project passes
# ---------------------------------------------------------------------------


class TestValidForgeProject(VerifierTestBase):

    def test_valid_forge_project_passes(self):
        self.builder.build_valid()
        result = self.run_verify()
        self.assertEqual(result.errors, [], msg="\n".join(result.errors))
        self.assertTrue(result.ok)


# ---------------------------------------------------------------------------
# Test 2 — missing expected recipe folder
# ---------------------------------------------------------------------------


class TestMissingRecipeFolder(VerifierTestBase):

    def test_missing_recipe_folder_errors(self):
        self.builder.with_gradle_wrapper().with_java().with_mods_toml()
        # No recipe folder written at all
        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("recipe folder not found" in e.lower() or "Expected recipe folder" in e
                for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 3 — wrong sibling recipe folder with JSON files
# ---------------------------------------------------------------------------


class TestWrongRecipeFolderSibling(VerifierTestBase):

    def test_wrong_recipe_folder_sibling_errors(self):
        # Expected folder is "recipes", but create "recipe" with JSON files instead
        self.builder.with_gradle_wrapper().with_java().with_mods_toml()
        # Create the correct folder (empty) + wrong folder with json
        (self.repo_dir / "src/main/resources/data/mymod/recipes").mkdir(parents=True, exist_ok=True)
        wrong = self.repo_dir / "src/main/resources/data/mymod/recipe"
        wrong.mkdir(parents=True, exist_ok=True)
        (wrong / "stray.json").write_text("{}", encoding="utf-8")

        result = self.run_verify()
        # Should error: expected folder is empty AND wrong sibling has json
        self.assertFalse(result.ok)
        error_text = " ".join(result.errors)
        self.assertIn("recipe", error_text)


# ---------------------------------------------------------------------------
# Test 4 — legacy recipe with result.id errors
# ---------------------------------------------------------------------------


class TestLegacyRecipeWithResultId(VerifierTestBase):

    def test_legacy_recipe_result_id_is_error(self):
        bad_recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["CCC"],
            "key": {"C": {"item": "minecraft:charcoal"}},
            "result": {"id": "minecraft:gunpowder", "count": 1},  # should be "item"
        }
        self.builder.build_valid()
        # Overwrite recipe with bad one
        recipe_dir = self.repo_dir / "src/main/resources/data/mymod/recipes"
        (recipe_dir / "recipe1.json").write_text(json.dumps(bad_recipe), encoding="utf-8")

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("result uses 'id'" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 5 — legacy shaped recipe with string key value errors
# ---------------------------------------------------------------------------


class TestLegacyShapedStringKey(VerifierTestBase):

    def test_legacy_shaped_string_key_is_error(self):
        bad_recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["CCC"],
            "key": {"C": "minecraft:charcoal"},  # should be {"item": ...}
            "result": {"item": "minecraft:gunpowder", "count": 1},
        }
        self.builder.build_valid()
        recipe_dir = self.repo_dir / "src/main/resources/data/mymod/recipes"
        (recipe_dir / "recipe1.json").write_text(json.dumps(bad_recipe), encoding="utf-8")

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("plain string" in e and "legacy" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 6 — modern recipe with result.item errors
# ---------------------------------------------------------------------------


class TestModernRecipeWithResultItem(VerifierTestBase):

    def test_modern_recipe_result_item_is_error(self):
        bad_recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["CCC"],
            "key": {"C": "minecraft:charcoal"},
            "result": {"item": "minecraft:gunpowder", "count": 1},  # should be "id"
        }
        # Fabric 1.21 uses modern format
        desc = _modern_descriptor()
        self.builder.with_gradle_wrapper().with_mods_toml()
        recipe_dir = self.repo_dir / "src/main/resources/data/mymod/recipe"
        recipe_dir.mkdir(parents=True, exist_ok=True)
        (recipe_dir / "recipe1.json").write_text(json.dumps(bad_recipe), encoding="utf-8")
        # Fabric java — write minimal file so java check passes (warning only)
        java_dir = self.repo_dir / "src/main/java/com/example/mymod"
        java_dir.mkdir(parents=True, exist_ok=True)

        result = verify_generated_project(
            self.repo_dir,
            _make_ctx(self.repo_dir, target_dict=_FABRIC_TARGET, descriptor=desc),
        )
        self.assertFalse(result.ok)
        self.assertTrue(
            any("result uses 'item'" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 7 — extra Java file errors
# ---------------------------------------------------------------------------


class TestExtraJavaFile(VerifierTestBase):

    def test_extra_java_file_errors(self):
        self.builder.build_valid()
        # Add a second unexpected Java file in the same package dir
        extra = self.repo_dir / "src/main/java/com/mymod/core/Config.java"
        extra.write_text("public class Config {}", encoding="utf-8")

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("Expected exactly 1" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 8 — ExampleMod.java leftover errors
# ---------------------------------------------------------------------------


class TestExampleModLeftover(VerifierTestBase):

    def test_example_mod_java_errors(self):
        self.builder.with_gradle_wrapper().with_recipe().with_mods_toml()
        # Write example file in the Forge default example package
        java_dir = self.repo_dir / "src/main/java/com/example/examplemod"
        java_dir.mkdir(parents=True, exist_ok=True)
        (java_dir / "ExampleMod.java").write_text(
            "public class ExampleMod {}", encoding="utf-8"
        )

        result = self.run_verify()
        self.assertFalse(result.ok)
        # Verifier should flag the example package dir and/or the wrong file location
        self.assertTrue(
            any(
                "com/example/examplemod" in e or "ExampleMod" in e
                or "exactly 1" in e or "not in the expected" in e
                for e in result.errors
            ),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 9 — Java file in wrong package errors
# ---------------------------------------------------------------------------


class TestJavaFileInWrongPackage(VerifierTestBase):

    def test_java_file_wrong_package_errors(self):
        self.builder.with_gradle_wrapper().with_recipe().with_mods_toml()
        # Write the file in a non-matching package dir (not com/mymod/core)
        wrong_dir = self.repo_dir / "src/main/java/org/wrong"
        wrong_dir.mkdir(parents=True, exist_ok=True)
        (wrong_dir / "MyMod.java").write_text(
            MINIMAL_FORGE_JAVA, encoding="utf-8"
        )

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("expected package path" in e.lower() or "not in the expected" in e
                for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 10 — Forge Java file missing Forge Mod import errors
# ---------------------------------------------------------------------------


class TestForgeMissingModImport(VerifierTestBase):

    def test_forge_missing_mod_import_errors(self):
        bad_java = """\
package com.mymod.core;

// MISSING: import net.minecraftforge.fml.common.Mod;

@Mod("mymod")
public class MyMod {
    public MyMod() {}
}
"""
        self.builder.with_gradle_wrapper().with_recipe().with_mods_toml()
        self.builder.with_java(content=bad_java)

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("missing expected import" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 11 — wrong @Mod mod id errors
# ---------------------------------------------------------------------------


class TestWrongModAnnotation(VerifierTestBase):

    def test_wrong_mod_id_in_annotation_errors(self):
        bad_java = """\
package com.mymod.core;

import net.minecraftforge.fml.common.Mod;

@Mod("wrongid")
public class MyMod {
    public MyMod() {}
}
"""
        self.builder.with_gradle_wrapper().with_recipe().with_mods_toml()
        self.builder.with_java(content=bad_java)

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("@Mod annotation" in e and "mymod" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 12 — metadata missing for Forge errors
# ---------------------------------------------------------------------------


class TestForgeMissingMetadata(VerifierTestBase):

    def test_forge_missing_mods_toml_errors(self):
        self.builder.with_gradle_wrapper().with_recipe().with_java()
        # Deliberately no mods.toml

        result = self.run_verify()
        self.assertFalse(result.ok)
        # Path separators differ by OS; check for the key segment instead
        self.assertTrue(
            any("mods.toml" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 13 — metadata still containing "examplemod"
# ---------------------------------------------------------------------------


class TestMetadataExampleString(VerifierTestBase):

    def test_mods_toml_with_examplemod_errors(self):
        dirty_toml = MINIMAL_FORGE_MODS_TOML + "\n# modId = \"examplemod\"\n"
        self.builder.with_gradle_wrapper().with_recipe().with_java()
        self.builder.with_mods_toml(content=dirty_toml)

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("examplemod" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 14 — missing gradle-wrapper.jar errors
# ---------------------------------------------------------------------------


class TestMissingGradleWrapperJar(VerifierTestBase):

    def test_missing_wrapper_jar_errors(self):
        self.builder.with_gradle_wrapper().with_recipe().with_java().with_mods_toml()
        # Remove the jar
        jar = self.repo_dir / "gradle/wrapper/gradle-wrapper.jar"
        jar.unlink()

        result = self.run_verify()
        self.assertFalse(result.ok)
        self.assertTrue(
            any("gradle-wrapper.jar" in e for e in result.errors),
            result.errors,
        )


# ---------------------------------------------------------------------------
# Test 15 — verifier warnings are collected by generator
# ---------------------------------------------------------------------------


class TestVerifierWarningsCollected(unittest.TestCase):
    """Verifier warnings (not errors) should be forwarded to GenerateResult.warnings."""

    def test_warnings_propagated_to_generate_result(self):
        import json
        from unittest.mock import patch
        from modsmith.verifier import VerificationResult

        # A VerificationResult with no errors but one warning
        fake_vr = VerificationResult(errors=[], warnings=["test warning from verifier"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "WORKSPACE"
            (workspace / "DETAILS").mkdir(parents=True)
            (workspace / "RECIPES").mkdir(parents=True)
            templates_dir = root / "MODTEMPLATES"
            mods_dir = root / "MODS"
            templates_dir.mkdir(parents=True)
            mods_dir.mkdir(parents=True)

            cfg = {
                "mod_id": "testmod",
                "mod_name": "Test Mod",
                "mod_version": "1.0.0",
                "group": "com.example.testmod",
                "package": "com.example.testmod",
                "authors": "tester",
                "license": "MIT",
                "description": "desc",
                "output_repo_name": "TestRepo",
                "targets": [{
                    "loader": "forge",
                    "template": "forge-tmpl",
                    "branch": "forge-1.20.1",
                    "mc_range": "1.20.1",
                    "minecraft_version": "1.20.1",
                    "minecraft_version_range": "[1.20.1,1.20.2)",
                }],
            }
            (workspace / "DETAILS" / "modsmith.json").write_text(
                json.dumps(cfg), encoding="utf-8"
            )
            recipe = {
                "type": "minecraft:crafting_shaped",
                "key": {"C": {"item": "minecraft:charcoal"}},
                "result": {"item": "minecraft:gunpowder", "count": 1},
            }
            (workspace / "RECIPES" / "r.json").write_text(json.dumps(recipe), encoding="utf-8")

            tpl = templates_dir / "forge-tmpl"
            tpl.mkdir()
            desc = {"loader": "forge", "minecraft_version": "1.20.1",
                    "recipe_folder": "recipes", "recipe_format": "legacy_1_20"}
            (tpl / "modsmith-template.json").write_text(json.dumps(desc), encoding="utf-8")

            if shutil.which("git") is None:
                self.skipTest("git required")

            # Patch verifier to return a warning-only result so generation succeeds
            with patch("modsmith.generator.verify_generated_project", return_value=fake_vr):
                from modsmith.generator import generate
                res = generate(workspace, templates_dir, mods_dir)

            self.assertIn("test warning from verifier", res.warnings)


# ---------------------------------------------------------------------------
# Test 16 — generator fails before commit if verifier errors exist
# ---------------------------------------------------------------------------


class TestGeneratorAbortsOnVerifierErrors(unittest.TestCase):
    """If verifier returns errors, generate() must raise GenerateError before committing."""

    def test_generator_raises_generate_error_on_verifier_errors(self):
        import json
        from modsmith.generator import generate, GenerateError
        from modsmith.verifier import VerificationResult

        fake_error_vr = VerificationResult(
            errors=["Injected verifier error"],
            warnings=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "WORKSPACE"
            (workspace / "DETAILS").mkdir(parents=True)
            (workspace / "RECIPES").mkdir(parents=True)
            templates_dir = root / "MODTEMPLATES"
            mods_dir = root / "MODS"
            templates_dir.mkdir(parents=True)
            mods_dir.mkdir(parents=True)

            cfg = {
                "mod_id": "testmod",
                "mod_name": "Test Mod",
                "mod_version": "1.0.0",
                "group": "com.example.testmod",
                "package": "com.example.testmod",
                "authors": "tester",
                "license": "MIT",
                "description": "desc",
                "output_repo_name": "TestRepo",
                "targets": [{
                    "loader": "forge",
                    "template": "forge-tmpl",
                    "branch": "forge-1.20.1",
                    "mc_range": "1.20.1",
                    "minecraft_version": "1.20.1",
                    "minecraft_version_range": "[1.20.1,1.20.2)",
                }],
            }
            (workspace / "DETAILS" / "modsmith.json").write_text(
                json.dumps(cfg), encoding="utf-8"
            )
            recipe = {
                "type": "minecraft:crafting_shaped",
                "key": {"C": {"item": "minecraft:charcoal"}},
                "result": {"item": "minecraft:gunpowder", "count": 1},
            }
            (workspace / "RECIPES" / "r.json").write_text(json.dumps(recipe), encoding="utf-8")

            tpl = templates_dir / "forge-tmpl"
            tpl.mkdir()
            desc = {"loader": "forge", "minecraft_version": "1.20.1",
                    "recipe_folder": "recipes", "recipe_format": "legacy_1_20"}
            (tpl / "modsmith-template.json").write_text(json.dumps(desc), encoding="utf-8")

            if shutil.which("git") is None:
                self.skipTest("git required")

            with patch("modsmith.generator.verify_generated_project", return_value=fake_error_vr):
                with self.assertRaises(GenerateError) as ctx:
                    generate(workspace, templates_dir, mods_dir)

            self.assertIn("Injected verifier error", str(ctx.exception))
            self.assertIn("Post-generation verification failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
