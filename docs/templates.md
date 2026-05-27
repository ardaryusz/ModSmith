# Mod Templates

ModSmith relies on template mod development projects to serve as blueprints when generating build targets.

## Template Folders in `MODTEMPLATES`

All blueprints must be placed within the `MODTEMPLATES/` directory.

* **Must be Unpacked:** Zip files or archive files are not supported. Templates must be fully extracted folders.
* **Independent Folder Structuring:** Each template should reside in its own folder (e.g., `MODTEMPLATES/forge-1.20.1`, `MODTEMPLATES/fabric-1.21`).
* **Preserving Gradle Wrappers:** Make sure the Gradle wrapper executable (`gradlew`/`gradlew.bat`) and its companion JAR (`gradle/wrapper/gradle-wrapper.jar`) are kept intact. ModSmith requires these files to execute background compilations during `modsmith build`.
* **Not Bundled by Default:** ModSmith does **not** package official Fabric, Forge, or NeoForge MDKs by default. You need to download these from official mod loader websites, extract them, and place them under `MODTEMPLATES/`.

---

## Template Descriptor (`modsmith-template.json`)

To describe how ModSmith should parse and compile a template, you must place a descriptor file named `modsmith-template.json` at the root of your template folder.

### Full Example Descriptor

Below is an example of a template descriptor for a Forge 1.20.1 template:

```json
{
  "loader": "forge",
  "minecraft_version": "1.20.1",
  "recipe_folder": "recipes",
  "recipe_format": "legacy_1_20",
  "metadata_files": [
    "src/main/resources/META-INF/mods.toml"
  ],
  "java_mod_import": "net.minecraftforge.fml.common.Mod",
  "uses_generated_metadata": false,
  "jar_loader_suffix": "forge"
}
```

### Descriptor Fields

* **`loader`** *(required)* (string): The loader type. One of `fabric`, `forge`, or `neoforge`.
* **`minecraft_version`** *(required)* (string): The target Minecraft version for this template (e.g., `1.20.1`, `1.21.4`).
* **`recipe_folder`** *(required)* (string): The resource path suffix where recipe JSON files are located. Use `recipes` for 1.20.x-style templates, or `recipe` for 1.21+ templates.
* **`recipe_format`** *(required)* (string): The format ModSmith should output for this template.
  * `legacy_1_20` — for 1.20.x Forge/Fabric/NeoForge templates (older recipe path conventions).
  * `modern_1_21` — for 1.21+ templates (new consolidated recipe path).
* **`jar_loader_suffix`** *(required)* (string): Suffix added to the compiled JAR filename (e.g. `forge`, `fabric`, `neoforge`).
* **`metadata_files`** *(optional)* (array of strings): Relative paths to configuration files (e.g., `fabric.mod.json`, `mods.toml`) where ModSmith inserts mod metadata during generation.
* **`java_mod_import`** *(optional)* (string): The main Java decorator/annotation/class import for the loader's entry point (e.g., `net.minecraftforge.fml.common.Mod`).
* **`uses_generated_metadata`** *(optional)* (boolean): Set to `true` if the template uses a metadata generation plugin rather than static metadata config files.

### Recipe Format Guidance

| Minecraft Version | Recommended `recipe_format` | Recommended `recipe_folder` |
|---|---|---|
| 1.20.x (e.g. 1.20.1, 1.20.4) | `legacy_1_20` | `recipes` |
| 1.21+ (e.g. 1.21.1, 1.21.4) | `modern_1_21` | `recipe` |

> [!NOTE]
> If a template lacks a `modsmith-template.json` descriptor, ModSmith will display an error during the `validate` step and mark the template as **ERROR** in the GUI. The GUI can create the descriptor for you automatically — see below.

---

## Template Listing & Verification

You can list all available templates under `MODTEMPLATES/` and verify their configurations using the `modsmith template list` command:

```bash
modsmith template list
```

This scans all template child directories and checks:
- The template name and absolute path.
- The presence and validity of `modsmith-template.json`.
- The parsed details (loader, MC version, recipe configurations, etc.).
- The existence of Gradle wrapper scripts (`gradlew`, `gradlew.bat`) and `gradle-wrapper.jar`.

If any template is missing its descriptor, has invalid JSON, or lacks `gradle-wrapper.jar`, the command reports the errors and exits with a non-zero status code (`1`). Missing scripts like `gradlew` or `gradlew.bat` generate warnings but do not fail the command (exit `0`).


## Importing Templates via GUI

The ModSmith Workbench GUI Templates screen offers a convenient **Add Template** button:
1. Click **Add Template** at the top of the Templates screen.
2. Enter a unique folder name (e.g. `forge-1.20.1`) for your destination template directory under `MODTEMPLATES`.
3. Pick the unpacked source folder representing the downloaded loader MDK/template on your system.
4. ModSmith will recursively copy the folder as-is.
5. If the template folder name already exists, the GUI will prompt you for confirmation before deleting the existing template directory safely (using `safe_delete_tree`) and copying the new MDK.
6. **If `modsmith-template.json` is missing** in the imported template, the GUI asks: *"Create it now?"*  — clicking **Yes** opens the descriptor form pre-filled with inferred values.

---

## Creating and Editing the Descriptor via GUI

The Templates screen has two dedicated buttons for managing `modsmith-template.json`:

### Create Descriptor / Edit Descriptor

1. Select a template row in the table.
2. Click **Create Descriptor** (if the file is missing) or **Edit Descriptor** (if it already exists).
3. A form dialog opens with the following fields:

   | Field | Description |
   |---|---|
   | Loader | `forge`, `fabric`, or `neoforge` |
   | Minecraft Version | e.g. `1.20.1`, `1.21.4` |
   | Recipe Format | `legacy_1_20` or `modern_1_21` |
   | Recipe Folder | Usually `recipes` |
   | JAR Loader Suffix | Suffix in the built JAR filename (usually matches loader) |

4. When **creating**, the form infers defaults from the folder name:
   - `forge-1.20.1` → Loader: forge, Version: 1.20.1, Format: legacy\_1\_20, Suffix: forge
   - `fabric-1.21.1` → Loader: fabric, Version: 1.21.1, Format: modern\_1\_21, Suffix: fabric
   - `neoforge-1.21.1` → Loader: neoforge, Version: 1.21.1, Format: modern\_1\_21, Suffix: neoforge

5. When **editing**, the form is pre-populated with all current values. Advanced fields (`metadata_files`, `java_mod_import`, `uses_generated_metadata`) are preserved as-is.

6. Click **Save** to write `modsmith-template.json` with UTF-8 encoding and `indent=2`.

7. After saving, the Templates table refreshes automatically. A previously **ERROR** row should become **WARNING** or **OK**.

### Open Descriptor JSON

Select a template row and click **Open Descriptor JSON** to open `modsmith-template.json` in your system default editor. If the file does not exist yet, a warning is shown instead.
