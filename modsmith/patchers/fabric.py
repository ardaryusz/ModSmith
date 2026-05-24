"""Fabric-specific file patcher."""

from __future__ import annotations

import json
import re
from pathlib import Path
from modsmith.context import TargetContext
from modsmith.patchers.base import BasePatcher


class FabricPatcher(BasePatcher):
    """Patches Fabric project files with mod-specific metadata."""

    def patch(self, repo_root: Path, ctx: TargetContext) -> list[str]:
        repo_root = Path(repo_root)
        warnings = []

        # 1. Patch gradle.properties
        gradle_props = repo_root / "gradle.properties"
        content = ""
        if gradle_props.exists():
            try:
                content = gradle_props.read_text(encoding="utf-8")
            except Exception:
                pass

        props_to_set = {
            "mc_range": ctx.target.mc_range,
            "mod_version": ctx.mod_ctx.mod_version,
            "maven_group": ctx.mod_ctx.group,
        }
        
        if ctx.target.minecraft_version:
            props_to_set["minecraft_version"] = ctx.target.minecraft_version

        # Helper to check if a property key is present in gradle.properties
        def has_prop(key: str) -> bool:
            pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=', re.MULTILINE)
            return bool(pattern.search(content))

        if not content or has_prop("archives_base_name"):
            props_to_set["archives_base_name"] = f"{ctx.mod_ctx.mod_id}-{ctx.target.mc_range}-fabric"
        if not content or has_prop("mod_id"):
            props_to_set["mod_id"] = ctx.mod_ctx.mod_id
        if not content or has_prop("mod_name"):
            props_to_set["mod_name"] = ctx.mod_ctx.mod_name

        for k, v in props_to_set.items():
            self.set_or_replace_gradle_property(gradle_props, k, v)

        # 2. Patch build.gradle
        build_gradle = repo_root / "build.gradle"
        if build_gradle.exists():
            archive_name = f"{ctx.mod_ctx.mod_id}-{ctx.target.mc_range}-fabric"
            self.patch_build_gradle_archive_name(build_gradle, archive_name)

        # 3. Patch fabric.mod.json
        fabric_json_path = repo_root / "src" / "main" / "resources" / "fabric.mod.json"
        if fabric_json_path.exists():
            try:
                with open(fabric_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                data["id"] = ctx.mod_ctx.mod_id
                data["version"] = ctx.mod_ctx.mod_version
                data["name"] = ctx.mod_ctx.mod_name
                data["description"] = ctx.mod_ctx.description
                data["license"] = ctx.mod_ctx.license

                # Set authors
                authors_list = [a.strip() for a in ctx.mod_ctx.authors.split(",") if a.strip()]
                if "authors" in data and isinstance(data["authors"], str):
                    data["authors"] = ctx.mod_ctx.authors
                else:
                    data["authors"] = authors_list

                # Set contact fields
                if ctx.mod_ctx.homepage or ctx.mod_ctx.issue_tracker:
                    if "contact" not in data or not isinstance(data["contact"], dict):
                        data["contact"] = {}
                    if ctx.mod_ctx.homepage:
                        data["contact"]["homepage"] = ctx.mod_ctx.homepage
                    if ctx.mod_ctx.issue_tracker:
                        data["contact"]["issues"] = ctx.mod_ctx.issue_tracker

                with open(fabric_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                warnings.append(f"Failed to parse fabric.mod.json: {e}")
        else:
            warnings.append("fabric.mod.json is missing")

        return warnings
