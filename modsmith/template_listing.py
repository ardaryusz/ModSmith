"""Template discovery, structure validation, and metadata listing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from modsmith.config import ConfigError, load_template_descriptor


@dataclass
class TemplateStatus:
    """Status details for an individual template directory under MODTEMPLATES."""

    name: str
    """The directory name of the template."""

    path: Path
    """The absolute path to the template directory."""

    has_descriptor: bool
    """True if modsmith-template.json exists in the directory."""

    descriptor_valid: bool
    """True if modsmith-template.json exists and parsed successfully."""

    error_message: str | None = None
    """Parsing error message if the descriptor is invalid."""

    loader: str = ""
    """Mod loader target specified in the descriptor."""

    minecraft_version: str = ""
    """Representative Minecraft version specified in the descriptor."""

    recipe_folder: str = ""
    """Recipe folder name (e.g. 'recipe' or 'recipes') specified in the descriptor."""

    recipe_format: str = ""
    """Recipe JSON format (e.g. 'modern_1_21' or 'legacy_1_20') specified in the descriptor."""

    jar_loader_suffix: str = ""
    """Suffix for built jars specified in the descriptor."""

    has_gradlew: bool = False
    """True if the gradlew shell script exists."""

    has_gradlew_bat: bool = False
    """True if the gradlew.bat batch script exists."""

    has_gradle_wrapper_jar: bool = False
    """True if gradle/wrapper/gradle-wrapper.jar exists."""


@dataclass
class TemplateListResult:
    """The outcome of scanning the templates directory."""

    templates: list[TemplateStatus] = field(default_factory=list)
    """List of all template directory statuses found, sorted alphabetically."""

    errors: list[str] = field(default_factory=list)
    """Aggregated validation errors that should block execution (exit 1)."""

    warnings: list[str] = field(default_factory=list)
    """Aggregated validation warnings (exit 0)."""

    @property
    def ok(self) -> bool:
        """True if the scan encountered no errors, otherwise False."""
        return len(self.errors) == 0


def list_templates(templates_dir: Path) -> TemplateListResult:
    """Scan and validate all template directories under templates_dir.

    Returns a TemplateListResult containing details about each template
    and lists of aggregated errors and warnings.
    """
    templates_dir = Path(templates_dir)

    if not templates_dir.exists():
        return TemplateListResult(
            errors=[f"Templates directory does not exist: {templates_dir}"]
        )

    if not templates_dir.is_dir():
        return TemplateListResult(
            errors=[f"Templates directory is not a directory: {templates_dir}"]
        )

    # Scan direct child folders, sorted alphabetically
    try:
        children = sorted(
            [child for child in templates_dir.iterdir() if child.is_dir()],
            key=lambda c: c.name.lower()
        )
    except OSError as exc:
        return TemplateListResult(
            errors=[f"Failed to scan templates directory: {exc}"]
        )

    if not children:
        return TemplateListResult(
            warnings=[f"Templates directory has no template folders: {templates_dir}"]
        )

    templates: list[TemplateStatus] = []
    errors: list[str] = []
    warnings: list[str] = []

    for child in children:
        name = child.name
        path = child.resolve()

        # Check descriptor
        descriptor_path = child / "modsmith-template.json"
        has_descriptor = descriptor_path.exists()
        descriptor_valid = False
        error_message = None

        loader = ""
        minecraft_version = ""
        recipe_folder = ""
        recipe_format = ""
        jar_loader_suffix = ""

        if has_descriptor:
            try:
                desc = load_template_descriptor(child)
                if desc is not None:
                    descriptor_valid = True
                    loader = desc.loader
                    minecraft_version = desc.minecraft_version
                    recipe_folder = desc.recipe_folder
                    recipe_format = desc.recipe_format
                    jar_loader_suffix = desc.jar_loader_suffix
                else:
                    error_message = "Descriptor file parsed but returned None"
                    errors.append(f"Template '{name}' has a missing or invalid descriptor: {error_message}")
            except ConfigError as exc:
                error_message = str(exc)
                errors.append(f"Template '{name}' has a missing or invalid descriptor: {error_message}")
        else:
            errors.append(f"Template '{name}' is missing modsmith-template.json")

        # Check Gradle files
        has_gradlew = (child / "gradlew").exists()
        has_gradlew_bat = (child / "gradlew.bat").exists()
        has_gradle_wrapper_jar = (child / "gradle" / "wrapper" / "gradle-wrapper.jar").exists()

        if not has_gradle_wrapper_jar:
            errors.append(f"Template '{name}' is missing gradle/wrapper/gradle-wrapper.jar")

        if not has_gradlew and not has_gradlew_bat:
            warnings.append(f"Template '{name}' is missing both gradlew and gradlew.bat")
        elif not has_gradlew:
            warnings.append(f"Template '{name}' is missing gradlew")
        elif not has_gradlew_bat:
            warnings.append(f"Template '{name}' is missing gradlew.bat")

        templates.append(
            TemplateStatus(
                name=name,
                path=path,
                has_descriptor=has_descriptor,
                descriptor_valid=descriptor_valid,
                error_message=error_message,
                loader=loader,
                minecraft_version=minecraft_version,
                recipe_folder=recipe_folder,
                recipe_format=recipe_format,
                jar_loader_suffix=jar_loader_suffix,
                has_gradlew=has_gradlew,
                has_gradlew_bat=has_gradlew_bat,
                has_gradle_wrapper_jar=has_gradle_wrapper_jar,
            )
        )

    return TemplateListResult(
        templates=templates,
        errors=errors,
        warnings=warnings,
    )
