# Installer Packaging

This page covers the design and packaging of the ModSmith Windows Installer.

## Overview

ModSmith provides a native Windows installation setup wizard formatted as `modsmith_<version>_<arch>-setup.exe` (e.g., `modsmith_1.0.0_x64-setup.exe`) using a combination of two tools:

* **PyInstaller:** Packages the Python source code and runtime environment into a standalone, dependency-free `modsmith.exe` inside `dist/ModSmith/`.
* **NSIS (Nullsoft Scriptable Install System):** Compiles the executable and support files into a single, self-extracting installer setup executable.

---

## Installer Behavior

The installer script (`installer/ModSmithInstaller.nsi`) is designed to provide a seamless setup experience without manual configuration:

1. **Program Files Installation:**
   Copies the application files to `C:\Program Files\ModSmith` (user-configurable). This folder is kept read-only for normal users.
2. **User Data Directory Creation:**
   Allows the user to select the home directory during installation (default: `%USERPROFILE%\Desktop\ModSmith`).
   Automatically initializes the user's workspace folders inside the selected home directory.
   This includes folders like `MODTEMPLATES/`, `WORKSPACE/`, `WORKSPACE/RECIPES/`, `WORKSPACE/DIST/`, and `MODS/`.
3. **Environment Setup:**
   Writes `MODSMITH_HOME` to `HKCU\Environment` set to the selected home path so the app knows where to run.
4. **PATH Modification (Optional):**
   If checked, reads the current user `Path` registry value, appends the installation path safely (handling empty PATH or duplicates), writes it back, and broadcasts `WM_SETTINGCHANGE`.
5. **Start Menu Shortcuts:**
   Creates a "ModSmith Command Prompt" shortcut that opens PowerShell starting inside your ModSmith home folder, displaying a welcome message.
6. **Safe Uninstall:**
   * Cleans up registry entries, shortcuts, and application files under Program Files.
   * Restores `Path` and `MODSMITH_HOME` environment variables.
   * **Intentionally preserves user data:** The uninstaller does **not** delete files under the home folder by default, protecting custom templates, recipes, and mod files.

---

## Manual Verification Checklist

After compiling a new version of the installer, perform the following steps to verify its behavior:

1. [ ] Double-click `modsmith_<version>_<arch>-setup.exe` (e.g., `modsmith_1.0.0_x64-setup.exe`) to run the installation wizard.
2. [ ] Choose a custom path or keep the default `C:\Program Files\ModSmith` and click Next.
3. [ ] Keep all components checked (Core, PATH, Start Menu) and click Install.
4. [ ] Verify that the custom or default home folder (typically `%USERPROFILE%\Desktop\ModSmith`) exists and contains sample JSON files.
5. [ ] Open the **ModSmith Command Prompt** from the Start Menu.
6. [ ] Verify that PowerShell opens inside the home folder and shows a cyan colored title.
7. [ ] Run `modsmith --version` and `modsmith validate` inside the terminal to verify they run successfully.
8. [ ] Go to Windows Settings > Apps > Installed Apps, select ModSmith, and click **Uninstall**.
9. [ ] Run the uninstaller.
10. [ ] Verify that files under `C:\Program Files\ModSmith` are deleted.
11. [ ] Verify that `MODSMITH_HOME` and the PATH additions are cleaned up from the registry.
12. [ ] Confirm that your workspace directories and custom files inside the home directory **remain intact**.

---

## ModSmith Branding & Icons

ModSmith uses a custom branding icon for the standalone executable, installer wizard, uninstaller, and Start Menu shortcuts:

* **PNG Source Logo (`assets/modsmith-logo.png`):** The primary source artwork (flat icon depicting a hammer striking a pixel-style cube).
* **ICO Icon (`assets/modsmith.ico`):** The compiled multi-size Windows icon file. It contains sizes: 16, 24, 32, 48, 64, 128, and 256 pixels.

### Regenerating the ICO Icon
If you modify the source logo `assets/modsmith-logo.png`, you can regenerate the icon by running the following script:

```powershell
.\scripts\make_icon.ps1
```

*Note: The script requires the Python `Pillow` library. If it is missing, you can install it using `py -m pip install Pillow`.*

---

## Installer Development & Troubleshooting

### `makensis` Not Found on PATH
If `build_installer.ps1` fails reporting that `makensis.exe` is missing, download NSIS from [SourceForge](https://nsis.sourceforge.io/Download) and add the installation folder (usually `C:\Program Files (x86)\NSIS`) to your Windows environment `PATH`.

### `EnvVarUpdate.nsh` Missing
Older versions of ModSmith relied on the third-party `EnvVarUpdate.nsh` header script. **We have intentionally replaced all EnvVarUpdate.nsh dependencies** with native registry read/write operations and custom string algorithms written in plain NSIS. 
* Do **not** try to download or configure `EnvVarUpdate.nsh` in your NSIS installation.
* The script is fully self-contained and compiles without any external plugins.
