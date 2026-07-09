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
from modsmith.utils import safe_delete_tree, run_subprocess
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
    git_has_staged_changes,
    git_is_file_tracked,
    git_is_file_locally_modified,
    git_last_commit_message,
    git_rm_file,
    git_rm_all_tracked,
    git_current_branch,
)


@dataclass
class GenerateResult:
    """Carries the outcome of the generation process for user display."""

    repo_dir: Path
    generated_branches: list[str]
    warnings: list[str]
    dry_run: bool = False
    landing_branch: str | None = None
    checked_out_branch: str | None = None



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
        Path("LICENSE"),
        Path("LICENSE.md"),
        Path("LICENSE.txt"),
        Path("LICENSE.html"),
        Path("LICENSE.docx")
    }
    
    # Walk the repo_dir and decide what to delete bottom-up
    for child in sorted(repo_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if ".git" in child.parts:
            continue
            
        rel = child.relative_to(repo_dir)
        
        # Check if it should be deleted
        should_delete = False
        if rel in always_delete_names:
            name_lower = rel.name.lower()
            if name_lower in ("license", "license.md", "license.txt", "license.html", "license.docx"):
                if not template_has_license_file(template_dir, rel.suffix):
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


def _can_safely_delete_stale_file(repo_dir: Path, filename: str, currently_selected_paths: set[str]) -> bool:
    if filename in currently_selected_paths:
        return False
    if not (repo_dir / filename).exists():
        return False
    if not git_is_file_tracked(repo_dir, filename):
        return False
    # Check last commit message
    msg = git_last_commit_message(repo_dir, filename)
    if msg not in ("Initialize landing branch", "Update landing branch"):
        return False
    # Check if modified or staged
    if git_is_file_locally_modified(repo_dir, filename):
        return False
    return True


def _verify_overwrite_safe(repo_dir: Path, filename: str):
    if git_is_file_locally_modified(repo_dir, filename):
        raise GenerateError(
            f"Cannot update landing {filename} because it contains uncommitted local changes. "
            f"Commit, discard, or copy those changes into the workspace sources before regenerating."
        )


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
        landing_branch_name = None
        landing_branch_action = None
        landing_files_to_write = []
        fallback_readme = False
        selected_license = None
        icon_status = "None"
        final_checkout = selected_targets[0].branch if selected_targets else None

        if config.landing_branch.enabled:
            landing_branch_name = config.landing_branch.name
            final_checkout = landing_branch_name
            
            existing_branches = []
            if output_repo_dir.exists():
                try:
                    existing_branches = git_list_branches(output_repo_dir)
                except Exception:
                    pass
            
            if landing_branch_name in existing_branches:
                landing_branch_action = "update"
            else:
                landing_branch_action = "create"

            landing_files_to_write.append("README.md")
            landing_files_to_write.append(".gitignore")

            readme_dir = mod_ctx.readme_dir
            readme_empty = True
            if readme_dir.exists():
                readme_src = readme_dir / "README.md"
                if readme_src.exists():
                    try:
                        content = readme_src.read_text(encoding="utf-8")
                        if content.strip():
                            readme_empty = False
                    except Exception:
                        pass
                if readme_empty:
                    md_files = list(readme_dir.glob("*.md"))
                    if md_files:
                        try:
                            content = md_files[0].read_text(encoding="utf-8")
                            if content.strip():
                                readme_empty = False
                        except Exception:
                            pass
            if readme_empty:
                fallback_readme = True

            license_dir = mod_ctx.license_dir
            license_file = None
            if license_dir.is_dir():
                try:
                    license_file = discover_license_file(license_dir)
                except Exception:
                    pass
            if license_file:
                selected_license = license_file.name
                landing_files_to_write.append(f"LICENSE{license_file.suffix.lower()}")

            if config.icon:
                icon_src = workspace_dir / config.icon.replace("/", os.sep)
                if icon_src.is_file():
                    icon_status = config.icon
                    landing_files_to_write.append("icon.png")
                else:
                    icon_status = f"{config.icon} (missing)"
            else:
                icon_status = "None"

            print(f"[DRY RUN] Landing branch: {landing_branch_name} ({landing_branch_action})")
            print(f"[DRY RUN] Intended files to write: {', '.join(landing_files_to_write)}")
            if fallback_readme:
                print("[DRY RUN] Fallback README: Yes (mod name heading only)")
            else:
                print("[DRY RUN] Fallback README: No (workspace README will be copied)")
            print(f"[DRY RUN] Selected license: {selected_license or 'None'}")
            print(f"[DRY RUN] Icon status: {icon_status}")
            print(f"[DRY RUN] Intended checkout branch: {final_checkout}")
        else:
            print("[DRY RUN] Landing branch generation: Disabled")
            print(f"[DRY RUN] Intended checkout branch: {final_checkout}")

        return GenerateResult(
            repo_dir=output_repo_dir,
            generated_branches=[tc.branch for tc in selected_targets],
            warnings=warnings,
            dry_run=True,
            landing_branch=landing_branch_name,
            checked_out_branch=final_checkout,
        )


    # 6. Real run
    # Simple overwrite check
    if output_repo_dir.exists() and not force:
        raise ValueError(f"Output repo already exists: {output_repo_dir}")

    # Discover and log workspace license once
    license_dir = mod_ctx.license_dir
    license_file = None
    if license_dir.is_dir():
        from modsmith.context import get_license_candidates
        candidates = get_license_candidates(license_dir)
        if len(candidates) > 1:
            names = [c.name for c in candidates]
            selected = candidates[0]
            print(f"Multiple license files found (candidates: {', '.join(names)}); using {selected.name}")
        
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

    # Preflight Checks if landing branch is enabled
    if config.landing_branch.enabled:
        # Preflight Check 1: Index staged check
        if git_has_staged_changes(output_repo_dir):
            raise GenerateError(
                "Staged changes already exist in the generated repository. "
                "Commit or unstage them before generating the landing branch."
            )

        # Preflight Check 2: Untracked managed-path collision check
        existing_branches = git_list_branches(output_repo_dir)
        landing_exists = config.landing_branch.name in existing_branches
        if not landing_exists:
            managed_paths = [
                "README.md",
                "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.html", "LICENSE.docx",
                "icon.png",
                ".gitignore"
            ]
            for name in managed_paths:
                p = output_repo_dir / name
                if p.exists() and not git_is_file_tracked(output_repo_dir, name):
                    raise GenerateError(
                        f"Cannot create landing branch because untracked file '{name}' "
                        f"already exists in the generated repository. "
                        f"Move, remove, or commit the file before generating the landing branch."
                    )

        # Preflight Check 3: Active modifications check (if landing branch is currently checked out)
        try:
            current_branch = git_current_branch(output_repo_dir)
        except Exception:
            current_branch = ""
        if current_branch == config.landing_branch.name:
            managed_paths = [
                "README.md",
                "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.html", "LICENSE.docx",
                "icon.png",
                ".gitignore"
            ]
            for name in managed_paths:
                p = output_repo_dir / name
                if p.exists() and git_is_file_locally_modified(output_repo_dir, name):
                    raise GenerateError(
                        f"Cannot update landing {name} because it contains uncommitted local changes. "
                        f"Commit, discard, or copy those changes into the workspace sources before regenerating."
                    )

    # Back up any unrelated untracked user files present in the repo before generation starts
    untracked_files_backup = {}
    if output_repo_dir.exists():
        try:
            from modsmith.utils import run_process
            res = run_process(["git", "ls-files", "--others", "--exclude-standard"], cwd=output_repo_dir, capture_output=True)
            for line in res.stdout.splitlines():
                line = line.strip()
                if line:
                    p = output_repo_dir / line
                    if p.is_file():
                        untracked_files_backup[line] = p.read_bytes()
        except Exception:
            pass

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

        # Copy workspace LICENSE if found and clean up stale alternate files
        managed_names = ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.html", "LICENSE.docx"]

        if license_file is not None:
            dest_name = f"LICENSE{license_file.suffix.lower()}"
            dest_path = output_repo_dir / dest_name

            try:
                shutil.copy2(license_file, dest_path)
                print(f"Copied license to generated branch: {dest_name}")
            except Exception as exc:
                raise ValueError(f"Failed to copy license file '{license_file}' to '{dest_path}': {exc}")

            # Clean up other stale alternate license formats if not provided by the template
            for m_name in managed_names:
                if m_name.lower() != dest_name.lower():
                    stale_file = output_repo_dir / m_name
                    ext = Path(m_name).suffix
                    if stale_file.exists() and not template_has_license_file(tc.template_dir, ext):
                        try:
                            stale_file.unlink()
                        except Exception:
                            pass
        else:
            # If no workspace license is selected, clean up any stale alternate formats not provided by the template
            for m_name in managed_names:
                stale_file = output_repo_dir / m_name
                ext = Path(m_name).suffix
                if stale_file.exists() and not template_has_license_file(tc.template_dir, ext):
                    try:
                        stale_file.unlink()
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
            if git_has_staged_changes(output_repo_dir):
                commit_msg = f"Generate {tc.loader} {tc.mc_range} version"
                git_commit(output_repo_dir, commit_msg)
        except Exception as exc:
            raise ValueError(f"Failed to commit changes to '{tc.branch}': {exc}")

    # Checkout the first branch generated at the end
    final_checked_out = None
    if selected_targets:
        try:
            git_checkout(output_repo_dir, selected_targets[0].branch)
            final_checked_out = selected_targets[0].branch
        except Exception as exc:
            warnings.append(f"Failed to checkout initial branch '{selected_targets[0].branch}' at the end: {exc}")

    # Generate and checkout landing branch if enabled
    landing_branch_name = None
    if config.landing_branch.enabled:
        landing_branch_name = config.landing_branch.name
        
        existing_branches = git_list_branches(output_repo_dir)
        landing_exists = landing_branch_name in existing_branches

        # Record originally checked-out branch for failure recovery
        original_branch = None
        try:
            original_branch = git_current_branch(output_repo_dir)
        except Exception:
            pass

        files_written_this_attempt = []
        try:
            # Switch to landing branch
            if landing_exists:
                git_checkout(output_repo_dir, landing_branch_name)
            else:
                git_create_orphan_branch(output_repo_dir, landing_branch_name)
                git_rm_all_tracked(output_repo_dir)

            # Restore backup of untracked files
            for rel_path, content in untracked_files_backup.items():
                dest_p = output_repo_dir / rel_path
                try:
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    dest_p.write_bytes(content)
                except Exception:
                    pass

            # Determine currently selected output paths
            currently_selected_paths = {
                "README.md",
                ".gitignore"
            }
            if license_file:
                currently_selected_paths.add(f"LICENSE{license_file.suffix.lower()}")
            if config.icon:
                currently_selected_paths.add("icon.png")

            # conflict verification checks before writing/deleting
            # --- Write README.md ---
            readme_dest = output_repo_dir / "README.md"
            _verify_overwrite_safe(output_repo_dir, "README.md")
            
            readme_written = False
            readme_dir = mod_ctx.readme_dir
            if readme_dir.exists():
                readme_src = readme_dir / "README.md"
                if readme_src.exists():
                    try:
                        content = readme_src.read_text(encoding="utf-8")
                        if content.strip():
                            shutil.copy2(readme_src, readme_dest)
                            files_written_this_attempt.append(readme_dest)
                            readme_written = True
                    except Exception as exc:
                        raise GenerateError(f"Workspace README file is unreadable: {exc}")
                
                if not readme_written:
                    md_files = list(readme_dir.glob("*.md"))
                    if md_files:
                        try:
                            content = md_files[0].read_text(encoding="utf-8")
                            if content.strip():
                                shutil.copy2(md_files[0], readme_dest)
                                files_written_this_attempt.append(readme_dest)
                                readme_written = True
                        except Exception as exc:
                            raise GenerateError(f"Workspace README file {md_files[0].name} is unreadable: {exc}")
            
            if not readme_written:
                # Fallback README.md
                content = f"# {config.mod_name}\n"
                readme_dest.write_text(content, encoding="utf-8")
                files_written_this_attempt.append(readme_dest)

            # Ensure README ends with newline
            try:
                content = readme_dest.read_text(encoding="utf-8")
                if not content.endswith("\n"):
                    readme_dest.write_text(content + "\n", encoding="utf-8")
            except Exception:
                pass

            # --- Write LICENSE ---
            if license_file is not None:
                license_dest_name = f"LICENSE{license_file.suffix.lower()}"
                _verify_overwrite_safe(output_repo_dir, license_dest_name)
                dest_path = output_repo_dir / license_dest_name
                try:
                    shutil.copy2(license_file, dest_path)
                    files_written_this_attempt.append(dest_path)
                except Exception as exc:
                    raise GenerateError(f"Workspace LICENSE file {license_file.name} is unreadable: {exc}")

            # --- Write Mod Icon ---
            if config.icon:
                _verify_overwrite_safe(output_repo_dir, "icon.png")
                icon_src = workspace_dir / config.icon.replace("/", os.sep)
                if icon_src.is_file():
                    try:
                        shutil.copy2(icon_src, output_repo_dir / "icon.png")
                        files_written_this_attempt.append(output_repo_dir / "icon.png")
                    except Exception as exc:
                        raise GenerateError(f"Configured mod icon '{config.icon}' is unreadable: {exc}")

            # --- Write .gitignore ---
            _verify_overwrite_safe(output_repo_dir, ".gitignore")
            gitignore_content = (
                "# IDE\n"
                ".idea/\n"
                ".vscode/\n"
                "*.iml\n\n"
                "# OS\n"
                ".DS_Store\n"
                "Thumbs.db\n\n"
                "# ModSmith\n"
                "*.log\n"
            )
            gitignore_dest = output_repo_dir / ".gitignore"
            gitignore_dest.write_text(gitignore_content, encoding="utf-8")
            files_written_this_attempt.append(gitignore_dest)

            # --- Stale files deletion ---
            all_managed_paths = [
                "README.md",
                "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.html", "LICENSE.docx",
                "icon.png",
                ".gitignore"
            ]
            for filename in all_managed_paths:
                if filename not in currently_selected_paths:
                    p = output_repo_dir / filename
                    if p.exists():
                        if _can_safely_delete_stale_file(output_repo_dir, filename, currently_selected_paths):
                            git_rm_file(output_repo_dir, filename)
                        else:
                            warnings.append(
                                f"Preserving landing {filename}: ownership or local state is ambiguous."
                            )

            # Stage only explicitly written files
            for p_written in files_written_this_attempt:
                rel_p = str(p_written.relative_to(output_repo_dir))
                run_subprocess(["git", "add", rel_p], cwd=output_repo_dir)

            # Commit staged changes if there are any
            if git_has_staged_changes(output_repo_dir):
                msg = "Initialize landing branch" if not landing_exists else "Update landing branch"
                git_commit(output_repo_dir, msg)

            final_checked_out = landing_branch_name

        except Exception as exc:
            # 1. Unlink files written this attempt
            for p_written in files_written_this_attempt:
                try:
                    if p_written.exists():
                        p_written.unlink()
                except Exception:
                    pass
            # 2. Reset staged changes on landing branch
            try:
                for p_written in files_written_this_attempt:
                    rel_p = str(p_written.relative_to(output_repo_dir))
                    run_subprocess(["git", "reset", "HEAD", "--", rel_p], cwd=output_repo_dir)
            except Exception:
                pass
            # 3. Switch back to original branch
            if original_branch:
                try:
                    git_checkout(output_repo_dir, original_branch)
                except Exception:
                    pass
            # 4. Delete the incomplete orphan branch reference if one exists
            if not landing_exists:
                try:
                    run_subprocess(["git", "branch", "-D", landing_branch_name], cwd=output_repo_dir)
                except Exception:
                    pass

            raise exc

    return GenerateResult(
        repo_dir=output_repo_dir,
        generated_branches=[tc.branch for tc in selected_targets],
        warnings=warnings,
        dry_run=False,
        landing_branch=landing_branch_name,
        checked_out_branch=final_checked_out,
    )
