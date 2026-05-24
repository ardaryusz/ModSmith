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

To describe how ModSmith should parse and compile a template, you can place a descriptor file named `modsmith-template.json` at the root of your template folder.

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

* **`loader`** (string): The loader type. Either `fabric`, `forge`, or `neoforge`.
* **`minecraft_version`** (string): The target Minecraft version range or specific version (e.g., `1.20.1`).
* **`recipe_folder`** (string): The resource path suffix where recipe JSON files are located. Usually `recipes` (for 1.20) or `recipe` (for 1.21+).
* **`recipe_format`** (string): The format ModSmith should output for this template. Must be either `legacy_1_20` or `modern_1_21`.
* **`metadata_files`** (array of strings): Relatives paths to configuration files (e.g., `fabric.mod.json`, `mods.toml`) where ModSmith needs to parse and insert mod details during generation.
* **`java_mod_import`** (string): The main Java decorator/annotation/class import representing the entry point of the loader (e.g., `net.minecraftforge.fml.common.Mod`).
* **`uses_generated_metadata`** (boolean): Set to `true` if the template uses a metadata generation plugin rather than standard metadata config files.
* **`jar_loader_suffix`** (string): Suffix added to the compiled JAR.

> [!NOTE]
> If a template lacks a `modsmith-template.json` descriptor, ModSmith will display a warning during the `validate` step. It will then apply robust heuristics based on the presence of common files (like `fabric.mod.json` or `mods.toml`) to determine settings automatically.
