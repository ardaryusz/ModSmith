"""Pure utility functions for Workspace Screen logic and derivations."""

from __future__ import annotations

import re
from pathlib import Path
from modsmith.config import load_template_descriptor


def derive_pascal_case(mod_name: str) -> str:
    """Derive PascalCase Java identifier from mod name.

    Rules:
    - Split on whitespace, symbols, and invalid Java identifier characters.
    - Title-case each word.
    - If the first character is a digit/number, remove leading numbers until
      a valid letter/underscore starts it.
    - If empty, fallback to 'ExampleMod'.
    """
    if not mod_name:
        return "ExampleMod"

    # Tokenize on any sequence of non-alphanumeric characters
    tokens = re.split(r"[^A-Za-z0-9]+", mod_name)
    parts = []
    for token in tokens:
        if token:
            parts.append(token[0].upper() + token[1:])

    result = "".join(parts)
    # Strip leading digits
    result = re.sub(r"^\d+", "", result)

    if not result:
        return "ExampleMod"
    return result


def derive_mc_range(mc_version: str) -> str:
    """Derive mc_range from MC version (e.g. '1.20.1' -> '1.20')."""
    parts = mc_version.strip().split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return mc_version.strip()


def make_exact_patch_range(mc_version: str) -> str:
    """Generate exact patch version range, e.g. '[1.20.1,1.20.2)'."""
    version = mc_version.strip()
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        patch = int(parts[2])
        parts[2] = str(patch + 1)
        next_ver = ".".join(parts)
        return f"[{version},{next_ver})"
    except ValueError:
        return f"[{version},{version}_next)"


def make_same_minor_range(mc_version: str) -> str:
    """Generate same minor version range, e.g. '[1.20.1,1.21)'."""
    version = mc_version.strip()
    parts = version.split(".")
    while len(parts) < 2:
        parts.append("0")
    try:
        minor = int(parts[1])
        parts[1] = str(minor + 1)
        next_ver = f"{parts[0]}.{parts[1]}"
        return f"[{version},{next_ver})"
    except ValueError:
        return f"[{version},{version}_next)"


def make_inclusive_range(from_ver: str, through_ver: str) -> str:
    """Generate inclusive custom range, e.g. '[1.20.1,1.20.4]'."""
    return f"[{from_ver.strip()},{through_ver.strip()}]"


def parse_version_range(vrange: str, mc_version: str) -> tuple[str, str, str]:
    """Parse version range into compatibility type and custom From/Through bounds.

    Returns:
        (compatibility_type, from_val, through_val)
    """
    vrange = vrange.strip().replace(" ", "")
    mc_version = mc_version.strip()

    if not vrange:
        return ("Exact patch version only", "", "")

    if vrange == make_exact_patch_range(mc_version):
        return ("Exact patch version only", "", "")

    if vrange == make_same_minor_range(mc_version):
        return ("Same minor version", "", "")

    # Clean brackets and parentheses for custom bounds extraction
    cleaned = vrange.lstrip("[").rstrip(")]")
    parts = cleaned.split(",")
    if len(parts) == 2:
        return ("Inclusive custom range", parts[0], parts[1])
    elif len(parts) == 1 and parts[0]:
        return ("Inclusive custom range", parts[0], parts[0])

    return ("Exact patch version only", "", "")


def infer_from_template(template_name: str, templates_dir: Path) -> dict:
    """Infer target values based on a template name and its directory."""
    res = {
        "loader": "",
        "minecraft_version": "",
        "branch": "",
        "mc_range": "",
    }
    if not template_name:
        return res

    desc = None
    t_path = templates_dir / template_name
    if t_path.is_dir():
        try:
            desc = load_template_descriptor(t_path)
        except Exception:
            pass

    if desc:
        res["loader"] = desc.loader or ""
        res["minecraft_version"] = desc.minecraft_version or ""

    # Inferences from template name prefix
    if not res["loader"]:
        for prefix in ["fabric", "neoforge", "forge"]:
            if template_name.lower().startswith(prefix + "-") or template_name.lower() == prefix:
                res["loader"] = prefix
                break

    # Inferences for MC version from template name
    if not res["minecraft_version"]:
        m = re.search(r"\d+\.\d+(?:\.\d+)?", template_name)
        if m:
            res["minecraft_version"] = m.group(0)

    # Defaults fallback
    loader = res["loader"] or "fabric"
    mc_ver = res["minecraft_version"] or "1.21"

    res["loader"] = loader
    res["minecraft_version"] = mc_ver
    res["branch"] = f"{loader}-{mc_ver}"
    res["mc_range"] = derive_mc_range(mc_ver)

    return res
