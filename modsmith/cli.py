"""Command-line interface for ModSmith.

Entry points
------------
- ``python -m modsmith``  (via ``__main__.py``)
- ``modsmith``            (via ``pyproject.toml`` console-script)

Sub-commands
------------
- ``validate``  — check workspace, config, and templates (Phase 2)
- ``generate``  — build orphan-branch Git repo (Phase 5)
- ``build``     — Gradle build + JAR collection (Phase 6, stub)
- ``clean``     — delete generated repo (Phase 7, stub)

Global flags
------------
- ``--workspace DIR``  override workspace root  (default: ``WORKSPACE``)
- ``--templates DIR``  override templates root  (default: ``MODTEMPLATES``)
- ``--mods DIR``       override mods root       (default: ``MODS``)
- ``--dry-run``        print planned actions without writing files or running Git
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from modsmith import __version__
from modsmith.validator import validate_workspace


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
        default="WORKSPACE",
        metavar="DIR",
        help="Path to the workspace directory (default: %(default)s)",
    )
    parser.add_argument(
        "--templates",
        default="MODTEMPLATES",
        metavar="DIR",
        help="Path to the mod templates directory (default: %(default)s)",
    )
    parser.add_argument(
        "--mods",
        default="MODS",
        metavar="DIR",
        help="Path to the output mods directory (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
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

    # ── build ─────────────────────────────────────────────────────────────────
    build_p = sub.add_parser(
        "build",
        help="[Phase 6] Build target branches with Gradle and collect JARs",
        description=(
            "Checks out each target branch in turn, runs ./gradlew build, "
            "and copies finished JARs into WORKSPACE/DIST/.  "
            "NOT YET IMPLEMENTED."
        ),
    )
    build_p.add_argument(
        "--branch",
        metavar="BRANCH",
        help="Build only the specified target branch",
    )

    # ── clean ─────────────────────────────────────────────────────────────────
    clean_p = sub.add_parser(
        "clean",
        help="[Phase 7] Delete the generated output repo",
        description=(
            "Deletes MODS/<output_repo_name> after a confirmation prompt.  "
            "NOT YET IMPLEMENTED."
        ),
    )
    clean_p.add_argument(
        "--force",
        action="store_true",
        help="Skip the confirmation prompt",
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
    """Handle ``modsmith build`` (Phase 6 stub)."""
    print("[modsmith] build is not yet implemented (Phase 6).")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Handle ``modsmith clean`` (Phase 7 stub)."""
    print("[modsmith] clean is not yet implemented (Phase 7).")
    return 0


# ---------------------------------------------------------------------------
# Dispatch table and entry point
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS: dict[str, object] = {
    "validate": cmd_validate,
    "generate": cmd_generate,
    "build": cmd_build,
    "clean": cmd_clean,
}


def main(argv: list[str] | None = None) -> None:
    """Parse *argv* (or ``sys.argv[1:]``) and dispatch to the appropriate handler."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))  # type: ignore[operator]


if __name__ == "__main__":
    main()
