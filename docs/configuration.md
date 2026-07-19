# Configuration (`modsmith.json`)

ModSmith reads your mod definition and compilation targets from `WORKSPACE/DETAILS/modsmith.json`. You can manage this file directly as a text file, or use the interactive **Workspace Config Editor** in the ModSmith desktop GUI to edit fields with real-time validation warnings and templates dropdown selection.

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
* **`icon`** (Optional, string): Relative path to a mod icon image under `WORKSPACE/` (e.g. `ASSETS/icon.png`). PNG is recommended. During generation, PNG icons are automatically injected into loader-specific metadata files.
* **`landing_branch`** (Optional, object): Configuration for the repository's GitHub/default presentation branch. If omitted, it defaults to being enabled with the name `main`.
  * **`enabled`** (boolean): Set to `true` to generate the landing branch (default: `true`).
  * **`name`** (string): The Git branch name for the landing branch (default: `main`). Must be a valid Git branch name and must not duplicate any target branch names.
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

Below is a complete `modsmith.json` defining two targets: Forge for Minecraft 1.20.1 and Fabric for Minecraft 1.21.2, along with a custom configured landing branch:

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
  "icon": "ASSETS/icon.png",
  "output_repo_name": "EasyPeasyGunpowder",
  "landing_branch": {
    "enabled": true,
    "name": "main"
  },
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

---

## Repository Hygiene (.gitignore Management)

ModSmith automatically normalizes .gitignore files on every generated branch so that Gradle build artifacts can never be accidentally committed.

### Managed Branches

| Branch | .gitignore policy |
| :----- | :------------------ |
| **Target branches** (fabric, forge, neoforge) | Template .gitignore is copied and then any missing canonical rules are merged in. Existing custom rules and comments are preserved. |
| **Landing branch** | A fully canonical .gitignore is written by ModSmith on every generation (deterministic). |

### Canonical Guaranteed Rules

Every generated branch is guaranteed to ignore:
.idea/, .vscode/, *.iml, out/, .DS_Store, Thumbs.db, .gradle/, uild/, 
un/, logs/, *.class, *.log, hs_err_pid*, 
eplay_pid*

### Custom Template Rules

If your custom template's .gitignore contains a bare *.jar rule, ModSmith automatically appends:

`gitignore
!gradle/wrapper/gradle-wrapper.jar
`

so that the Gradle wrapper JAR remains tracked. Official templates do not contain a bare *.jar rule.

See [usage.md](usage.md#repository-hygiene) for full details.
