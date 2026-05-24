# ModSmith

**ModSmith** is a local automation tool for generating recipe-only Minecraft mods across
multiple mod loaders and Minecraft version ranges using unpacked mod templates.

## What it does

Define your mod once in a single `modsmith.json` file, place your recipe JSON files in
the workspace, and ModSmith will generate a local Git repository with **one branch per
target** (loader × Minecraft version range). Each branch contains a complete,
root-level Minecraft mod project ready to build with Gradle.

## Initial scope

- **Recipe-only mods** — no custom items, blocks, entities, or non-trivial Java code.
- Supported loaders: **Forge**, **NeoForge**, **Fabric**.
- Automatic recipe format conversion between 1.20.1-style and 1.21+-style.
- Local Git initialization with orphan branches per target.
- No GitHub remote setup — that stays in your hands.

## Requirements

- Python 3.10+
- Git (on `PATH`)
- Java (only needed when building with Gradle, not for generation)

## Quickstart

```sh
# Install in development mode
pip install -e ".[dev]"

# Validate your workspace
python -m modsmith validate

# Generate the output repo
python -m modsmith generate
```

## Workspace layout

```
ModSmith/
├── MODTEMPLATES/               # Place unpacked mod templates here
│   ├── forge-1.20.1/
│   ├── forge-1.21-1.21.1/
│   ├── neoforge-1.21.2-1.21.11/
│   └── fabric-1.21.2-1.21.11/
│
├── WORKSPACE/
│   ├── DETAILS/
│   │   └── modsmith.json       # Mod definition and targets
│   ├── RECIPES/
│   │   └── *.json              # Recipe files (1.20.1 or 1.21+ format)
│   └── README/
│       └── README.md           # Optional README copied into each branch
│
└── MODS/
    └── <output_repo_name>/     # Generated Git repo (one orphan branch per target)
```

## modsmith.json example

```json
{
  "mod_id": "easypeasygunpowder",
  "mod_name": "Easy Peasy Gunpowder",
  "mod_version": "1.1.0",
  "group": "com.ardaryusz.easypeasygunpowder",
  "package": "com.ardaryusz.easypeasygunpowder",
  "authors": "ardaryusz",
  "license": "MIT",
  "description": "Adds two crafting recipes for gunpowder.",
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

Optional field: `"main_class": "EasyPeasyGunpowder"` — if omitted, derived from `mod_name`.

## CLI reference

| Command | Description |
|---------|-------------|
| `modsmith validate` | Validate workspace, templates, and config |
| `modsmith generate` | Generate the output repo with one branch per target |
| `modsmith build` | *(Phase 6)* Build all branches and collect JARs |
| `modsmith clean` | *(Phase 7)* Delete the generated output repo |

Global flags: `--workspace DIR`, `--templates DIR`, `--mods DIR`, `--dry-run`

## JAR naming

Generated JARs follow the pattern:

```
<mod_id>-<mc_range>-<loader>-<mod_version>.jar
```

Example: `easypeasygunpowder-1.20.1-forge-1.1.0.jar`

## Template descriptor (optional)

Each template folder can contain a `modsmith-template.json` file:

```json
{
  "loader": "forge",
  "minecraft_version": "1.20.1",
  "recipe_folder": "recipes",
  "recipe_format": "legacy_1_20",
  "metadata_files": ["src/main/resources/META-INF/mods.toml"],
  "java_mod_import": "net.minecraftforge.fml.common.Mod",
  "uses_generated_metadata": false,
  "jar_loader_suffix": "forge"
}
```

ModSmith will warn loudly if a selected template does not have this file.

## Development

```sh
# Run tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_config.py -v
```

## License

MIT
