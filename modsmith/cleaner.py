"""Orchestrator for deleting the generated repository (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from modsmith.config import load_mod_config, ConfigError
from modsmith.utils import safe_delete_tree


@dataclass
class CleanResult:
    repo_dir: Path
    deleted: bool
    dry_run: bool
    message: str


class CleanError(Exception):
    """Raised when deletion fails due to permissions, file handles, or other OS errors."""


def clean(
    workspace_dir: Path,
    mods_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    confirm_fn: Callable[[str], str] | None = None,
) -> CleanResult:
    """Delete the generated output repository.

    1. Load WORKSPACE/DETAILS/modsmith.json.
    2. Resolve output repo: MODS/<output_repo_name>.
    3. If output repo does not exist: friendly message, exit 0.
    4. If output repo exists:
       - without --force: prompt for confirmation. Accept y/yes case-insensitive.
       - with --force: delete without prompting.
    5. Use safe_delete_tree.
    6. On dry-run: print/return what would be deleted, do not prompt or delete.
    """
    config_path = workspace_dir / "DETAILS" / "modsmith.json"
    try:
        config = load_mod_config(config_path)
    except ConfigError as exc:
        raise CleanError(f"Could not load modsmith.json: {exc}") from exc

    repo_dir = mods_dir / config.output_repo_name

    if not repo_dir.exists():
        return CleanResult(
            repo_dir=repo_dir,
            deleted=False,
            dry_run=dry_run,
            message=f"No generated repository found at: {repo_dir}",
        )

    if dry_run:
        return CleanResult(
            repo_dir=repo_dir,
            deleted=False,
            dry_run=True,
            message=f"Dry run: Would delete generated repository at: {repo_dir}",
        )

    if not force:
        prompt_msg = f"Delete generated repo MODS/{config.output_repo_name}? [y/n] "
        
        if confirm_fn is None:
            try:
                response = input(prompt_msg)
            except (KeyboardInterrupt, EOFError):
                response = "n"
        else:
            response = confirm_fn(prompt_msg)

        if response.strip().lower() not in ("y", "yes"):
            return CleanResult(
                repo_dir=repo_dir,
                deleted=False,
                dry_run=False,
                message="Deletion cancelled by user.",
            )

    try:
        safe_delete_tree(repo_dir)
    except OSError as exc:
        raise CleanError(f"Failed to delete repository {repo_dir}: {exc}") from exc

    return CleanResult(
        repo_dir=repo_dir,
        deleted=True,
        dry_run=False,
        message=f"Successfully deleted generated repository at: {repo_dir}",
    )
