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

        # Check 20 — duplicate (loader, mc_range) pairs → warnings only
        seen_loader_range: dict[tuple[str, str], int] = {}
        for i, t in enumerate(config.targets):
            key = (t.loader, t.mc_range)
            if key in seen_loader_range:
                result.add_warning(
                    f"targets[{i}] has the same loader+mc_range "
                    f"('{t.loader}', '{t.mc_range}') as "
                    f"targets[{seen_loader_range[key]}]."
                )
            else:
                seen_loader_range[key] = i

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
