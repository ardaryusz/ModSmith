"""Utility helpers: string validation, name derivation, and subprocess wrapping."""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

# Minecraft mod IDs: lowercase letters, digits, underscores; must start with letter.
_MOD_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Java identifier segment: letters/digits/underscore/dollar, must not start with digit.
_JAVA_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

# Java keywords that cannot be used as identifiers.
_JAVA_KEYWORDS: frozenset[str] = frozenset(
    {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch",
        "char", "class", "const", "continue", "default", "do", "double",
        "else", "enum", "extends", "final", "finally", "float", "for",
        "goto", "if", "implements", "import", "instanceof", "int", "interface",
        "long", "native", "new", "package", "private", "protected", "public",
        "return", "short", "static", "strictfp", "super", "switch",
        "synchronized", "this", "throw", "throws", "transient", "try",
        "var", "void", "volatile", "while",
        # Literals that are not keywords but also cannot be identifiers.
        "true", "false", "null",
    }
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def is_valid_mod_id(mod_id: str) -> bool:
    """Return True if *mod_id* is a valid Minecraft mod identifier.

    Rules: lowercase ASCII letters, digits, and underscores only; must start
    with a letter.  No spaces, hyphens, or uppercase letters allowed.
    """
    return bool(_MOD_ID_RE.match(mod_id))


def is_valid_java_identifier(name: str) -> bool:
    """Return True if *name* is a valid single Java identifier.

    A valid Java identifier matches ``[A-Za-z_$][A-Za-z0-9_$]*`` and is not a
    reserved keyword or literal (``true``, ``false``, ``null``).
    """
    if not _JAVA_IDENT_RE.match(name):
        return False
    return name not in _JAVA_KEYWORDS


def is_valid_java_package(package: str) -> bool:
    """Return True if *package* is a valid dot-separated Java package name.

    Requires at least two segments (e.g. ``com.example``) and each segment
    must be a valid Java identifier.
    """
    if not package:
        return False
    parts = package.split(".")
    if len(parts) < 2:
        return False
    return all(is_valid_java_identifier(part) for part in parts)


# ---------------------------------------------------------------------------
# Name derivation
# ---------------------------------------------------------------------------


def to_class_name(mod_name: str) -> str:
    """Derive a PascalCase Java class name from a human-readable mod name.

    Splits on whitespace, hyphens, underscores, and other non-alphanumeric
    characters, title-cases each token, and concatenates them.

    Examples::

        "Easy Peasy Gunpowder" -> "EasyPeasyGunpowder"
        "my_mod-name"          -> "MyModName"
        "cool mod 2"           -> "CoolMod2"

    If the result would start with a digit (unusual but possible), ``"Mod"``
    is prepended to keep it a valid Java identifier.  Returns an empty string
    if *mod_name* contains no usable alphanumeric characters.
    """
    # Split on any run of non-alphanumeric characters.
    tokens = re.split(r"[^A-Za-z0-9]+", mod_name)
    parts: list[str] = []
    for token in tokens:
        if not token:
            continue
        # Title-case: uppercase first char, leave the rest as-is.
        parts.append(token[0].upper() + token[1:])

    result = "".join(parts)
    if result and result[0].isdigit():
        result = "Mod" + result
    return result


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


_hide_windows_globally = False


def set_hide_windows(hide: bool) -> None:
    """Enable or disable console window hiding for subprocesses globally."""
    global _hide_windows_globally
    _hide_windows_globally = hide


def run_process(
    args: list[str],
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    hide_window: bool = False,
    on_log_line: callable | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run *args* as a subprocess.

    On Windows, if *hide_window* is True (or globally enabled), hides any
    created CMD/console window without using shell=True.

    If *on_log_line* is provided, merges stderr into stdout, streams output
    line-by-line, and does not block/deadlock.
    """
    import os
    import sys

    actual_hide = hide_window or _hide_windows_globally or (os.environ.get("MODSMITH_HIDE_WINDOW") == "1")

    creationflags = 0
    startupinfo = None
    if actual_hide and sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            startupinfo.wShowWindow = 0  # SW_HIDE

    kwargs: dict[str, any] = {}
    if creationflags:
        kwargs["creationflags"] = creationflags
    if startupinfo:
        kwargs["startupinfo"] = startupinfo

    if on_log_line is not None:
        process = subprocess.Popen(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            **kwargs,
        )

        stdout_lines = []
        if process.stdout:
            for line in process.stdout:
                clean_line = line.rstrip("\r\n")
                on_log_line(clean_line)
                stdout_lines.append(line)

        process.wait()
        stdout_content = "".join(stdout_lines)

        return subprocess.CompletedProcess(
            args=args,
            returncode=process.returncode,
            stdout=stdout_content,
            stderr="",
        )

    # Standard execution
    stdout_redir = subprocess.PIPE if capture_output else None
    stderr_redir = subprocess.PIPE if capture_output else None

    res = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=stdout_redir,
        stderr=stderr_redir,
        text=True,
        **kwargs,
    )
    return res


def run_subprocess(
    args: list[str],
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run *args* as a subprocess and return the completed process.

    Raises :class:`subprocess.CalledProcessError` on non-zero exit.
    Raises :class:`FileNotFoundError` if the executable is not on ``PATH``.
    """
    res = run_process(args, cwd=cwd, capture_output=True)
    if res.returncode != 0:
        raise subprocess.CalledProcessError(
            res.returncode,
            args,
            output=res.stdout,
            stderr=res.stderr,
        )
    return res


# ---------------------------------------------------------------------------
# Safe directory deletion
# ---------------------------------------------------------------------------


def safe_delete_tree(path: Path) -> None:
    """Recursively delete *path*, handling read-only files on Windows.

    Git repositories (and Gradle caches) can contain read-only files inside
    ``.git/objects/``.  On Windows, ``shutil.rmtree`` raises ``[WinError 5]
    Access is denied`` when it encounters them.  This helper:

    1. Makes every file under *path* writable before attempting deletion.
    2. Supplies an ``onerror`` / ``onexc`` handler that clears the read-only
       attribute and retries whenever rmtree stumbles.
    3. Raises :class:`OSError` with a clear, actionable message if deletion
       still fails after the retry.

    Does nothing if *path* does not exist.
    """
    path = Path(path)
    if not path.exists():
        return

    def _make_writable(p: Path) -> None:
        """Best-effort: remove read-only flag from *p*."""
        try:
            p.chmod(p.stat().st_mode | stat.S_IWRITE | stat.S_IWGRP | stat.S_IWOTH)
        except Exception:
            pass

    # Pre-pass: make everything writable so the primary rmtree usually succeeds.
    for item in path.rglob("*"):
        _make_writable(item)
    _make_writable(path)

    # onerror/onexc handler for shutil.rmtree
    def _on_error(func, failed_path, exc_info):
        """Chmod the failed path and retry once."""
        _make_writable(Path(failed_path))
        try:
            func(failed_path)
        except Exception:
            pass  # give rmtree a chance to continue; we check existence at the end

    import sys
    if sys.version_info >= (3, 12):
        # Python 3.12+ uses onexc instead of onerror
        shutil.rmtree(path, onexc=_on_error)
    else:
        shutil.rmtree(path, onerror=_on_error)

    if path.exists():
        raise OSError(
            f"Could not fully delete '{path}'.\n"
            "On Windows, file handles may still be open.  Try:\n"
            "  1. Close any IDEs or Explorer windows viewing that folder.\n"
            "  2. Stop Gradle daemons:  cd MODS\\<repo> && gradlew.bat --stop\n"
            "  3. Delete the folder manually, then re-run generate."
        )


def is_valid_git_branch_name(name: str) -> bool:
    """Validate branch names against standard Git ref character and syntax rules."""
    if not name or not isinstance(name, str):
        return False
    if not name.strip():
        return False
    if name.startswith("-"):
        return False
    if name.startswith("/") or name.endswith("/"):
        return False
    if name.endswith("."):
        return False
    if ".." in name:
        return False
    if "@{" in name:
        return False
    if name == "@":
        return False
    # Check invalid characters: space, tilde, caret, colon, question, asterisk, open bracket, backslash, control/delete
    invalid_chars = {' ', '~', '^', ':', '?', '*', '[', '\\'}
    for char in name:
        if char in invalid_chars:
            return False
        if ord(char) <= 31 or ord(char) == 127:
            return False
    # Check components
    parts = name.split("/")
    for part in parts:
        if not part:
            return False
        if part.startswith("."):
            return False
        if part.endswith(".lock"):
            return False
    return True

