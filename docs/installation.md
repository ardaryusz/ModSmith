# Installation

This guide covers how to install ModSmith using the Windows installer or set it up from source for development.

## Installing via Windows Installer (Recommended)

The easiest way to get started with ModSmith on Windows is by downloading and running the pre-built installer: `modsmith_<version>_<arch>-setup.exe` (e.g., `modsmith_2.1.3_x64-setup.exe`).

The installer bundles both the **ModSmith GUI** (`modsmith.exe`) and the **CLI** (`modsmith_cli.exe`) into a single distribution. After installation, the **ModSmith** Start Menu shortcut launches the GUI, and the CLI is available from any terminal.

### 2. Quick One-line Install (PowerShell)
You can download and run the latest installer directly from the GitHub releases in one command. Run the following command in an elevated PowerShell session (Run as Administrator):

```powershell
$repo="ardaryusz/ModSmith"; $rel=irm "https://api.github.com/repos/$repo/releases/latest" -Headers @{ "User-Agent"="modsmith-installer" }; $asset=$rel.assets | ? { $_.name -match 'x64-setup\.exe$' } | select -First 1; if(-not $asset){ throw "No x64-setup.exe asset found in latest release." }; $tmp=Join-Path $env:TEMP $asset.name; iwr $asset.browser_download_url -OutFile $tmp; Start-Process $tmp -Verb RunAs -Wait
```

### 3. Safer Expanded Install Script (PowerShell)
For a safer, more readable version of the download and installation script, copy the following block into an elevated PowerShell session:

```powershell
# Define the repository
$repo = "ardaryusz/ModSmith"

# Fetch latest release details from GitHub API
Write-Host "Fetching latest release from GitHub..."
$Headers = @{ "User-Agent" = "modsmith-installer" }
$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers $Headers

# Find the x64-setup.exe asset
$Asset = $Release.assets | Where-Object { $_.name -match 'x64-setup\.exe$' } | Select-Object -First 1

if (-not $Asset) {
    throw "No x64-setup.exe asset found in the latest release."
}

# Download to temp directory
$TempPath = Join-Path $env:TEMP $Asset.name
Write-Host "Downloading $($Asset.name)..."
Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $TempPath

# Run the installer elevated
Write-Host "Starting installation with administrator privileges..."
Start-Process -FilePath $TempPath -Verb RunAs -Wait
```


### 2. Default Installation Paths
* **Application Files (Read-Only):**
  `C:\Program Files\ModSmith`
  *(Note: ModSmith does not use the installation directory in Program Files to store writable project data due to Windows permission constraints).*
* **User Data & Workspace Home (Writable):**
  `%USERPROFILE%\Desktop\ModSmith` (Default, unless customized during setup)
  All templates, config files, recipes, and compiled outputs will live here.

### 3. Home Directory Selection & `MODSMITH_HOME`
During installation, the setup wizard will present two directory pages:
1. **Install Location** (e.g. `C:\Program Files\ModSmith`) for program binaries.
2. **Home Location** (e.g. `C:\Users\<You>\Desktop\ModSmith`) where workspaces, templates, generated mods, and built jars reside.

The installer defines a user-level environment variable named `MODSMITH_HOME` pointing to this home path. This environment variable tells `modsmith` where to automatically locate your templates, workspace configuration, and generated projects.

#### Changing the Home Directory Later
If you ever wish to use a different folder as your workspace root without passing explicit command-line flags, you can run the following command to persistently change it:
```bash
modsmith_cli home set "D:\ModSmith"
```
*Note: You will need to open a new terminal window for the environment variable change to take effect in your command shells.*

#### Manual Workspace Migration
If you are moving from an existing installation (e.g., from `%USERPROFILE%\Documents\ModSmith` to the new `%USERPROFILE%\Desktop\ModSmith` default):
1. **Copy** your old ModSmith home folder contents to the new folder location.
2. Run `modsmith_cli home set <new location>` to point the environment to the new location.
3. Run `modsmith_cli doctor` to verify that all configuration and templates are parsed correctly.
4. Manually **delete** the old folder only after you have fully verified that the new workspace is functioning correctly.

---

## Installing & Running from Source

If you prefer to run ModSmith directly using Python or want to develop new features, you can set it up from source.

### Requirements
* **Git:** Required to generate and manage version-controlled mod target repositories.
* **Java 21 (or newer):** Crucial for compiling and building modern Minecraft mods (Minecraft 1.20.5+ and 1.21+ require Java 21).
* **Python 3.10+:** Only required when running or developing ModSmith from source.
* **NSIS 3.x & PyInstaller:** Only needed if you plan to compile the standalone `modsmith.exe` and build the Windows installer (`ModSmithSetup.exe`) yourself.

### Steps to Run from Source
1. **Clone the Repository:**
   ```bash
   git clone https://github.com/ardaryusz/ModSmith.git
   cd ModSmith
   ```

2. **Set up a Virtual Environment:**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Dependencies in Editable/Development Mode:**
   ```bash
   pip install -e ".[dev,gui]"
   ```
   Omit `gui` if you only need the CLI.

4. **Verify the CLI Installation:**
   ```bash
   python -m modsmith --help
   ```

5. **Launch the GUI (requires PySide6):**
   ```bash
   python -m modsmith_gui
   ```
