# Configuration (`modsmith.json`)

ModSmith reads your mod definition and compilation targets from `WORKSPACE/DETAILS/modsmith.json`.

## Full Schema Fields

### Top-Level Fields

* **`mod_id`** (Required, string): Lowercase alphanumeric identifier starting with a letter. It represents the internal name of your mod (e.g., `easypeasygunpowder`).
* **`mod_name`** (Required, string): The user-facing name of your mod (e.g., `Easy Peasy Gunpowder`).
* **`mod_version`** (Required, string): Semantic version string of your mod (e.g., `1.1.0`).
* **`group`** (Required, string): The Maven group ID / base package for your code (e.g., `com.ardaryusz.easypeasygunpowder`).
* **`package`** (Required, string): The Java package in which initializer classes are placed (e.g., `com.ardaryusz.easypeasygunpowder`).
* **`authors`** (Required, string): Mod author(s) name.
* **`license`** (Required, string): The software license applied to your mod (e.g., `MIT` or `GPL-3.0-only`).
* **`description`** (Required, string): Short text description of what your mod does.
* **`output_repo_name`** (Required, string): Name of the generated folder under `MODS/` (e.g., `EasyPeasyGunpowder`).
* **`main_class`** (Optional, string): The class name of your mod initializer. If omitted, it will default to the `mod_name` formatted in PascalCase (e.g., `EasyPeasyGunpowder`).
* **`homepage`** (Optional, string): URL pointing to your mod's homepage or website.
* **`issue_tracker`** (Optional, string): URL pointing to where bugs and issues can be reported.
* **`targets`** (Required, array of objects): A list of build configurations representing loaders and Minecraft versions.

### Target-Specific Fields

Each target in the `targets` array contains the following fields:

* **`loader`** (Required, string): The mod loader targeted. Must be one of `fabric`, `forge`, or `neoforge`.
* **`template`** (Required, string): The name of the unpacked folder inside `MODTEMPLATES/` to use as the template.
* **`branch`** (Required, string): The name of the Git branch generated for this target.
* **`mc_range`** (Required, string): Short version descriptor used in the final compiled JAR's filename (e.g., `1.20.1`).
* **`minecraft_version`** (Required, string): The exact Minecraft version targeted (e.g., `1.20.1` or `1.21.1`).
* **`minecraft_version_range`** (Optional, string): The target loader's version boundary specification. Used in metadata files (like `mods.toml` or `neoforge.mods.toml`) to restrict loading (e.g., `[1.20.1,1.20.2)` or `[1.21-beta,)`).

---

## Complete Example

Below is a complete `modsmith.json` defining two targets: Forge for Minecraft 1.20.1 and Fabric for Minecraft 1.21.2:

```json
{
  "mod_id": "easypeasygunpowder",
  "mod_name": "Easy Peasy Gunpowder",
  "mod_version": "1.1.0",
  "group": "com.ardaryusz.easypeasygunpowder",
  "package": "com.ardaryusz.easypeasygunpowder",
  "authors": "ardaryusz",
  "license": "MIT",
  "description": "Adds simple crafting recipes for gunpowder.",
  "homepage": "https://github.com/ardaryusz/EasyPeasyGunpowder",
  "issue_tracker": "https://github.com/ardaryusz/EasyPeasyGunpowder/issues",
  "output_repo_name": "EasyPeasyGunpowder",
  "targets": [
    {
      "loader": "forge",
      "template": "forge-1.20.1",
      "branch": "forge-1.20.1",
      "mc_range": "1.20.1",
      "minecraft_version": "1.20.1",
      "minecraft_version_range": "[1.20.1,1.20.2)"
    },
    {
      "loader": "fabric",
      "template": "fabric-1.21.2-1.21.11",
      "branch": "fabric-1.21.2-1.21.11",
      "mc_range": "1.21.2-1.21.11",
      "minecraft_version": "1.21.2"
    }
  ]
}
```

---

## Supported Loaders

ModSmith supports:
* **`fabric`**
* **`forge`**
* **`neoforge`**
