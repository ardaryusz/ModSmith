"""Pure helpers for template descriptor inference and defaults.

These functions have no PySide6 dependency and are fully testable without a GUI.
The dialog (``TemplateDescriptorDialog``) imports them to pre-populate form fields.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWN_LOADERS = ("forge", "fabric", "neoforge")

RECIPE_FORMAT_LEGACY = "legacy_pre_1_20_5"
RECIPE_FORMAT_TRANSITIONAL = "transitional_1_20_5_to_1_21_1"
RECIPE_FORMAT_MODERN = "modern_1_21_2_plus"

RECIPE_FORMAT_DISPLAY_TO_STORED = {
    "Legacy (<= 1.20.4)": "legacy_pre_1_20_5",
    "Transitional (1.20.5 - 1.21.1)": "transitional_1_20_5_to_1_21_1",
    "Modern (>= 1.21.2)": "modern_1_21_2_plus",
}
RECIPE_FORMAT_STORED_TO_DISPLAY = {v: k for k, v in RECIPE_FORMAT_DISPLAY_TO_STORED.items()}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse minecraft version string into (major, minor, patch) tuple."""
    if not version_str:
        return 1, 21, 2
    parts = version_str.strip().split(".")
    try:
        major = int(parts[0]) if len(parts) >= 1 else 1
        minor = int(parts[1]) if len(parts) >= 2 else 0
        patch = int(parts[2]) if len(parts) >= 3 else 0
        return major, minor, patch
    except (ValueError, IndexError):
        return 1, 21, 2


def recipe_format_for_minecraft_version(version: str) -> str:
    """Return the recommended recipe format string for *version*.

    Rules:
    - <= 1.20.4 -> "legacy_pre_1_20_5"
    - 1.20.5 - 1.21.1 -> "transitional_1_20_5_to_1_21_1"
    - >= 1.21.2 -> "modern_1_21_2_plus"
    """
    if not version:
        return RECIPE_FORMAT_MODERN

    major, minor, patch = parse_version(version)
    if major < 1 or (major == 1 and minor < 20) or (major == 1 and minor == 20 and patch <= 4):
        return RECIPE_FORMAT_LEGACY
    elif major == 1 and minor == 20:  # 1.20.5, 1.20.6
        return RECIPE_FORMAT_TRANSITIONAL
    elif major == 1 and minor == 21 and patch <= 1:  # 1.21, 1.21.1
        return RECIPE_FORMAT_TRANSITIONAL
    else:  # >= 1.21.2
        return RECIPE_FORMAT_MODERN


def resolve_recipe_format_string(raw_format: str, mc_version: str) -> str:
    """Resolve raw format string (with backward compatibility) to the new stored name."""
    if not raw_format:
        return recipe_format_for_minecraft_version(mc_version)
    
    if raw_format == "legacy_1_20":
        if not mc_version:
            return RECIPE_FORMAT_LEGACY
        major, minor, patch = parse_version(mc_version)
        if major < 1 or (major == 1 and minor < 20) or (major == 1 and minor == 20 and patch <= 4):
            return RECIPE_FORMAT_LEGACY
        else:
            return RECIPE_FORMAT_TRANSITIONAL
    elif raw_format == "modern_1_21":
        if not mc_version:
            return RECIPE_FORMAT_MODERN
        major, minor, patch = parse_version(mc_version)
        if major == 1 and minor == 21 and patch <= 1:
            return RECIPE_FORMAT_TRANSITIONAL
        elif major > 1 or (major == 1 and minor > 21) or (major == 1 and minor == 21 and patch >= 2):
            return RECIPE_FORMAT_MODERN
        else:
            return RECIPE_FORMAT_TRANSITIONAL

    if raw_format in (RECIPE_FORMAT_LEGACY, RECIPE_FORMAT_TRANSITIONAL, RECIPE_FORMAT_MODERN):
        return raw_format
    return recipe_format_for_minecraft_version(mc_version)


def recipe_folder_for_minecraft_version(version: str) -> str:
    """Return the recommended recipe folder name for *version*.

    Rules:
    - ``1.21`` or higher → ``"recipe"``
    - ``1.20.x`` or lower → ``"recipes"``
    - Unparseable or empty → ``"recipe"`` (safe default)
    """
    if not version:
        return "recipe"

    parts = version.strip().split(".")
    try:
        major = int(parts[0]) if parts else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return "recipe"

    if major > 1 or (major == 1 and minor >= 21):
        return "recipe"
    return "recipes"


def infer_template_descriptor_defaults(template_folder_name: str) -> dict:
    """Infer sensible ``modsmith-template.json`` defaults from a folder name.

    Folder names follow the convention ``<loader>-<mc_version>`` (e.g.
    ``forge-1.20.1``, ``fabric-1.21.1``, ``neoforge-1.21.4``).

    Parameters
    ----------
    template_folder_name:
        The bare folder name (not a full path).  Extra path components are
        stripped automatically.

    Returns
    -------
    dict
        A dictionary with keys matching the ``TemplateDescriptor`` fields that
        the dialog exposes:

        ``loader``, ``minecraft_version``, ``recipe_format``,
        ``recipe_folder``, ``jar_loader_suffix``.

        Fields that cannot be inferred are returned as empty strings so the
        caller can show them as blank inputs.
    """
    # Strip any path separators — we only care about the bare name
    name = template_folder_name.strip().replace("\\", "/").split("/")[-1]

    loader = ""
    minecraft_version = ""

    # Try to match "<loader>-<mc_version>" — loader must be a known value
    # and mc_version must look like a dotted number string.
    for known in KNOWN_LOADERS:
        prefix = known + "-"
        if name.lower().startswith(prefix):
            remainder = name[len(prefix):]
            # Accept remainder if it looks like a version (digits and dots)
            if re.match(r"^\d+(\.\d+)*$", remainder):
                loader = known
                minecraft_version = remainder
                break

    recipe_format = recipe_format_for_minecraft_version(minecraft_version)
    recipe_folder = recipe_folder_for_minecraft_version(minecraft_version)
    jar_loader_suffix = loader  # default suffix matches loader name

    return {
        "loader": loader,
        "minecraft_version": minecraft_version,
        "recipe_format": recipe_format,
        "recipe_folder": recipe_folder,
        "jar_loader_suffix": jar_loader_suffix,
    }
