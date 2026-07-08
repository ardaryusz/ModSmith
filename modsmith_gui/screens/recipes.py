"""Recipes screen — view and validate all recipes in WORKSPACE/RECIPES."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt, Slot

from modsmith.recipes import detect_format, RecipeFormat


def _get_default_dir(subdir: str) -> Path:
    """Helper to resolve directory relative to MODSMITH_HOME or CWD."""
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


@dataclass
class RecipeItemStatus:
    """Status details for an individual recipe file under WORKSPACE/RECIPES."""

    filename: str
    path: Path
    recipe_type: str
    detected_format: str
    result: str
    status: str
    error_message: str | None = None


class RecipesScreen(QWidget):
    """Screen for scanning, validation, and detail viewing of ModSmith recipes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_recipes: list[RecipeItemStatus] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Recipes")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)

        # --- Top control row ---
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedWidth(80)
        self._btn_refresh.clicked.connect(self.refresh)

        self._btn_open_folder = QPushButton("Open Recipes Folder")
        self._btn_open_folder.clicked.connect(self._open_recipes_folder)

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
        detail_group = QGroupBox("Selected Recipe Details")
        detail_form = QFormLayout(detail_group)
        detail_form.setContentsMargins(10, 8, 10, 8)
        detail_form.setSpacing(6)
        detail_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._txt_detail_path = QLineEdit()
        self._txt_detail_path.setReadOnly(True)

        self._lbl_detail_error = QLabel("Select a recipe row to view details.")
        self._lbl_detail_error.setWordWrap(True)
        self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")

        detail_form.addRow("Absolute path:", self._txt_detail_path)
        detail_form.addRow("Details:", self._lbl_detail_error)

        root.addWidget(detail_group)

        # First refresh
        self.refresh()

    def refresh(self) -> None:
        """Scan recipe JSON files on disk one-by-one defensively."""
        workspace_dir = _get_default_dir("WORKSPACE")
        recipes_dir = workspace_dir / "RECIPES"

        self._table.clearSelection()
        self._txt_detail_path.setText("")
        self._lbl_detail_error.setText("Select a recipe row to view details.")
        self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")

        # Handle folder missing defensively
        if not recipes_dir.exists():
            self._current_recipes = []
            self._table.hide()
            self._lbl_empty_state.setText(
                f"WORKSPACE/RECIPES folder does not exist:\n{recipes_dir}\n\n"
                "Please configure MODSMITH_HOME or create this folder inside your active workspace."
            )
            self._lbl_empty_state.setStyleSheet(
                "background-color: #fce8e6; color: #a94442; border: 1px solid #ebccd1; "
                "border-radius: 4px; padding: 12px; font-size: 12px;"
            )
            self._lbl_empty_state.show()
            self._lbl_status.setText("Error: WORKSPACE/RECIPES folder missing")
            return

        # Find JSON recipe files
        try:
            recipe_files = sorted(recipes_dir.glob("*.json"), key=lambda p: p.name.lower())
        except OSError as exc:
            self._current_recipes = []
            self._table.hide()
            self._lbl_empty_state.setText(f"Failed to scan recipes folder:\n{exc}")
            self._lbl_empty_state.show()
            self._lbl_status.setText("Error: Failed to scan directory")
            return

        if not recipe_files:
            self._current_recipes = []
            self._table.hide()
            self._lbl_empty_state.setText(
                f"No recipe JSON files found in:\n{recipes_dir}\n\n"
                "To create a recipe, add a JSON file matching Minecraft's crafting shaped/shapeless format."
            )
            self._lbl_empty_state.setStyleSheet(
                "background-color: #ffe8d6; color: #b87800; border: 1px solid #ffd0a8; "
                "border-radius: 4px; padding: 12px; font-size: 12px;"
            )
            self._lbl_empty_state.show()
            self._lbl_status.setText("Warning: No recipes found")
            return

        # Recipes found: scan them robustly one by one
        self._lbl_empty_state.hide()
        self._table.show()

        scanned_items: list[RecipeItemStatus] = []
        error_cnt = 0

        for path in recipe_files:
            filename = path.name
            recipe_type = "—"
            detected_format = "—"
            result_str = "—"
            status = "OK"
            error_message = None

            try:
                text = path.read_text(encoding="utf-8")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("JSON root is not a dictionary object")

                # Retrieve attributes
                recipe_type = data.get("type", "—")
                fmt = detect_format(data)
                if fmt == RecipeFormat.LEGACY_PRE_1_20_5:
                    detected_format = "Legacy (<= 1.20.4)"
                elif fmt == RecipeFormat.TRANSITIONAL_1_20_5_TO_1_21_1:
                    detected_format = "Transitional (1.20.5 - 1.21.1)"
                else:
                    detected_format = "Modern (>= 1.21.2)"

                # Parse result
                res = data.get("result")
                if isinstance(res, str):
                    result_str = res
                elif isinstance(res, dict):
                    res_id = res.get("id") or res.get("item", "—")
                    count = res.get("count")
                    if count is not None:
                        result_str = f"{res_id} (x{count})"
                    else:
                        result_str = res_id

            except Exception as exc:
                status = "ERROR"
                error_message = str(exc)
                error_cnt += 1

            scanned_items.append(
                RecipeItemStatus(
                    filename=filename,
                    path=path.resolve(),
                    recipe_type=recipe_type,
                    detected_format=detected_format,
                    result=result_str,
                    status=status,
                    error_message=error_message,
                )
            )

        self._current_recipes = scanned_items

        # Build table structure
        self._table.setRowCount(0)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "File", "Type", "Detected Format", "Result", "Status"
        ])

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # Make the File name column stretchable
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row_idx, item in enumerate(scanned_items):
            self._table.insertRow(row_idx)

            # Columns: File, Type, Detected Format, Result, Status
            self._table.setItem(row_idx, 0, QTableWidgetItem(item.filename))
            self._table.setItem(row_idx, 1, QTableWidgetItem(item.recipe_type))
            self._table.setItem(row_idx, 2, QTableWidgetItem(item.detected_format))
            self._table.setItem(row_idx, 3, QTableWidgetItem(item.result))

            status_item = QTableWidgetItem(item.status)
            if item.status == "ERROR":
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item.setForeground(Qt.GlobalColor.darkGreen)

            self._table.setItem(row_idx, 4, status_item)

        ok_cnt = len(scanned_items) - error_cnt
        self._lbl_status.setText(
            f"Found {len(scanned_items)} recipes ({ok_cnt} OK, {error_cnt} errors)"
        )

    @Slot()
    def _open_recipes_folder(self) -> None:
        """Open the active recipes directory in File Explorer safely."""
        workspace_dir = _get_default_dir("WORKSPACE")
        recipes_dir = workspace_dir / "RECIPES"

        if not recipes_dir.is_dir():
            QMessageBox.warning(
                self,
                "Open Folder",
                f"Recipes directory does not exist:\n{recipes_dir}",
            )
            return

        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(recipes_dir)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(recipes_dir)])
            else:
                subprocess.Popen(["xdg-open", str(recipes_dir)])
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Open Folder",
                f"Failed to open directory:\n{exc}",
            )

    @Slot()
    def _on_selection_changed(self) -> None:
        """Show details for the selected recipe."""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            self._txt_detail_path.setText("")
            self._lbl_detail_error.setText("Select a recipe row to view details.")
            self._lbl_detail_error.setStyleSheet("color: #666; font-size: 11px;")
            return

        row = selected_rows[0].row()
        if row < len(self._current_recipes):
            item = self._current_recipes[row]
            self._txt_detail_path.setText(str(item.path))

            if item.status == "ERROR":
                self._lbl_detail_error.setText(f"❌ Load error:\n{item.error_message}")
                self._lbl_detail_error.setStyleSheet("color: #b00; font-size: 11px;")
            else:
                self._lbl_detail_error.setText(
                    f"✓ Recipe parsed successfully.\n"
                    f"  Type: {item.recipe_type}\n"
                    f"  Format: {item.detected_format}\n"
                    f"  Result: {item.result}"
                )
                self._lbl_detail_error.setStyleSheet("color: #060; font-size: 11px;")
