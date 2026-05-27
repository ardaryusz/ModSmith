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

# Recipe format names (must match backend TemplateDescriptor schema)
RECIPE_FORMAT_LEGACY = "legacy_1_20"
RECIPE_FORMAT_MODERN = "modern_1_21"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def recipe_format_for_minecraft_version(version: str) -> str:
    """Return the recommended recipe format string for *version*.

    Rules:
    - ``1.21`` or higher → ``"modern_1_21"``
    - ``1.20.x`` or lower → ``"legacy_1_20"``
    - Unparseable or empty → ``"modern_1_21"`` (safe default)

    Parameters
    ----------
    version:
        A dotted Minecraft version string such as ``"1.20.1"`` or ``"1.21.4"``.

    Returns
    -------
    str
        One of ``RECIPE_FORMAT_MODERN`` or ``RECIPE_FORMAT_LEGACY``.
    """
    if not version:
        return RECIPE_FORMAT_MODERN

    parts = version.strip().split(".")
    try:
        major = int(parts[0]) if parts else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return RECIPE_FORMAT_MODERN

    if major > 1 or (major == 1 and minor >= 21):
        return RECIPE_FORMAT_MODERN
    return RECIPE_FORMAT_LEGACY


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
