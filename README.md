<div align="center"> <img src="assets/image.png"> </div>

**ModSmith** is a local automation tool for generating simple recipe-only Minecraft mods across Fabric, Forge, and NeoForge using unpacked templates.

---

## Features

- **Multi-loader target generation:** Generate mods for Fabric, Forge, and NeoForge concurrently.
- **Automatic recipe format conversion:** Seamlessly translate recipes between legacy (1.20) and modern (1.21) formats.
- **Isolated Git branches:** Creates clean local Git orphan branches per target to prevent version skew.
- **Project verification:** Automatic generated-project verification, Java package matching, and entrypoint pruning.
- **Gradle build automation:** Build all loader targets in sequence using automated Gradle compilation.
- **Windows installer support:** Package and deploy the tool using an optimized Windows installation setup wizard.

---

## Quick Start

### 1. Install ModSmith

- **Windows Installer (Recommended):** Download and run `modsmith_<version>_<arch>-setup.exe` (e.g., `modsmith_1.0.0_x64-setup.exe`), which automatically configures your workspace folder structure and environment paths.
- **PowerShell One-liner (Latest Release):** Run the following command in an elevated PowerShell session:
  ```powershell
  $repo="ardaryusz/ModSmith"; $rel=irm "https://api.github.com/repos/$repo/releases/latest" -Headers @{ "User-Agent"="modsmith-installer" }; $asset=$rel.assets | ? { $_.name -match 'x64-setup\.exe$' } | select -First 1; if(-not $asset){ throw "No x64-setup.exe asset found in latest release." }; $tmp=Join-Path $env:TEMP $asset.name; iwr $asset.browser_download_url -OutFile $tmp; Start-Process $tmp -Verb RunAs -Wait
  ```
- **From Source:** Clone the repository and run:
  ```bash
  pip install -e ".[dev]"
  ```

### 2. Prepare Workspace Configuration

Create the file `WORKSPACE/DETAILS/modsmith.json` defining your mod details and compilation targets:

```json
{
  "mod_id": "easypeasygunpowder",
  "mod_name": "Easy Peasy Gunpowder",
  "mod_version": "1.1.0",
  "group": "com.ardaryusz.easypeasygunpowder",
  "package": "com.ardaryusz.easypeasygunpowder",
  "authors": "ardaryusz",
  "license": "MIT",
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

### 3. Place Input Files

- Place your custom recipe JSON files under `WORKSPACE/RECIPES/` (either legacy 1.20 or modern 1.21 format).
- Download and place unpacked Minecraft mod MDKs inside `MODTEMPLATES/` (e.g. `MODTEMPLATES/forge-1.20.1`).

### 4. Execute Workflow

Run the sequence of commands in your terminal:

```bash
# 1. Validate configuration, template compatibility, and recipes
modsmith validate

# 2. Overwrite/generate mod projects with proper structures and translated recipes
modsmith generate

# 3. Compile and build final production JAR files
modsmith build
```

Once complete, your compiled mod `.jar` files will be placed inside `WORKSPACE/DIST/`.

---

## Basic Commands

- `modsmith validate` — Run semantic and directory layout check.
- `modsmith generate` — Generate project templates and convert recipes. Add `--force` to overwrite existing.
- `modsmith build` — Check out targets and execute Gradle wrapper build tasks.
- `modsmith clean` — Delete the generated mod projects directory.
- `modsmith home <SUBCOMMAND>` — Manage your ModSmith home directory and workspaces persistently (show, set, unset, open).

> [!WARNING]
> The folders `MODTEMPLATES/`, `WORKSPACE/`, and `MODS/` represent local/user-managed files and compiled build artifacts. These folders are **gitignored** in active source repositories. Do not commit templates, private credentials, or binary outputs to your main project repository.

---

## Full Documentation

Detailed instructions and references are located in the `docs/` folder:

- [Installation Guide](docs/installation.md) — Setup pathways, path layouts, and system prerequisites.
- [Usage Guide](docs/usage.md) — Workflow commands, file layout descriptions, and end-to-end example.
- [CLI Reference](docs/cli.md) — Comprehensive command syntax, global options, and dry runs.
- [Configuration Guide](docs/configuration.md) — Detailed schema and explanations of `modsmith.json`.
- [Template Blueprint Guide](docs/templates.md) — Using `modsmith-template.json` to customize loader MDK templates.
- [Recipe Conversion Reference](docs/recipes.md) — Minecraft recipe formats, shaped/shapeless conversions, and syntax checks.
- [Development Guide](docs/development.md) — Setting up the workspace, running unit tests, and the release cycle.
- [Installer Packaging](docs/installer.md) — PyInstaller and NSIS compilation details and manual checks.
- [Troubleshooting Guide](docs/troubleshooting.md) — Quick solutions to common errors and system locks.

---

## License

This project is licensed under the [GNU General Public License v3.0 (GPLv3)](LICENSE).
