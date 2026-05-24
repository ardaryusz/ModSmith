# Development Guide

This guide describes how to set up ModSmith for local development, run tests, build binaries, and manage releases.

## Local Environment Setup

### 1. Create a Python Virtual Environment
Initialize a clean environment to isolate dependencies:
```bash
python -m venv venv
```
Activate it in PowerShell:
```powershell
.\venv\Scripts\activate
```
Or in Command Prompt:
```cmd
.\venv\Scripts\activate.bat
```

### 2. Install ModSmith in Editable Mode
Install the packages and all development/testing dependencies:
```bash
pip install -e ".[dev]"
```

---

## Running Tests

We use `pytest` for unit testing and validation routines.

To run all tests:
```bash
py -m pytest tests/ -v
```

To run a specific test suite:
```bash
py -m pytest tests/test_config.py -v
```

---

## Building Executables & Installers

ModSmith provides PowerShell scripts under `scripts/` to orchestrate packaging.

### 1. Compiling `modsmith.exe`
The executable is compiled using PyInstaller:
```powershell
.\scripts\build_exe.ps1
```
This cleans prior artifacts and produces a standalone folder package inside `dist/ModSmith/`.

### 2. Compiling the Setup Installer (`ModSmithSetup.exe`)
The installer compiles the files into a standalone setup wizard using NSIS (Nullsoft Scriptable Install System):
```powershell
.\scripts\build_installer.ps1
```
This compiles the executable, packs resources, and writes the output setup file to `dist/installer/ModSmithSetup.exe`.

---

## Git Ignore Policy

To prevent local workspace data, secrets, or temporary compilation files from polluting the public git repository, the following paths are strictly gitignored:
* `MODS/`
* `MODTEMPLATES/`
* `WORKSPACE/`
* `dist/`
* `build/`
* `venv/`
* `*.spec` (excluding `modsmith.spec`)

Do **not** commit templates, customized recipes, compiled `.jar` files, or installer builds to the main project repository.

---

## Release Process

When preparing a new release of ModSmith:

1. **Bump Version:**
   Update the version strings in:
   * `setup.py` / project metadata
   * `installer/ModSmithInstaller.nsi` (`PRODUCT_VERSION` definition)
   * `modsmith/__init__.py` or version files.
2. **Execute Tests:**
   Run the test suite (`py -m pytest tests/ -v`) to ensure no regressions exist.
3. **Build the Installer:**
   Run `.\scripts\build_installer.ps1` to produce the fresh `ModSmithSetup.exe`.
4. **Git Tag:**
   Commit the version bump and tag the commit:
   ```bash
   git add .
   git commit -m "chore: bump version to vX.Y.Z"
   git tag -a vX.Y.Z -m "Release version X.Y.Z"
   git push origin main --tags
   ```
5. **Publish Releases:**
   Upload `dist/installer/ModSmithSetup.exe` to the GitHub Releases section matching the tagged version.
