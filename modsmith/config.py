"""Configuration dataclasses and loaders for ModSmith.

Public API
----------
- ``ConfigError``          — raised on any parse or validation failure
- ``TargetConfig``         — one entry in the ``targets`` array
- ``ModConfig``            — top-level modsmith.json model
- ``TemplateDescriptor``   — optional per-template modsmith-template.json model
- ``load_mod_config()``    — parse and validate modsmith.json
- ``load_template_descriptor()`` — parse modsmith-template.json (returns None if absent)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modsmith.utils import (
    is_valid_mod_id,
    is_valid_java_identifier,
    is_valid_java_package,
    to_class_name,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when modsmith.json is missing, invalid JSON, or has bad values."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TargetConfig:
    """One entry in the ``targets`` array of modsmith.json."""

    loader: str
    """Mod loader identifier: ``"forge"``, ``"neoforge"``, or ``"fabric"``."""

    template: str
    """Name of the template folder under ``MODTEMPLATES/``."""

    branch: str
    """Git branch name for this target (e.g. ``"forge-1.20.1"``)."""

    mc_range: str
    """Human-readable MC version range label (e.g. ``"1.21-1.21.1"``)."""

    minecraft_version: str
    """Representative MC version string (e.g. ``"1.21.1"``)."""

    minecraft_version_range: str = ""
    """Gradle-style version range (e.g. ``"[1.21,1.21.2)"``). Optional for Fabric."""


@dataclass
class ModConfig:
    """Parsed and validated top-level modsmith.json."""

    mod_id: str
    """Mod identifier — lowercase letters, digits, and underscores only."""

    mod_name: str
    """Human-readable display name (e.g. ``"Easy Peasy Gunpowder"``)."""

    mod_version: str
    """Mod version string (e.g. ``"1.1.0"``)."""

    group: str
    """Maven group / Gradle group ID (e.g. ``"com.ardaryusz.easypeasygunpowder"``)."""

    package: str
    """Java package name for the main entrypoint class."""

    authors: str
    """Author name(s) as a plain string."""

    license: str
    """SPDX licence identifier or full name."""

    description: str
    """Short description of the mod."""

    output_repo_name: str
    """Name of the generated Git repository folder inside ``MODS/``."""

    targets: list[TargetConfig]
    """One or more generation targets."""

    main_class: str = ""
    """PascalCase Java class name. Derived from ``mod_name`` if not set explicitly."""

    homepage: str = ""
    """Optional project homepage URL."""

    issue_tracker: str = ""
    """Optional issue tracker URL."""

    icon: str = ""
    """Optional mod icon path relative to WORKSPACE (e.g. ``"ASSETS/icon.png"``)."""


@dataclass
class TemplateDescriptor:
    """Parsed ``modsmith-template.json`` from a template folder.

    All fields are optional and fall back to sensible defaults so that
    ModSmith can operate (with warnings) even without this file.
    """

    loader: str = ""
    """Mod loader this template targets."""

    minecraft_version: str = ""
    """Representative Minecraft version for this template."""

    recipe_folder: str = "recipe"
    """Relative path segment for recipes inside ``data/<mod_id>/``.
    ``"recipe"`` for 1.21+ (Fabric/Forge/NeoForge), ``"recipes"`` for 1.20.1 Forge."""

    recipe_format: str = "modern_1_21"
    """Recipe JSON format: ``"modern_1_21"`` or ``"legacy_1_20"``."""

    metadata_files: list[str] = field(default_factory=list)
    """Relative paths to mod-metadata files that must be patched (e.g. mods.toml)."""

    java_mod_import: str = ""
    """Fully-qualified ``@Mod`` annotation import for this loader."""

    uses_generated_metadata: bool = False
    """True if the template generates metadata from gradle.properties at build time."""

    jar_loader_suffix: str = ""
    """Loader string used in jar naming (e.g. ``"forge"``). Defaults to ``loader``."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SUPPORTED_LOADERS = frozenset({"forge", "neoforge", "fabric"})


def _require(data: dict[str, Any], key: str, context: str = "modsmith.json") -> Any:
    """Return *data[key]*, raising :class:`ConfigError` if missing or blank."""
    value = data.get(key)
    if value is None:
        raise ConfigError(f"{context}: required field '{key}' is missing.")
    if isinstance(value, str) and not value.strip():
        raise ConfigError(f"{context}: field '{key}' must not be empty.")
    return value


def _parse_target(raw: Any, index: int) -> TargetConfig:
    ctx = f"targets[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{ctx} must be a JSON object, got {type(raw).__name__}.")

    loader = _require(raw, "loader", ctx)
    if loader not in _SUPPORTED_LOADERS:
        raise ConfigError(
            f"{ctx}.loader '{loader}' is not supported. "
            f"Valid loaders: {', '.join(sorted(_SUPPORTED_LOADERS))}."
        )

    return TargetConfig(
        loader=loader,
        template=_require(raw, "template", ctx),
        branch=_require(raw, "branch", ctx),
        mc_range=_require(raw, "mc_range", ctx),
        minecraft_version=_require(raw, "minecraft_version", ctx),
        minecraft_version_range=raw.get("minecraft_version_range", ""),
    )


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_mod_config(path: Path | str) -> ModConfig:
    """Parse and validate *path* (a ``modsmith.json`` file).

    Returns a fully-populated :class:`ModConfig`.

    Raises :class:`ConfigError` on any structural or value problem so that
    callers get one consistent exception type regardless of whether the file
    is missing, malformed JSON, or has invalid field values.
    """
    path = Path(path)

    if not path.exists():
        raise ConfigError(f"modsmith.json not found at: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"{path}: top-level value must be a JSON object, "
            f"got {type(data).__name__}."
        )

    # --- mod_id ---------------------------------------------------------------
    mod_id = _require(data, "mod_id")
    if not is_valid_mod_id(mod_id):
        raise ConfigError(
            f"mod_id '{mod_id}' is invalid: use lowercase letters, digits, "
            "and underscores only, starting with a letter."
        )

    # --- package --------------------------------------------------------------
    package = _require(data, "package")
    if not is_valid_java_package(package):
        raise ConfigError(
            f"package '{package}' is not a valid Java package name. "
            "Use dot-separated lowercase identifiers with at least two segments "
            "(e.g. 'com.example.mymod')."
        )

    # --- main_class: explicit override or derived from mod_name ---------------
    mod_name = _require(data, "mod_name")
    explicit_class = data.get("main_class", "").strip()
    if explicit_class:
        if not is_valid_java_identifier(explicit_class):
            raise ConfigError(
                f"main_class '{explicit_class}' is not a valid Java identifier."
            )
        main_class = explicit_class
    else:
        derived = to_class_name(mod_name)
        if not derived or not is_valid_java_identifier(derived):
            raise ConfigError(
                f"Could not derive a valid Java class name from mod_name '{mod_name}'. "
                "Please add an explicit 'main_class' field to modsmith.json."
            )
        main_class = derived

    # --- targets --------------------------------------------------------------
    raw_targets = _require(data, "targets")
    if not isinstance(raw_targets, list):
        raise ConfigError("targets must be a JSON array.")
    if not raw_targets:
        raise ConfigError("targets must contain at least one entry.")

    targets = [_parse_target(t, i) for i, t in enumerate(raw_targets)]

    return ModConfig(
        mod_id=mod_id,
        mod_name=mod_name,
        mod_version=_require(data, "mod_version"),
        group=_require(data, "group"),
        package=package,
        authors=_require(data, "authors"),
        license=_require(data, "license"),
        description=_require(data, "description"),
        output_repo_name=_require(data, "output_repo_name"),
        targets=targets,
        main_class=main_class,
        homepage=data.get("homepage", ""),
        issue_tracker=data.get("issue_tracker", ""),
        icon=data.get("icon", ""),
    )


def load_template_descriptor(template_dir: Path | str) -> TemplateDescriptor | None:
    """Parse ``modsmith-template.json`` from *template_dir*.

    Returns ``None`` if the file does not exist (the caller should warn).
    Raises :class:`ConfigError` if the file exists but cannot be read or parsed.
    """
    desc_path = Path(template_dir) / "modsmith-template.json"
    if not desc_path.exists():
        return None

    try:
        text = desc_path.read_text(encoding="utf-8")
        raw = json.loads(text)
    except OSError as exc:
        raise ConfigError(f"Cannot read template descriptor {desc_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {desc_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"{desc_path}: top-level value must be a JSON object."
        )

    return TemplateDescriptor(
        loader=raw.get("loader", ""),
        minecraft_version=raw.get("minecraft_version", ""),
        recipe_folder=raw.get("recipe_folder", "recipe"),
        recipe_format=raw.get("recipe_format", "modern_1_21"),
        metadata_files=raw.get("metadata_files", []),
        java_mod_import=raw.get("java_mod_import", ""),
        uses_generated_metadata=raw.get("uses_generated_metadata", False),
        jar_loader_suffix=raw.get("jar_loader_suffix", ""),
    )
