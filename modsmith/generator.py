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

import shutil
from modsmith.utils import safe_delete_tree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modsmith.config import load_mod_config, load_template_descriptor
from modsmith.context import ModContext, TargetContext
from modsmith.validator import validate_workspace
from modsmith.templates import copy_template, write_java_entrypoint
from modsmith.recipes import load_recipes, write_recipes, RecipeFormat
from modsmith.patchers import get_patcher
from modsmith.verifier import verify_generated_project
from modsmith.git_ops import (
    git_init,
    git_create_orphan_branch,
    git_clear_working_tree,
    git_add_all,
    git_commit,
    git_checkout,
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
    """Check if Minecraft version is 1.20.x or lower (legacy recipe format)."""
    try:
        parts = version.split('.')
        if len(parts) >= 2:
            minor = int(parts[1])
            return minor <= 20
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
    # Simple overwrite: delete entire output repo and regenerate if exists and --force
    if output_repo_dir.exists():
        if force:
            try:
                safe_delete_tree(output_repo_dir)
            except OSError as exc:
                raise ValueError(f"Failed to delete existing output repo: {exc}")
        else:
            raise ValueError(f"Output repo already exists: {output_repo_dir}")


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
            git_create_orphan_branch(output_repo_dir, tc.branch)
        except Exception as exc:
            raise ValueError(f"Failed to create orphan branch '{tc.branch}': {exc}")

        # Clear working tree
        git_clear_working_tree(output_repo_dir)

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
        if tc.descriptor and tc.descriptor.recipe_format:
            target_format = RecipeFormat(tc.descriptor.recipe_format)
        else:
            if is_legacy_recipe_version(tc.minecraft_version):
                target_format = RecipeFormat.LEGACY_1_20
            else:
                target_format = RecipeFormat.MODERN_1_21

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
