"""Abstract base class for all loader-specific file patchers."""

from __future__ import annotations

import abc
import re
from pathlib import Path
from modsmith.context import TargetContext


class BasePatcher(abc.ABC):
    """Base class for loader-specific project file patchers.

    Each concrete subclass handles the patching logic for one mod loader
    (Forge, NeoForge, Fabric).  Patchers receive the root of the copied
    template tree and a :class:`~modsmith.context.TargetContext` and return
    a list of warning strings for any missing-but-expected files.
    """

    @abc.abstractmethod
    def patch(self, repo_root: Path, ctx: TargetContext) -> list[str]:
        """Patch all project files in *repo_root* for the given *ctx*.

        Parameters
        ----------
        repo_root:
            Root directory of the copied template (already at the Git repo root).
        ctx:
            A :class:`~modsmith.context.TargetContext` instance.

        Returns
        -------
        list[str]
            Zero or more warning messages (e.g. "expected file X not found").
            The caller is responsible for displaying them.
        """

    # ------------------------------------------------------------------
    # Shared helpers (available to all subclasses)
    # ------------------------------------------------------------------

    @staticmethod
    def replace_in_file(path: Path, replacements: dict[str, str]) -> bool:
        """Replace all occurrences of each key with its value in *path*.

        Returns ``True`` if the file was modified, ``False`` if it did not
        exist or no replacements were made.
        """
        if not path.exists() or not path.is_file():
            return False
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return False

        original = content
        for k, v in replacements.items():
            content = content.replace(k, v)

        if content != original:
            try:
                path.write_text(content, encoding="utf-8")
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def set_or_replace_gradle_property(path: Path, key: str, value: str) -> bool:
        """If key exists, replace the line in gradle.properties. If missing, append key=value."""
        if not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{key}={value}\n", encoding="utf-8")
                return True
            except Exception:
                return False

        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return False

        lines = content.splitlines()
        found = False
        new_lines = []

        # Regex to match key=value or key = value, ignoring comments starting with #
        pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=')

        for line in lines:
            if not line.strip().startswith('#') and pattern.match(line):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key}={value}")

        new_content = "\n".join(new_lines)
        if new_lines and not new_content.endswith("\n"):
            new_content += "\n"

        try:
            path.write_text(new_content, encoding="utf-8")
            return True
        except Exception:
            return False

    @staticmethod
    def patch_build_gradle_archive_name(path: Path, archive_name: str) -> bool:
        """Insert or replace a base block in build.gradle with archivesName = archive_name."""
        if not path.exists() or not path.is_file():
            return False
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return False

        # First, replace any archivesBaseName assignments (e.g. Fabric templates)
        content = re.sub(
            r'^[ \t]*archivesBaseName\s*=\s*[\'"][^\'"]*[\'"]',
            f'archivesBaseName = "{archive_name}"',
            content,
            flags=re.MULTILINE
        )
        content = re.sub(
            r'^[ \t]*archivesBaseName\s*=\s*\S+',
            f'archivesBaseName = "{archive_name}"',
            content,
            flags=re.MULTILINE
        )

        # Check if base { ... } block exists
        base_blocks = list(re.finditer(r'base\s*\{([^}]*)\}', content, re.DOTALL))
        if base_blocks:
            new_content = content
            offset = 0
            for match in base_blocks:
                block_inner = match.group(1)
                start, end = match.span(1)

                # Check if archivesName exists inside
                archives_match = re.search(r'archivesName\s*=\s*.*$', block_inner, re.MULTILINE)
                if archives_match:
                    patched_inner = block_inner[:archives_match.start()] + f'archivesName = "{archive_name}"' + block_inner[archives_match.end():]
                else:
                    patched_inner = f'\n    archivesName = "{archive_name}"' + block_inner

                new_content = new_content[:start + offset] + patched_inner + new_content[end + offset:]
                offset += len(patched_inner) - len(block_inner)
            content = new_content
        else:
            if not content.endswith("\n") and content:
                content += "\n"
            content += f'\nbase {{\n    archivesName = "{archive_name}"\n}}\n'

        try:
            path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False
