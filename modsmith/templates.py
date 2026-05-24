"""Template discovery, copying, and Java entrypoint generation."""

from __future__ import annotations

import shutil
from pathlib import Path
from modsmith.context import TargetContext
from modsmith.utils import is_valid_java_package, is_valid_java_identifier


def list_templates(templates_dir: Path) -> list[str]:
    """Return immediate child directory names under templates_dir, sorted alphabetically."""
    templates_dir = Path(templates_dir)
    if not templates_dir.exists() or not templates_dir.is_dir():
        return []
    return sorted([
        child.name for child in templates_dir.iterdir()
        if child.is_dir()
    ])


_GRADLE_WRAPPER_JAR = ("gradle", "wrapper", "gradle-wrapper.jar")


def copy_template(template_dir: Path, dest_dir: Path) -> None:
    """Copy all files/folders from template_dir into dest_dir, excluding specific items.

    Exclusion rules:
    - Directories: ``.git``, ``build``, ``.gradle``, ``run``, ``out`` (and all their contents).
    - Files: all ``*.jar`` files **except** ``gradle/wrapper/gradle-wrapper.jar``, which is
      required by the Gradle wrapper scripts (``gradlew`` / ``gradlew.bat``).  Without this
      file, the generated project cannot run Gradle at all.
    """
    template_dir = Path(template_dir)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    exclude_dirs = {".git", "build", ".gradle", "run", "out"}

    # Walk through the template directory
    for path in template_dir.rglob("*"):
        rel_path = path.relative_to(template_dir)
        # Check if any path segment matches the excluded directories
        if any(part in exclude_dirs for part in rel_path.parts):
            continue

        if path.is_file():
            if path.suffix == ".jar" and rel_path.parts != _GRADLE_WRAPPER_JAR:
                continue
            dest_file = dest_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest_file)
        elif path.is_dir():
            dest_path = dest_dir / rel_path
            dest_path.mkdir(parents=True, exist_ok=True)


def find_java_source_root(repo_root: Path) -> Path | None:
    """Return repo_root/src/main/java, creating it if it doesn't exist."""
    repo_root = Path(repo_root)
    java_dir = repo_root / "src" / "main" / "java"
    try:
        java_dir.mkdir(parents=True, exist_ok=True)
        return java_dir
    except Exception:
        return None


def write_java_entrypoint(repo_root: Path, ctx: TargetContext) -> list[str]:
    """Write minimal Java entrypoint class and delete obvious template example package folders."""
    repo_root = Path(repo_root)
    warnings = []

    java_root = find_java_source_root(repo_root)
    if not java_root:
        warnings.append("Could not find or create Java source root.")
        return warnings

    # Delete obvious template example Java source folders
    for folder in ["com/example", "example", "examplemod"]:
        target_dir = java_root / folder
        if target_dir.exists() and target_dir.is_dir():
            try:
                shutil.rmtree(target_dir)
            except Exception:
                pass

    package = ctx.mod_ctx.package
    main_class = ctx.mod_ctx.main_class
    mod_id = ctx.mod_ctx.mod_id
    loader = ctx.target.loader.lower()

    # Validate package and main class
    if not is_valid_java_package(package):
        warnings.append(f"Invalid Java package name: '{package}'")
    if not is_valid_java_identifier(main_class):
        warnings.append(f"Invalid Java class name: '{main_class}'")

    if loader not in ("forge", "neoforge", "fabric"):
        warnings.append(f"Cannot determine loader import for loader: '{ctx.target.loader}'")

    if warnings:
        return warnings

    # Fabric behavior: skip writing Java file in Phase 4 as per prompt
    if loader == "fabric":
        return []

    # Determine mod loader import & annotation
    if loader == "forge":
        mod_import = "net.minecraftforge.fml.common.Mod"
    elif loader == "neoforge":
        mod_import = "net.neoforged.fml.common.Mod"
    else:
        return warnings

    # Create package folder
    package_dir = java_root / package.replace(".", "/")
    package_dir.mkdir(parents=True, exist_ok=True)

    class_file = package_dir / f"{main_class}.java"
    class_content = f"""package {package};

import {mod_import};

@Mod("{mod_id}")
public class {main_class} {{
    public {main_class}() {{
        // Entrypoint
    }}
}}
"""
    try:
        class_file.write_text(class_content, encoding="utf-8")
    except Exception as e:
        warnings.append(f"Failed to write Java entrypoint file: {e}")

    return warnings
