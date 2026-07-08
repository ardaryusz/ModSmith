"""Generation orchestrator: drives the full generate flow for all targets.

Phase 5:
- Orphan Git branch creation
- Clearing working trees
- Template copying
- Patcher orchestration
- Recipe conversion and writing
- Entrypoint writing
- Git commits
"""

from __future__ import annotations

import os
import shutil
from modsmith.utils import safe_delete_tree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modsmith.config import load_mod_config, load_template_descriptor
from modsmith.context import ModContext, TargetContext, discover_license_file
from modsmith.validator import validate_workspace
from modsmith.templates import copy_template, write_java_entrypoint
from modsmith.recipes import load_recipes, write_recipes, RecipeFormat, resolve_recipe_format
from modsmith.patchers import get_patcher
from modsmith.verifier import verify_generated_project
from modsmith.git_ops import (
    git_init,
    git_create_orphan_branch,
    git_clear_working_tree,
    git_add_all,
    git_commit,
    git_checkout,
    git_list_branches,
    write_gitignore,
)


@dataclass
class GenerateResult:
    """Carries the outcome of the generation process for user display."""

    repo_dir: Path
    generated_branches: list[str]
    warnings: list[str]
    dry_run: bool = False


class GenerateError(Exception):
    """Raised when generation fails due to verifier errors on a target branch."""


def is_legacy_recipe_version(version: str) -> bool:
    """Check if Minecraft version is 1.20.4 or lower (legacy recipe format)."""
    try:
        parts = version.split('.')
        if len(parts) >= 2:
            minor = int(parts[1])
            if minor < 20:
                return True
            if minor == 20:
                patch = int(parts[2]) if len(parts) >= 3 else 0
                return patch <= 4
    except (ValueError, IndexError):
        pass
    return False


def _write_default_readme(path: Path, ctx: ModContext) -> None:
    """Generate a standard README.md file in the output repository."""
    content = f"""# {ctx.mod_name}

{ctx.description}

Generated automatically by ModSmith.

## Details
- Mod ID: `{ctx.mod_id}`
- Version: `{ctx.mod_version}`
- Authors: {ctx.authors}
- License: {ctx.license}
"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception:
        pass


def template_has_license_file(template_dir: Path, ext: str) -> bool:
    """Check if template_dir contains a file named LICENSE (case-insensitive) with ext (case-insensitive)."""
    if not template_dir.is_dir():
        return False
    ext_lower = ext.lower()
    for entry in template_dir.iterdir():
        if entry.is_file() and entry.stem.lower() == "license" and entry.suffix.lower() == ext_lower:
            return True
    return False


def clear_working_tree_selectively(repo_dir: Path, template_dir: Path) -> None:
    """Selectively delete files in repo_dir that are template-provided or ModSmith-generated,
    preserving unrelated user-added files and folders.
    """
    if not repo_dir.exists():
        return

    # Helper to get all relative paths in a directory recursively
    def get_relative_paths(base_dir: Path) -> set[Path]:
        paths = set()
        if base_dir.is_dir():
            for p in base_dir.rglob("*"):
                paths.add(p.relative_to(base_dir))
        return paths

    template_paths = get_relative_paths(template_dir)
    
    always_delete_names = {
        Path(".gitignore"),
        Path("README.md"),
        Path("LICENSE.md"),
        Path("LICENSE.txt")
    }
    
    # Walk the repo_dir and decide what to delete bottom-up
    for child in sorted(repo_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if ".git" in child.parts:
            continue
            
        rel = child.relative_to(repo_dir)
        
        # Check if it should be deleted
        should_delete = False
        if rel in always_delete_names:
            # For LICENSE.md and LICENSE.txt, only delete if NOT present in template
            if rel.name.lower() == "license.md":
                if not template_has_license_file(template_dir, ".md"):
                    should_delete = True
            elif rel.name.lower() == "license.txt":
                if not template_has_license_file(template_dir, ".txt"):
                    should_delete = True
            else:
                should_delete = True
        elif rel in template_paths:
            should_delete = True
        elif any(parent in always_delete_names or parent in template_paths for parent in rel.parents):
            should_delete = True
            
        if should_delete:
            if child.is_file() or child.is_symlink():
                try:
                    child.unlink()
                except Exception:
                    pass
            elif child.is_dir():
                try:
                    child.rmdir()
                except Exception:
                    pass


def generate(
    workspace_dir: Path,
    templates_dir: Path,
    mods_dir: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    target_branch: str | None = None,
) -> GenerateResult:
    """Generate a local Git repository with one orphan branch per target mod project.

    Steps:
    1. Load WORKSPACE/DETAILS/modsmith.json
    2. Call validate_workspace and fail if errors exist
    3. Construct ModContext and TargetContext objects internally
    4. Filter target branches
    5. Handle repository directories (and deletion if --force)
    6. For each target branch: copy templates, patch, write entrypoints, convert recipes, commit
    """
    workspace_dir = Path(workspace_dir).resolve()
    templates_dir = Path(templates_dir).resolve()
    mods_dir = Path(mods_dir).resolve()

    # 1. Load config
    config_path = workspace_dir / "DETAILS" / "modsmith.json"
    if not config_path.exists():
        raise ValueError(f"modsmith.json not found at: {config_path}")

    try:
        config = load_mod_config(config_path)
    except Exception as exc:
        raise ValueError(f"Failed to load modsmith.json: {exc}")

    # 2. Validate workspace
    validation_res = validate_workspace(
        workspace_dir=workspace_dir,
        templates_dir=templates_dir,
        mods_dir=mods_dir,
        force=force,
    )

    if not validation_res.ok:
        err_msg = "Validation failed:\n" + "\n".join(f" - {e}" for e in validation_res.errors)
        raise ValueError(err_msg)

    # 3. Build ModContext and TargetContext objects
    mod_ctx = ModContext(
        config=config,
        workspace_dir=workspace_dir,
        templates_dir=templates_dir,
        mods_dir=mods_dir,
    )

    targets: list[TargetContext] = []
    for t in config.targets:
        desc = load_template_descriptor(templates_dir / t.template)
        targets.append(TargetContext(mod_ctx=mod_ctx, target=t, descriptor=desc))

    # 4. Select targets
    if target_branch is not None:
        selected_targets = [tc for tc in targets if tc.branch == target_branch]
        if not selected_targets:
            raise ValueError(f"No target matches branch '{target_branch}'")
    else:
        selected_targets = targets

    output_repo_dir = mod_ctx.output_repo_dir
    warnings = list(validation_res.warnings)

    # 5. Handle dry_run (completely side-effect free)
    if dry_run:
        return GenerateResult(
            repo_dir=output_repo_dir,
            generated_branches=[tc.branch for tc in selected_targets],
            warnings=warnings,
            dry_run=True,
        )

    # 6. Real run
    # Simple overwrite check
    if output_repo_dir.exists() and not force:
        raise ValueError(f"Output repo already exists: {output_repo_dir}")

    # Discover and log workspace license once
    license_dir = mod_ctx.license_dir
    license_file = None
    if license_dir.is_dir():
        md_matches = []
        txt_matches = []
        try:
            for entry in license_dir.iterdir():
                if entry.is_file():
                    stem_lower = entry.stem.lower()
                    ext_lower = entry.suffix.lower()
                    if stem_lower == "license":
                        if ext_lower == ".md":
                            md_matches.append(entry)
                        elif ext_lower == ".txt":
                            txt_matches.append(entry)
        except OSError:
            pass

        md_matches.sort(key=lambda p: p.name)
        txt_matches.sort(key=lambda p: p.name)
        total_matches = len(md_matches) + len(txt_matches)
        if total_matches > 1:
            selected_name = md_matches[0].name if md_matches else txt_matches[0].name
            print(f"Multiple license files found; using {selected_name}")
        
        license_file = discover_license_file(license_dir)
        if license_file is not None:
            norm_path = os.path.normpath(str(license_file))
            print(f"License selected: {norm_path}")

    if license_file is None:
        print("No workspace license file found; generated branches will not include one")


    output_repo_dir.mkdir(parents=True, exist_ok=True)

    # Init Git
    try:
        git_init(output_repo_dir)
    except Exception as exc:
        raise ValueError(f"Failed to initialize Git repository: {exc}")

    # Load recipes
    try:
        recipes = load_recipes(mod_ctx.recipes_dir)
    except Exception as exc:
        raise ValueError(f"Failed to load recipes: {exc}")

    # Generate each selected branch
    for i, tc in enumerate(selected_targets):
        # Create / Checkout orphan branch
        try:
            existing_branches = git_list_branches(output_repo_dir)
            if tc.branch in existing_branches:
                git_checkout(output_repo_dir, tc.branch)
            else:
                git_create_orphan_branch(output_repo_dir, tc.branch)
        except Exception as exc:
            raise ValueError(f"Failed to checkout or create branch '{tc.branch}': {exc}")

        # Clear working tree selectively, preserving unrelated user-added content
        clear_working_tree_selectively(output_repo_dir, tc.template_dir)

        # Write standard .gitignore
        try:
            write_gitignore(output_repo_dir)
        except Exception as exc:
            warnings.append(f"Failed to write .gitignore for '{tc.branch}': {exc}")

        # Copy template
        try:
            copy_template(tc.template_dir, output_repo_dir)
        except Exception as exc:
            raise ValueError(f"Failed to copy template for '{tc.branch}': {exc}")

        # Delete modsmith-template.json if copied
        desc_file = output_repo_dir / "modsmith-template.json"
        if desc_file.exists():
            try:
                desc_file.unlink()
            except Exception:
                pass

        # Write README.md
        readme_dest = output_repo_dir / "README.md"
        readme_dir = mod_ctx.readme_dir
        if readme_dir.exists():
            readme_src = readme_dir / "README.md"
            if readme_src.exists():
                try:
                    shutil.copy2(readme_src, readme_dest)
                except Exception:
                    _write_default_readme(readme_dest, mod_ctx)
            else:
                md_files = list(readme_dir.glob("*.md"))
                if md_files:
                    try:
                        shutil.copy2(md_files[0], readme_dest)
                    except Exception:
                        _write_default_readme(readme_dest, mod_ctx)
                else:
                    _write_default_readme(readme_dest, mod_ctx)
        else:
            _write_default_readme(readme_dest, mod_ctx)

        # Copy workspace LICENSE if found
        out_license_md = output_repo_dir / "LICENSE.md"
        out_license_txt = output_repo_dir / "LICENSE.txt"

        if license_file is not None:
            dest_name = f"LICENSE{license_file.suffix.lower()}"
            dest_path = output_repo_dir / dest_name

            # Clean up the stale alternate license format if not provided by the template
            if license_file.suffix.lower() == ".md":
                if out_license_txt.exists() and not template_has_license_file(tc.template_dir, ".txt"):
                    try:
                        out_license_txt.unlink()
                    except Exception:
                        pass
            elif license_file.suffix.lower() == ".txt":
                if out_license_md.exists() and not template_has_license_file(tc.template_dir, ".md"):
                    try:
                        out_license_md.unlink()
                    except Exception:
                        pass

            try:
                shutil.copy2(license_file, dest_path)
                print(f"Copied license to generated branch: {dest_name}")
            except Exception as exc:
                raise ValueError(f"Failed to copy license file '{license_file}' to '{dest_path}': {exc}")
        else:
            # If no license is selected in workspace, clean up any stale license files not provided by the template
            if out_license_md.exists() and not template_has_license_file(tc.template_dir, ".md"):
                try:
                    out_license_md.unlink()
                except Exception:
                    pass
            if out_license_txt.exists() and not template_has_license_file(tc.template_dir, ".txt"):
                try:
                    out_license_txt.unlink()
                except Exception:
                    pass

        # Copy mod icon to loader-specific resource location (PNG only)
        if mod_ctx.config.icon:
            icon_src = mod_ctx.workspace_dir / mod_ctx.config.icon.replace("/", os.sep)
            if icon_src.is_file():
                if icon_src.suffix.lower() == ".png":
                    try:
                        if tc.loader == "fabric":
                            # Fabric: src/main/resources/assets/<mod_id>/icon.png
                            icon_dest_dir = (
                                output_repo_dir / "src" / "main" / "resources"
                                / "assets" / mod_ctx.mod_id
                            )
                            icon_dest_dir.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(icon_src, icon_dest_dir / "icon.png")
                        else:
                            # Forge / NeoForge: src/main/resources/icon.png
                            icon_dest_dir = output_repo_dir / "src" / "main" / "resources"
                            icon_dest_dir.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(icon_src, icon_dest_dir / "icon.png")
                    except Exception as exc:
                        warnings.append(
                            f"Failed to copy mod icon for '{tc.branch}': {exc}"
                        )
                else:
                    warnings.append(
                        f"Mod icon '{mod_ctx.config.icon}' is not PNG — "
                        f"skipping icon injection for '{tc.branch}'"
                    )
            else:
                warnings.append(
                    f"Mod icon file not found: {icon_src} — "
                    f"skipping icon injection for '{tc.branch}'"
                )

        # Patch metadata
        try:
            patcher = get_patcher(tc.loader)
            patch_warnings = patcher.patch(output_repo_dir, tc)
            warnings.extend(patch_warnings)
        except Exception as exc:
            warnings.append(f"Failed to patch metadata for '{tc.branch}': {exc}")

        # Write Java entrypoint
        try:
            entry_warnings = write_java_entrypoint(output_repo_dir, tc)
            warnings.extend(entry_warnings)
        except Exception as exc:
            warnings.append(f"Failed to write Java entrypoint for '{tc.branch}': {exc}")

        # Convert and write recipes
        raw_fmt = tc.descriptor.recipe_format if tc.descriptor else None
        target_format = resolve_recipe_format(raw_fmt, tc.minecraft_version)

        recipe_folder = tc.recipe_folder
        dest_data_dir = output_repo_dir / "src" / "main" / "resources" / "data"

        try:
            write_recipes(
                recipes=recipes,
                output_data_dir=dest_data_dir,
                mod_id=mod_ctx.mod_id,
                recipe_folder=recipe_folder,
                target_format=target_format,
            )
        except Exception as exc:
            raise ValueError(f"Failed to write converted recipes for '{tc.branch}': {exc}")

        # Verify the fully-assembled project before committing
        vr = verify_generated_project(output_repo_dir, tc)
        warnings.extend(vr.warnings)
        if not vr.ok:
            err_detail = "\n".join(f"  - {e}" for e in vr.errors)
            raise GenerateError(
                f"Post-generation verification failed for branch '{tc.branch}':\n"
                + err_detail
            )

        # Stage and commit
        try:
            git_add_all(output_repo_dir)
            commit_msg = f"Generate {tc.loader} {tc.mc_range} version"
            git_commit(output_repo_dir, commit_msg)
        except Exception as exc:
            raise ValueError(f"Failed to commit changes to '{tc.branch}': {exc}")

    # Checkout the first branch generated at the end
    if selected_targets:
        try:
            git_checkout(output_repo_dir, selected_targets[0].branch)
        except Exception as exc:
            warnings.append(f"Failed to checkout initial branch '{selected_targets[0].branch}' at the end: {exc}")

    return GenerateResult(
        repo_dir=output_repo_dir,
        generated_branches=[tc.branch for tc in selected_targets],
        warnings=warnings,
        dry_run=False,
    )
