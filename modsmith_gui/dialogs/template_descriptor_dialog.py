"""Template Descriptor Editor dialog.

Opens a simple form that lets the user create or edit the
``modsmith-template.json`` descriptor for a specific template folder.

Usage::

    dialog = TemplateDescriptorDialog(
        template_path=Path("MODTEMPLATES/forge-1.20.1"),
        parent=self,
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        self.refresh()

The dialog infers sensible defaults from the folder name when no descriptor
file exists yet.  When an existing descriptor is found it is loaded and the
form is pre-populated with the stored values.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt

from modsmith_gui.template_descriptor_utils import (
    infer_template_descriptor_defaults,
    KNOWN_LOADERS,
    RECIPE_FORMAT_LEGACY,
    RECIPE_FORMAT_MODERN,
    recipe_format_for_minecraft_version,
    recipe_folder_for_minecraft_version,
)

_DESCRIPTOR_FILENAME = "modsmith-template.json"


class TemplateDescriptorDialog(QDialog):
    """Form dialog for creating or editing ``modsmith-template.json``.

    Parameters
    ----------
    template_path:
        Absolute path to the template folder (e.g. ``MODTEMPLATES/forge-1.20.1``).
    parent:
        Optional parent widget.
    """

    def __init__(
        self,
        template_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._template_path = Path(template_path)
        self._descriptor_path = self._template_path / _DESCRIPTOR_FILENAME
        self._editing = self._descriptor_path.exists()

        self.setWindowTitle(
            "Edit Descriptor" if self._editing else "Create Descriptor"
        )
        self.setMinimumWidth(440)
        self.setModal(True)

        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Header
        action = "Editing" if self._editing else "Creating"
        header = QLabel(f"{action}: <b>{self._template_path.name}</b>")
        header.setWordWrap(True)
        root.addWidget(header)

        desc_label = QLabel(
            f"Descriptor file: <code>{self._descriptor_path}</code>"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #555; font-size: 11px;")
        root.addWidget(desc_label)

        # Form
        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Loader
        self._cmb_loader = QComboBox()
        self._cmb_loader.addItems(list(KNOWN_LOADERS))
        self._cmb_loader.setEditable(False)
        self._cmb_loader.currentTextChanged.connect(self._on_loader_changed)
        form.addRow("Loader:", self._cmb_loader)

        # Minecraft Version
        self._txt_mc_version = QLineEdit()
        self._txt_mc_version.setPlaceholderText("e.g. 1.20.1 or 1.21.4")
        self._txt_mc_version.editingFinished.connect(self._on_mc_version_editing_finished)
        form.addRow("Minecraft Version:", self._txt_mc_version)

        # Recipe Format
        self._cmb_recipe_format = QComboBox()
        self._cmb_recipe_format.addItems([RECIPE_FORMAT_LEGACY, RECIPE_FORMAT_MODERN])
        self._cmb_recipe_format.setEditable(False)
        form.addRow("Recipe Format:", self._cmb_recipe_format)

        # Recipe Folder
        self._cmb_recipe_folder = QComboBox()
        self._cmb_recipe_folder.addItems(["recipes", "recipe"])
        self._cmb_recipe_folder.setEditable(False)
        form.addRow("Recipe Folder:", self._cmb_recipe_folder)

        # JAR Loader Suffix
        self._txt_jar_suffix = QLineEdit()
        self._txt_jar_suffix.setPlaceholderText("e.g. forge, fabric, neoforge")
        # Track whether the user has manually edited the suffix field
        self._jar_suffix_user_edited = False
        self._txt_jar_suffix.textEdited.connect(self._on_jar_suffix_edited)
        form.addRow("JAR Loader Suffix:", self._txt_jar_suffix)

        root.addLayout(form)

        # Hint
        hint = QLabel(
            "<i>Recipe Format:</i> use <code>legacy_1_20</code> for 1.20.x "
            "and <code>modern_1_21</code> for 1.21+."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(hint)

        # Buttons
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_box.accepted.connect(self._on_save)
        self._btn_box.rejected.connect(self.reject)
        root.addWidget(self._btn_box)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Fill form fields from existing descriptor or inferred defaults."""
        if self._editing:
            self._load_existing()
        else:
            self._load_defaults()

    def _load_defaults(self) -> None:
        """Infer defaults from the template folder name."""
        defaults = infer_template_descriptor_defaults(self._template_path.name)
        self._set_loader(defaults["loader"])
        self._txt_mc_version.setText(defaults["minecraft_version"])
        self._set_recipe_format(defaults["recipe_format"])
        self._set_recipe_folder(defaults["recipe_folder"])
        self._txt_jar_suffix.setText(defaults["jar_loader_suffix"])
        self._jar_suffix_user_edited = False

    def _load_existing(self) -> None:
        """Load and populate form from existing descriptor JSON."""
        try:
            raw = json.loads(self._descriptor_path.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Load Error",
                f"Could not read existing descriptor:\n{exc}\n\n"
                "Defaulting to inferred values.",
            )
            self._load_defaults()
            return

        self._set_loader(raw.get("loader", ""))
        self._txt_mc_version.setText(raw.get("minecraft_version", ""))
        self._set_recipe_format(raw.get("recipe_format", RECIPE_FORMAT_MODERN))
        self._set_recipe_folder(raw.get("recipe_folder", "recipes"))
        # Only mark as user-edited if jar_loader_suffix was explicitly set
        suffix = raw.get("jar_loader_suffix", "")
        self._txt_jar_suffix.setText(suffix)
        # If the stored suffix differs from loader, treat as user-edited
        loader_val = self._cmb_loader.currentText()
        self._jar_suffix_user_edited = bool(suffix) and suffix != loader_val

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_loader(self, loader: str) -> None:
        idx = self._cmb_loader.findText(loader, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self._cmb_loader.setCurrentIndex(idx)
        else:
            # Unknown loader: select first item (form is still editable)
            self._cmb_loader.setCurrentIndex(0)

    def _set_recipe_format(self, fmt: str) -> None:
        idx = self._cmb_recipe_format.findText(fmt, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self._cmb_recipe_format.setCurrentIndex(idx)
        else:
            # Default to modern
            idx_modern = self._cmb_recipe_format.findText(RECIPE_FORMAT_MODERN)
            self._cmb_recipe_format.setCurrentIndex(max(idx_modern, 0))

    def _set_recipe_folder(self, folder: str) -> None:
        idx = self._cmb_recipe_folder.findText(folder, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self._cmb_recipe_folder.setCurrentIndex(idx)
        else:
            QMessageBox.warning(
                self,
                "Unknown Recipe Folder",
                f"Unknown recipe folder value '{folder}' found in descriptor. "
                "Defaulting to 'recipes'."
            )
            idx_recipes = self._cmb_recipe_folder.findText("recipes")
            self._cmb_recipe_folder.setCurrentIndex(max(idx_recipes, 0))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_loader_changed(self, loader: str) -> None:
        """Auto-fill JAR suffix when the user changes the loader combo."""
        if not self._jar_suffix_user_edited:
            self._txt_jar_suffix.setText(loader)

    def _on_jar_suffix_edited(self) -> None:
        """Mark suffix as manually edited so auto-fill stops overwriting it."""
        self._jar_suffix_user_edited = True

    def _on_mc_version_editing_finished(self) -> None:
        """Update recipe_format and recipe_folder to defaults when Minecraft version changes."""
        version = self._txt_mc_version.text().strip()
        if version:
            fmt = recipe_format_for_minecraft_version(version)
            self._set_recipe_format(fmt)
            folder = recipe_folder_for_minecraft_version(version)
            self._set_recipe_folder(folder)

    def _on_save(self) -> None:
        """Validate fields and write descriptor JSON."""
        loader = self._cmb_loader.currentText().strip()
        mc_version = self._txt_mc_version.text().strip()
        recipe_format = self._cmb_recipe_format.currentText().strip()
        recipe_folder = self._cmb_recipe_folder.currentText().strip()
        jar_suffix = self._txt_jar_suffix.text().strip()

        # Validation
        missing = []
        if not loader:
            missing.append("Loader")
        if not mc_version:
            missing.append("Minecraft Version")
        if not recipe_format:
            missing.append("Recipe Format")
        if not recipe_folder:
            missing.append("Recipe Folder")
        if not jar_suffix:
            missing.append("JAR Loader Suffix")

        if missing:
            QMessageBox.warning(
                self,
                "Validation Error",
                "The following required fields are empty:\n• " + "\n• ".join(missing),
            )
            return

        # Build JSON (only expose the fields the dialog manages;
        # preserve existing advanced fields if editing)
        data: dict = {}
        if self._editing:
            try:
                data = json.loads(self._descriptor_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        data["loader"] = loader
        data["minecraft_version"] = mc_version
        data["recipe_format"] = recipe_format
        data["recipe_folder"] = recipe_folder
        data["jar_loader_suffix"] = jar_suffix

        try:
            self._descriptor_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not write descriptor file:\n{exc}",
            )
            return

        self.accept()

    # ------------------------------------------------------------------
    # Public accessor (for tests)
    # ------------------------------------------------------------------

    @property
    def descriptor_path(self) -> Path:
        """Absolute path where the descriptor file will be written."""
        return self._descriptor_path
