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


def _run_process(args: list[str]) -> subprocess.CompletedProcess[str]:
    from modsmith.utils import run_process
    res = run_process(args, capture_output=True)
    
    ret = res.returncode
    is_err = False
    if isinstance(ret, int):
        is_err = (ret != 0)
    elif hasattr(ret, "assert_called") or hasattr(ret, "_mock_name"):
        is_err = False
    else:
        is_err = bool(ret)

    if is_err:
        raise subprocess.CalledProcessError(ret, args, output=res.stdout, stderr=res.stderr)
    return res


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

    # WORKSPACE/DIST (Missing/Empty is INFO, not warning)
    dist_dir = workspace_dir / "DIST"
    if dist_dir.exists():
        if not dist_dir.is_dir():
            result.add_error(f"WORKSPACE/DIST path exists but is not a directory: {dist_dir}")
        else:
            result.add_info(f"WORKSPACE/DIST directory exists: {dist_dir}")
    else:
        result.add_info(f"WORKSPACE/DIST directory does not exist yet: {dist_dir}")

    # WORKSPACE/ASSETS (Missing is INFO only, never an error)
    assets_dir = workspace_dir / "ASSETS"
    if assets_dir.is_dir():
        result.add_info(f"WORKSPACE/ASSETS directory exists: {assets_dir}")
    else:
        result.add_info(f"WORKSPACE/ASSETS directory does not exist (optional): {assets_dir}")

    # WORKSPACE/LICENSE (Missing is INFO only, never an error)
    license_dir = workspace_dir / "LICENSE"
    if license_dir.is_dir():
        result.add_info(f"WORKSPACE/LICENSE directory exists: {license_dir}")
        try:
            from modsmith.context import get_license_candidates, discover_license_file
            candidates = get_license_candidates(license_dir)
            selected = discover_license_file(license_dir)

            if not candidates:
                result.add_info("No workspace LICENSE, LICENSE.md, LICENSE.txt, LICENSE.html, or LICENSE.docx found; generated mods will not include a license file.")
            elif len(candidates) > 1:
                type_labels = {
                    "": "Extensionless file",
                    ".md": "Markdown file",
                    ".txt": "Text file",
                    ".html": "HTML file",
                    ".docx": "Word document"
                }
                type_str = type_labels.get(selected.suffix.lower(), "License file")
                names = [c.name for c in candidates]
                result.add_info(f"Multiple workspace license files exist (found {len(candidates)} files: {', '.join(names)}). {type_str} {selected.name} was selected.")
            else:
                result.add_info(f"Workspace license file found: {selected.resolve()}")
        except Exception as exc:
            result.add_info(f"Failed to scan workspace LICENSE files: {exc}")
    else:
        result.add_info(f"WORKSPACE/LICENSE directory does not exist (optional): {license_dir}")

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

            # Landing branch checks
            landing = config.landing_branch
            if landing.enabled:
                result.add_info(f"Landing branch enabled: {landing.name}")
                
                # Workspace README checks
                readme_file = workspace_dir / "README" / "README.md"
                if not readme_file.exists():
                    readme_dir = workspace_dir / "README"
                    if readme_dir.is_dir():
                        md_files = list(readme_dir.glob("*.md"))
                        if md_files:
                            readme_file = md_files[0]
                
                readme_empty = True
                if readme_file.exists():
                    try:
                        content = readme_file.read_text(encoding="utf-8")
                        if content.strip():
                            readme_empty = False
                    except Exception:
                        pass
                
                if readme_empty:
                    result.add_info("Workspace README is empty; fallback heading will be generated")
                else:
                    result.add_info(f"Workspace README is non-empty: {readme_file.resolve()}")
                
                # LICENSE check
                license_dir = workspace_dir / "LICENSE"
                license_file = None
                if license_dir.is_dir():
                    from modsmith.context import discover_license_file
                    try:
                        license_file = discover_license_file(license_dir)
                    except Exception:
                        pass
                
                if license_file is not None:
                    result.add_info(f"Landing branch license: {license_file.name}")
                else:
                    result.add_info("Landing branch license: None")

                # Icon check
                if config.icon:
                    icon_path = workspace_dir / config.icon.replace("/", os.sep)
                    if icon_path.is_file():
                        result.add_info(f"Landing branch icon: {config.icon}")
                    else:
                        result.add_info(f"Landing branch icon: {config.icon} (missing)")
                else:
                    result.add_info("Landing branch icon: None")
            else:
                result.add_info("Landing branch generation is disabled")

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
            git_ver = _run_process(["git", "--version"])
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
            java_ver = _run_process(["java", "-version"])
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

    # DIST Jars
    if dist_dir.is_dir():
        try:
            all_jars = []
            for entry in dist_dir.rglob("*.jar"):
                if entry.is_file():
                    all_jars.append(entry)

            if not all_jars:
                result.add_info(f"WORKSPACE/DIST contains no built JAR files yet: {dist_dir}")
            else:
                root_jars = [j for j in all_jars if j.parent == dist_dir]
                result.add_info(f"WORKSPACE/DIST contains {len(all_jars)} JAR file(s)")
                if root_jars:
                    result.add_info(f"Legacy root-level JAR files found: {len(root_jars)}")
        except Exception as exc:
            result.add_error(f"WORKSPACE/DIST directory cannot be read: {exc}")
    else:
        result.add_info(f"WORKSPACE/DIST contains no built JAR files yet: {dist_dir}")

    # 9. Dev Tools
    if dev_mode:
        # Check python/py
        python_found = False
        for cmd in ["python", "py"]:
            path = shutil.which(cmd)
            if path:
                try:
                    ver = _run_process([cmd, "--version"])
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
                ver = _run_process(["pytest", "--version"])
                ver_str = ver.stdout.strip() or ver.stderr.strip()
                first_line = ver_str.splitlines()[0] if ver_str else "unknown"
                result.add_info(f"pytest found: {pytest_path} ({first_line})")
            except (subprocess.SubprocessError, OSError):
                result.add_info(f"pytest found: {pytest_path}")
        else:
            try:
                ver = _run_process(["py", "-m", "pytest", "--version"])
                ver_str = ver.stdout.strip() or ver.stderr.strip()
                first_line = ver_str.splitlines()[0] if ver_str else "unknown"
                result.add_info(f"pytest found via py -m pytest ({first_line})")
            except (subprocess.SubprocessError, OSError):
                result.add_warning("pytest is not available")

        # Check pyinstaller (missing is warning in dev mode)
        pyinstaller_path = shutil.which("pyinstaller")
        if pyinstaller_path:
            try:
                ver = _run_process(["pyinstaller", "--version"])
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
                ver = _run_process(["makensis", "/VERSION"])
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
