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

    LEGACY_1_20 = "legacy_1_20"
    MODERN_1_21 = "modern_1_21"


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
    """Infer whether *recipe_dict* uses the legacy 1.20 or modern 1.21 format.

    Detection priority (first definitive signal wins):

    1. ``result.id``   → modern
    2. ``result.item`` → legacy
    3. Shaped key contains a string value → modern
    4. Shaped key contains a simple ``{"item": …}``-only object value → legacy
    5. Shapeless ingredients contain a string entry → modern
    6. Shapeless ingredients contain a ``{"item": …}``-only object entry → legacy
    7. Ambiguous → modern (new workspaces default to modern)
    """
    result = recipe_dict.get("result")
    if isinstance(result, dict):
        if "id" in result:
            return RecipeFormat.MODERN_1_21
        if "item" in result:
            return RecipeFormat.LEGACY_1_20

    recipe_type = recipe_dict.get("type", "")

    if recipe_type == _SHAPED:
        key = recipe_dict.get("key", {})
        if isinstance(key, dict):
            for v in key.values():
                if isinstance(v, str):
                    return RecipeFormat.MODERN_1_21
                if isinstance(v, dict) and set(v.keys()) == {"item"}:
                    return RecipeFormat.LEGACY_1_20

    if recipe_type == _SHAPELESS:
        ingredients = recipe_dict.get("ingredients", [])
        if isinstance(ingredients, list):
            for ing in ingredients:
                if isinstance(ing, str):
                    return RecipeFormat.MODERN_1_21
                if isinstance(ing, dict) and set(ing.keys()) == {"item"}:
                    return RecipeFormat.LEGACY_1_20

    # Ambiguous — default to modern.
    return RecipeFormat.MODERN_1_21


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
    """Return a deep copy of *recipe_dict* converted to the 1.21 modern format.

    - Shaped key values: ``{"item": "..."}`` → ``"..."``
    - Shapeless ingredient objects: ``{"item": "..."}`` → ``"..."``
    - Result: ``result.item`` → ``result.id``
    - Tags, complex objects, and unknown fields are preserved.
    """
    out: dict[str, Any] = copy.deepcopy(recipe_dict)
    recipe_type = out.get("type", "")

    # result
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

    # For other recipe types: only result was converted (done above).
    return out


def convert_to_legacy(recipe_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *recipe_dict* converted to the 1.20 legacy format.

    - Shaped key values: ``"..."`` → ``{"item": "..."}``
    - Shapeless ingredient strings: ``"..."`` → ``{"item": "..."}``
    - Result: ``result.id`` → ``result.item``
    - Tags, complex objects, and unknown fields are preserved.
    """
    out: dict[str, Any] = copy.deepcopy(recipe_dict)
    recipe_type = out.get("type", "")

    # result
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

    # For other recipe types: only result was converted (done above).
    return out


def convert_recipe(
    recipe_dict: dict[str, Any],
    target_format: RecipeFormat,
) -> dict[str, Any]:
    """Dispatch to the appropriate converter based on *target_format*.

    Returns an unconverted deep copy when no conversion is needed
    (i.e. the recipe is already in the target format).
    """
    if target_format == RecipeFormat.MODERN_1_21:
        return convert_to_modern(recipe_dict)
    return convert_to_legacy(recipe_dict)


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
