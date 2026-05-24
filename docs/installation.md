# Installation

This guide covers how to install ModSmith using the Windows installer or set it up from source for development.

## Installing via Windows Installer (Recommended)

The easiest way to get started with ModSmith on Windows is by downloading and running the pre-built installer: `ModSmithSetup.exe`.

### 1. Run the Setup Wizard
Double-click `ModSmithSetup.exe` and follow the on-screen prompts.

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
