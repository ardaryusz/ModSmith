"""Runtime context dataclasses that carry resolved paths and state through generation.

``ModContext`` wraps a parsed ``ModConfig`` together with the three root directories
resolved from CLI flags.  ``TargetContext`` adds per-target state (template dir,
descriptor, archive naming) so downstream code never needs to re-derive them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from modsmith.config import ModConfig, TargetConfig, TemplateDescriptor


# ---------------------------------------------------------------------------
# ModContext
# ---------------------------------------------------------------------------


@dataclass
class ModContext:
    """Flattened runtime view of :class:`ModConfig` plus resolved filesystem paths.

    Constructed once by the CLI and passed to every generator / patcher function.
    The three directory paths are resolved from CLI flags before being stored.
    """

    config: ModConfig

    workspace_dir: Path = field(default_factory=lambda: Path("WORKSPACE").resolve())
    templates_dir: Path = field(default_factory=lambda: Path("MODTEMPLATES").resolve())
    mods_dir: Path = field(default_factory=lambda: Path("MODS").resolve())

    # ------------------------------------------------------------------
    # Convenience paths derived from workspace_dir
    # ------------------------------------------------------------------

    @property
    def recipes_dir(self) -> Path:
        """``WORKSPACE/RECIPES/``"""
        return self.workspace_dir / "RECIPES"

    @property
    def readme_dir(self) -> Path:
        """``WORKSPACE/README/``"""
        return self.workspace_dir / "README"

    @property
    def details_dir(self) -> Path:
        """``WORKSPACE/DETAILS/``"""
        return self.workspace_dir / "DETAILS"

    @property
    def assets_dir(self) -> Path:
        """``WORKSPACE/ASSETS/``"""
        return self.workspace_dir / "ASSETS"

    @property
    def output_repo_dir(self) -> Path:
        """``MODS/<output_repo_name>/``"""
        return self.mods_dir / self.config.output_repo_name

    # ------------------------------------------------------------------
    # Delegate frequently-used config fields for ergonomic access
    # ------------------------------------------------------------------

    @property
    def mod_id(self) -> str:
        return self.config.mod_id

    @property
    def mod_name(self) -> str:
        return self.config.mod_name

    @property
    def mod_version(self) -> str:
        return self.config.mod_version

    @property
    def main_class(self) -> str:
        return self.config.main_class

    @property
    def package(self) -> str:
        return self.config.package

    @property
    def group(self) -> str:
        return self.config.group

    @property
    def authors(self) -> str:
        return self.config.authors

    @property
    def license(self) -> str:
        return self.config.license

    @property
    def description(self) -> str:
        return self.config.description

    @property
    def homepage(self) -> str:
        return self.config.homepage

    @property
    def issue_tracker(self) -> str:
        return self.config.issue_tracker

    @property
    def icon(self) -> str:
        return self.config.icon


# ---------------------------------------------------------------------------
# TargetContext
# ---------------------------------------------------------------------------


@dataclass
class TargetContext:
    """Per-target runtime state combining a :class:`TargetConfig` with resolved paths.

    Provides derived properties so patchers and generators never compute the same
    values independently.
    """

    mod_ctx: ModContext
    target: TargetConfig
    descriptor: TemplateDescriptor | None
    """``None`` when the template folder has no ``modsmith-template.json``."""

    @property
    def mod(self) -> ModContext:
        """Alias for mod_ctx for convenience and backward compatibility."""
        return self.mod_ctx

    # ------------------------------------------------------------------
    # Filesystem paths
    # ------------------------------------------------------------------

    @property
    def template_dir(self) -> Path:
        """Absolute path to the selected template folder."""
        return self.mod_ctx.templates_dir / self.target.template

    # ------------------------------------------------------------------
    # Delegate target fields
    # ------------------------------------------------------------------

    @property
    def loader(self) -> str:
        return self.target.loader

    @property
    def branch(self) -> str:
        return self.target.branch

    @property
    def mc_range(self) -> str:
        return self.target.mc_range

    @property
    def minecraft_version(self) -> str:
        return self.target.minecraft_version

    @property
    def minecraft_version_range(self) -> str:
        return self.target.minecraft_version_range

    # ------------------------------------------------------------------
    # Derived build / archive properties
    # ------------------------------------------------------------------

    @property
    def mc_version_label(self) -> str:
        """Human-readable Minecraft version label for use in JAR filenames.

        Rules:
        - For a single-version target (exact patch or same minor range), use
          ``minecraft_version`` verbatim (e.g. ``"1.20.1"``).
        - For an inclusive custom range ``[from,through]``, use ``"from-through"``
          (e.g. ``"1.21.2-1.21.11"``).
        - Never use ``mc_range`` (which drops the patch number) and never emit
          raw Maven interval syntax like ``[1.20.1,1.20.2)``.
        """
        vrange = (self.target.minecraft_version_range or "").strip()
        mc_ver = (self.target.minecraft_version or "").strip()

        if vrange:
            # Detect inclusive custom range: must start with '[' and end with ']'
            if vrange.startswith("[") and vrange.endswith("]"):
                inner = vrange[1:-1]  # strip surrounding brackets
                parts = inner.split(",", 1)
                if len(parts) == 2:
                    from_ver = parts[0].strip()
                    through_ver = parts[1].strip()
                    if from_ver and through_ver and from_ver != through_ver:
                        return f"{from_ver}-{through_ver}"

        # Default: use the exact minecraft_version (e.g. "1.20.1")
        return mc_ver if mc_ver else self.target.mc_range

    @property
    def archive_base_name(self) -> str:
        """Gradle ``archivesName`` value: ``<mod_id>-<mc_version_label>-<loader>``."""
        suffix = self.descriptor.jar_loader_suffix if self.descriptor and self.descriptor.jar_loader_suffix else self.target.loader
        return f"{self.mod_ctx.mod_id}-{self.mc_version_label}-{suffix}"

    @property
    def expected_jar_name(self) -> str:
        """Full expected JAR file name: ``<archive_base_name>-<mod_version>.jar``."""
        return f"{self.archive_base_name}-{self.mod_ctx.mod_version}.jar"

    @property
    def recipe_folder(self) -> str:
        """Recipe subfolder name (``"recipe"`` or ``"recipes"``).

        Reads from the template descriptor if available, otherwise falls back to
        a version-based heuristic: ``"recipes"`` for < 1.21, ``"recipe"`` for >= 1.21.
        """
        if self.descriptor:
            return self.descriptor.recipe_folder
        # Heuristic fallback based on the version component.
        try:
            parts = self.target.minecraft_version.split(".")
            major = int(parts[0]) if len(parts) >= 1 else 1
            minor = int(parts[1]) if len(parts) >= 2 else 0
            if major > 1 or (major == 1 and minor >= 21):
                return "recipe"
            return "recipes"
        except (ValueError, IndexError):
            return "recipe"

    @property
    def recipe_dest_dir(self) -> Path:
        """Absolute path to ``src/main/resources/data/<mod_id>/<recipe_folder>/``
        inside the output repo root (used after the template has been copied)."""
        return (
            self.mod_ctx.output_repo_dir
            / "src" / "main" / "resources"
            / "data" / self.mod_ctx.mod_id
            / self.recipe_folder
        )
