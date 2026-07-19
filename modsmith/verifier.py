"""Post-generation verification for recipe-only mod projects.

Public API
----------
- ``VerificationResult``         — dataclass: errors, warnings, ok
- ``verify_generated_project``   — inspect a generated branch root and return a result
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modsmith.context import TargetContext
from modsmith.recipes import RecipeFormat


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Carries errors and warnings from a single branch verification pass."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True only when there are no errors (warnings are allowed)."""
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Loader → expected @Mod import
_LOADER_MOD_IMPORT: dict[str, str] = {
    "forge": "net.minecraftforge.fml.common.Mod",
    "neoforge": "net.neoforged.fml.common.Mod",
}

# Known example / template identifiers that must not appear in generated files
_TEMPLATE_IDENTS = (
    "ExampleMod",
    "examplemod",
    "EXAMPLE_BLOCK",
    "EXAMPLE_ITEM",
    "CreativeModeTab",
    "DeferredRegister",
    "Config.SPEC",
)

# Well-known example package directory fragments that are unambiguously leftover
# template code -- these are NOT part of any legitimate mod package.
_EXAMPLE_PACKAGES = (
    "com/example/examplemod",  # Forge / NeoForge default
    "com/example/ExampleMod",  # variant capitalisation
    "example/examplemod",      # some Fabric templates
    "examplemod",              # flat example package
)

# Metadata locations per loader
_FORGE_META = Path("src/main/resources/META-INF/mods.toml")
_NEOFORGE_META_PRIMARY = Path("src/main/templates/META-INF/neoforge.mods.toml")
_NEOFORGE_META_FALLBACK = Path("src/main/resources/META-INF/neoforge.mods.toml")
_FABRIC_META = Path("src/main/resources/fabric.mod.json")

# Strings that must NOT appear in metadata files
_META_EXAMPLE_STRINGS = ("examplemod", "Example Mod", "YourNameHere", "com.example.examplemod")

# Java source size warning threshold (lines)
_JAVA_LINE_WARN_THRESHOLD = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recipe_format(ctx: TargetContext) -> RecipeFormat:
    """Resolve the expected recipe format for this target."""
    from modsmith.recipes import resolve_recipe_format
    raw_fmt = ctx.descriptor.recipe_format if ctx.descriptor else None
    return resolve_recipe_format(raw_fmt, ctx.minecraft_version)


def _is_tag_ingredient(value: Any) -> bool:
    """Return True if *value* is a tag ingredient object (not a plain item)."""
    if isinstance(value, dict):
        return "tag" in value and "item" not in value
    return False


# ---------------------------------------------------------------------------
# Verification sections
# ---------------------------------------------------------------------------


def _verify_recipe_folder(
    repo_root: Path,
    ctx: TargetContext,
    result: VerificationResult,
) -> None:
    """Check 1 + 2: recipe folder path and recipe file content."""
    mod_id = ctx.mod_ctx.mod_id
    expected_folder = ctx.recipe_folder
    wrong_folder = "recipe" if expected_folder == "recipes" else "recipes"

    recipe_base = repo_root / "src" / "main" / "resources" / "data" / mod_id
    expected_dir = recipe_base / expected_folder
    wrong_dir = recipe_base / wrong_folder

    # 1a — expected folder must exist
    if not expected_dir.is_dir():
        result.errors.append(
            f"Expected recipe folder not found: {expected_dir.relative_to(repo_root)}"
        )
        return  # nothing more to check if folder is absent

    # 1b — wrong sibling folder containing JSON files is an error
    if wrong_dir.is_dir() and list(wrong_dir.glob("*.json")):
        result.errors.append(
            f"Wrong recipe folder '{wrong_folder}' contains JSON files "
            f"(expected '{expected_folder}'). "
            f"Check recipe_folder in the template descriptor."
        )

    # 2 — at least one .json file
    recipe_files = sorted(expected_dir.glob("*.json"))
    if not recipe_files:
        result.errors.append(
            f"No recipe JSON files found in: {expected_dir.relative_to(repo_root)}"
        )
        return

    fmt = _recipe_format(ctx)

    for rfile in recipe_files:
        try:
            data = json.loads(rfile.read_text(encoding="utf-8"))
        except Exception as exc:
            result.errors.append(f"Cannot parse recipe '{rfile.name}': {exc}")
            continue

        rtype = data.get("type", "")
        _verify_recipe_content(rfile.name, data, rtype, fmt, result)


def _verify_recipe_content(
    filename: str,
    data: dict,
    rtype: str,
    fmt: RecipeFormat,
    result: VerificationResult,
) -> None:
    """Verify a single parsed recipe dict against the expected format."""
    result_obj = data.get("result", {})

    if isinstance(result_obj, dict):
        if fmt == RecipeFormat.LEGACY_PRE_1_20_5:
            if "id" in result_obj and "item" not in result_obj:
                result.errors.append(
                    f"Recipe '{filename}': result uses 'id' (modern) but expected 'item' "
                    f"(legacy_pre_1_20_5 format)."
                )
        elif fmt in (RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1, RecipeFormat.MODERN_1_21_2_PLUS):
            if "item" in result_obj and "id" not in result_obj:
                result.errors.append(
                    f"Recipe '{filename}': result uses 'item' (legacy) but expected 'id' "
                    f"({fmt.value} format)."
                )

    if "minecraft:crafting_shaped" in rtype:
        keys = data.get("key", {})
        if isinstance(keys, dict):
            for k, v in keys.items():
                if _is_tag_ingredient(v):
                    continue  # tags are fine in both formats
                if isinstance(v, dict) and set(v.keys()) != {"item"}:
                    continue  # complex are fine
                
                if fmt in (RecipeFormat.LEGACY_PRE_1_20_5, RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1):
                    if isinstance(v, str):
                        result.errors.append(
                            f"Recipe '{filename}': shaped key '{k}' is a plain string "
                            f"(modern style) but target format is {fmt.value}."
                        )
                elif fmt == RecipeFormat.MODERN_1_21_2_PLUS:
                    if isinstance(v, dict) and set(v.keys()) == {"item"}:
                        result.errors.append(
                            f"Recipe '{filename}': shaped key '{k}' is an object "
                            f"(legacy style) but target format is modern_1_21_2_plus."
                        )

    if "minecraft:crafting_shapeless" in rtype:
        ingredients = data.get("ingredients", [])
        if isinstance(ingredients, list):
            for ing in ingredients:
                if _is_tag_ingredient(ing):
                    continue
                if isinstance(ing, dict) and set(ing.keys()) != {"item"}:
                    continue
                
                if fmt in (RecipeFormat.LEGACY_PRE_1_20_5, RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1):
                    if isinstance(ing, str):
                        result.errors.append(
                            f"Recipe '{filename}': shapeless ingredient is a plain string "
                            f"(modern style) but target format is {fmt.value}."
                        )
                elif fmt == RecipeFormat.MODERN_1_21_2_PLUS:
                    if isinstance(ing, dict) and set(ing.keys()) == {"item"}:
                        result.errors.append(
                            f"Recipe '{filename}': shapeless ingredient is an object "
                            f"(legacy style) but target format is modern_1_21_2_plus."
                        )


def _verify_java_sources(
    repo_root: Path,
    ctx: TargetContext,
    result: VerificationResult,
) -> None:
    """Check 3: Java source cleanliness for a recipe-only mod."""
    loader = ctx.loader.lower()
    java_root = repo_root / "src" / "main" / "java"

    if not java_root.is_dir():
        # Fabric entrypoints may live elsewhere; treat as warning only
        if loader == "fabric":
            result.warnings.append("src/main/java not found (Fabric — may be expected).")
        else:
            result.errors.append("src/main/java directory not found.")
        return

    # Gather all .java files
    all_java = list(java_root.rglob("*.java"))

    # Resolve package / main_class early — needed for both the example-pkg check and later
    package = ctx.mod_ctx.package
    main_class = ctx.mod_ctx.main_class

    # Check for leftover example packages.
    # Skip any path that is a legitimate prefix of the mod's own package path.
    own_pkg_path = package.replace(".", "/")
    for ep in _EXAMPLE_PACKAGES:
        ep_dir = java_root / Path(ep)
        if ep_dir.exists() and ep_dir.is_dir():
            if not own_pkg_path.startswith(ep) and not ep.startswith(own_pkg_path):
                result.errors.append(
                    f"Example package directory still present: "
                    f"src/main/java/{ep}"
                )

    # Exactly one .java file expected
    if len(all_java) == 0:
        if loader == "fabric":
            result.warnings.append("No .java files found in src/main/java (Fabric).")
        else:
            result.errors.append("No .java files found in src/main/java.")
        return
    if len(all_java) > 1:
        extras = [str(f.relative_to(repo_root)) for f in all_java]
        result.errors.append(
            f"Expected exactly 1 .java file but found {len(all_java)}: "
            + ", ".join(extras)
        )

    # Determine the expected file path
    expected_java = java_root / Path(package.replace(".", "/")) / f"{main_class}.java"

    for jf in all_java:
        # Check it is in the right location
        if jf.resolve() != expected_java.resolve():
            result.errors.append(
                f"Java file '{jf.relative_to(repo_root)}' is not in the expected "
                f"package path for '{package}.{main_class}'."
            )

        try:
            content = jf.read_text(encoding="utf-8")
        except Exception as exc:
            result.errors.append(f"Cannot read Java file '{jf.name}': {exc}")
            continue

        lines = content.splitlines()

        # Warn if suspiciously large
        if len(lines) > _JAVA_LINE_WARN_THRESHOLD:
            result.warnings.append(
                f"Java file '{jf.name}' is {len(lines)} lines long "
                f"(expected < {_JAVA_LINE_WARN_THRESHOLD} for a recipe-only mod)."
            )

        # Check for template identifiers
        for ident in _TEMPLATE_IDENTS:
            if ident in content:
                result.errors.append(
                    f"Java file '{jf.name}' still contains template identifier: '{ident}'."
                )

        # Loader-specific import and annotation checks (skip Fabric for now)
        if loader in _LOADER_MOD_IMPORT:
            expected_import = _LOADER_MOD_IMPORT[loader]
            import_stmt = f"import {expected_import};"
            # Check that the import appears as an actual statement (not in a comment)
            has_import = any(
                line.lstrip().startswith(import_stmt)
                for line in lines
                if not line.lstrip().startswith("//")
            )
            if not has_import:
                result.errors.append(
                    f"Java file '{jf.name}' is missing expected import: "
                    f"'import {expected_import};'"
                )

            mod_id = ctx.mod_ctx.mod_id
            # Accept @Mod("modid") directly ...
            direct_annotation = f'@Mod("{mod_id}")'
            # ... or @Mod(ClassName.MODID) + MODID = "modid"
            modid_const = f'"{mod_id}"'
            if direct_annotation not in content and modid_const not in content:
                result.errors.append(
                    f"Java file '{jf.name}': @Mod annotation does not reference "
                    f"mod id '{mod_id}'."
                )


def _verify_metadata(
    repo_root: Path,
    ctx: TargetContext,
    result: VerificationResult,
) -> None:
    """Check 4: loader-specific metadata file presence and content."""
    loader = ctx.loader.lower()

    if loader == "forge":
        meta = repo_root / _FORGE_META
        if not meta.exists():
            result.errors.append(
                f"Forge metadata not found: {_FORGE_META}"
            )
        else:
            _check_meta_example_strings(meta, result)

    elif loader == "neoforge":
        primary = repo_root / _NEOFORGE_META_PRIMARY
        fallback = repo_root / _NEOFORGE_META_FALLBACK
        meta = primary if primary.exists() else (fallback if fallback.exists() else None)
        if meta is None:
            result.warnings.append(
                "NeoForge metadata not found "
                f"(checked {_NEOFORGE_META_PRIMARY} and {_NEOFORGE_META_FALLBACK})."
            )
        else:
            _check_meta_example_strings(meta, result)

    elif loader == "fabric":
        meta = repo_root / _FABRIC_META
        if not meta.exists():
            result.errors.append(
                f"Fabric metadata not found: {_FABRIC_META}"
            )
        else:
            _check_meta_example_strings(meta, result)


def _check_meta_example_strings(meta_path: Path, result: VerificationResult) -> None:
    """Emit errors for any known example placeholder strings still in *meta_path*."""
    try:
        content = meta_path.read_text(encoding="utf-8")
    except Exception as exc:
        result.warnings.append(f"Cannot read metadata file '{meta_path.name}': {exc}")
        return
    for s in _META_EXAMPLE_STRINGS:
        if s in content:
            result.errors.append(
                f"Metadata file '{meta_path.name}' still contains example string: '{s}'."
            )


def _verify_gradle_wrapper(
    repo_root: Path,
    result: VerificationResult,
) -> None:
    """Check 5: Gradle wrapper scripts and the wrapper JAR."""
    has_bat = (repo_root / "gradlew.bat").exists()
    has_sh = (repo_root / "gradlew").exists()
    if not has_bat and not has_sh:
        result.errors.append(
            "No Gradle wrapper script found (expected 'gradlew.bat' or 'gradlew')."
        )

    wrapper_jar = repo_root / "gradle" / "wrapper" / "gradle-wrapper.jar"
    if not wrapper_jar.exists():
        result.errors.append(
            "Gradle wrapper JAR not found: gradle/wrapper/gradle-wrapper.jar. "
            "Generated project will not be buildable."
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _verify_no_mixins(
    repo_root: Path,
    ctx: TargetContext,
    result: VerificationResult,
) -> None:
    """Check 6: verify no project-owned Mixin artifacts exist in generated project."""
    # 1. No mixins key in fabric.mod.json
    fabric_json = repo_root / "src" / "main" / "resources" / "fabric.mod.json"
    if fabric_json.exists():
        try:
            with open(fabric_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "mixins" in data:
                result.errors.append("fabric.mod.json contains forbidden top-level 'mixins' key.")
        except Exception as exc:
            result.errors.append(f"Cannot parse fabric.mod.json: {exc}")

    # 2. No *.mixins.json or *.refmap.json files
    res_dirs = [
        repo_root / "src" / "main" / "resources",
        repo_root / "src" / "client" / "resources",
    ]
    for rdir in res_dirs:
        if rdir.is_dir():
            for f in rdir.rglob("*"):
                if f.is_file():
                    n_lower = f.name.lower()
                    if n_lower.endswith(".mixins.json") or (n_lower.endswith(".refmap.json") and not n_lower.startswith("minecraft")):
                        result.errors.append(f"Forbidden Mixin/refmap resource file present: {f.relative_to(repo_root)}")

    # 3. No Mixin source classes
    src_dir = repo_root / "src"
    if src_dir.is_dir():
        for f in src_dir.rglob("*"):
            if f.is_file() and f.suffix in (".java", ".kt"):
                parts_lower = [p.lower() for p in f.parts]
                if "mixin" in parts_lower or "mixins" in parts_lower or "examplemixin" in f.name.lower():
                    result.errors.append(f"Forbidden Mixin source file present: {f.relative_to(repo_root)}")
                else:
                    try:
                        content = f.read_text(encoding="utf-8")
                        if "org.spongepowered.asm.mixin" in content:
                            result.errors.append(f"Source file '{f.relative_to(repo_root)}' contains Sponge Mixin imports.")
                    except Exception:
                        pass


def verify_generated_project(
    repo_root: Path,
    ctx: TargetContext,
) -> VerificationResult:
    """Inspect a generated target branch directory and return a :class:`VerificationResult`.

    Checks performed
    ----------------
    1. Recipe folder path (correct name, no wrong sibling with JSON files)
    2. Recipe file content (format-appropriate result/key/ingredient fields)
    3. Java source cleanliness (one file, correct package, no template remnants)
    4. Loader metadata presence and absence of example strings
    5. Gradle wrapper scripts and JAR
    6. Absence of project-owned Mixins
    """
    repo_root = Path(repo_root)
    result = VerificationResult()

    _verify_recipe_folder(repo_root, ctx, result)
    _verify_java_sources(repo_root, ctx, result)
    _verify_metadata(repo_root, ctx, result)
    _verify_gradle_wrapper(repo_root, result)
    _verify_no_mixins(repo_root, ctx, result)

    return result
