"""Forge-specific file patcher."""

from __future__ import annotations

import re
from pathlib import Path
from modsmith.context import TargetContext
from modsmith.patchers.base import BasePatcher


class ForgePatcher(BasePatcher):
    """Patches Forge project files with mod-specific metadata."""

    def patch(self, repo_root: Path, ctx: TargetContext) -> list[str]:
        repo_root = Path(repo_root)
        warnings = []

        # 1. Patch gradle.properties
        gradle_props = repo_root / "gradle.properties"
        
        # Properties to set/replace
        props_to_set = {
            "mc_range": ctx.target.mc_range,
            "mod_id": ctx.mod_ctx.mod_id,
            "mod_name": ctx.mod_ctx.mod_name,
            "mod_license": ctx.mod_ctx.license,
            "mod_version": ctx.mod_ctx.mod_version,
            "mod_group_id": ctx.mod_ctx.group,
        }
        
        if ctx.target.minecraft_version:
            props_to_set["minecraft_version"] = ctx.target.minecraft_version
        if ctx.target.minecraft_version_range:
            props_to_set["minecraft_version_range"] = ctx.target.minecraft_version_range
        if ctx.mod_ctx.authors:
            props_to_set["mod_authors"] = ctx.mod_ctx.authors
        if ctx.mod_ctx.description:
            props_to_set["mod_description"] = ctx.mod_ctx.description

        for k, v in props_to_set.items():
            self.set_or_replace_gradle_property(gradle_props, k, v)

        # 2. Patch build.gradle
        build_gradle = repo_root / "build.gradle"
        if build_gradle.exists():
            archive_name = f"{ctx.mod_ctx.mod_id}-{ctx.mc_version_label}-forge"
            self.patch_build_gradle_archive_name(build_gradle, archive_name)

            try:
                content = build_gradle.read_text(encoding="utf-8")
                
                # Patch version
                version_pattern = re.compile(r'^[ \t]*version\s*=\s*\S+', re.MULTILINE)
                if version_pattern.search(content):
                    content = re.sub(
                        r'^[ \t]*version\s*=\s*\S+',
                        f'version = "{ctx.mod_ctx.mod_version}"',
                        content,
                        flags=re.MULTILINE
                    )
                else:
                    content = f'version = "{ctx.mod_ctx.mod_version}"\n' + content

                # Patch group
                group_pattern = re.compile(r'^[ \t]*group\s*=\s*\S+', re.MULTILINE)
                if group_pattern.search(content):
                    content = re.sub(
                        r'^[ \t]*group\s*=\s*\S+',
                        f'group = "{ctx.mod_ctx.group}"',
                        content,
                        flags=re.MULTILINE
                    )
                else:
                    content = f'group = "{ctx.mod_ctx.group}"\n' + content

                build_gradle.write_text(content, encoding="utf-8")
            except Exception:
                pass

        # 3. Patch mods.toml
        mods_toml = repo_root / "src" / "main" / "resources" / "META-INF" / "mods.toml"
        if mods_toml.exists():
            replacements = {
                "examplemod": ctx.mod_ctx.mod_id,
                "Example Mod": ctx.mod_ctx.mod_name,
                "com.example.examplemod": ctx.mod_ctx.group,
                "YourNameHere": ctx.mod_ctx.authors,
                "Example mod description...": ctx.mod_ctx.description,
            }
            self.replace_in_file(mods_toml, replacements)

            # Inject/replace logoFile for PNG icons
            if ctx.mod_ctx.config.icon and ctx.mod_ctx.config.icon.lower().endswith(".png"):
                self._inject_logo_file(mods_toml, "icon.png")
        else:
            warnings.append("META-INF/mods.toml is missing")

        return warnings

    @staticmethod
    def _inject_logo_file(toml_path: Path, logo_value: str) -> None:
        """Set or replace ``logoFile`` in a TOML metadata file.

        If ``logoFile`` already exists, replace its value.
        Otherwise, insert ``logoFile="<logo_value>"`` after the first
        ``[[mods]]`` header.
        """
        try:
            content = toml_path.read_text(encoding="utf-8")
        except Exception:
            return

        logo_pattern = re.compile(r'^(\s*logoFile\s*=\s*).*$', re.MULTILINE)
        if logo_pattern.search(content):
            content = logo_pattern.sub(rf'\g<1>"{logo_value}"', content)
        else:
            # Insert after [[mods]] section header
            mods_header = re.search(r'^\[\[mods\]\]\s*$', content, re.MULTILINE)
            if mods_header:
                insert_pos = mods_header.end()
                content = (
                    content[:insert_pos]
                    + f'\nlogoFile="{logo_value}"\n'
                    + content[insert_pos:]
                )

        try:
            toml_path.write_text(content, encoding="utf-8")
        except Exception:
            pass
