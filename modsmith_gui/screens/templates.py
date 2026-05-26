"""Templates screen — view and validate all templates in MODTEMPLATES."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt, Slot

from modsmith.template_listing import list_templates, TemplateStatus


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

        self._btn_open_folder = QPushButton("Open Templates Folder")
        self._btn_open_folder.clicked.connect(self._open_templates_folder)

        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color: #666; font-size: 11px;")

        controls.addWidget(self._btn_refresh)
        controls.addWidget(self._btn_open_folder)
        controls.addWidget(self._lbl_status)
        controls.addStretch()

        root.addLayout(controls)

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
        detail_group = QGroupBox("Selected Template Details")
        detail_form = QFormLayout(detail_group)
        detail_form.setContentsMargins(10, 8, 10, 8)
        detail_form.setSpacing(6)
        detail_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._txt_detail_path = QLineEdit()
        self._txt_detail_path.setReadOnly(True)

        self._lbl_detail_error = QLabel("Select a template row to view details.")
        self._lbl_detail_error.setWordWrap(True)
        self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")

        detail_form.addRow("Absolute path:", self._txt_detail_path)
        detail_form.addRow("Status details:", self._lbl_detail_error)

        root.addWidget(detail_group)

        # First refresh
        self.refresh()

    def refresh(self) -> None:
        """Scan templates on disk and rebuild the table."""
        tpl_dir = _get_default_dir("MODTEMPLATES")
        self._table.clearSelection()
        self._txt_detail_path.setText("")
        self._lbl_detail_error.setText("Select a template row to view details.")
        self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")

        # Handle folder missing defensively
        if not tpl_dir.exists():
            self._current_templates = []
            self._table.hide()
            self._lbl_empty_state.setText(
                f"Templates folder does not exist:\n{tpl_dir}\n\n"
                "Please configure MODSMITH_HOME or create this folder inside your active workspace."
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
            self._lbl_empty_state.setText(
                f"No templates found in:\n{tpl_dir}\n\n"
                "To create a new template, make a directory in MODTEMPLATES containing a 'modsmith-template.json' descriptor."
            )
            self._lbl_empty_state.setStyleSheet(
                "background-color: #ffe8d6; color: #b87800; border: 1px solid #ffd0a8; "
                "border-radius: 4px; padding: 12px; font-size: 12px;"
            )
            self._lbl_empty_state.show()
            self._lbl_status.setText("Warning: Empty templates folder")
            return

        # Templates found: show table and hide warning
        self._lbl_empty_state.hide()
        self._table.show()

        # Build table structure
        self._table.setRowCount(0)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Name", "Loader", "MC Version", "Recipe Format", "Recipe Folder", "Wrapper", "Status"
        ])

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # Make the Name column stretchable
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row_idx, status in enumerate(result.templates):
            self._table.insertRow(row_idx)

            # Columns: Name, Loader, MC Version, Recipe Format, Recipe Folder, Wrapper, Status
            self._table.setItem(row_idx, 0, QTableWidgetItem(status.name))
            self._table.setItem(row_idx, 1, QTableWidgetItem(status.loader or "—"))
            self._table.setItem(row_idx, 2, QTableWidgetItem(status.minecraft_version or "—"))
            self._table.setItem(row_idx, 3, QTableWidgetItem(status.recipe_format or "—"))
            self._table.setItem(row_idx, 4, QTableWidgetItem(status.recipe_folder or "—"))

            # Wrapper jar status
            wrap_str = "gradle-wrapper.jar" if status.has_gradle_wrapper_jar else "Missing wrapper"
            wrap_item = QTableWidgetItem(wrap_str)
            if not status.has_gradle_wrapper_jar:
                wrap_item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(row_idx, 5, wrap_item)

            # Combined Status
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

    @Slot()
    def _on_selection_changed(self) -> None:
        """Show details for the selected template."""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            self._txt_detail_path.setText("")
            self._lbl_detail_error.setText("Select a template row to view details.")
            self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")
            return

        row = selected_rows[0].row()
        if row < len(self._current_templates):
            status = self._current_templates[row]
            self._txt_detail_path.setText(str(status.path))

            details = []
            if not status.has_descriptor:
                details.append("• Missing descriptor file (modsmith-template.json)")
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
                # If blocker issues exist, color red, else color amber
                if not status.has_descriptor or not status.descriptor_valid or not status.has_gradle_wrapper_jar:
                    self._lbl_detail_error.setStyleSheet("color: #b00; font-size: 11px;")
                else:
                    self._lbl_detail_error.setStyleSheet("color: #b87800; font-size: 11px;")
            else:
                self._lbl_detail_error.setText("✓ Template is valid and ready to compile.")
                self._lbl_detail_error.setStyleSheet("color: #060; font-size: 11px;")
