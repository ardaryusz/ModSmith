# CLI Reference

This document describes all CLI options, global flags, subcommands, and usage examples.

> [!NOTE]
> * **If using the pre-compiled installer:** Run `modsmith_cli` in place of `modsmith` in all examples (e.g., `modsmith_cli validate`).
> * **If running from source/development:** Run `python -m modsmith` (e.g., `python -m modsmith validate`).

## Global Options

Global options must be passed **before** the subcommand.

* **`--version`**
  Print the version of ModSmith and exit.
* **`-w, --workspace <path>`**
  Set the path to the workspace directory. Overrides `MODSMITH_HOME`.
* **`-t, --templates <path>`**
  Set the path to the templates directory. Overrides `MODSMITH_HOME`.
* **`-m, --mods <path>`**
  Set the path to the generated mods directory. Overrides `MODSMITH_HOME`.
* **`--dry-run`**
  Print details about what files, directories, branches, or builds would be run without actually modifying them on disk. Can be passed as a global flag (before the command) or a command-local flag (after `generate`, `build`, or `clean`).

> [!TIP]
> You can pass `--dry-run` either globally or locally for the `generate`, `build`, and `clean` commands.
> * **Both positions are supported:**
>   - `modsmith --dry-run generate`
>   - `modsmith generate --dry-run`

---

## Commands

### `validate`
Analyzes your environment, config files, templates, and recipes to ensure everything is valid and ready to generate.
```bash
modsmith validate
```

### `generate`
Generates one or more mod projects in `MODS/<output_repo_name>`.
* **`--force`**: If the target directory already exists, deletes and overwrites it. Without this flag, `generate` will fail if the folder is already present.
```bash
modsmith generate
modsmith generate --force
```

### `build`
Compiles each generated target by checking out its branch and running its Gradle wrapper build.
* **`--branch <name>`**: Build only a specific target branch rather than building all branches configured in `modsmith.json`.
```bash
modsmith build
modsmith build --branch forge-1.20.1
```

### `clean`
Deletes the generated repository under `MODS/<output_repo_name>`.
* **`--force`**: Automatically confirms deletion without interactive prompts.
```bash
modsmith clean
modsmith clean --force
```

### `template`
Manages and lists available mod templates in `MODTEMPLATES/`.
* **`list`**: Scans all template subfolders under `MODTEMPLATES/` and verifies that their descriptors (`modsmith-template.json`) and build wrappers exist and are valid.
```bash
modsmith template list
```

### `home`
Manages the `MODSMITH_HOME` environment variable and directory structures.
* **`show`**: Prints the current effective home folder path and resolved absolute directories.
* **`set <path>`**: Creates the standard subfolders at the target path, and persistently sets the `MODSMITH_HOME` environment variable (Windows only).
* **`unset`**: Persistently deletes the `MODSMITH_HOME` environment variable (Windows only).
* **`open`**: Launches the current effective home directory in your system file explorer.
```bash
modsmith home show
modsmith home set <path>
modsmith home unset
modsmith home open
```

---

## Examples

* **Validate the current workspace setup:**
  ```bash
  modsmith validate
  ```
* **Simulate generating the mod files (Dry Run):**
  ```bash
  modsmith --dry-run generate
  ```
* **Force re-generate the mod project (overwriting existing files):**
  ```bash
  modsmith generate --force
  ```
* **Compile and build all targets:**
  ```bash
  modsmith build
  ```
* **Build only the Forge target branch:**
  ```bash
  modsmith build --branch forge-1.20.1
  ```
* **Interactively delete the generated mod directory:**
  ```bash
  modsmith clean
  ```
* **Force delete the generated mod directory without confirmation:**
  ```bash
  modsmith clean --force
  ```
* **Show the current active workspace home path:**
  ```bash
  modsmith home show
  ```
* **Set the home folder to a custom location:**
  ```bash
  modsmith home set "D:\ModSmithWorkspace"
  ```
* **Open the workspace folder in File Explorer:**
  ```bash
  modsmith home open
  ```
* **List and verify all templates under MODTEMPLATES:**
  ```bash
  modsmith template list
  ```
* **List templates under a custom directory:**
  ```bash
  modsmith --templates "C:\custom\templates" template list
  ```
