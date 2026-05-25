# Troubleshooting Guide

This page lists common errors and solutions encountered when using, compiling, or developing ModSmith.

## Setup & Compilation Errors

### 1. `makensis.exe not found on PATH`
* **Cause:** The NSIS compiler is not installed or its installation directory is not added to the system PATH.
* **Solution:**
  1. Download and install NSIS from [nsis.sourceforge.io](https://nsis.sourceforge.io/).
  2. Add the installation folder (typically `C:\Program Files (x86)\NSIS`) to your system/user `Path` environment variable.
  3. Restart your terminal or VS Code to apply the changes.

### 2. `EnvVarUpdate.nsh not found`
* **Cause:** A third-party NSIS plugin was referenced.
* **Solution:** ModSmith has been updated to remove this dependency. If you encounter this error, make sure your local checkout is up-to-date and that `ModSmithInstaller.nsi` does not contain `!include EnvVarUpdate.nsh`.

---

## Build & Gradle Errors

### 3. `Could not find or load main class org.gradle.wrapper.GradleWrapperMain`
* **Cause:** The template in `MODTEMPLATES/` is missing the Gradle wrapper JAR file (`gradle/wrapper/gradle-wrapper.jar`). Git ignores often filter out `.jar` files, which may lead to this file being excluded when copy-pasting template files.
* **Solution:** Ensure that `gradle-wrapper.jar` exists inside your template folder under `gradle/wrapper/`. If it is missing, download a clean Gradle wrapper distribution or copy the folder from a clean MDK zip.

### 4. `Unsupported class file major version 69`
* **Cause:** The version of Java running the Gradle task is incompatible with the version expected by the template. Major version `69` corresponds to Java 22, while some older templates require Java 21 or Java 17.
* **Solution:** Set your `JAVA_HOME` environment variable to point to the correct Java Development Kit (JDK) version required by the template (typically Java 21).

---

## ModSmith Execution & CLI Errors

### 5. `generate --force` Access Denied on Windows
* **Cause:** During regeneration, ModSmith deletes the target folder under `MODS/`. If you have a file in that folder open in an IDE, or if a terminal is active inside `MODS/<output_repo_name>`, Windows locks the directory.
* **Solution:**
  1. Close all active terminals or command prompts located inside the `MODS/` directory.
  2. Close any files from that folder open in editors.
  3. Run `modsmith clean --force` or `modsmith generate --force` again.

### 6. Unrecognized option `--dry-run` or similar error
* **Cause:** The `--dry-run` flag was passed after the command (e.g., `modsmith generate --dry-run`).
* **Solution:** In ModSmith, `--dry-run` is a global flag. It must be placed *before* the command name.
  * **Correct:** `modsmith --dry-run generate`

### 7. `modsmith` command still works after running Windows Uninstaller
* **Cause:** You previously installed ModSmith using `pip install -e .` or `pip install -e ".[dev]"` from source. Windows uninstall cleans up the standalone installer files but does not delete Python site-packages linkages.
* **Solution:** Run `pip uninstall modsmith` in your active Python/virtual environment to clean up source linkages.

---

## Recipe & Template Issues

### 8. IDE shows Java compilation errors/warnings in template files
* **Cause:** Standard MDK templates contain default example classes (like `ExampleMod.java`) or outdated imports.
* **Solution:** ModSmith automatically cleans or translates these placeholders during `generate` based on your `modsmith.json` configurations. You can safely ignore warnings in raw templates.

### 9. Recipes are not appearing in the compiled mod target
* **Cause:** The recipe output folder is named incorrectly in the target template.
* **Solution:** Ensure that your template's `modsmith-template.json` has `recipe_folder` set correctly:
  * For Minecraft 1.20: `"recipe_folder": "recipes"`
  * For Minecraft 1.21+: `"recipe_folder": "recipe"`
  Verify that the template MDK contains the matching resource folder path structure under `src/main/resources/data/<modid>/`.

---

## Home Directory & Environment Variable Issues

### 10. `MODSMITH_HOME` change is not appearing in terminal/shells
* **Cause:** When you set the environment variable using `modsmith home set`, the variable is saved persistently in the user registry, but existing shell/terminal sessions do not reload their environment automatically.
* **Solution:** Open a new terminal window or restart your command prompt or VS Code for the environment changes to take effect.

### 11. Existing files are missing after changing the Home location
* **Cause:** ModSmith does not automatically migrate your existing data to prevent accidental data loss.
* **Solution:** Follow the manual migration steps:
  1. Copy the files/folders from your old home directory (e.g. `%USERPROFILE%\Documents\ModSmith`) to your new home directory (e.g. `%USERPROFILE%\Desktop\ModSmith`).
  2. Run `modsmith doctor` to verify the files are detected correctly.
  3. Delete the old folder only after successful validation.

---

## Git & GitHub Issues

### 12. Push to remote rejected because the remote contains existing files
* **Cause:** The remote Git repository contains files (like `README.md` or `LICENSE`) that do not exist in your local generated target branch.
* **Solution:** Run `git pull origin <branch-name> --allow-unrelated-histories` to merge remote files before pushing, or force-push if you want to overwrite the remote branch.
