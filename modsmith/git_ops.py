"""Git operations: init, orphan branch creation, staging, and committing."""

from __future__ import annotations

import shutil
from pathlib import Path
from modsmith.utils import run_subprocess


def git_init(repo_dir: Path) -> None:
    """Initialize a new Git repository in repo_dir."""
    repo_dir = Path(repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)
    run_subprocess(["git", "init"], cwd=repo_dir)
    # Ensure local dummy configuration for clean environments (like CI)
    _ensure_git_user_config(repo_dir)


def git_create_orphan_branch(repo_dir: Path, branch_name: str) -> None:
    """Create and switch to a new Git orphan branch."""
    run_subprocess(["git", "checkout", "--orphan", branch_name], cwd=repo_dir)


def git_clear_working_tree(repo_dir: Path) -> None:
    """Delete all files and folders in repo_dir except .git."""
    repo_dir = Path(repo_dir)
    if not repo_dir.exists():
        return
    for child in repo_dir.iterdir():
        if child.name == ".git":
            continue
        if child.is_file() or child.is_symlink():
            try:
                child.unlink()
            except Exception:
                pass
        elif child.is_dir():
            try:
                shutil.rmtree(child)
            except Exception:
                pass


def git_add_all(repo_dir: Path) -> None:
    """Stage all current files in the repository."""
    run_subprocess(["git", "add", "-A"], cwd=repo_dir)


def git_commit(repo_dir: Path, message: str) -> None:
    """Commit the staged changes with message."""
    # Ensure local config is present just in case before committing
    _ensure_git_user_config(repo_dir)
    run_subprocess(["git", "commit", "-m", message], cwd=repo_dir)


def git_checkout(repo_dir: Path, branch_name: str) -> None:
    """Switch to an existing branch."""
    run_subprocess(["git", "checkout", branch_name], cwd=repo_dir)


def git_current_branch(repo_dir: Path) -> str:
    """Return the name of the currently checked-out branch."""
    res = run_subprocess(["git", "branch", "--show-current"], cwd=repo_dir)
    return res.stdout.strip()


def git_list_branches(repo_dir: Path) -> list[str]:
    """Return a list of all local branches in alphabetical order."""
    res = run_subprocess(["git", "branch", "--format=%(refname:short)"], cwd=repo_dir)
    branches = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    return sorted(branches)


def write_gitignore(repo_dir: Path) -> None:
    """Write standard .gitignore file to repo_dir."""
    gitignore_path = Path(repo_dir) / ".gitignore"
    content = """.gradle/
build/
run/
out/
*.jar
*.log
.idea/
__pycache__/
"""
    gitignore_path.write_text(content, encoding="utf-8")


def _ensure_git_user_config(repo_dir: Path) -> None:
    """Helper to ensure a local Git user.name/email is configured so commit works on clean environments."""
    try:
        run_subprocess(["git", "config", "user.name"], cwd=repo_dir)
    except Exception:
        try:
            run_subprocess(["git", "config", "local", "user.name", "ModSmith Generator"], cwd=repo_dir)
            run_subprocess(["git", "config", "local", "user.email", "generator@modsmith.local"], cwd=repo_dir)
        except Exception:
            pass
