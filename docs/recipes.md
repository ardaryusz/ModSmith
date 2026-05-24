# Recipe Formats & Conversion

ModSmith specializes in recipe-only mod automation. It provides transparent conversion between Minecraft versions, meaning you write your recipe definitions once, and ModSmith outputs the correct format based on the target version.

## Recipe-Only Scope

ModSmith targets vanilla and modded recipe systems. Supported recipe categories include:
* **`minecraft:crafting_shaped`**
* **`minecraft:crafting_shapeless`**
* **Non-crafting/Custom Recipes:** Smelting, blasting, smoking, smithing, or mod-specific custom recipe objects. ModSmith converts the main result structure and preserves additional properties transparently.

---

## Minecraft 1.20 vs. Minecraft 1.21 Formats

Minecraft 1.21 introduced significant changes to the built-in recipe engine. The directory names, result schemas, and shaped keys were modified.

### Legacy Format (Minecraft 1.20.x and below)
* **Directory Name:** `data/<modid>/recipes/`
* **Ingredient Structure:** Uses objects wrapping items:
  ```json
  "C": { "item": "minecraft:charcoal" }
  ```
* **Result Structure:** Uses the `item` key inside the result block:
  ```json
  "result": {
    "item": "minecraft:gunpowder",
    "count": 4
  }
}
```

### Modern Format (Minecraft 1.21.x and above)
* **Directory Name:** `data/<modid>/recipe/` (Singular)
* **Ingredient Structure:** Uses direct strings for standard items:
  ```json
  "C": "minecraft:charcoal"
  ```
* **Result Structure:** Uses the `id` key instead of `item` inside the result block:
  ```json
  "result": {
    "id": "minecraft:gunpowder",
    "count": 4
  }
}
```

---

## Code Examples

### Modern Shaped Recipe Input (1.21 Format)
Written in `WORKSPACE/RECIPES/blaster.json`:
```json
{
  "type": "minecraft:crafting_shaped",
  "pattern": [
    "III",
    "I I",
    "III"
  ],
  "key": {
    "I": "minecraft:iron_ingot"
  },
  "result": {
    "id": "minecraft:iron_block",
    "count": 1
  }
}
```

### Legacy Shaped Recipe Output (1.20 Format)
Automatically converted and generated in a Minecraft 1.20 target:
```json
{
  "type": "minecraft:crafting_shaped",
  "pattern": [
    "III",
    "I I",
    "III"
  ],
  "key": {
    "I": {
      "item": "minecraft:iron_ingot"
    }
  },
  "result": {
    "item": "minecraft:iron_block",
    "count": 1
  }
}
```

---

## Preservation of Complex Objects

To avoid breaking advanced functionality, ModSmith respects complex constructs:
* **Item Tags:** If an ingredient refers to a tag (e.g., `{"tag": "minecraft:logs"}`), it is kept intact.
* **Complex Ingredients:** Arrays of options, custom mod keys, and custom recipes are passed through cleanly.

---

## Automated Verification

During both the `validate` and `generate` steps, ModSmith runs built-in checkers to ensure correctness:
* It parses each recipe file to verify it is valid JSON.
* It verifies that the `type` field is declared.
* It ensures required structure details (like `result` objects containing either `item` or `id`) are correct.
* It reports invalid syntax details directly to the CLI, pointing out the exact recipe file with issues.
