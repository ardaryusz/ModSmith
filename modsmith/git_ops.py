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
    """Write or update the .gitignore in *repo_dir* with all canonical rules.

    If the file already exists (e.g. copied from a template), canonical rules
    are merged in while preserving existing custom rules and comments.
    A bare ``*.jar`` rule from legacy templates receives a
    ``!gradle/wrapper/gradle-wrapper.jar`` negation exception.
    """
    from modsmith.gitignore_rules import ensure_gitignore_rules
    ensure_gitignore_rules(Path(repo_dir) / ".gitignore")


def _ensure_git_user_config(repo_dir: Path) -> None:
    """Helper to ensure a local Git user.name/email is configured so commit works on clean environments."""
    try:
        run_subprocess(["git", "config", "user.name"], cwd=repo_dir)
    except Exception:
        try:
            run_subprocess(["git", "config", "--local", "user.name", "ModSmith Generator"], cwd=repo_dir)
            run_subprocess(["git", "config", "--local", "user.email", "generator@modsmith.local"], cwd=repo_dir)
        except Exception:
            pass


def git_head_exists(repo_dir: Path) -> bool:
    """Return True if the repository has at least one commit (HEAD exists)."""
    from modsmith.utils import run_process
    res = run_process(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True)
    return res.returncode == 0


def git_has_staged_changes(repo_dir: Path) -> bool:
    """Return True if there are staged changes relative to HEAD."""
    from modsmith.utils import run_process
    if not git_head_exists(repo_dir):
        # In a repository with no commits, check if any files are in the index
        res = run_process(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True)
        for line in res.stdout.splitlines():
            if line.startswith("A ") or line.startswith("M "):
                return True
        return False

    res = run_process(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, capture_output=True)
    if res.returncode == 0:
        return False
    if res.returncode == 1:
        return True
    raise RuntimeError(f"Git diff --cached --quiet failed with exit code {res.returncode}: {res.stderr}")



def git_is_file_tracked(repo_dir: Path, filename: str) -> bool:
    """Return True if the file is tracked in the current Git branch index."""
    from modsmith.utils import run_process
    res = run_process(["git", "ls-files", "--error-unmatch", filename], cwd=repo_dir, capture_output=True)
    return res.returncode == 0


def git_is_file_locally_modified(repo_dir: Path, filename: str) -> bool:
    """Return True if the file has local unstaged or staged modifications or is untracked."""
    from modsmith.utils import run_process
    if not (repo_dir / filename).exists():
        return False
    res = run_process(["git", "status", "--porcelain", "--", filename], cwd=repo_dir, capture_output=True)
    return bool(res.stdout.strip())


def git_last_commit_message(repo_dir: Path, filename: str) -> str:
    """Return the message of the last commit that touched the file."""
    from modsmith.utils import run_process
    res = run_process(["git", "log", "-1", "--format=%s", "--", filename], cwd=repo_dir, capture_output=True)
    return res.stdout.strip()


def git_rm_file(repo_dir: Path, filename: str) -> None:
    """Delete a tracked file and stage the deletion."""
    run_subprocess(["git", "rm", "-f", filename], cwd=repo_dir)


def git_rm_all_tracked(repo_dir: Path) -> None:
    """Remove all tracked files from both the index and working tree (retaining untracked files)."""
    run_subprocess(["git", "rm", "-rf", "."], cwd=repo_dir)

