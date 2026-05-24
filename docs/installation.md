# Installation

This guide covers how to install ModSmith using the Windows installer or set it up from source for development.

## Installing via Windows Installer (Recommended)

The easiest way to get started with ModSmith on Windows is by downloading and running the pre-built installer: `modsmith_<version>_<arch>-setup.exe` (e.g., `modsmith_1.0.0_x64-setup.exe`).

### 1. Run the Setup Wizard
Double-click the downloaded setup file (e.g., `modsmith_1.0.0_x64-setup.exe`) and follow the on-screen prompts.

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
* **User Data & Workspace (Writable):**
  `%USERPROFILE%\Documents\ModSmith`
  All templates, config files, recipes, and compiled outputs will live here.

### 3. Understanding `MODSMITH_HOME`
During installation, the setup wizard defines a user-level environment variable named `MODSMITH_HOME` set to your user data path (e.g., `C:\Users\<You>\Documents\ModSmith`). 
This environment variable tells `modsmith.exe` where to automatically locate your templates, workspace configuration, and generated projects.

If you ever wish to use a different folder as your workspace root without passing explicit command-line flags, you can change the `MODSMITH_HOME` environment variable value in your Windows system settings.

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
   pip install -e ".[dev]"
   ```

4. **Verify the Installation:**
   ```bash
   python -m modsmith --help
   ```
