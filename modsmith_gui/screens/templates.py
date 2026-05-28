"""Templates screen — view, validate, and edit template descriptors.

Provides:
  - Tabular listing of all template folders under MODTEMPLATES.
  - Detail panel for the selected template row.
  - Buttons: Refresh, Add Template, Open Templates Folder,
             Create/Edit Descriptor, Open Descriptor JSON.
  - Descriptor dialog integration for creating or editing modsmith-template.json.
  - Post-import prompt: offer to create descriptor if it was missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import re
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QMessageBox, QInputDialog, QFileDialog,
    QDialog,
)
from PySide6.QtCore import Qt, Slot

from modsmith.template_listing import list_templates, TemplateStatus
from modsmith.utils import safe_delete_tree
from modsmith_gui.dialogs.template_descriptor_dialog import TemplateDescriptorDialog


def _get_default_dir(subdir: str) -> Path:
    """Helper to resolve directory relative to MODSMITH_HOME or CWD."""
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


class TemplatesScreen(QWidget):
    """Screen for scanning, validation and detail viewing of ModSmith templates."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_templates: list[TemplateStatus] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Templates")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)

        # --- Top control row ---
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedWidth(80)
        self._btn_refresh.clicked.connect(self.refresh)

        self._btn_add_template = QPushButton("Add Template")
        self._btn_add_template.clicked.connect(self._add_template)

        self._btn_open_folder = QPushButton("Open Templates Folder")
        self._btn_open_folder.clicked.connect(self._open_templates_folder)

        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color: #666; font-size: 11px;")

        controls.addWidget(self._btn_refresh)
        controls.addWidget(self._btn_add_template)
        controls.addWidget(self._btn_open_folder)
        controls.addWidget(self._lbl_status)
        controls.addStretch()

        root.addLayout(controls)

        # --- Second button row: descriptor actions ---
        desc_controls = QHBoxLayout()
        desc_controls.setSpacing(8)

        self._btn_descriptor = QPushButton("Create Descriptor")
        self._btn_descriptor.setMinimumWidth(150)
        self._btn_descriptor.setToolTip(
            "Create or edit the modsmith-template.json descriptor for the selected template."
        )
        self._btn_descriptor.clicked.connect(self._on_descriptor)

        self._btn_open_descriptor_json = QPushButton("Open Descriptor JSON")
        self._btn_open_descriptor_json.setMinimumWidth(155)
        self._btn_open_descriptor_json.setToolTip(
            "Open the modsmith-template.json file in the system default editor."
        )
        self._btn_open_descriptor_json.clicked.connect(self._on_open_descriptor_json)

        desc_controls.addWidget(self._btn_descriptor)
        desc_controls.addWidget(self._btn_open_descriptor_json)
        desc_controls.addStretch()

        root.addLayout(desc_controls)

        # --- Empty state warning label ---
        self._lbl_empty_state = QLabel("")
        self._lbl_empty_state.setWordWrap(True)
        self._lbl_empty_state.setStyleSheet(
            "background-color: #ffe8d6; color: #b87800; border: 1px solid #ffd0a8; "
            "border-radius: 4px; padding: 12px; font-size: 12px;"
        )
        self._lbl_empty_state.hide()
        root.addWidget(self._lbl_empty_state)

        # --- Main table ---
        self._table = QTableWidget()
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        root.addWidget(self._table, stretch=1)

        # --- Detail group at the bottom ---
        self._detail_group = QGroupBox("Selected Template Details")
        detail_form = QFormLayout(self._detail_group)
        detail_form.setContentsMargins(10, 8, 10, 8)
        detail_form.setSpacing(6)
        detail_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._txt_detail_path = QLineEdit()
        self._txt_detail_path.setReadOnly(True)

        self._txt_detail_descriptor_path = QLineEdit()
        self._txt_detail_descriptor_path.setReadOnly(True)

        self._lbl_detail_error = QLabel("Select a template row to view details.")
        self._lbl_detail_error.setWordWrap(True)
        self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")

        detail_form.addRow("Template path:", self._txt_detail_path)
        detail_form.addRow("Descriptor path:", self._txt_detail_descriptor_path)
        detail_form.addRow("Status details:", self._lbl_detail_error)

        root.addWidget(self._detail_group)

        # Set initial disabled states
        self._btn_descriptor.setEnabled(False)
        self._btn_open_descriptor_json.setEnabled(False)
        self._detail_group.setEnabled(False)

        # First refresh
        self.refresh()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Scan templates on disk and rebuild the table."""
        tpl_dir = _get_default_dir("MODTEMPLATES")
        self._table.clearSelection()
        self._txt_detail_path.setText("")
        self._txt_detail_descriptor_path.setText("")
        self._lbl_detail_error.setText("Select a template row to view details.")
        self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")
        self._btn_descriptor.setText("Create Descriptor")

        # Handle folder missing defensively
        if not tpl_dir.exists():
            self._current_templates = []
            self._table.hide()
            self._detail_group.hide()
            self._btn_descriptor.hide()
            self._btn_open_descriptor_json.hide()
            self._lbl_empty_state.setText(
                f"Templates folder does not exist:\n{tpl_dir}"
            )
            self._lbl_empty_state.setStyleSheet(
                "background-color: #fce8e6; color: #a94442; border: 1px solid #ebccd1; "
                "border-radius: 4px; padding: 12px; font-size: 12px;"
            )
            self._lbl_empty_state.show()
            self._lbl_status.setText("Error: MODTEMPLATES folder missing")
            return

        # Perform the actual template listing
        result = list_templates(tpl_dir)
        self._current_templates = result.templates

        if not result.templates:
            self._table.hide()
            self._detail_group.hide()
            self._btn_descriptor.hide()
            self._btn_open_descriptor_json.hide()
            self._lbl_empty_state.setText(
                f"No templates found in:\n{tpl_dir}\n\n"
                "Use Add Template to import a template folder."
            )
            self._lbl_empty_state.setStyleSheet(
                "background-color: #ffe8d6; color: #b87800; border: 1px solid #ffd0a8; "
                "border-radius: 4px; padding: 12px; font-size: 12px;"
            )
            self._lbl_empty_state.show()
            self._lbl_status.setText("Warning: Empty templates folder")
            return

        # Templates found: show table, show controls and hide warning
        self._lbl_empty_state.hide()
        self._table.show()
        self._detail_group.show()
        self._btn_descriptor.show()
        self._btn_open_descriptor_json.show()
        # Reset selection to ensure selection changed handler runs and sets initial disabled state
        self._on_selection_changed()

        # Build table structure
        self._table.setRowCount(0)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Name", "Loader", "MC Version", "Recipe Format", "Recipe Folder", "Wrapper", "Status"
        ])

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row_idx, status in enumerate(result.templates):
            self._table.insertRow(row_idx)

            self._table.setItem(row_idx, 0, QTableWidgetItem(status.name))
            self._table.setItem(row_idx, 1, QTableWidgetItem(status.loader or "—"))
            self._table.setItem(row_idx, 2, QTableWidgetItem(status.minecraft_version or "—"))
            self._table.setItem(row_idx, 3, QTableWidgetItem(status.recipe_format or "—"))
            self._table.setItem(row_idx, 4, QTableWidgetItem(status.recipe_folder or "—"))

            wrap_str = "gradle-wrapper.jar" if status.has_gradle_wrapper_jar else "Missing wrapper"
            wrap_item = QTableWidgetItem(wrap_str)
            if not status.has_gradle_wrapper_jar:
                wrap_item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(row_idx, 5, wrap_item)

            if not status.has_descriptor or not status.descriptor_valid or not status.has_gradle_wrapper_jar:
                status_str = "ERROR"
                status_item = QTableWidgetItem(status_str)
                status_item.setForeground(Qt.GlobalColor.red)
            elif not status.has_gradlew or not status.has_gradlew_bat:
                status_str = "WARNING"
                status_item = QTableWidgetItem(status_str)
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                status_str = "OK"
                status_item = QTableWidgetItem(status_str)
                status_item.setForeground(Qt.GlobalColor.darkGreen)

            self._table.setItem(row_idx, 6, status_item)

        err_cnt = len(result.errors)
        warn_cnt = len(result.warnings)
        self._lbl_status.setText(
            f"Found {len(result.templates)} templates ({err_cnt} errors, {warn_cnt} warnings)"
        )

    # ------------------------------------------------------------------
    # Descriptor actions
    # ------------------------------------------------------------------

    def _selected_template(self) -> TemplateStatus | None:
        """Return the currently selected TemplateStatus, or None if none selected."""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        if row < len(self._current_templates):
            return self._current_templates[row]
        return None

    @Slot()
    def _on_descriptor(self) -> None:
        """Open the descriptor dialog for the selected template."""
        status = self._selected_template()
        if status is None:
            QMessageBox.warning(
                self,
                "No Template Selected",
                "Please select a template row first.",
            )
            return

        self._open_descriptor_dialog(status.path)

    def _open_descriptor_dialog(self, template_path: Path) -> None:
        """Open the TemplateDescriptorDialog for *template_path* and refresh on accept."""
        dialog = TemplateDescriptorDialog(template_path=template_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    @Slot()
    def _on_open_descriptor_json(self) -> None:
        """Open the selected template's descriptor JSON in the system default editor."""
        status = self._selected_template()
        if status is None:
            QMessageBox.warning(
                self,
                "No Template Selected",
                "Please select a template row first.",
            )
            return

        descriptor_path = status.path / "modsmith-template.json"
        if not descriptor_path.exists():
            QMessageBox.warning(
                self,
                "Descriptor Not Found",
                "Descriptor does not exist yet.\n\n"
                "Click \"Create Descriptor\" to create it.",
            )
            return

        try:
            if sys.platform == "win32":
                os.startfile(str(descriptor_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(descriptor_path)])
            else:
                subprocess.Popen(["xdg-open", str(descriptor_path)])
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Open Error",
                f"Could not open descriptor file:\n{exc}",
            )

    # ------------------------------------------------------------------
    # Add Template
    # ------------------------------------------------------------------

    @Slot()
    def _add_template(self) -> None:
        """Prompt for folder import details, copy MDK source folder, and refresh."""
        tpl_dir = _get_default_dir("MODTEMPLATES")
        if not tpl_dir.exists():
            try:
                tpl_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Import Template",
                    f"Templates folder does not exist and could not be created:\n{exc}"
                )
                return

        # 1. Ask for template destination name
        dest_name, ok = QInputDialog.getText(
            self,
            "Add Template",
            "Template Name (e.g. forge-1.20.1):",
            QLineEdit.EchoMode.Normal,
            ""
        )
        if not ok or not dest_name.strip():
            return

        dest_name = dest_name.strip()
        if not re.match(r"^[A-Za-z0-9_.-]+$", dest_name):
            QMessageBox.critical(
                self,
                "Import Error",
                "Invalid template folder name. Use alphanumeric characters, dashes, dots, and underscores only."
            )
            return

        dest_path = tpl_dir / dest_name

        # 2. Ask user to pick the unpacked source directory
        source_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Unpacked Template / MDK Source Directory"
        )
        if not source_dir:
            return

        source_path = Path(source_dir)
        if not source_path.is_dir():
            QMessageBox.critical(self, "Import Error", "Source must be a valid directory.")
            return

        # 3. Check for existence and prompt for overwrite
        if dest_path.exists():
            reply = QMessageBox.question(
                self,
                "Template Exists",
                f"A template folder named '{dest_name}' already exists. Overwrite/replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            try:
                safe_delete_tree(dest_path)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Import Error",
                    f"Failed to delete existing template directory:\n{exc}"
                )
                return

        # 4. Copy recursively
        try:
            shutil.copytree(source_path, dest_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to copy template folder:\n{exc}"
            )
            return

        # 5. Check descriptor — offer to create it now if missing
        desc_path = dest_path / "modsmith-template.json"
        if not desc_path.exists():
            reply = QMessageBox.question(
                self,
                "Descriptor Missing",
                "Template imported, but modsmith-template.json is missing.\n\n"
                "Create it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_descriptor_dialog(dest_path)
                self.refresh()
                return

        QMessageBox.information(
            self,
            "Template Imported",
            f"Successfully imported template '{dest_name}' into MODTEMPLATES."
        )

        self.refresh()

    # ------------------------------------------------------------------
    # Open templates folder
    # ------------------------------------------------------------------

    @Slot()
    def _open_templates_folder(self) -> None:
        """Open the active templates directory in File Explorer safely."""
        tpl_dir = _get_default_dir("MODTEMPLATES")
        if not tpl_dir.is_dir():
            QMessageBox.warning(
                self,
                "Open Folder",
                f"Templates directory does not exist:\n{tpl_dir}",
            )
            return

        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(tpl_dir)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(tpl_dir)])
            else:
                subprocess.Popen(["xdg-open", str(tpl_dir)])
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Open Folder",
                f"Failed to open directory:\n{exc}",
            )

    # ------------------------------------------------------------------
    # Selection handler
    # ------------------------------------------------------------------

    @Slot()
    def _on_selection_changed(self) -> None:
        """Update detail panel and button state for the selected template."""
        status = self._selected_template()

        if status is None:
            self._txt_detail_path.setText("")
            self._txt_detail_descriptor_path.setText("")
            self._lbl_detail_error.setText("Select a template row to view details.")
            self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")
            self._btn_descriptor.setText("Create Descriptor")
            self._btn_descriptor.setEnabled(False)
            self._btn_open_descriptor_json.setEnabled(False)
            self._detail_group.setEnabled(False)
            return

        # Enable actions when selected
        self._btn_descriptor.setEnabled(True)
        self._btn_open_descriptor_json.setEnabled(True)
        self._detail_group.setEnabled(True)

        # Populate path fields
        self._txt_detail_path.setText(str(status.path))
        descriptor_file = status.path / "modsmith-template.json"
        self._txt_detail_descriptor_path.setText(str(descriptor_file))

        # Update descriptor button label
        if status.has_descriptor:
            self._btn_descriptor.setText("Edit Descriptor")
        else:
            self._btn_descriptor.setText("Create Descriptor")

        # Build status details
        details = []
        if not status.has_descriptor:
            details.append(
                "• Missing descriptor file (modsmith-template.json)\n"
                "  → Click \"Create Descriptor\" to fix it."
            )
        elif not status.descriptor_valid:
            details.append(f"• Invalid descriptor file: {status.error_message}")
        if not status.has_gradle_wrapper_jar:
            details.append("• Missing standard wrapper file (gradle/wrapper/gradle-wrapper.jar)")
        if not status.has_gradlew:
            details.append("• Missing gradlew shell script (required for Linux/macOS)")
        if not status.has_gradlew_bat:
            details.append("• Missing gradlew.bat batch script (required for Windows)")

        if details:
            self._lbl_detail_error.setText("\n".join(details))
            if not status.has_descriptor or not status.descriptor_valid or not status.has_gradle_wrapper_jar:
                self._lbl_detail_error.setStyleSheet("color: #b00; font-size: 11px;")
            else:
                self._lbl_detail_error.setStyleSheet("color: #b87800; font-size: 11px;")
        else:
            self._lbl_detail_error.setText("✓ Template is valid and ready to compile.")
            self._lbl_detail_error.setStyleSheet("color: #060; font-size: 11px;")
