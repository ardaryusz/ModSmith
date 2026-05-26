# Usage Guide

ModSmith separates your configuration and recipes from the generated code, maintaining a clean and robust workspace layout.

## Normal Workflow

The standard local development workflow in ModSmith consists of four simple steps:

```mermaid
graph TD
    A[validate] --> B[generate]
    B --> C[build]
    C --> D[clean]
```

1. **`modsmith validate`**
   Validates the structure of your templates, syntax of your recipes, schema of `modsmith.json`, and ensures development tools like Git are available on your system path.
   
2. **`modsmith generate`**
   Translates your recipes, parses metadata, configures build environments, and generates the mod repository files in the `MODS/` directory.

3. **`modsmith build`**
   Runs the Gradle wrappers in the generated directories to compile the targets, producing final mod `.jar` files in `WORKSPACE/DIST/`.

4. **`modsmith clean`**
   Recursively cleans the generated mod repository directories.

---

## Folder Layout

The following directories reside under your `MODSMITH_HOME` (or the folder from which you execute ModSmith if not set):

* **`MODTEMPLATES/`**
  Stores unpacked Minecraft MDK templates for various loaders and Minecraft versions (e.g., `forge-1.20.1`, `fabric-1.21`). These are used as blueprints when generating your projects.
* **`WORKSPACE/DETAILS/`**
  Contains `modsmith.json`, the main configuration file where you declare metadata, options, and compile targets.
* **`WORKSPACE/RECIPES/`**
  Place all your custom recipe JSON files here. You can use either legacy (1.20) or modern (1.21) recipe formats, and ModSmith will handle conversion.
* **`WORKSPACE/README/`**
  *Optional.* Contains a `README.md` that is automatically copied to the root of each generated mod target branch.
* **`WORKSPACE/DIST/`**
  The target folder where finalized, compiled mod release `.jar` files are copied after a successful `build`.
* **`MODS/`**
  Where the generated mod target repositories are created and managed by ModSmith.

---

## End-to-End Example: Easy Peasy Gunpowder

Here is a conceptual walk-through of creating a mod called **Easy Peasy Gunpowder** which adds a crafting recipe to turn charcoal and sulfur/sugar into gunpowder.

### Step 1: Initialize folders
Create the folder structure (if not using the Windows installer which sets this up automatically):
```
Desktop/ModSmith/
├── MODTEMPLATES/
├── WORKSPACE/
│   ├── DETAILS/
│   ├── RECIPES/
│   └── DIST/
└── MODS/
```

### Step 2: Add Unpacked Templates
Download standard Fabric, Forge, or NeoForge MDKs, unzip them, and place them into `MODTEMPLATES/` (e.g., `MODTEMPLATES/forge-1.20.1`). Make sure the gradle wrapper is present. You can verify that all your templates are valid and ready to use by running `modsmith template list`.

### Step 3: Define Mod Configuration
Create `WORKSPACE/DETAILS/modsmith.json`:
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
  "output_repo_name": "EasyPeasyGunpowder",
  "targets": [
    {
      "loader": "forge",
      "template": "forge-1.20.1",
      "branch": "forge-1.20.1",
      "mc_range": "1.20.1",
      "minecraft_version": "1.20.1",
      "minecraft_version_range": "[1.20.1,1.20.2)"
    }
  ]
}
```

### Step 4: Write Recipe Files
Place a recipe file inside `WORKSPACE/RECIPES/gunpowder.json`:
```json
{
  "type": "minecraft:crafting_shapeless",
  "ingredients": [
    "minecraft:charcoal",
    "minecraft:sugar"
  ],
  "result": {
    "id": "minecraft:gunpowder",
    "count": 4
  }
}
```

### Step 5: Validate, Generate, and Build
Now run the workflow commands:
```bash
modsmith validate
modsmith generate
modsmith build
```

---

## Generated Git Branches

During the `generate` phase, ModSmith initializes a local Git repository inside `MODS/EasyPeasyGunpowder`. 

* **Orphan Branches:** ModSmith creates each configured target on an independent **orphan branch** (e.g., `forge-1.20.1`). There is no common `main` or `master` branch sharing code between targets, preventing version skew.
* **Checked-out State:** Once generation finishes, ModSmith keeps the first configured target checked out in the working directory so you can explore it or run Gradle tasks directly.

---

## DIST Output

After running `modsmith build`, the compiled binary outputs are retrieved from the build directory of each target branch and copied to your `WORKSPACE/DIST/` folder. They follow this naming convention:
```
<mod_id>-<mc_range>-<loader>-<mod_version>.jar
```
For example: `easypeasygunpowder-1.20.1-forge-1.1.0.jar`

---

## Working with the GUI

ModSmith includes a clean, simple, and native desktop GUI for managing your workspace configuration, templates, recipes, and documentation.

### Workspace Config Editor
Under the **Workspace** tab, you can view and edit your active `modsmith.json` configuration inside standard native fields:
* Edit your Mod ID, Name, Version, Maven Group, Package, Authors, License, and multiline Description.
* Real-time input warning validation highlights Mod ID, Package, or Main Class errors in soft red if they violate Java or ModSmith syntax guidelines.
* Add and configure target compiler environments dynamically. You can choose loader branches (`fabric`, `forge`, `neoforge`) and select from available template blueprints via dropdown selectors.
* Clicking **Save Config** automatically saves a local backup (`modsmith.json.bak`) of your prior settings before serializing pretty-printed, UTF-8 encoded JSON to disk.
* Click **Validate Config** to execute backend checks and log validation passes or errors.

### README Editor & Previewer
The **README** tab provides a convenient environment to edit `WORKSPACE/README/README.md`:
* Edit raw Markdown inside a monospace plain-text editor.
* Switch to the **Preview** tab to inspect live compiled HTML formatting (headings, lists, bold/italic, blockquotes) powered by Qt's Markdown engine.
* Easily save modifications or load changes at any point.

### Template Import
In the **Templates** tab, you can easily integrate new templates without navigating filesystem directories manually:
* Click **Add Template**, input the destination folder name (e.g. `fabric-1.21.1`), and select the source directory (such as an unzipped MDK).
* The tool recursively copies files, prompts for confirmation before safely overwriting any conflicting folder, and logs success details while immediately refreshing lists.
