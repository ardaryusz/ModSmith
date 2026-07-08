"""Recipe loading, format detection, and format conversion for ModSmith.

Public API
----------
- ``RecipeFormat``          — enum: LEGACY_1_20, MODERN_1_21
- ``RecipeError``           — raised on unreadable / invalid recipe files
- ``detect_format``         — infer format from a recipe dict
- ``convert_to_legacy``     — deep-copy a recipe dict converted to 1.20 legacy format
- ``convert_to_modern``     — deep-copy a recipe dict converted to 1.21 modern format
- ``convert_recipe``        — dispatch to either converter based on target format
- ``load_recipes``          — read all *.json files from a directory
- ``write_recipes``         — write converted recipes into the output data tree

Format definitions
------------------
Legacy 1.20 (``LEGACY_1_20``):
  - Shaped key values are objects:    ``"C": {"item": "minecraft:charcoal"}``
  - result uses ``"item"`` field:     ``"result": {"item": "...", "count": N}``
  - Shapeless ingredients are objects: ``[{"item": "minecraft:charcoal"}]``

Modern 1.21 (``MODERN_1_21``):
  - Shaped key values may be strings: ``"C": "minecraft:charcoal"``
  - result uses ``"id"`` field:       ``"result": {"id": "...", "count": N}``
  - Shapeless ingredients may be strings: ``["minecraft:charcoal"]``
"""

from __future__ import annotations

import copy
import json
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class RecipeFormat(Enum):
    """Recognised Minecraft recipe JSON formats."""

    LEGACY_PRE_1_20_5 = "legacy_pre_1_20_5"
    TRANSITIONAL_1_20_5_TO_1_21_1 = "transitional_1_20_5_to_1_21_1"
    MODERN_1_21_2_PLUS = "modern_1_21_2_plus"


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


def infer_format_from_version(version: str) -> RecipeFormat:
    """Infer target recipe format based on minecraft version."""
    major, minor, patch = parse_version(version)
    if major < 1 or (major == 1 and minor < 20) or (major == 1 and minor == 20 and patch <= 4):
        return RecipeFormat.LEGACY_PRE_1_20_5
    elif major == 1 and minor == 20:  # 1.20.5, 1.20.6
        return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1
    elif major == 1 and minor == 21 and patch <= 1:  # 1.21, 1.21.1
        return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1
    else:  # >= 1.21.2
        return RecipeFormat.MODERN_1_21_2_PLUS


def resolve_recipe_format(descriptor_format: str | None, minecraft_version: str) -> RecipeFormat:
    """Resolve RecipeFormat from descriptor string (supporting backward compatibility) and MC version."""
    if not descriptor_format:
        return infer_format_from_version(minecraft_version)

    if descriptor_format == "legacy_1_20":
        if not minecraft_version:
            return RecipeFormat.LEGACY_PRE_1_20_5
        major, minor, patch = parse_version(minecraft_version)
        if major < 1 or (major == 1 and minor < 20) or (major == 1 and minor == 20 and patch <= 4):
            return RecipeFormat.LEGACY_PRE_1_20_5
        else:
            return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1
    elif descriptor_format == "modern_1_21":
        if not minecraft_version:
            return RecipeFormat.MODERN_1_21_2_PLUS
        major, minor, patch = parse_version(minecraft_version)
        if major == 1 and minor == 21 and patch <= 1:
            return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1
        elif major > 1 or (major == 1 and minor > 21) or (major == 1 and minor == 21 and patch >= 2):
            return RecipeFormat.MODERN_1_21_2_PLUS
        else:
            return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1

    try:
        return RecipeFormat(descriptor_format)
    except ValueError:
        return infer_format_from_version(minecraft_version)


class RecipeError(Exception):
    """Raised when a recipe file cannot be read or parsed."""


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_SHAPED = "minecraft:crafting_shaped"
_SHAPELESS = "minecraft:crafting_shapeless"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def detect_format(recipe_dict: dict[str, Any]) -> RecipeFormat:
    """Infer which format *recipe_dict* uses.

    Detection priority (first definitive signal wins):

    1. ``result.id``   → modern or transitional
    2. ``result.item`` → legacy
    3. Shaped key contains a string value → modern
    4. Shaped key contains a simple ``{"item": …}``-only object value → legacy or transitional
    5. Shapeless ingredients contain a string entry → modern
    6. Shapeless ingredients contain a ``{"item": …}``-only entry → legacy or transitional
    7. Ambiguous → modern
    """
    result = recipe_dict.get("result")
    if isinstance(result, dict):
        if "id" in result:
            # Could be modern or transitional. Check keys/ingredients first.
            recipe_type = recipe_dict.get("type", "")
            if recipe_type == _SHAPED:
                key = recipe_dict.get("key", {})
                if isinstance(key, dict):
                    for v in key.values():
                        if isinstance(v, str):
                            return RecipeFormat.MODERN_1_21_2_PLUS
                        if isinstance(v, dict) and set(v.keys()) == {"item"}:
                            return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1
            elif recipe_type == _SHAPELESS:
                ingredients = recipe_dict.get("ingredients", [])
                if isinstance(ingredients, list):
                    for ing in ingredients:
                        if isinstance(ing, str):
                            return RecipeFormat.MODERN_1_21_2_PLUS
                        if isinstance(ing, dict) and set(ing.keys()) == {"item"}:
                            return RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1
            return RecipeFormat.MODERN_1_21_2_PLUS
        if "item" in result:
            return RecipeFormat.LEGACY_PRE_1_20_5

    recipe_type = recipe_dict.get("type", "")

    if recipe_type == _SHAPED:
        key = recipe_dict.get("key", {})
        if isinstance(key, dict):
            for v in key.values():
                if isinstance(v, str):
                    return RecipeFormat.MODERN_1_21_2_PLUS
                if isinstance(v, dict) and set(v.keys()) == {"item"}:
                    return RecipeFormat.LEGACY_PRE_1_20_5

    if recipe_type == _SHAPELESS:
        ingredients = recipe_dict.get("ingredients", [])
        if isinstance(ingredients, list):
            for ing in ingredients:
                if isinstance(ing, str):
                    return RecipeFormat.MODERN_1_21_2_PLUS
                if isinstance(ing, dict) and set(ing.keys()) == {"item"}:
                    return RecipeFormat.LEGACY_PRE_1_20_5

    # Ambiguous — default to modern.
    return RecipeFormat.MODERN_1_21_2_PLUS


# ---------------------------------------------------------------------------
# Internal ingredient helpers
# ---------------------------------------------------------------------------


def _ingredient_to_modern(ingredient: Any) -> Any:
    """Convert a single ingredient value to modern format.

    - Simple ``{"item": "..."}`` → ``"..."``
    - Tags, complex objects, or strings are left unchanged.
    """
    if isinstance(ingredient, dict):
        # Only simplify if the only key is "item" (no tag, no extra fields).
        if set(ingredient.keys()) == {"item"}:
            return ingredient["item"]
    # Already a string, has a tag, or is complex — leave unchanged.
    return ingredient


def _ingredient_to_legacy(ingredient: Any) -> Any:
    """Convert a single ingredient value to legacy format.

    - String ``"minecraft:x"`` → ``{"item": "minecraft:x"}``
    - Objects (tags, complex) are left unchanged.
    """
    if isinstance(ingredient, str):
        return {"item": ingredient}
    return ingredient


# ---------------------------------------------------------------------------
# Result conversion helpers
# ---------------------------------------------------------------------------


def _result_to_modern(result: Any) -> Any:
    """Convert a result object: ``item`` → ``id`` (preserves all other fields)."""
    if not isinstance(result, dict):
        return result
    if "item" not in result:
        return result
    out = dict(result)
    out["id"] = out.pop("item")
    return out


def _result_to_legacy(result: Any) -> Any:
    """Convert a result object: ``id`` → ``item`` (preserves all other fields)."""
    if not isinstance(result, dict):
        return result
    if "id" not in result:
        return result
    out = dict(result)
    out["item"] = out.pop("id")
    return out


# ---------------------------------------------------------------------------
# Public converters
# ---------------------------------------------------------------------------


def convert_to_modern(recipe_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *recipe_dict* converted to the modern format."""
    out: dict[str, Any] = copy.deepcopy(recipe_dict)
    recipe_type = out.get("type", "")

    if "result" in out:
        out["result"] = _result_to_modern(out["result"])

    if recipe_type == _SHAPED:
        key = out.get("key")
        if isinstance(key, dict):
            out["key"] = {k: _ingredient_to_modern(v) for k, v in key.items()}

    elif recipe_type == _SHAPELESS:
        ingredients = out.get("ingredients")
        if isinstance(ingredients, list):
            out["ingredients"] = [_ingredient_to_modern(i) for i in ingredients]

    return out


def convert_to_legacy(recipe_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *recipe_dict* converted to the legacy format."""
    out: dict[str, Any] = copy.deepcopy(recipe_dict)
    recipe_type = out.get("type", "")

    if "result" in out:
        out["result"] = _result_to_legacy(out["result"])

    if recipe_type == _SHAPED:
        key = out.get("key")
        if isinstance(key, dict):
            out["key"] = {k: _ingredient_to_legacy(v) for k, v in key.items()}

    elif recipe_type == _SHAPELESS:
        ingredients = out.get("ingredients")
        if isinstance(ingredients, list):
            out["ingredients"] = [_ingredient_to_legacy(i) for i in ingredients]

    return out


def convert_to_transitional(recipe_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *recipe_dict* converted to the transitional format."""
    out: dict[str, Any] = copy.deepcopy(recipe_dict)
    recipe_type = out.get("type", "")

    # result
    if "result" in out:
        out["result"] = _result_to_modern(out["result"])

    if recipe_type == _SHAPED:
        key = out.get("key")
        if isinstance(key, dict):
            out["key"] = {k: _ingredient_to_legacy(v) for k, v in key.items()}

    elif recipe_type == _SHAPELESS:
        ingredients = out.get("ingredients")
        if isinstance(ingredients, list):
            out["ingredients"] = [_ingredient_to_legacy(i) for i in ingredients]

    return out


def convert_recipe(
    recipe_dict: dict[str, Any],
    target_format: RecipeFormat,
) -> dict[str, Any]:
    """Dispatch to the appropriate converter based on *target_format*."""
    if target_format == RecipeFormat.LEGACY_PRE_1_20_5:
        return convert_to_legacy(recipe_dict)
    elif target_format == RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1:
        return convert_to_transitional(recipe_dict)
    return convert_to_modern(recipe_dict)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_recipes(recipes_dir: Path | str) -> list[tuple[str, dict[str, Any]]]:
    """Read all ``*.json`` files directly under *recipes_dir*, sorted by filename.

    Returns a list of ``(filename, recipe_dict)`` pairs.

    Raises :class:`RecipeError` if any file cannot be read or is not valid JSON.
    """
    recipes_dir = Path(recipes_dir)
    results: list[tuple[str, dict[str, Any]]] = []

    for json_path in sorted(recipes_dir.glob("*.json")):
        try:
            text = json_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RecipeError(
                f"Cannot read recipe file {json_path.name}: {exc}"
            ) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RecipeError(
                f"Invalid JSON in recipe file {json_path.name}: {exc}"
            ) from exc

        results.append((json_path.name, data))

    return results


def write_recipes(
    recipes: list[tuple[str, dict[str, Any]]],
    output_data_dir: Path | str,
    mod_id: str,
    recipe_folder: str,
    target_format: RecipeFormat,
) -> None:
    """Write converted recipes into the standard Minecraft data-pack location.

    Output path per file::

        <output_data_dir>/<mod_id>/<recipe_folder>/<filename>

    Each file is pretty-printed with ``indent=2`` and ends with a trailing
    newline.  Directories are created as needed.

    Parameters
    ----------
    recipes:
        List of ``(filename, recipe_dict)`` pairs as returned by
        :func:`load_recipes`.
    output_data_dir:
        Root data directory, typically
        ``<output_repo_dir>/src/main/resources/data/``.
    mod_id:
        Mod identifier used as the namespace directory.
    recipe_folder:
        Subfolder name — ``"recipe"`` (modern) or ``"recipes"`` (legacy).
    target_format:
        The format to convert each recipe to before writing.
    """
    output_data_dir = Path(output_data_dir)
    dest_dir = output_data_dir / mod_id / recipe_folder
    dest_dir.mkdir(parents=True, exist_ok=True)

    for filename, recipe_dict in recipes:
        converted = convert_recipe(recipe_dict, target_format)
        dest_path = dest_dir / filename
        dest_path.write_text(
            json.dumps(converted, indent=2) + "\n",
            encoding="utf-8",
        )
