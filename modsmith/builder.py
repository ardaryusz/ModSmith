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

import re
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
    #: Maps branch name -> destination JAR path for per-branch log output.
    jar_map: dict[str, Path] = field(default_factory=dict)


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
# Branch-name sanitization helpers
# ---------------------------------------------------------------------------

# Characters illegal in Windows filenames (beyond NUL, which Path handles)
_ILLEGAL_WIN_CHARS = re.compile(r'[<>:"/\\|?*]')
# Leading/trailing dots and spaces are problematic on Windows
_TRIM_CHARS = re.compile(r'^[\s.]+|[\s.]+$')


def _sanitize_branch_name(branch: str) -> str:
    """Return a filename-safe version of *branch*.

    Transformations applied (in order):
    1. Replace ``/`` and ``\\`` with ``-``.
    2. Strip characters illegal on Windows filenames: ``< > : " | ? *``.
    3. Trim leading/trailing spaces and dots.
    4. Collapse runs of ``-`` into a single ``-``.
    5. Fall back to ``_branch_`` if the result is empty.
    """
    safe = branch.replace("/", "-").replace("\\", "-")
    safe = _ILLEGAL_WIN_CHARS.sub("", safe)
    safe = _TRIM_CHARS.sub("", safe)
    safe = re.sub(r"-{2,}", "-", safe)
    return safe or "_branch_"


def _make_dist_jar_name(mod_id: str, branch: str, mod_version: str) -> str:
    """Return the canonical DIST filename for a target branch.

    Format: ``<mod_id>-<sanitized_branch>-<mod_version>.jar``

    Example::

        _make_dist_jar_name("easypeasyslime", "fabric-1.21-1.21.1", "1.0.1")
        # → "easypeasyslime-fabric-1.21-1.21.1-1.0.1.jar"
    """
    return f"{mod_id}-{_sanitize_branch_name(branch)}-{mod_version}.jar"


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
# Helper: clean stale target JARs (branch-name scoped)
# ---------------------------------------------------------------------------


def _clean_stale_jars_for_branch(
    dist_dir: Path,
    mod_id: str,
    mod_version: str,
    branch_name: str,
) -> None:
    """Remove any previously-collected JAR for *branch_name* in *dist_dir*.

    Only the deterministic branch-based filename is targeted:
    ``<mod_id>-<sanitized_branch>-<mod_version>.jar``

    This prevents stale files from a previous build run for the same branch
    without touching JARs produced by other branches.
    """
    if not dist_dir.is_dir():
        return

    expected_name = _make_dist_jar_name(mod_id, branch_name, mod_version)
    stale = dist_dir / expected_name
    if stale.is_file():
        try:
            stale.unlink()
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
    # Kept for backward compatibility but no longer used for naming:
    loader: str | None = None,
    mc_version: str | None = None,
    # Tracks dest paths already written in this build run (collision guard):
    _seen_dest: dict[str, str] | None = None,
) -> tuple[list[Path], Path | None]:
    """Copy the release JAR from ``build/libs/`` into *dist_dir*.

    When *mod_id*, *mod_version*, and *branch_name* are all provided the
    destination filename is computed as::

        <mod_id>-<sanitized_branch_name>-<mod_version>.jar

    This guarantees a unique filename per configured target regardless of the
    Gradle-generated name.

    Returns
    -------
    tuple[list[Path], Path | None]
        A tuple of ``(copied_paths, dist_jar_path)`` where *dist_jar_path*
        is the single branch-named destination (or ``None`` if branch naming
        was not used).

    Raises :class:`BuildError` if:
    - ``build/libs/`` does not exist.
    - No valid release JAR is found there.
    - Two different branches resolve to the same DIST filename in the same
      build run (collision).
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
    branch_dest: Path | None = None

    use_branch_naming = bool(mod_id and mod_version and branch_name)

    if use_branch_naming:
        # Clean the previous JAR for this branch (from an earlier run).
        _clean_stale_jars_for_branch(dist_dir, mod_id, mod_version, branch_name)

        # Collision guard: check BEFORE the loop because all source JARs in
        # build/libs will be renamed to the same branch-based dest name.
        # The guard must fire only when a *different* branch tries to claim
        # the same dest name — not when the same branch produces multiple
        # intermediate JARs (e.g. shadow + regular release).
        branch_dest_name = _make_dist_jar_name(mod_id, branch_name, mod_version)
        if _seen_dest is not None:
            if branch_dest_name in _seen_dest:
                other_branch = _seen_dest[branch_dest_name]
                if other_branch != branch_name:
                    raise BuildError(
                        f"JAR filename collision detected: both target branch "
                        f"'{other_branch}' and '{branch_name}' would produce "
                        f"'{branch_dest_name}'. Ensure branch names are unique."
                    )
            else:
                _seen_dest[branch_dest_name] = branch_name

    for jar in sorted(candidates):
        if use_branch_naming:
            dest_name = branch_dest_name  # pre-computed above
        else:
            dest_name = jar.name

        dest = dist_dir / dest_name
        shutil.copy2(jar, dest)
        if dest not in copied:
            copied.append(dest)
        if use_branch_naming:
            branch_dest = dest

    return copied, branch_dest


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
       d. copy release JAR to ``WORKSPACE/DIST/<modid>-<mod_version>/``
          using the branch-based unique filename.
    7. Leave the repo checked out on the **first** branch that was built.

    Raises
    ------
    :class:`BuildError`
         For any user-fixable problem (missing repo, missing branch, Gradle
         failure, missing JARs, or a JAR filename collision between targets).
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
    jar_map: dict[str, Path] = {}

    versioned_dist_dir = dist_dir / f"{config.mod_id}-{config.mod_version}"

    # Tracks dest filenames written in this build run to detect collisions.
    seen_dest: dict[str, str] = {}

    for br in requested:
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
        target_cfg = next((t for t in config.targets if t.branch == br), None)

        # Collect JARs — uses branch-based unique naming
        jars, branch_jar = collect_built_jars(
            repo_dir,
            versioned_dist_dir,
            mod_id=config.mod_id,
            mod_version=config.mod_version,
            branch_name=br,
            loader=target_cfg.loader if target_cfg else None,
            mc_version=target_cfg.minecraft_version if target_cfg else None,
            _seen_dest=seen_dest,
        )
        all_jars.extend(jars)
        if branch_jar is not None:
            jar_map[br] = branch_jar
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
        jar_map=jar_map,
    )
