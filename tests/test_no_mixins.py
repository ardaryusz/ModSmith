"""Tests for ModSmith 2.1.2 no-Mixins policy, normalization, entrypoint cleanup, and validation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from modsmith.validator import check_template_no_mixins, validate_workspace
from modsmith.generator import normalize_no_mixins
from modsmith.verifier import verify_generated_project


def test_repository_source_templates_have_zero_mixins():
    """Verify that all source templates in MODTEMPLATES/ contain zero project-owned Mixins."""
    repo_root = Path(__file__).resolve().parent.parent
    templates_dir = repo_root / "MODTEMPLATES"
    assert templates_dir.is_dir(), f"MODTEMPLATES directory not found at {templates_dir}"

    for t_dir in templates_dir.iterdir():
        if t_dir.is_dir():
            safe_remnants, unsafe_remnants = check_template_no_mixins(t_dir)
            assert not safe_remnants, f"Template '{t_dir.name}' contains safe Mixin remnants: {safe_remnants}"
            assert not unsafe_remnants, f"Template '{t_dir.name}' contains unsafe Mixin remnants: {unsafe_remnants}"


def test_normal_java_class_and_valid_entrypoint_survive(tmp_path: Path):
    """Regression test: ExampleMixin is removed, but normal ModInitializer class and valid entrypoint survive."""
    t_dir = tmp_path / "test-repo"
    t_dir.mkdir()

    # Normal class
    mod_dir = t_dir / "src" / "main" / "java" / "com" / "example" / "mod"
    mod_dir.mkdir(parents=True)
    mod_class = mod_dir / "MyMod.java"
    mod_class.write_text("package com.example.mod;\npublic class MyMod {}\n", encoding="utf-8")

    # Mixin class
    mixin_dir = mod_dir / "mixin"
    mixin_dir.mkdir(parents=True)
    mixin_class = mixin_dir / "ExampleMixin.java"
    mixin_class.write_text("package com.example.mod.mixin;\nimport org.spongepowered.asm.mixin.Mixin;\n@Mixin(Object.class)\npublic class ExampleMixin {}\n", encoding="utf-8")

    # fabric.mod.json
    res_dir = t_dir / "src" / "main" / "resources"
    res_dir.mkdir(parents=True)
    fabric_json = res_dir / "fabric.mod.json"
    fabric_json.write_text(json.dumps({
        "schemaVersion": 1,
        "id": "mymod",
        "mixins": ["mymod.mixins.json"],
        "entrypoints": {
            "main": ["com.example.mod.MyMod", "com.example.mod.mixin.ExampleMixin"]
        }
    }, indent=4), encoding="utf-8")

    # Normalize
    normalize_no_mixins(t_dir, "fabric")

    # Assertions
    assert mod_class.exists(), "Normal Java class must survive"
    assert not mixin_class.exists(), "ExampleMixin must be deleted"
    assert not mixin_dir.exists(), "Empty mixin directory must be pruned"

    with open(fabric_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "mixins" not in data
    assert "entrypoints" in data
    assert data["entrypoints"]["main"] == ["com.example.mod.MyMod"]


def test_data_only_fabric_output_has_no_entrypoints(tmp_path: Path):
    """Test that when no Java source files exist, the entire entrypoints key is removed."""
    t_dir = tmp_path / "data-only-repo"
    res_dir = t_dir / "src" / "main" / "resources"
    res_dir.mkdir(parents=True)
    fabric_json = res_dir / "fabric.mod.json"
    fabric_json.write_text(json.dumps({
        "schemaVersion": 1,
        "id": "mymod",
        "entrypoints": {
            "main": ["com.example.mod.NonExistent"]
        }
    }, indent=4), encoding="utf-8")

    normalize_no_mixins(t_dir, "fabric")

    with open(fabric_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "entrypoints" not in data


def test_unsafe_mixin_setup_causes_validation_error(tmp_path: Path):
    """Test that unsafe Mixin setup (@Mixin in normal class or service file) produces unsafe remnants."""
    t_dir = tmp_path / "unsafe-template"
    mod_dir = t_dir / "src" / "main" / "java" / "com" / "example"
    mod_dir.mkdir(parents=True)
    (mod_dir / "NormalClass.java").write_text("package com.example;\nimport org.spongepowered.asm.mixin.Mixin;\n@Mixin(Object.class)\npublic class NormalClass {}\n")

    safe, unsafe = check_template_no_mixins(t_dir)
    assert unsafe == ["src/main/java/com/example/NormalClass.java: Mixin annotation in non-mixin class"]


def test_legacy_runtime_template_warns_and_normalizes(tmp_path: Path):
    """Test that safe legacy Mixin artifacts produce safe remnants for warnings."""
    t_dir = tmp_path / "legacy-template"
    res_dir = t_dir / "src" / "main" / "resources"
    res_dir.mkdir(parents=True)
    (res_dir / "legacy.mixins.json").write_text("{}")

    safe, unsafe = check_template_no_mixins(t_dir)
    assert safe == ["src/main/resources/legacy.mixins.json"]
    assert not unsafe


def test_normalization_idempotency_exact(tmp_path: Path):
    """Test that running normalize_no_mixins twice produces identical directory tree and file bytes."""
    t_dir = tmp_path / "idempotent-repo"
    res_dir = t_dir / "src" / "main" / "resources"
    res_dir.mkdir(parents=True)
    (res_dir / "test.mixins.json").write_text("{}")
    (res_dir / "fabric.mod.json").write_text(json.dumps({"mixins": ["test.mixins.json"]}))

    # 1st normalization
    normalize_no_mixins(t_dir, "fabric")

    def snapshot(root: Path) -> dict[str, bytes]:
        snap = {}
        for p in sorted(root.rglob("*")):
            if p.is_file():
                snap[str(p.relative_to(root))] = p.read_bytes()
        return snap

    snap1 = snapshot(t_dir)

    # 2nd normalization
    normalize_no_mixins(t_dir, "fabric")
    snap2 = snapshot(t_dir)

    assert snap1 == snap2, "Snapshot after 2nd normalization must be 100% identical to 1st"


def test_validator_does_not_reject_access_wideners_or_transformers(tmp_path: Path):
    """Test that access wideners and access transformers are NOT falsely flagged as Mixins."""
    t_dir = tmp_path / "clean-template"
    t_dir.mkdir(parents=True)

    res_dir = t_dir / "src" / "main" / "resources"
    res_dir.mkdir(parents=True)
    (res_dir / "mod.accesswidener").write_text("accessWidener v1 named")

    meta_dir = res_dir / "META-INF"
    meta_dir.mkdir(parents=True)
    (meta_dir / "accesstransformer.cfg").write_text("public net.minecraft.client.Minecraft field_71474_y")

    safe, unsafe = check_template_no_mixins(t_dir)
    assert not safe
    assert not unsafe
