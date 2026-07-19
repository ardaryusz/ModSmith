"""Canonical .gitignore rules for ModSmith-generated repositories.

Public API
----------
- REQUIRED_GITIGNORE_RULES   — tuple of required rule strings (no newlines)
- FORBIDDEN_ARTIFACT_PATTERNS — patterns used by safety scans
- render_canonical_gitignore()  — produce deterministic ModSmith-managed content
- ensure_gitignore_rules()      — merge canonical rules into existing custom files
- GitignoreUpdateResult         — dataclass returned by ensure_gitignore_rules()
- scan_staged_for_artifacts()   — scan ``git diff --cached`` output for forbidden paths
- scan_committed_for_artifacts()— scan ``git ls-tree -r HEAD`` output for forbidden paths
- scan_template_for_artifacts() — scan a source template directory before copying
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Canonical rule set
# ---------------------------------------------------------------------------

# Each entry is a single gitignore pattern (no trailing newlines).
REQUIRED_GITIGNORE_RULES: tuple[str, ...] = (
    # IDE
    ".idea/",
    ".vscode/",
    "*.iml",
    "out/",
    # OS
    ".DS_Store",
    "Thumbs.db",
    # Gradle and development output
    ".gradle/",
    "build/",
    "run/",
    "logs/",
    "*.class",
    "*.log",
    "hs_err_pid*",
    "replay_pid*",
)

# Patterns whose presence in a staged/committed/template tree indicates a forbidden artifact.
# These are prefix checks against paths returned by git ls-tree / git diff --cached.
FORBIDDEN_ARTIFACT_PATTERNS: tuple[str, ...] = (
    ".gradle/",
    "build/",
    "run/",
    "logs/",
    "out/",
)

# Glob-style suffixes to reject in staged/committed paths
FORBIDDEN_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    ".class",
    ".log",
)

# Filename prefixes for JVM crash/replay files
FORBIDDEN_ARTIFACT_PREFIXES: tuple[str, ...] = (
    "hs_err_pid",
    "replay_pid",
)

# Never flag this path as a forbidden artifact even though it ends in .jar
_SAFE_JAR_PATH = "gradle/wrapper/gradle-wrapper.jar"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class GitignoreUpdateResult:
    """Result of ensure_gitignore_rules()."""
    added: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    had_bare_jar_rule: bool = False
    appended_jar_exception: bool = False


# ---------------------------------------------------------------------------
# Helpers: normalise a gitignore line for comparison
# ---------------------------------------------------------------------------

def _norm(rule: str) -> str:
    """Normalise a gitignore pattern for membership tests.

    Strips trailing slashes so that ``build/`` and ``build`` both match the
    canonical ``build/`` rule, and strips leading/trailing whitespace.
    """
    return rule.strip().rstrip("/")


def _effective_rules_in_file(text: str) -> set[str]:
    """Return the set of normalised non-comment, non-blank patterns in *text*."""
    result: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            result.add(_norm(stripped))
    return result


def _missing_canonical_rules(existing_text: str) -> list[str]:
    """Return canonical rules that are absent from *existing_text*.

    Comparison is done via _norm so ``build`` matches ``build/``.
    """
    existing = _effective_rules_in_file(existing_text)
    return [r for r in REQUIRED_GITIGNORE_RULES if _norm(r) not in existing]


# ---------------------------------------------------------------------------
# render_canonical_gitignore()
# ---------------------------------------------------------------------------

_CANONICAL_BODY = """\
# IDE
.idea/
.vscode/
*.iml
out/

# OS
.DS_Store
Thumbs.db

# Gradle and development output
.gradle/
build/
run/
logs/
*.class
*.log
hs_err_pid*
replay_pid*
"""

def render_canonical_gitignore(*, header_comment: str = "# ModSmith managed") -> str:
    """Return the fully-rendered, deterministic ModSmith-managed .gitignore content.

    Used for:
    - Landing branch .gitignore (generator.py)
    - Official source template .gitignore files

    The output is always identical for the same *header_comment*, has no
    duplicate rules, and ends with exactly one newline.
    """
    return f"{header_comment}\n{_CANONICAL_BODY}"


# ---------------------------------------------------------------------------
# ensure_gitignore_rules()
# ---------------------------------------------------------------------------

def ensure_gitignore_rules(path: Path) -> GitignoreUpdateResult:
    """Merge canonical rules into an existing or missing .gitignore file.

    Behaviour:
    - If the file is missing, write the full canonical content.
    - If the file exists, preserve *all* existing content (rules, comments,
      blank lines) and append only the canonical rules that are absent.
    - Handles custom/legacy templates that contain a bare ``*.jar`` rule:
      appends ``!gradle/wrapper/gradle-wrapper.jar`` after the ``*.jar`` line.
    - Ensures exactly one trailing newline.
    - Deterministic and idempotent.

    Returns a GitignoreUpdateResult describing what was changed.
    """
    path = Path(path)
    result = GitignoreUpdateResult()

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_canonical_gitignore(), encoding="utf-8")
        result.added = list(REQUIRED_GITIGNORE_RULES)
        return result

    existing_text = path.read_text(encoding="utf-8")

    # Detect bare *.jar rule (present in some legacy templates)
    has_jar_rule = any(
        line.strip() in ("*.jar", "*.jar ") or line.strip() == "*.jar"
        for line in existing_text.splitlines()
    )
    has_jar_exception = "!gradle/wrapper/gradle-wrapper.jar" in existing_text

    missing = _missing_canonical_rules(existing_text)

    # Nothing to add and no jar fixup needed?
    if not missing and (not has_jar_rule or has_jar_exception):
        result.already_present = list(REQUIRED_GITIGNORE_RULES)
        result.had_bare_jar_rule = has_jar_rule
        return result

    lines = existing_text.splitlines(keepends=True)

    # Ensure file ends with exactly one newline before we append
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"

    new_content = "".join(lines)

    # Append *.jar exception directly after the *.jar line
    if has_jar_rule and not has_jar_exception:
        result.had_bare_jar_rule = True
        result.appended_jar_exception = True
        fixed_lines = []
        for line in new_content.splitlines(keepends=True):
            fixed_lines.append(line)
            if line.strip() == "*.jar":
                fixed_lines.append("!gradle/wrapper/gradle-wrapper.jar\n")
        new_content = "".join(fixed_lines)

    if missing:
        if not new_content.endswith("\n\n"):
            new_content = new_content.rstrip("\n") + "\n"
        new_content += "\n# ModSmith (generated-artifact rules)\n"
        for rule in missing:
            new_content += f"{rule}\n"
        result.added = missing

    # Guarantee exactly one trailing newline
    new_content = new_content.rstrip("\n") + "\n"

    path.write_text(new_content, encoding="utf-8")
    result.already_present = [r for r in REQUIRED_GITIGNORE_RULES if r not in missing]
    return result


# ---------------------------------------------------------------------------
# Artifact safety scanners
# ---------------------------------------------------------------------------

def _is_forbidden_path(rel_path: str) -> bool:
    """Return True if *rel_path* represents a forbidden build artifact.

    Checks:
    - Path starts with a FORBIDDEN_ARTIFACT_PATTERNS prefix
    - Path ends with a FORBIDDEN_ARTIFACT_SUFFIXES suffix
    - Filename starts with a FORBIDDEN_ARTIFACT_PREFIXES prefix
    Exemptions:
    - gradle/wrapper/gradle-wrapper.jar
    """
    if rel_path == _SAFE_JAR_PATH:
        return False
    # Normalise separators
    norm = rel_path.replace("\\", "/")
    for pat in FORBIDDEN_ARTIFACT_PATTERNS:
        prefix = pat.rstrip("/") + "/"
        if norm == prefix.rstrip("/") or norm.startswith(prefix):
            return True
    for suf in FORBIDDEN_ARTIFACT_SUFFIXES:
        if norm.endswith(suf):
            return True
    fname = norm.rsplit("/", 1)[-1]
    for pre in FORBIDDEN_ARTIFACT_PREFIXES:
        if fname.startswith(pre):
            return True
    return False


def scan_staged_for_artifacts(
    repo_dir: Path,
) -> list[str]:
    """Return staged paths that are forbidden build artifacts.

    Uses ``git diff --cached --name-only --diff-filter=ACMR`` so only
    added/copied/modified/renamed files are checked — no deleted files.
    """
    from modsmith.utils import run_process
    res = run_process(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=repo_dir,
        capture_output=True,
    )
    forbidden: list[str] = []
    for line in res.stdout.splitlines():
        path = line.strip()
        if path and _is_forbidden_path(path):
            forbidden.append(path)
    return forbidden


def scan_committed_for_artifacts(
    repo_dir: Path,
) -> list[str]:
    """Return paths tracked in HEAD that are forbidden build artifacts.

    Uses ``git ls-tree -r --name-only HEAD``.
    """
    from modsmith.utils import run_process
    res = run_process(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
    )
    forbidden: list[str] = []
    for line in res.stdout.splitlines():
        path = line.strip()
        if path and _is_forbidden_path(path):
            forbidden.append(path)
    return forbidden


def scan_template_for_artifacts(
    template_dir: Path,
) -> list[str]:
    """Return file paths inside *template_dir* that are forbidden build artifacts.

    Excludes `.git/`, `gradle/wrapper/gradle-wrapper.jar`, and any path that
    is itself a `.gitignore` or `modsmith-template.json`.
    """
    template_dir = Path(template_dir)
    forbidden: list[str] = []
    if not template_dir.is_dir():
        return forbidden
    exclude_dirs = {".git", "build", ".gradle", "run", "out", "logs"}
    for f in template_dir.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(template_dir)
        except ValueError:
            continue
        rel_str = str(rel).replace("\\", "/")
        # Skip .git internals
        if any(part == ".git" for part in rel.parts):
            continue
        if _is_forbidden_path(rel_str):
            forbidden.append(rel_str)
    return forbidden
