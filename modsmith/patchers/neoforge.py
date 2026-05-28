"""NeoForge-specific file patcher."""

from __future__ import annotations

from pathlib import Path
from modsmith.context import TargetContext
from modsmith.patchers.base import BasePatcher
from modsmith.patchers.forge import ForgePatcher


class NeoForgePatcher(BasePatcher):
    """Patches NeoForge project files with mod-specific metadata."""

    def patch(self, repo_root: Path, ctx: TargetContext) -> list[str]:
        repo_root = Path(repo_root)
        warnings = []

        # 1. Patch gradle.properties
        gradle_props = repo_root / "gradle.properties"
        
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
            archive_name = f"{ctx.mod_ctx.mod_id}-{ctx.mc_version_label}-neoforge"
            self.patch_build_gradle_archive_name(build_gradle, archive_name)

        # 3. Patch neoforge.mods.toml
        neoforge_toml_template = repo_root / "src" / "main" / "templates" / "META-INF" / "neoforge.mods.toml"
        neoforge_toml_resource = repo_root / "src" / "main" / "resources" / "META-INF" / "neoforge.mods.toml"
        
        patched_any = False
        replacements = {
            "examplemod": ctx.mod_ctx.mod_id,
            "Example Mod": ctx.mod_ctx.mod_name,
            "com.example.examplemod": ctx.mod_ctx.group,
            "YourNameHere": ctx.mod_ctx.authors,
            "Example mod description...": ctx.mod_ctx.description,
        }

        inject_logo = (
            ctx.mod_ctx.config.icon
            and ctx.mod_ctx.config.icon.lower().endswith(".png")
        )

        if neoforge_toml_template.exists():
            self.replace_in_file(neoforge_toml_template, replacements)
            if inject_logo:
                ForgePatcher._inject_logo_file(neoforge_toml_template, "icon.png")
            patched_any = True
        
        if neoforge_toml_resource.exists():
            self.replace_in_file(neoforge_toml_resource, replacements)
            if inject_logo:
                ForgePatcher._inject_logo_file(neoforge_toml_resource, "icon.png")
            patched_any = True

        if not patched_any:
            warnings.append("META-INF/neoforge.mods.toml is missing")

        return warnings
