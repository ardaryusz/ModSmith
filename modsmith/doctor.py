"""Diagnostics and environment checking logic for ModSmith."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modsmith import __version__
from modsmith.config import ConfigError, load_mod_config, load_template_descriptor
from modsmith.recipes import RecipeError, load_recipes


@dataclass
class DoctorResult:
    """Accumulates diagnostic messages and outcome of doctor checks."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def add_info(self, message: str) -> None:
        """Add an informational message."""
        self.infos.append(message)

    @property
    def ok(self) -> bool:
        """Return True if there are no errors."""
        return len(self.errors) == 0


def diagnose_environment(
    workspace_dir: Path,
    templates_dir: Path,
    mods_dir: Path,
    *,
    dev_mode: bool = False,
) -> DoctorResult:
    """Check ModSmith environment and return a DoctorResult.

    This function is completely read-only. It will not create directories or
    write files.
    """
    result = DoctorResult()

    # 1. ModSmith version
    result.add_info(f"ModSmith version: {__version__}")

    # 2. Paths
    home_val = os.environ.get("MODSMITH_HOME")
    if home_val:
        result.add_info(f"MODSMITH_HOME is set: {home_val}")
    else:
        result.add_info("MODSMITH_HOME is not set")
    result.add_info(f"Workspace path: {workspace_dir.resolve()}")
    result.add_info(f"Templates path: {templates_dir.resolve()}")
    result.add_info(f"Mods path: {mods_dir.resolve()}")

    # 3. Folder existence
    # WORKSPACE
    if workspace_dir.is_dir():
        result.add_info(f"WORKSPACE directory exists: {workspace_dir}")
    else:
        result.add_error(f"WORKSPACE directory does not exist: {workspace_dir}")

    # WORKSPACE/DETAILS
    details_dir = workspace_dir / "DETAILS"
    if details_dir.is_dir():
        result.add_info(f"WORKSPACE/DETAILS directory exists: {details_dir}")
    else:
        result.add_error(f"WORKSPACE/DETAILS directory does not exist: {details_dir}")

    # WORKSPACE/RECIPES
    recipes_dir = workspace_dir / "RECIPES"
    if recipes_dir.is_dir():
        result.add_info(f"WORKSPACE/RECIPES directory exists: {recipes_dir}")
    else:
        result.add_error(f"WORKSPACE/RECIPES directory does not exist: {recipes_dir}")

    # WORKSPACE/README
    readme_dir = workspace_dir / "README"
    if readme_dir.is_dir():
        result.add_info(f"WORKSPACE/README directory exists: {readme_dir}")
    else:
        result.add_warning(f"WORKSPACE/README directory does not exist: {readme_dir}")

    # WORKSPACE/DIST (Missing/Empty is a warning, not an error)
    dist_dir = workspace_dir / "DIST"
    if dist_dir.is_dir():
        result.add_info(f"WORKSPACE/DIST directory exists: {dist_dir}")
    else:
        result.add_warning(f"WORKSPACE/DIST directory does not exist: {dist_dir}")

    # WORKSPACE/ASSETS (Missing is INFO only, never an error)
    assets_dir = workspace_dir / "ASSETS"
    if assets_dir.is_dir():
        result.add_info(f"WORKSPACE/ASSETS directory exists: {assets_dir}")
    else:
        result.add_info(f"WORKSPACE/ASSETS directory does not exist (optional): {assets_dir}")

    # MODTEMPLATES (Missing templates root is an error)
    if templates_dir.is_dir():
        result.add_info(f"MODTEMPLATES directory exists: {templates_dir}")
    else:
        result.add_error(f"MODTEMPLATES directory does not exist: {templates_dir}")

    # MODS (Missing output mods directory is a warning, not an error)
    if mods_dir.is_dir():
        result.add_info(f"MODS directory exists: {mods_dir}")
    else:
        result.add_warning(f"MODS directory does not exist: {mods_dir}")

    # 4. Config
    config_path = details_dir / "modsmith.json"
    config = None
    if not config_path.exists():
        result.add_error(f"modsmith.json not found at: {config_path}")
    else:
        result.add_info(f"modsmith.json file exists: {config_path}")
        try:
            config = load_mod_config(config_path)
            result.add_info("modsmith.json parsed successfully")
            if not config.targets:
                result.add_error("modsmith.json: targets list is empty")
            else:
                result.add_info(f"modsmith.json contains {len(config.targets)} target(s)")
        except ConfigError as exc:
            result.add_error(f"Failed to parse modsmith.json: {exc}")

    # 5. Recipes (Missing recipes folder or invalid recipe files are errors)
    if recipes_dir.is_dir():
        json_files = list(recipes_dir.glob("*.json"))
        if not json_files:
            result.add_error(f"WORKSPACE/RECIPES contains no .json recipe files: {recipes_dir}")
        else:
            result.add_info(f"WORKSPACE/RECIPES contains {len(json_files)} .json recipe file(s)")
            try:
                load_recipes(recipes_dir)
                result.add_info("All recipe JSON files parsed successfully")
            except RecipeError as exc:
                result.add_error(f"Failed to parse recipes: {exc}")
    else:
        result.add_error("Cannot check recipes because WORKSPACE/RECIPES directory is missing")

    # 6. Templates
    if config is not None:
        for i, target in enumerate(config.targets):
            t_dir = templates_dir / target.template
            if not t_dir.is_dir():
                result.add_error(f"Target '{target.branch}': template directory not found: {t_dir}")
                continue

            result.add_info(f"Target '{target.branch}': template directory exists: {t_dir}")

            # Check descriptor
            desc_path = t_dir / "modsmith-template.json"
            if not desc_path.exists():
                result.add_warning(
                    f"Target '{target.branch}': template '{target.template}' "
                    "has no modsmith-template.json — defaults will be used"
                )
            else:
                try:
                    load_template_descriptor(t_dir)
                    result.add_info(f"Target '{target.branch}': template descriptor parsed successfully")
                except ConfigError as exc:
                    result.add_error(f"Target '{target.branch}': failed to parse template descriptor: {exc}")

            # Check gradlew / gradlew.bat
            gradlew = t_dir / "gradlew"
            gradlew_bat = t_dir / "gradlew.bat"
            if gradlew.exists() or gradlew_bat.exists():
                result.add_info(f"Target '{target.branch}': gradlew/gradlew.bat exists")
            else:
                result.add_error(f"Target '{target.branch}': gradlew or gradlew.bat is missing in {t_dir}")

            # Check gradle/wrapper/gradle-wrapper.jar
            wrapper_jar = t_dir / "gradle" / "wrapper" / "gradle-wrapper.jar"
            if wrapper_jar.exists():
                result.add_info(f"Target '{target.branch}': gradle-wrapper.jar exists")
            else:
                result.add_error(f"Target '{target.branch}': gradle-wrapper.jar is missing: {wrapper_jar}")

    # 7. Tools (Git and Java are errors for normal workflows)
    # Git
    git_path = shutil.which("git")
    if git_path:
        result.add_info(f"Git executable found: {git_path}")
        try:
            git_ver = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
            result.add_info(f"Git version: {git_ver.stdout.strip()}")
        except (subprocess.SubprocessError, OSError) as exc:
            result.add_warning(f"Failed to query Git version: {exc}")
    else:
        result.add_error("Git was not found on PATH. Git is required to generate mod repositories.")

    # Java
    java_path = shutil.which("java")
    if java_path:
        result.add_info(f"Java executable found: {java_path}")
        try:
            java_ver = subprocess.run(["java", "-version"], capture_output=True, text=True, check=True)
            output = java_ver.stderr.strip() or java_ver.stdout.strip()
            first_line = output.splitlines()[0] if output else "unknown"
            result.add_info(f"Java version: {first_line}")
        except (subprocess.SubprocessError, OSError) as exc:
            result.add_warning(f"Failed to query Java version: {exc}")
    else:
        result.add_error("Java was not found on PATH. Java is needed to build mods with Gradle.")

    # 8. Output
    # Generated repo (missing is INFO, not error)
    if config is not None:
        repo_dir = mods_dir / config.output_repo_name
        if repo_dir.is_dir():
            result.add_info(f"Generated repository exists: {repo_dir}")
        else:
            result.add_info(f"Generated repository does not exist (not yet generated): {repo_dir}")

    # DIST Jars (missing/empty is a warning, not an error)
    if dist_dir.is_dir():
        jars = list(dist_dir.glob("*.jar"))
        if not jars:
            result.add_warning(f"WORKSPACE/DIST directory contains no JAR files: {dist_dir}")
        else:
            result.add_info(f"WORKSPACE/DIST contains {len(jars)} JAR file(s)")

    # 9. Dev Tools
    if dev_mode:
        # Check python/py
        python_found = False
        for cmd in ["python", "py"]:
            path = shutil.which(cmd)
            if path:
                try:
                    ver = subprocess.run([cmd, "--version"], capture_output=True, text=True, check=True)
                    ver_str = ver.stdout.strip() or ver.stderr.strip()
                    result.add_info(f"{cmd} executable found: {path} ({ver_str})")
                    python_found = True
                    break
                except (subprocess.SubprocessError, OSError):
                    pass
        if not python_found:
            result.add_warning("Neither 'python' nor 'py' executable could be found/queried for version")

        # Check pytest
        pytest_path = shutil.which("pytest")
        if pytest_path:
            try:
                ver = subprocess.run(["pytest", "--version"], capture_output=True, text=True, check=True)
                ver_str = ver.stdout.strip() or ver.stderr.strip()
                first_line = ver_str.splitlines()[0] if ver_str else "unknown"
                result.add_info(f"pytest found: {pytest_path} ({first_line})")
            except (subprocess.SubprocessError, OSError):
                result.add_info(f"pytest found: {pytest_path}")
        else:
            try:
                ver = subprocess.run(["py", "-m", "pytest", "--version"], capture_output=True, text=True, check=True)
                ver_str = ver.stdout.strip() or ver.stderr.strip()
                first_line = ver_str.splitlines()[0] if ver_str else "unknown"
                result.add_info(f"pytest found via py -m pytest ({first_line})")
            except (subprocess.SubprocessError, OSError):
                result.add_warning("pytest is not available")

        # Check pyinstaller (missing is warning in dev mode)
        pyinstaller_path = shutil.which("pyinstaller")
        if pyinstaller_path:
            try:
                ver = subprocess.run(["pyinstaller", "--version"], capture_output=True, text=True, check=True)
                ver_str = ver.stdout.strip() or ver.stderr.strip()
                result.add_info(f"pyinstaller found: {pyinstaller_path} ({ver_str})")
            except (subprocess.SubprocessError, OSError):
                result.add_info(f"pyinstaller found: {pyinstaller_path}")
        else:
            result.add_warning("pyinstaller was not found on PATH")

        # Check makensis (missing is warning in dev mode)
        makensis_path = shutil.which("makensis")
        if makensis_path:
            try:
                ver = subprocess.run(["makensis", "/VERSION"], capture_output=True, text=True, check=True)
                ver_str = ver.stdout.strip() or ver.stderr.strip()
                result.add_info(f"makensis found: {makensis_path} (v{ver_str})")
            except (subprocess.SubprocessError, OSError):
                result.add_info(f"makensis found: {makensis_path}")
        else:
            result.add_warning("makensis was not found on PATH")

        # Project files
        proj_root = Path(__file__).resolve().parent.parent
        ico_file = proj_root / "assets" / "modsmith.ico"
        if ico_file.is_file():
            result.add_info(f"assets/modsmith.ico exists: {ico_file}")
        else:
            result.add_warning(f"assets/modsmith.ico is missing: {ico_file}")

        build_exe = proj_root / "scripts" / "build_exe.ps1"
        if build_exe.is_file():
            result.add_info(f"scripts/build_exe.ps1 exists: {build_exe}")
        else:
            result.add_warning(f"scripts/build_exe.ps1 is missing: {build_exe}")

        build_inst = proj_root / "scripts" / "build_installer.ps1"
        if build_inst.is_file():
            result.add_info(f"scripts/build_installer.ps1 exists: {build_inst}")
        else:
            result.add_warning(f"scripts/build_installer.ps1 is missing: {build_inst}")

    return result
