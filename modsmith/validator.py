"""Workspace validation logic for ModSmith.

Public API
----------
- ``ValidationResult``   — collects errors and warnings from all checks
- ``validate_workspace`` — run every Phase-2 check and return the result

Exit-code contract (enforced by the CLI, not here):
  0 — no errors (warnings are allowed)
  1 — one or more errors
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from modsmith.config import ConfigError, load_mod_config, load_template_descriptor


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Accumulates errors and warnings produced by validate_workspace()."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def add_error(self, message: str) -> None:
        """Append *message* to the error list."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Append *message* to the warning list."""
        self.warnings.append(message)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def ok(self) -> bool:
        """True when there are no errors (warnings do not affect this)."""
        return len(self.errors) == 0


def check_template_no_mixins(template_dir: Path) -> tuple[list[str], list[str]]:
    """Scan a template directory for project-owned Mixin artifacts or configurations.

    Returns a tuple of (safe_remnants, unsafe_remnants).
    - safe_remnants: standard legacy Mixin files/configs that can be automatically normalized.
    - unsafe_remnants: ambiguous or custom Mixin setups requiring hard-fail validation.
    """
    safe: list[str] = []
    unsafe: list[str] = []
    template_dir = Path(template_dir)
    if not template_dir.is_dir():
        return safe, unsafe

    # 1. fabric.mod.json
    fabric_json = template_dir / "src" / "main" / "resources" / "fabric.mod.json"
    if fabric_json.exists():
        try:
            with open(fabric_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "mixins" in data:
                safe.append("fabric.mod.json: mixins")
        except Exception:
            pass

    # 2. Resources (*.mixins.json, *.refmap.json)
    res_dir = template_dir / "src" / "main" / "resources"
    if res_dir.is_dir():
        for f in res_dir.rglob("*"):
            if f.is_file():
                name_lower = f.name.lower()
                if name_lower.endswith(".mixins.json") or (name_lower.endswith(".refmap.json") and not name_lower.startswith("minecraft")):
                    safe.append(str(f.relative_to(template_dir)).replace("\\", "/"))

    # 3. Source files
    src_dir = template_dir / "src"
    if src_dir.is_dir():
        import re
        for f in src_dir.rglob("*"):
            if f.is_file() and f.suffix in (".java", ".kt"):
                rel_path = str(f.relative_to(template_dir)).replace("\\", "/")
                parts_lower = [p.lower() for p in f.parts]
                if "mixin" in parts_lower or "mixins" in parts_lower or "examplemixin" in f.name.lower():
                    safe.append(rel_path)
                else:
                    try:
                        content = f.read_text(encoding="utf-8")
                        if "org.spongepowered.asm.mixin" in content or re.search(r'@Mixin\b', content):
                            # Mixin annotation inside non-mixin package/class is unsafe
                            unsafe.append(f"{rel_path}: Mixin annotation in non-mixin class")
                    except Exception:
                        pass

    # 4. Services & Connectors
    services_dir = template_dir / "src" / "main" / "resources" / "META-INF" / "services"
    if services_dir.is_dir():
        for sfile in services_dir.glob("*mixin*"):
            unsafe.append(str(sfile.relative_to(template_dir)).replace("\\", "/"))

    # 5. Build scripts & manifests
    import re
    for script_name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.properties"):
        sfile = template_dir / script_name
        if sfile.exists():
            try:
                content = sfile.read_text(encoding="utf-8")
                if re.search(r'id\s+[\'"]org\.spongepowered\.mixin[\'"]', content):
                    safe.append(script_name)
                elif (
                    "MixinConfigs" in content
                    or "MixinConnector" in content
                    or "mixin.defaultRefmapName" in content
                    or "outRefMapFile" in content
                    or re.search(r'^\s*mixin\s*\{', content, re.MULTILINE)
                ):
                    unsafe.append(f"{script_name}: custom Mixin configuration")
            except Exception:
                pass

    return safe, unsafe


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------


def validate_workspace(
    workspace_dir: Path,
    templates_dir: Path,
    mods_dir: Path,
    *,
    force: bool = False,
) -> ValidationResult:
    """Run all Phase-2 validation checks and return a :class:`ValidationResult`.

    Checks are ordered so that later checks can rely on earlier ones having
    succeeded (e.g. recipe checks skip when the folder is absent).  Whenever
    a check fails it appends to ``result.errors`` or ``result.warnings`` and
    continues — the full list is always returned.

    Parameters
    ----------
    workspace_dir:
        Absolute path to the ``WORKSPACE/`` root.
    templates_dir:
        Absolute path to the ``MODTEMPLATES/`` root.
    mods_dir:
        Absolute path to the ``MODS/`` root.
    force:
        When ``True``, suppress the "output repo already exists" error (check 15).
    """
    result = ValidationResult()

    # ------------------------------------------------------------------
    # Check 1 — modsmith.json exists
    # ------------------------------------------------------------------
    details_dir = workspace_dir / "DETAILS"
    config_path = details_dir / "modsmith.json"

    if not config_path.exists():
        result.add_error(
            f"modsmith.json not found at: {config_path}"
        )
        # Without a config we cannot continue — return early.
        _check_tool_availability(result)
        return result

    # ------------------------------------------------------------------
    # Check 2 — modsmith.json parses into ModConfig
    # (checks 3–8 are enforced inside load_mod_config / _parse_target)
    # ------------------------------------------------------------------
    config = None
    try:
        config = load_mod_config(config_path)
    except ConfigError as exc:
        result.add_error(str(exc))

    # ------------------------------------------------------------------
    # Config-dependent checks (only when parsing succeeded)
    # ------------------------------------------------------------------
    if config is not None:
        # Check 18 — duplicate branch names
        seen_branches: dict[str, int] = {}
        for i, t in enumerate(config.targets):
            if t.branch in seen_branches:
                result.add_error(
                    f"targets[{i}].branch '{t.branch}' is a duplicate of "
                    f"targets[{seen_branches[t.branch]}].branch."
                )
            else:
                seen_branches[t.branch] = i

        # Check 20 — duplicate (loader, minecraft_version) pairs → warnings only
        seen_loader_version: dict[tuple[str, str], int] = {}
        for i, t in enumerate(config.targets):
            key = (t.loader, t.minecraft_version)
            if key in seen_loader_version:
                result.add_warning(
                    f"targets[{i}] has the same loader+minecraft_version "
                    f"('{t.loader}', '{t.minecraft_version}') as "
                    f"targets[{seen_loader_version[key]}]."
                )
            else:
                seen_loader_version[key] = i

        # Check 21 — duplicate (loader, template) pairs → warnings only
        seen_loader_template: dict[tuple[str, str], int] = {}
        for i, t in enumerate(config.targets):
            key = (t.loader, t.template)
            if key in seen_loader_template:
                result.add_warning(
                    f"targets[{i}] has the same loader+template "
                    f"('{t.loader}', '{t.template}') as "
                    f"targets[{seen_loader_template[key]}]."
                )
            else:
                seen_loader_template[key] = i

        # Check 9 & 10 — template folders exist; descriptor warning if absent
        for i, t in enumerate(config.targets):
            template_dir = templates_dir / t.template
            if not template_dir.is_dir():
                result.add_error(
                    f"targets[{i}]: template folder not found: {template_dir}"
                )
            else:
                # Check 10 — warn if descriptor absent
                desc_path = template_dir / "modsmith-template.json"
                if not desc_path.exists():
                    result.add_warning(
                        f"targets[{i}]: template '{t.template}' has no "
                        "modsmith-template.json — template metadata defaults will be used."
                    )
                else:
                    # Check 11 — parse descriptor if present
                    try:
                        load_template_descriptor(template_dir)
                    except ConfigError as exc:
                        result.add_error(str(exc))

                # Check for project-owned Mixin remnants
                safe_remnants, unsafe_remnants = check_template_no_mixins(template_dir)
                if unsafe_remnants:
                    rem_str = "\n".join(f"- {r}" for r in unsafe_remnants)
                    result.add_error(
                        f"Template '{t.template}' contains unsupported/ambiguous Mixin configuration:\n"
                        f"{rem_str}\n"
                        "Remove all project-owned Mixin usage before generating this template."
                    )
                elif safe_remnants:
                    result.add_warning(
                        f"Template '{t.template}' contains legacy Mixin artifacts; "
                        "they will be removed from the generated recipe-mod branch."
                    )

        # Check 15 — output repo must not already exist (unless --force)
        output_repo_dir = mods_dir / config.output_repo_name
        if not force and output_repo_dir.exists():
            result.add_error(
                f"Output repo already exists: {output_repo_dir}. "
                "Pass --force to override this check."
            )

    # ------------------------------------------------------------------
    # Check 12 & 13 — WORKSPACE/RECIPES/ exists and has ≥1 .json file
    # ------------------------------------------------------------------
    recipes_dir = workspace_dir / "RECIPES"

    if not recipes_dir.is_dir():
        result.add_error(
            f"RECIPES directory not found at: {recipes_dir}"
        )
    else:
        json_files = list(recipes_dir.glob("*.json"))
        if not json_files:
            result.add_error(
                f"RECIPES directory contains no .json files: {recipes_dir}"
            )
        else:
            # Check 14 — every recipe file must be valid JSON
            for recipe_file in json_files:
                try:
                    recipe_file.read_text(encoding="utf-8")
                    json.loads(recipe_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    result.add_error(
                        f"Recipe file is not valid JSON — {recipe_file.name}: {exc}"
                    )
                except OSError as exc:
                    result.add_error(
                        f"Cannot read recipe file {recipe_file.name}: {exc}"
                    )

    # ------------------------------------------------------------------
    # Check readability of files (unreadable files are errors)
    # ------------------------------------------------------------------
    # 1. README
    readme_dir = workspace_dir / "README"
    if readme_dir.is_dir():
        readme_file = readme_dir / "README.md"
        if readme_file.exists():
            try:
                readme_file.read_text(encoding="utf-8")
            except OSError as exc:
                result.add_error(f"Workspace README file is unreadable: {exc}")
        else:
            md_files = list(readme_dir.glob("*.md"))
            if md_files:
                try:
                    md_files[0].read_text(encoding="utf-8")
                except OSError as exc:
                    result.add_error(f"Workspace README file {md_files[0].name} is unreadable: {exc}")

    # 2. LICENSE
    license_dir = workspace_dir / "LICENSE"
    if license_dir.is_dir():
        from modsmith.context import get_license_candidates
        try:
            candidates = get_license_candidates(license_dir)
            for c in candidates:
                try:
                    c.read_bytes()
                except OSError as exc:
                    result.add_error(f"Workspace LICENSE file {c.name} is unreadable: {exc}")
        except Exception as exc:
            result.add_error(f"Workspace LICENSE folder is unreadable: {exc}")

    # 3. Configured Icon
    if config is not None and config.icon:
        import os
        icon_src = workspace_dir / config.icon.replace("/", os.sep)
        if icon_src.exists():
            try:
                icon_src.read_bytes()
            except OSError as exc:
                result.add_error(f"Configured mod icon '{config.icon}' is unreadable: {exc}")

    # ------------------------------------------------------------------
    # Checks 16 & 17 — tool availability on PATH
    # ------------------------------------------------------------------
    _check_tool_availability(result)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_tool_availability(result: ValidationResult) -> None:
    """Append errors/warnings for missing PATH tools (checks 16 & 17)."""
    # Check 16 — git is required
    if shutil.which("git") is None:
        result.add_error(
            "'git' was not found on PATH. Git is required to generate mod repos."
        )

    # Check 17 — java is a warning only
    if shutil.which("java") is None:
        result.add_warning(
            "'java' was not found on PATH. Java is needed to build mods with Gradle, "
            "but is not required for validation or generation."
        )
