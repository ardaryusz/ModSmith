"""Tests for modsmith.recipes (Phase 3 — recipe loading and format conversion).

Coverage:
- detect_format: legacy shaped, modern shaped
- detect_format: legacy shapeless, modern shapeless
- detect_format: ambiguous defaults to modern
- convert_to_modern: shaped legacy → modern
- convert_to_legacy: shaped modern → legacy
- convert_to_modern: shapeless legacy → modern
- convert_to_legacy: shapeless modern → legacy
- tag ingredients are preserved in both directions
- complex ingredient objects are preserved in both directions
- non-crafting recipes: only result.item / result.id is converted
- original input dict is not mutated
- convert_recipe dispatches correctly
- load_recipes: returns sorted filenames
- load_recipes: raises RecipeError on invalid JSON
- write_recipes: writes to correct path with correct content
- write_recipes: output JSON has indent=2 and trailing newline
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from modsmith.recipes import (
    RecipeError,
    RecipeFormat,
    convert_recipe,
    convert_to_legacy,
    convert_to_modern,
    detect_format,
    load_recipes,
    write_recipes,
)

# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures" / "recipes"

# --- shaped -----------------------------------------------------------------

LEGACY_SHAPED: dict[str, Any] = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["CCC", "CCC", "CCC"],
    "key": {
        "C": {"item": "minecraft:charcoal"}
    },
    "result": {"item": "minecraft:gunpowder", "count": 1},
}

MODERN_SHAPED: dict[str, Any] = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["CCC", "CCC", "CCC"],
    "key": {
        "C": "minecraft:charcoal"
    },
    "result": {"id": "minecraft:gunpowder", "count": 1},
}

# --- shapeless --------------------------------------------------------------

LEGACY_SHAPELESS: dict[str, Any] = {
    "type": "minecraft:crafting_shapeless",
    "ingredients": [
        {"item": "minecraft:charcoal"},
        {"item": "minecraft:gunpowder"},
    ],
    "result": {"item": "minecraft:fire_charge", "count": 3},
}

MODERN_SHAPELESS: dict[str, Any] = {
    "type": "minecraft:crafting_shapeless",
    "ingredients": [
        "minecraft:charcoal",
        "minecraft:gunpowder",
    ],
    "result": {"id": "minecraft:fire_charge", "count": 3},
}

# --- tag ingredients --------------------------------------------------------

SHAPED_WITH_TAG: dict[str, Any] = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["LLL"],
    "key": {
        "L": {"tag": "minecraft:logs"}
    },
    "result": {"id": "minecraft:planks", "count": 4},
}

SHAPELESS_WITH_TAG: dict[str, Any] = {
    "type": "minecraft:crafting_shapeless",
    "ingredients": [
        {"tag": "minecraft:logs"},
        "minecraft:stick",
    ],
    "result": {"id": "minecraft:chest", "count": 1},
}

# --- complex ingredients ----------------------------------------------------

SHAPED_COMPLEX: dict[str, Any] = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["AB"],
    "key": {
        "A": {"item": "minecraft:coal", "count": 2},
        "B": {"items": ["minecraft:coal", "minecraft:charcoal"]},
    },
    "result": {"id": "minecraft:torch", "count": 4},
}

SHAPELESS_COMPLEX: dict[str, Any] = {
    "type": "minecraft:crafting_shapeless",
    "ingredients": [
        {"item": "minecraft:coal", "count": 2},
        {"items": ["minecraft:coal", "minecraft:charcoal"]},
    ],
    "result": {"id": "minecraft:torch", "count": 4},
}

# --- non-crafting recipe (smelting) ----------------------------------------

SMELTING_LEGACY: dict[str, Any] = {
    "type": "minecraft:smelting",
    "ingredient": {"item": "minecraft:iron_ore"},
    "result": {"item": "minecraft:iron_ingot", "count": 1},
    "experience": 0.7,
    "cookingtime": 200,
}

SMELTING_MODERN: dict[str, Any] = {
    "type": "minecraft:smelting",
    "ingredient": {"item": "minecraft:iron_ore"},
    "result": {"id": "minecraft:iron_ingot", "count": 1},
    "experience": 0.7,
    "cookingtime": 200,
}

# ---------------------------------------------------------------------------
# Tests — detect_format
# ---------------------------------------------------------------------------


class TestDetectFormat(unittest.TestCase):
    """detect_format identifies the format from recipe content."""

    def test_detect_legacy_shaped(self):
        self.assertEqual(detect_format(LEGACY_SHAPED), RecipeFormat.LEGACY_1_20)

    def test_detect_modern_shaped(self):
        self.assertEqual(detect_format(MODERN_SHAPED), RecipeFormat.MODERN_1_21)

    def test_detect_legacy_shapeless(self):
        self.assertEqual(detect_format(LEGACY_SHAPELESS), RecipeFormat.LEGACY_1_20)

    def test_detect_modern_shapeless(self):
        self.assertEqual(detect_format(MODERN_SHAPELESS), RecipeFormat.MODERN_1_21)

    def test_detect_via_result_id(self):
        """result.id is the most reliable modern signal."""
        recipe = {"type": "minecraft:smelting", "result": {"id": "minecraft:iron_ingot"}}
        self.assertEqual(detect_format(recipe), RecipeFormat.MODERN_1_21)

    def test_detect_via_result_item(self):
        """result.item is the legacy signal."""
        recipe = {"type": "minecraft:smelting", "result": {"item": "minecraft:iron_ingot"}}
        self.assertEqual(detect_format(recipe), RecipeFormat.LEGACY_1_20)

    def test_ambiguous_defaults_to_modern(self):
        """A recipe with no detectable signals should default to modern."""
        recipe = {"type": "minecraft:crafting_shaped", "pattern": [], "key": {}}
        self.assertEqual(detect_format(recipe), RecipeFormat.MODERN_1_21)

    def test_detect_modern_from_fixture_file(self):
        data = json.loads((_FIXTURES / "modern_recipe.json").read_text())
        self.assertEqual(detect_format(data), RecipeFormat.MODERN_1_21)

    def test_detect_legacy_from_fixture_file(self):
        data = json.loads((_FIXTURES / "legacy_recipe.json").read_text())
        self.assertEqual(detect_format(data), RecipeFormat.LEGACY_1_20)


# ---------------------------------------------------------------------------
# Tests — convert_to_modern (shaped)
# ---------------------------------------------------------------------------


class TestConvertToModernShaped(unittest.TestCase):
    """convert_to_modern correctly converts legacy shaped recipes."""

    def setUp(self):
        self.result = convert_to_modern(LEGACY_SHAPED)

    def test_type_preserved(self):
        self.assertEqual(self.result["type"], "minecraft:crafting_shaped")

    def test_pattern_preserved(self):
        self.assertEqual(self.result["pattern"], ["CCC", "CCC", "CCC"])

    def test_key_value_becomes_string(self):
        self.assertEqual(self.result["key"]["C"], "minecraft:charcoal")

    def test_result_item_becomes_id(self):
        self.assertIn("id", self.result["result"])
        self.assertNotIn("item", self.result["result"])
        self.assertEqual(self.result["result"]["id"], "minecraft:gunpowder")

    def test_result_count_preserved(self):
        self.assertEqual(self.result["result"]["count"], 1)

    def test_detect_format_of_output_is_modern(self):
        self.assertEqual(detect_format(self.result), RecipeFormat.MODERN_1_21)


# ---------------------------------------------------------------------------
# Tests — convert_to_legacy (shaped)
# ---------------------------------------------------------------------------


class TestConvertToLegacyShaped(unittest.TestCase):
    """convert_to_legacy correctly converts modern shaped recipes."""

    def setUp(self):
        self.result = convert_to_legacy(MODERN_SHAPED)

    def test_type_preserved(self):
        self.assertEqual(self.result["type"], "minecraft:crafting_shaped")

    def test_pattern_preserved(self):
        self.assertEqual(self.result["pattern"], ["CCC", "CCC", "CCC"])

    def test_key_value_becomes_item_object(self):
        self.assertEqual(self.result["key"]["C"], {"item": "minecraft:charcoal"})

    def test_result_id_becomes_item(self):
        self.assertIn("item", self.result["result"])
        self.assertNotIn("id", self.result["result"])
        self.assertEqual(self.result["result"]["item"], "minecraft:gunpowder")

    def test_result_count_preserved(self):
        self.assertEqual(self.result["result"]["count"], 1)

    def test_detect_format_of_output_is_legacy(self):
        self.assertEqual(detect_format(self.result), RecipeFormat.LEGACY_1_20)


# ---------------------------------------------------------------------------
# Tests — convert_to_modern (shapeless)
# ---------------------------------------------------------------------------


class TestConvertToModernShapeless(unittest.TestCase):
    """convert_to_modern correctly converts legacy shapeless recipes."""

    def setUp(self):
        self.result = convert_to_modern(LEGACY_SHAPELESS)

    def test_type_preserved(self):
        self.assertEqual(self.result["type"], "minecraft:crafting_shapeless")

    def test_ingredients_become_strings(self):
        self.assertEqual(
            self.result["ingredients"],
            ["minecraft:charcoal", "minecraft:gunpowder"],
        )

    def test_result_item_becomes_id(self):
        self.assertIn("id", self.result["result"])
        self.assertNotIn("item", self.result["result"])
        self.assertEqual(self.result["result"]["id"], "minecraft:fire_charge")

    def test_result_count_preserved(self):
        self.assertEqual(self.result["result"]["count"], 3)

    def test_detect_format_of_output_is_modern(self):
        self.assertEqual(detect_format(self.result), RecipeFormat.MODERN_1_21)


# ---------------------------------------------------------------------------
# Tests — convert_to_legacy (shapeless)
# ---------------------------------------------------------------------------


class TestConvertToLegacyShapeless(unittest.TestCase):
    """convert_to_legacy correctly converts modern shapeless recipes."""

    def setUp(self):
        self.result = convert_to_legacy(MODERN_SHAPELESS)

    def test_type_preserved(self):
        self.assertEqual(self.result["type"], "minecraft:crafting_shapeless")

    def test_ingredients_become_objects(self):
        self.assertEqual(
            self.result["ingredients"],
            [{"item": "minecraft:charcoal"}, {"item": "minecraft:gunpowder"}],
        )

    def test_result_id_becomes_item(self):
        self.assertIn("item", self.result["result"])
        self.assertNotIn("id", self.result["result"])
        self.assertEqual(self.result["result"]["item"], "minecraft:fire_charge")

    def test_result_count_preserved(self):
        self.assertEqual(self.result["result"]["count"], 3)

    def test_detect_format_of_output_is_legacy(self):
        self.assertEqual(detect_format(self.result), RecipeFormat.LEGACY_1_20)


# ---------------------------------------------------------------------------
# Tests — tag ingredients preserved
# ---------------------------------------------------------------------------


class TestTagIngredientPreservation(unittest.TestCase):
    """Tag-based ingredients must never be converted to plain strings."""

    def test_shaped_tag_preserved_on_modern_conversion(self):
        result = convert_to_modern(SHAPED_WITH_TAG)
        # Tag should remain as object, not be flattened to string.
        self.assertEqual(result["key"]["L"], {"tag": "minecraft:logs"})

    def test_shaped_tag_preserved_on_legacy_conversion(self):
        result = convert_to_legacy(SHAPED_WITH_TAG)
        self.assertEqual(result["key"]["L"], {"tag": "minecraft:logs"})

    def test_shapeless_tag_preserved_on_modern_conversion(self):
        result = convert_to_modern(SHAPELESS_WITH_TAG)
        # First ingredient is a tag object — must stay as object.
        self.assertEqual(result["ingredients"][0], {"tag": "minecraft:logs"})

    def test_shapeless_tag_preserved_on_legacy_conversion(self):
        result = convert_to_legacy(SHAPELESS_WITH_TAG)
        self.assertEqual(result["ingredients"][0], {"tag": "minecraft:logs"})

    def test_shapeless_string_still_converted_alongside_tag(self):
        """The string ingredient after the tag should still be converted to/from object."""
        # Modern → legacy: "minecraft:stick" should become {"item": "minecraft:stick"}
        result = convert_to_legacy(SHAPELESS_WITH_TAG)
        self.assertEqual(result["ingredients"][1], {"item": "minecraft:stick"})


# ---------------------------------------------------------------------------
# Tests — complex ingredient objects preserved
# ---------------------------------------------------------------------------


class TestComplexIngredientPreservation(unittest.TestCase):
    """Objects with more than just "item" must not be simplified."""

    def test_shaped_complex_item_with_count_preserved(self):
        result = convert_to_modern(SHAPED_COMPLEX)
        # {"item": "minecraft:coal", "count": 2} must stay — not simplified.
        self.assertEqual(result["key"]["A"], {"item": "minecraft:coal", "count": 2})

    def test_shaped_complex_items_list_preserved(self):
        result = convert_to_modern(SHAPED_COMPLEX)
        self.assertEqual(
            result["key"]["B"],
            {"items": ["minecraft:coal", "minecraft:charcoal"]},
        )

    def test_shapeless_complex_item_with_count_preserved(self):
        result = convert_to_modern(SHAPELESS_COMPLEX)
        self.assertEqual(result["ingredients"][0], {"item": "minecraft:coal", "count": 2})

    def test_shapeless_complex_items_list_preserved(self):
        result = convert_to_modern(SHAPELESS_COMPLEX)
        self.assertEqual(
            result["ingredients"][1],
            {"items": ["minecraft:coal", "minecraft:charcoal"]},
        )

    def test_convert_to_legacy_complex_preserves_objects(self):
        result = convert_to_legacy(SHAPED_COMPLEX)
        self.assertEqual(result["key"]["A"], {"item": "minecraft:coal", "count": 2})
        self.assertEqual(
            result["key"]["B"],
            {"items": ["minecraft:coal", "minecraft:charcoal"]},
        )


# ---------------------------------------------------------------------------
# Tests — non-crafting recipes (smelting etc.)
# ---------------------------------------------------------------------------


class TestNonCraftingRecipeConversion(unittest.TestCase):
    """For non-crafting types only result.item/id is converted."""

    def test_smelting_legacy_to_modern_result_id(self):
        result = convert_to_modern(SMELTING_LEGACY)
        self.assertIn("id", result["result"])
        self.assertNotIn("item", result["result"])
        self.assertEqual(result["result"]["id"], "minecraft:iron_ingot")

    def test_smelting_modern_to_legacy_result_item(self):
        result = convert_to_legacy(SMELTING_MODERN)
        self.assertIn("item", result["result"])
        self.assertNotIn("id", result["result"])
        self.assertEqual(result["result"]["item"], "minecraft:iron_ingot")

    def test_smelting_ingredient_not_modified(self):
        """Smelting ingredient should not be touched."""
        result = convert_to_modern(SMELTING_LEGACY)
        self.assertEqual(result["ingredient"], {"item": "minecraft:iron_ore"})

    def test_smelting_extra_fields_preserved(self):
        result = convert_to_modern(SMELTING_LEGACY)
        self.assertAlmostEqual(result["experience"], 0.7)
        self.assertEqual(result["cookingtime"], 200)


# ---------------------------------------------------------------------------
# Tests — no mutation of original
# ---------------------------------------------------------------------------


class TestNoMutation(unittest.TestCase):
    """Converters must not mutate the original recipe dict."""

    def test_convert_to_modern_does_not_mutate(self):
        import copy
        original = copy.deepcopy(LEGACY_SHAPED)
        convert_to_modern(original)
        self.assertEqual(original, LEGACY_SHAPED)

    def test_convert_to_legacy_does_not_mutate(self):
        import copy
        original = copy.deepcopy(MODERN_SHAPED)
        convert_to_legacy(original)
        self.assertEqual(original, MODERN_SHAPED)

    def test_convert_to_modern_shapeless_does_not_mutate(self):
        import copy
        original = copy.deepcopy(LEGACY_SHAPELESS)
        convert_to_modern(original)
        self.assertEqual(original, LEGACY_SHAPELESS)


# ---------------------------------------------------------------------------
# Tests — convert_recipe dispatch
# ---------------------------------------------------------------------------


class TestConvertRecipe(unittest.TestCase):
    """convert_recipe dispatches to the correct converter."""

    def test_dispatch_to_modern(self):
        result = convert_recipe(LEGACY_SHAPED, RecipeFormat.MODERN_1_21)
        self.assertEqual(detect_format(result), RecipeFormat.MODERN_1_21)

    def test_dispatch_to_legacy(self):
        result = convert_recipe(MODERN_SHAPED, RecipeFormat.LEGACY_1_20)
        self.assertEqual(detect_format(result), RecipeFormat.LEGACY_1_20)

    def test_idempotent_modern_to_modern(self):
        result = convert_recipe(MODERN_SHAPED, RecipeFormat.MODERN_1_21)
        self.assertEqual(result["result"]["id"], "minecraft:gunpowder")
        self.assertNotIn("item", result["result"])

    def test_idempotent_legacy_to_legacy(self):
        result = convert_recipe(LEGACY_SHAPED, RecipeFormat.LEGACY_1_20)
        self.assertEqual(result["result"]["item"], "minecraft:gunpowder")
        self.assertNotIn("id", result["result"])


# ---------------------------------------------------------------------------
# Tests — load_recipes
# ---------------------------------------------------------------------------


class TestLoadRecipes(unittest.TestCase):
    """load_recipes reads and sorts recipe files."""

    def test_load_from_fixtures(self):
        recipes = load_recipes(_FIXTURES)
        self.assertGreater(len(recipes), 0)

    def test_returns_list_of_tuples(self):
        recipes = load_recipes(_FIXTURES)
        for name, data in recipes:
            self.assertIsInstance(name, str)
            self.assertIsInstance(data, dict)

    def test_sorted_by_filename(self):
        recipes = load_recipes(_FIXTURES)
        names = [name for name, _ in recipes]
        self.assertEqual(names, sorted(names))

    def test_fixtures_include_modern_and_legacy(self):
        recipes = load_recipes(_FIXTURES)
        names = {name for name, _ in recipes}
        self.assertIn("modern_recipe.json", names)
        self.assertIn("legacy_recipe.json", names)

    def test_load_recipes_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{ not valid json }", encoding="utf-8")
            with self.assertRaises(RecipeError) as ctx:
                load_recipes(tmp)
        self.assertIn("bad.json", str(ctx.exception))

    def test_load_recipes_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipes = load_recipes(tmp)
        self.assertEqual(recipes, [])

    def test_load_recipes_sorted_with_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Write files in non-alphabetical order.
            for name in ("z_recipe.json", "a_recipe.json", "m_recipe.json"):
                (Path(tmp) / name).write_text(
                    json.dumps({"type": "minecraft:crafting_shaped"}), encoding="utf-8"
                )
            recipes = load_recipes(tmp)
        names = [n for n, _ in recipes]
        self.assertEqual(names, ["a_recipe.json", "m_recipe.json", "z_recipe.json"])


# ---------------------------------------------------------------------------
# Tests — write_recipes
# ---------------------------------------------------------------------------


class TestWriteRecipes(unittest.TestCase):
    """write_recipes writes converted recipes to the correct path."""

    def _setup_and_write(
        self,
        tmp: str,
        recipes: list[tuple[str, dict]],
        target_format: RecipeFormat,
        mod_id: str = "testmod",
        recipe_folder: str = "recipe",
    ) -> Path:
        data_dir = Path(tmp) / "data"
        write_recipes(recipes, data_dir, mod_id, recipe_folder, target_format)
        return data_dir / mod_id / recipe_folder

    def test_output_path_is_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self._setup_and_write(
                tmp,
                [("gunpowder.json", LEGACY_SHAPED)],
                RecipeFormat.MODERN_1_21,
            )
            self.assertTrue((dest / "gunpowder.json").exists())

    def test_recipe_folder_name_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            write_recipes(
                [("r.json", LEGACY_SHAPED)],
                data_dir,
                "mymod",
                "recipes",
                RecipeFormat.LEGACY_1_20,
            )
            self.assertTrue((data_dir / "mymod" / "recipes" / "r.json").exists())

    def test_converted_content_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self._setup_and_write(
                tmp,
                [("test.json", LEGACY_SHAPED)],
                RecipeFormat.MODERN_1_21,
            )
            written = json.loads((dest / "test.json").read_text())
        # Key should now be a string (modern format).
        self.assertEqual(written["key"]["C"], "minecraft:charcoal")
        self.assertIn("id", written["result"])

    def test_output_has_indent_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self._setup_and_write(
                tmp,
                [("test.json", MODERN_SHAPED)],
                RecipeFormat.MODERN_1_21,
            )
            raw = (dest / "test.json").read_text(encoding="utf-8")
        # indent=2 means lines start with exactly 2 spaces for top-level fields.
        self.assertTrue(any(line.startswith("  ") for line in raw.splitlines()))

    def test_output_ends_with_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self._setup_and_write(
                tmp,
                [("test.json", MODERN_SHAPED)],
                RecipeFormat.MODERN_1_21,
            )
            raw = (dest / "test.json").read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"), repr(raw[-5:]))

    def test_multiple_recipes_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self._setup_and_write(
                tmp,
                [
                    ("shaped.json", LEGACY_SHAPED),
                    ("shapeless.json", LEGACY_SHAPELESS),
                ],
                RecipeFormat.MODERN_1_21,
            )
            self.assertTrue((dest / "shaped.json").exists())
            self.assertTrue((dest / "shapeless.json").exists())

    def test_directories_created_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            deeply_nested = Path(tmp) / "a" / "b" / "c"
            # Should not raise even though path doesn't exist yet.
            write_recipes(
                [("r.json", MODERN_SHAPED)],
                deeply_nested,
                "mymod",
                "recipe",
                RecipeFormat.MODERN_1_21,
            )
            self.assertTrue((deeply_nested / "mymod" / "recipe" / "r.json").exists())


# ---------------------------------------------------------------------------
# Tests — round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip(unittest.TestCase):
    """Converting to the other format and back must produce the original."""

    def _assert_round_trip(self, original: dict, via: RecipeFormat) -> None:
        import copy
        original = copy.deepcopy(original)
        converted = convert_recipe(original, via)
        back_format = (
            RecipeFormat.LEGACY_1_20
            if via == RecipeFormat.MODERN_1_21
            else RecipeFormat.MODERN_1_21
        )
        recovered = convert_recipe(converted, back_format)
        self.assertEqual(recovered, original)

    def test_shaped_legacy_round_trip_via_modern(self):
        self._assert_round_trip(LEGACY_SHAPED, RecipeFormat.MODERN_1_21)

    def test_shaped_modern_round_trip_via_legacy(self):
        self._assert_round_trip(MODERN_SHAPED, RecipeFormat.LEGACY_1_20)

    def test_shapeless_legacy_round_trip_via_modern(self):
        self._assert_round_trip(LEGACY_SHAPELESS, RecipeFormat.MODERN_1_21)

    def test_shapeless_modern_round_trip_via_legacy(self):
        self._assert_round_trip(MODERN_SHAPELESS, RecipeFormat.LEGACY_1_20)

    def test_smelting_legacy_round_trip_via_modern(self):
        self._assert_round_trip(SMELTING_LEGACY, RecipeFormat.MODERN_1_21)


if __name__ == "__main__":
    unittest.main()
