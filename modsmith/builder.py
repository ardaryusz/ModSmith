"""Gradle build orchestrator for ModSmith Phase 6.

Public API
----------
- ``BuildError``              — raised on any recoverable build failure
- ``BuildResult``             — dataclass carrying build outcome
- ``find_gradle_wrapper``     — locate gradlew.bat / gradlew in a repo
- ``collect_built_jars``      — copy release JARs from build/libs to DIST
- ``run_gradle_build``        — execute the Gradle wrapper subprocess
- ``build``                   — top-level entry point wired to the CLI
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from modsmith.config import load_mod_config
from modsmith.git_ops import git_checkout, git_list_branches
from modsmith.utils import run_process


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class BuildError(Exception):
    """Raised when the build cannot proceed due to a user-fixable problem."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BuildResult:
    """Carries the outcome of a ``build`` invocation for display by the CLI."""

    repo_dir: Path
    built_branches: list[str]
    copied_jars: list[Path]
    warnings: list[str]
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Jar exclusion rules
# ---------------------------------------------------------------------------

_EXCLUDED_SUFFIXES: tuple[str, ...] = (
    "-sources.jar",
    "-javadoc.jar",
    "-dev.jar",
    "-dev-shadow.jar",
)


def _is_release_jar(name: str) -> bool:
    """Return True if *name* is a normal release JAR (not sources/javadoc/dev)."""
    return name.endswith(".jar") and not any(
        name.endswith(s) for s in _EXCLUDED_SUFFIXES
    )


# ---------------------------------------------------------------------------
# Helper: locate Gradle wrapper
# ---------------------------------------------------------------------------


def find_gradle_wrapper(repo_dir: Path) -> Path:
    """Return the path to the Gradle wrapper script inside *repo_dir*.

    Preference order
    ----------------
    - Windows: ``gradlew.bat`` first, then ``gradlew`` as fallback.
    - Other OS: ``gradlew`` first, then ``gradlew.bat`` as fallback.

    Raises :class:`BuildError` if neither wrapper exists.
    """
    repo_dir = Path(repo_dir)
    if sys.platform == "win32":
        primary = repo_dir / "gradlew.bat"
        fallback = repo_dir / "gradlew"
    else:
        primary = repo_dir / "gradlew"
        fallback = repo_dir / "gradlew.bat"

    if primary.exists():
        return primary
    if fallback.exists():
        return fallback
    raise BuildError(
        f"No Gradle wrapper found in '{repo_dir}'. "
        "Expected 'gradlew.bat' (Windows) or 'gradlew' (Unix)."
    )


# ---------------------------------------------------------------------------
# Helper: run Gradle
# ---------------------------------------------------------------------------


def run_gradle_build(
    repo_dir: Path,
    wrapper: Path,
    on_log_line: callable | None = None,
) -> None:
    """Run ``wrapper clean build`` inside *repo_dir*.

    Uses ``run_process`` helper. Raises :class:`BuildError`
    on non-zero exit or if the wrapper executable is not found.
    """
    cmd = [str(wrapper), "clean", "build"]
    try:
        result = run_process(
            cmd,
            cwd=str(repo_dir),
            on_log_line=on_log_line,
        )
    except FileNotFoundError as exc:
        raise BuildError(f"Gradle wrapper not executable: {exc}") from exc

    if result.returncode != 0:
        if on_log_line is not None:
            raise BuildError(
                f"Gradle build failed (exit {result.returncode}) in branch being built."
            )
        else:
            tail = "\n".join(result.stderr.splitlines()[-20:]) if result.stderr else ""
            raise BuildError(
                f"Gradle build failed (exit {result.returncode}) "
                f"in branch being built.\n{tail}".strip()
            )


# ---------------------------------------------------------------------------
# Helper: clean stale target JARs
# ---------------------------------------------------------------------------


def _clean_stale_jars_for_branch(
    dist_dir: Path,
    mod_id: str,
    mod_version: str,
    branch_name: str,
    loader: str,
    mc_version: str,
    new_jar_names: set[str],
) -> None:
    """Removes stale ModSmith-produced JARs in dist_dir for the branch currently being built.

    Any JAR matching the mod_id, mod_version, and containing the loader name and mc version base
    that is NOT in new_jar_names is considered stale and deleted.
    """
    if not dist_dir.is_dir():
        return

    loader_lower = loader.lower()
    mc_parts = mc_version.split(".")
    mc_base = f"{mc_parts[0]}.{mc_parts[1]}" if len(mc_parts) >= 2 else mc_version

    # Check for any loader keywords in branch name
    branch_lower = branch_name.lower()
    branch_loaders = [kw for kw in ("forge", "fabric", "neoforge") if kw in branch_lower]

    for entry in dist_dir.glob("*.jar"):
        if not entry.is_file():
            continue
        if entry.name in new_jar_names:
            continue

        name = entry.name
        if name.startswith(f"{mod_id}-") and name.endswith(f"-{mod_version}.jar"):
            middle = name[len(mod_id) + 1 : -len(mod_version) - 5].lower()
            
            # Check if this jar belongs to the current target branch being built
            loader_match = (loader_lower in middle) or any(kw in middle for kw in branch_loaders)
            mc_match = mc_base in middle
            
            if loader_match and mc_match:
                try:
                    entry.unlink()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Helper: collect JARs
# ---------------------------------------------------------------------------


def collect_built_jars(
    repo_dir: Path,
    dist_dir: Path,
    mod_id: str | None = None,
    mod_version: str | None = None,
    branch_name: str | None = None,
    loader: str | None = None,
    mc_version: str | None = None,
) -> list[Path]:
    """Copy release JARs from ``build/libs/`` into *dist_dir*.

    Excluded patterns (not copied):
    - ``*-sources.jar``
    - ``*-javadoc.jar``
    - ``*-dev.jar``
    - ``*-dev-shadow.jar``

    Returns the list of destination paths for every JAR that was copied.

    Raises :class:`BuildError` if ``build/libs/`` does not exist or contains
    no valid release JARs.
    """
    libs_dir = repo_dir / "build" / "libs"
    if not libs_dir.is_dir():
        raise BuildError(
            f"Expected build output directory not found: {libs_dir}. "
            "Did the Gradle build succeed?"
        )

    candidates = [p for p in libs_dir.iterdir() if _is_release_jar(p.name)]
    if not candidates:
        raise BuildError(
            f"No release JARs found in '{libs_dir}'. "
            "Check Gradle output or exclusion rules."
        )

    dist_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    new_jar_names = {jar.name for jar in candidates}

    # Clean up stale JARs for this branch if we have target metadata
    if mod_id and mod_version and branch_name and loader and mc_version:
        _clean_stale_jars_for_branch(
            dist_dir,
            mod_id,
            mod_version,
            branch_name,
            loader,
            mc_version,
            new_jar_names,
        )

    for jar in sorted(candidates):
        dest = dist_dir / jar.name
        shutil.copy2(jar, dest)
        copied.append(dest)
    return copied


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def build(
    workspace_dir: Path,
    mods_dir: Path,
    *,
    branch: str | None = None,
    dry_run: bool = False,
    on_log_line: callable | None = None,
) -> BuildResult:
    """Build generated target branches with Gradle and collect release JARs.

    Steps
    -----
    1. Load ``WORKSPACE/DETAILS/modsmith.json``.
    2. Resolve ``MODS/<output_repo_name>``; fail if it does not exist.
    3. List branches present in the generated repo.
    4. Determine which branches to build (all configured targets, or just
       the one named by *branch*); fail if any requested branch is missing.
    5. On dry-run: return immediately with the plan — no checkout, no Gradle,
       no DIST directory.
    6. On real build: for each branch —
       a. ``git checkout``
       b. find Gradle wrapper
       c. ``gradlew clean build``
       d. copy release JARs to ``WORKSPACE/DIST/<modid>-<mod_version>/``
    7. Leave the repo checked out on the **first** branch that was built.

    Raises
    ------
    :class:`BuildError`
         For any user-fixable problem (missing repo, missing branch, Gradle
         failure, missing JARs).
    """
    workspace_dir = Path(workspace_dir).resolve()
    mods_dir = Path(mods_dir).resolve()

    # 1. Load config
    config_path = workspace_dir / "DETAILS" / "modsmith.json"
    if not config_path.exists():
        raise BuildError(f"modsmith.json not found at: {config_path}")
    try:
        config = load_mod_config(config_path)
    except Exception as exc:
        raise BuildError(f"Failed to load modsmith.json: {exc}") from exc

    # 2. Locate repo
    repo_dir = mods_dir / config.output_repo_name
    if not repo_dir.exists():
        raise BuildError(
            f"Generated repo not found: {repo_dir}. "
            "Run 'python -m modsmith generate' first."
        )

    # 3. Available branches in the repo
    try:
        available_branches = git_list_branches(repo_dir)
    except Exception as exc:
        raise BuildError(f"Could not list Git branches in '{repo_dir}': {exc}") from exc

    # 4. Determine requested branches
    if branch is not None:
        if branch not in available_branches:
            raise BuildError(
                f"Branch '{branch}' does not exist in '{repo_dir}'. "
                f"Available branches: {', '.join(available_branches) or '(none)'}"
            )
        requested = [branch]
    else:
        # All config target branches, in config order, filtered to those present
        config_branches = [t.branch for t in config.targets]
        missing = [b for b in config_branches if b not in available_branches]
        if missing:
            raise BuildError(
                f"The following configured branches are missing from the generated "
                f"repo: {', '.join(missing)}. Re-run generate or use --branch."
            )
        requested = config_branches

    dist_dir = workspace_dir / "DIST"
    warnings: list[str] = []

    # 5. Dry-run: return plan only
    if dry_run:
        return BuildResult(
            repo_dir=repo_dir,
            built_branches=requested,
            copied_jars=[],
            warnings=warnings,
            dry_run=True,
        )

    # 6. Real build
    built: list[str] = []
    all_jars: list[Path] = []

    versioned_dist_dir = dist_dir / f"{config.mod_id}-{config.mod_version}"

    for i, br in enumerate(requested):
        # Checkout
        try:
            git_checkout(repo_dir, br)
        except Exception as exc:
            raise BuildError(f"Failed to checkout branch '{br}': {exc}") from exc

        # Find wrapper
        wrapper = find_gradle_wrapper(repo_dir)

        # Run Gradle
        run_gradle_build(repo_dir, wrapper, on_log_line=on_log_line)

        # Find target configuration details
        target_cfg = None
        for t in config.targets:
            if t.branch == br:
                target_cfg = t
                break

        # Collect JARs
        jars = collect_built_jars(
            repo_dir,
            versioned_dist_dir,
            mod_id=config.mod_id,
            mod_version=config.mod_version,
            branch_name=br,
            loader=target_cfg.loader if target_cfg else None,
            mc_version=target_cfg.minecraft_version if target_cfg else None,
        )
        all_jars.extend(jars)
        built.append(br)

    # 7. Leave on first built branch
    if built:
        try:
            git_checkout(repo_dir, built[0])
        except Exception as exc:
            warnings.append(
                f"Could not restore checkout to first branch '{built[0]}': {exc}"
            )

    return BuildResult(
        repo_dir=versioned_dist_dir,  # Return versioned path as repo_dir for display
        built_branches=built,
        copied_jars=all_jars,
        warnings=warnings,
        dry_run=False,
    )
