"""Utility helpers: string validation, name derivation, and subprocess wrapping."""

from __future__ import annotations

import re
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


def run_subprocess(
    args: list[str],
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run *args* as a subprocess and return the completed process.

    Raises :class:`subprocess.CalledProcessError` on non-zero exit.
    Raises :class:`FileNotFoundError` if the executable is not on ``PATH``.
    """
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
    )
