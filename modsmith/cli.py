"""Command-line interface for ModSmith.

Entry points
------------
- ``python -m modsmith``  (via ``__main__.py``)
- ``modsmith``            (via ``pyproject.toml`` console-script)

Sub-commands
------------
- ``validate``  — check workspace, config, and templates
- ``generate``  — build orphan-branch Git repo
- ``build``     — Gradle build + JAR collection
- ``clean``     — delete generated repo

Global flags
------------
- ``--workspace DIR``  override workspace root  (default: ``WORKSPACE``)
- ``--templates DIR``  override templates root  (default: ``MODTEMPLATES``)
- ``--mods DIR``       override mods root       (default: ``MODS``)
- ``--dry-run``        print planned actions without writing files or running Git

Environment variables
---------------------
- ``MODSMITH_HOME``  If set, defaults for ``--workspace``, ``--templates``,
  and ``--mods`` resolve as sub-directories of this path instead of the
  current working directory.  Explicit CLI flags always take precedence.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from modsmith import __version__
from modsmith.validator import validate_workspace


# ---------------------------------------------------------------------------
# MODSMITH_HOME default-path helper
# ---------------------------------------------------------------------------


def _get_default_dir(subdir: str) -> str:
    """Return the default path for *subdir* respecting ``MODSMITH_HOME``.

    If the ``MODSMITH_HOME`` environment variable is set, returns
    ``$MODSMITH_HOME/<subdir>`` as a string.  Otherwise returns the bare
    *subdir* name (relative to the current working directory), preserving
    backwards-compatible behaviour.
    """
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return str(Path(home) / subdir)
    return subdir


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modsmith",
        description=(
            "ModSmith — local automation tool for generating recipe-only "
            "Minecraft mods across multiple mod loaders and MC version ranges."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--workspace",
        default=_get_default_dir("WORKSPACE"),
        metavar="DIR",
        help="Path to the workspace directory (default: %(default)s)",
    )
    parser.add_argument(
        "--templates",
        default=_get_default_dir("MODTEMPLATES"),
        metavar="DIR",
        help="Path to the mod templates directory (default: %(default)s)",
    )
    parser.add_argument(
        "--mods",
        default=_get_default_dir("MODS"),
        metavar="DIR",
        help="Path to the output mods directory (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="global_dry_run",
        help="Print planned actions without writing files or running Git commands",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── validate ──────────────────────────────────────────────────────────────
    validate_p = sub.add_parser(
        "validate",
        help="Validate the workspace configuration and templates",
        description=(
            "Checks that modsmith.json is valid, all target templates exist, "
            "recipe files are present, and Git is available.  "
            "Exits 0 on success, 1 if any errors are found."
        ),
    )
    validate_p.add_argument(
        "--force",
        action="store_true",
        help="Suppress the 'output repo already exists' warning/error",
    )

    # ── generate ──────────────────────────────────────────────────────────────
    generate_p = sub.add_parser(
        "generate",
        help="Generate the output mod repo with one orphan branch per target",
        description=(
            "Creates MODS/<output_repo_name>, initialises Git, and produces one "
            "orphan branch per target containing a complete, patched Minecraft mod "
            "project ready to build with Gradle."
        ),
    )
    generate_p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Delete and fully regenerate the output repo if it already exists. "
            "Without this flag, generate fails if the repo exists."
        ),
    )
    generate_p.add_argument(
        "--target",
        metavar="BRANCH",
        help="Generate only the specified target branch (matched by branch name)",
    )
    generate_p.add_argument(
        "--dry-run",
        action="store_true",
        dest="command_dry_run",
        help="Print planned actions without writing files or running Git commands",
    )

    # ── build ─────────────────────────────────────────────────────────────────
    build_p = sub.add_parser(
        "build",
        help="Build target branches with Gradle and collect JARs",
        description=(
            "Checks out each target branch in turn, runs gradlew clean build, "
            "and copies finished release JARs into WORKSPACE/DIST/."
        ),
    )
    build_p.add_argument(
        "--branch",
        metavar="BRANCH",
        help="Build only the specified target branch",
    )
    build_p.add_argument(
        "--dry-run",
        action="store_true",
        dest="command_dry_run",
        help="Print planned actions without writing files or running Git commands",
    )

    # ── clean ─────────────────────────────────────────────────────────────────
    clean_p = sub.add_parser(
        "clean",
        help="Delete the generated output repo",
        description=(
            "Deletes MODS/<output_repo_name> after a confirmation prompt.  "
        ),
    )
    clean_p.add_argument(
        "--force",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    clean_p.add_argument(
        "--dry-run",
        action="store_true",
        dest="command_dry_run",
        help="Print planned actions without writing files or running Git commands",
    )

    # ── doctor ────────────────────────────────────────────────────────────────
    doctor_p = sub.add_parser(
        "doctor",
        help="Check the environment and report issues",
        description=(
            "Inspects the local ModSmith environment, checking directories, "
            "configuration, recipes, templates, and path tools. "
            "Exits 0 on success, 1 if any errors are found."
        ),
    )
    doctor_p.add_argument(
        "--dev",
        action="store_true",
        help="Include development and release-packaging checks",
    )

    # ── home ──────────────────────────────────────────────────────────────────
    home_p = sub.add_parser(
        "home",
        help="Manage the MODSMITH_HOME environment variable and directories",
        description="Show, set, unset, or open the persistent ModSmith home directory.",
    )
    home_sub = home_p.add_subparsers(dest="home_command", metavar="SUBCOMMAND")
    home_sub.required = True

    # home show
    home_sub.add_parser(
        "show",
        help="Show the current effective ModSmith home directory",
    )

    # home set <path>
    home_set_p = home_sub.add_parser(
        "set",
        help="Set the ModSmith home directory persistently",
    )
    home_set_p.add_argument(
        "path",
        help="The target path for the ModSmith home directory",
    )

    # home unset
    home_sub.add_parser(
        "unset",
        help="Remove the ModSmith home directory persistently",
    )

    # home open
    home_sub.add_parser(
        "open",
        help="Open the current ModSmith home directory in file explorer",
    )

    # ── template ──────────────────────────────────────────────────────────────
    template_p = sub.add_parser(
        "template",
        help="List and verify available mod templates",
        description="List and verify available templates under MODTEMPLATES.",
    )
    template_sub = template_p.add_subparsers(dest="template_command", metavar="SUBCOMMAND")
    template_sub.required = True

    # template list
    template_sub.add_parser(
        "list",
        help="List all templates and report whether each one is usable",
    )

    return parser


# ---------------------------------------------------------------------------
# Path resolution helper
# ---------------------------------------------------------------------------


def _resolve_dirs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """Return ``(workspace_dir, templates_dir, mods_dir)`` as absolute Paths."""
    return (
        Path(args.workspace).resolve(),
        Path(args.templates).resolve(),
        Path(args.mods).resolve(),
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> int:
    """Handle ``modsmith validate``.

    Runs all workspace checks, prints every error and warning, then exits with
    code 0 (no errors) or 1 (one or more errors).  Warnings never fail.
    """
    workspace_dir, templates_dir, mods_dir = _resolve_dirs(args)

    result = validate_workspace(
        workspace_dir=workspace_dir,
        templates_dir=templates_dir,
        mods_dir=mods_dir,
        force=args.force,
    )

    # Print warnings
    for w in result.warnings:
        print(f"  [WARN]  {w}")

    # Print errors
    for e in result.errors:
        print(f"  [ERROR] {e}")

    # Print summary
    if result.ok:
        print("Validation passed")
        return 0
    else:
        print(
            f"Validation failed with {len(result.errors)} error(s), "
            f"{len(result.warnings)} warning(s)"
        )
        return 1


def cmd_generate(args: argparse.Namespace) -> int:
    """Handle ``modsmith generate``.

    Initialises a Git repository and produces one orphan branch per target.
    """
    workspace_dir, templates_dir, mods_dir = _resolve_dirs(args)
    from modsmith.generator import generate

    try:
        res = generate(
            workspace_dir=workspace_dir,
            templates_dir=templates_dir,
            mods_dir=mods_dir,
            dry_run=args.dry_run,
            force=args.force,
            target_branch=args.target,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Print warnings
    for w in res.warnings:
        print(f"  [WARN]  {w}")

    if res.dry_run:
        print(f"Dry run complete. Planned repository at: {res.repo_dir}")
        print("Planned branches:")
        for b in res.generated_branches:
            print(f"  - {b}")
    else:
        print(f"Repository generated successfully at: {res.repo_dir}")
        print("Generated branches:")
        for b in res.generated_branches:
            print(f"  - {b}")
        print("\nNext steps:")
        try:
            rel = res.repo_dir.relative_to(Path.cwd())
        except ValueError:
            rel = res.repo_dir
        print(f"  - Change directory: cd {rel}")
        print("  - Build the mods:   python -m modsmith build")

    return 0



def cmd_build(args: argparse.Namespace) -> int:
    """Handle ``modsmith build``.

    Checks out each target branch, runs Gradle, and collects release JARs
    into ``WORKSPACE/DIST/``.
    """
    workspace_dir, _templates_dir, mods_dir = _resolve_dirs(args)
    from modsmith.builder import build, BuildError

    try:
        res = build(
            workspace_dir=workspace_dir,
            mods_dir=mods_dir,
            branch=args.branch,
            dry_run=args.dry_run,
        )
    except BuildError as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1

    # Print warnings
    for w in res.warnings:
        print(f"  [WARN]  {w}")

    if res.dry_run:
        print(f"Dry run — repo: {res.repo_dir}")
        print("Planned branches (gradlew clean build):")
        for b in res.built_branches:
            print(f"  - {b}")
    else:
        print(f"Build complete — repo: {res.repo_dir}")
        print("Built branches:")
        for b in res.built_branches:
            print(f"  - {b}")
        if res.copied_jars:
            print("\nJARs copied to WORKSPACE/DIST/:")
            for j in res.copied_jars:
                print(f"  - {j.name}")

    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Handle ``modsmith clean``.

    Deletes the generated repository MODS/<output_repo_name>.
    """
    workspace_dir, _templates_dir, mods_dir = _resolve_dirs(args)
    from modsmith.cleaner import clean, CleanError

    try:
        res = clean(
            workspace_dir=workspace_dir,
            mods_dir=mods_dir,
            force=args.force,
            dry_run=args.dry_run,
        )
    except CleanError as exc:
        print(f"Clean error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(res.message)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Handle ``modsmith doctor``.

    Runs diagnostic checks on workspace, paths, config, recipes, and tools.
    Prints status with appropriate prefixes. Returns 0 if ok, 1 if error.
    """
    workspace_dir, templates_dir, mods_dir = _resolve_dirs(args)
    from modsmith.doctor import diagnose_environment

    result = diagnose_environment(
        workspace_dir=workspace_dir,
        templates_dir=templates_dir,
        mods_dir=mods_dir,
        dev_mode=args.dev,
    )

    # Print logs
    for info in result.infos:
        print(f"  [INFO]  {info}")

    for warn in result.warnings:
        print(f"  [WARN]  {warn}")

    for err in result.errors:
        print(f"  [ERROR] {err}")

    # Print summary
    print(f"\nDoctor finished: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")

    if result.ok:
        return 0
    return 1


def cmd_home(args: argparse.Namespace) -> int:
    """Handle ``modsmith home``.

    Dispatches to show, set, unset, or open subcommands.
    """
    from modsmith.home import (
        get_effective_home,
        ensure_home_structure,
        set_user_home,
        unset_user_home,
        open_home,
    )

    h_cmd = args.home_command

    if h_cmd == "show":
        effective = get_effective_home()
        if effective:
            print(f"MODSMITH_HOME is set: {effective}")
        else:
            print("MODSMITH_HOME is unset. Relative defaults are active.")
            print("  WORKSPACE, MODTEMPLATES, MODS")

        workspace_dir, templates_dir, mods_dir = _resolve_dirs(args)
        print("Resolved paths:")
        print(f"  Workspace: {workspace_dir}")
        print(f"  Templates: {templates_dir}")
        print(f"  Mods:      {mods_dir}")
        return 0

    elif h_cmd == "set":
        target_path = Path(args.path)
        # Create standard home structure
        ensure_home_structure(target_path)
        # Set persistently
        set_user_home(target_path)

        # print success status
        print(f"[OK] Set MODSMITH_HOME to: {target_path.resolve()}")
        print("[OK] Created/verified workspace folders")
        print("[INFO] Open a new terminal for the change to appear in new shells.")
        print("[INFO] Existing data was not moved automatically.")
        return 0

    elif h_cmd == "unset":
        unset_user_home()
        print("[OK] Removed MODSMITH_HOME from user environment.")
        print("[INFO] Existing ModSmith data folders were not deleted.")
        print("[INFO] Open a new terminal for the change to appear.")
        return 0

    elif h_cmd == "open":
        effective = get_effective_home()
        if effective:
            open_home(effective)
        else:
            print("[INFO] MODSMITH_HOME is unset. Relative defaults are active.")
            print("Opening the current working directory instead.")
            open_home(Path.cwd())
        return 0

    return 1


def cmd_template(args: argparse.Namespace) -> int:
    """Handle ``modsmith template`` commands."""
    t_cmd = args.template_command

    if t_cmd == "list":
        _, templates_dir, _ = _resolve_dirs(args)
        from modsmith.template_listing import list_templates

        print(f"  [INFO]  Scanning templates directory: {templates_dir}")
        result = list_templates(templates_dir)

        # Print all template details
        for t in result.templates:
            print(f"  [INFO]  Template: {t.name}")
            print(f"  [INFO]    Path: {t.path}")

            if t.has_descriptor:
                print("  [OK]      modsmith-template.json exists")
            else:
                print("  [ERROR]   modsmith-template.json is missing")

            if t.descriptor_valid:
                print("  [OK]      Descriptor parses successfully")
                print(f"  [INFO]      Loader:            {t.loader}")
                print(f"  [INFO]      Minecraft version: {t.minecraft_version}")
                print(f"  [INFO]      Recipe folder:     {t.recipe_folder}")
                print(f"  [INFO]      Recipe format:     {t.recipe_format}")
                print(f"  [INFO]      JAR loader suffix: {t.jar_loader_suffix}")
            elif t.has_descriptor:
                print(f"  [ERROR]   Descriptor failed to parse: {t.error_message}")

            if t.has_gradlew and t.has_gradlew_bat:
                print("  [OK]      gradlew and gradlew.bat both exist")
            elif t.has_gradlew:
                print("  [WARN]    gradlew exists, but gradlew.bat is missing")
            elif t.has_gradlew_bat:
                print("  [WARN]    gradlew.bat exists, but gradlew is missing")
            else:
                print("  [WARN]    Both gradlew and gradlew.bat are missing")

            if t.has_gradle_wrapper_jar:
                print("  [OK]      gradle/wrapper/gradle-wrapper.jar exists")
            else:
                print("  [ERROR]   gradle/wrapper/gradle-wrapper.jar is missing")

        # Print global errors/warnings if any
        for err in result.errors:
            print(f"  [ERROR] {err}")
        for warn in result.warnings:
            print(f"  [WARN]  {warn}")

        if result.ok:
            if not result.templates:
                return 0
            print("  [OK]    All templates are valid and usable.")
            return 0
        else:
            print(f"  [ERROR] Template validation failed with {len(result.errors)} error(s).")
            return 1

    return 1


# ---------------------------------------------------------------------------
# Dispatch table and entry point
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS: dict[str, object] = {
    "validate": cmd_validate,
    "generate": cmd_generate,
    "build": cmd_build,
    "clean": cmd_clean,
    "doctor": cmd_doctor,
    "home": cmd_home,
    "template": cmd_template,
}


def main(argv: list[str] | None = None) -> None:
    """Parse *argv* (or ``sys.argv[1:]``) and dispatch to the appropriate handler."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.dry_run = bool(getattr(args, "global_dry_run", False) or getattr(args, "command_dry_run", False))

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))  # type: ignore[operator]


if __name__ == "__main__":
    main()
