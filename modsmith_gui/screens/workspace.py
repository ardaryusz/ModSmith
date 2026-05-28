"""Workspace screen — edit modsmith.json configuration with form fields and targets table."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QPlainTextEdit, QComboBox,
    QMessageBox, QScrollArea, QFrame, QFileDialog,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)

from modsmith.config import load_mod_config, ConfigError
from modsmith_gui.widgets.log_panel import LogPanel
from modsmith_gui.workspace_utils import (
    derive_pascal_case,
    derive_mc_range,
    make_exact_patch_range,
    make_same_minor_range,
    make_inclusive_range,
    parse_version_range,
    infer_from_template,
)


def _get_default_dir(subdir: str) -> Path:
    """Helper to resolve directory relative to MODSMITH_HOME or CWD."""
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


class WorkspaceScreen(QWidget):
    """Screen for loading, editing, saving, and validating modsmith.json."""

    def __init__(self, log_panel: LogPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_panel = log_panel

        # State tracking to avoid repeated missing modsmith.json prompts
        self._missing_config_prompt_answered = False
        self._last_home_path_for_prompt = os.environ.get("MODSMITH_HOME", "")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Workspace Config")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)

        # --- Top control row ---
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._btn_refresh = QPushButton("Load / Refresh")
        self._btn_refresh.setFixedWidth(100)
        self._btn_refresh.clicked.connect(self._on_manual_refresh)

        self._btn_save = QPushButton("Save Config")
        self._btn_save.setFixedWidth(100)
        self._btn_save.clicked.connect(self._save_config)

        self._btn_validate = QPushButton("Validate Config")
        self._btn_validate.setFixedWidth(120)
        self._btn_validate.clicked.connect(self._validate_config)

        self._btn_clear = QPushButton("Clear All")
        self._btn_clear.setFixedWidth(100)
        self._btn_clear.clicked.connect(self._clear_all)

        self._btn_open_folder = QPushButton("Open DETAILS Folder")
        self._btn_open_folder.setFixedWidth(140)
        self._btn_open_folder.clicked.connect(self._open_details_folder)

        controls.addWidget(self._btn_refresh)
        controls.addWidget(self._btn_save)
        controls.addWidget(self._btn_validate)
        controls.addWidget(self._btn_clear)
        controls.addWidget(self._btn_open_folder)
        controls.addStretch()

        root.addLayout(controls)

        # --- Scrollable content area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- Details GroupBox ---
        details_group = QGroupBox("Mod Metadata (modsmith.json)")
        details_form = QFormLayout(details_group)
        details_form.setContentsMargins(10, 8, 10, 8)
        details_form.setSpacing(6)
        details_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._txt_mod_id = QLineEdit()
        self._txt_mod_id.setPlaceholderText("e.g. easypeasygunpowder")
        self._txt_mod_id.textChanged.connect(self._validate_inputs)

        self._txt_mod_name = QLineEdit()
        self._txt_mod_name.setPlaceholderText("e.g. Easy Peasy Gunpowder")

        self._txt_mod_version = QLineEdit()
        self._txt_mod_version.setPlaceholderText("e.g. 1.0.0")

        self._txt_group = QLineEdit()
        self._txt_group.setPlaceholderText("e.g. com.example")

        self._txt_authors = QLineEdit()
        self._txt_authors.setPlaceholderText("e.g. developer_name")

        self._txt_license = QLineEdit()
        self._txt_license.setPlaceholderText("e.g. MIT")

        self._txt_description = QPlainTextEdit()
        self._txt_description.setPlaceholderText("Write a short description of the mod here...")
        self._txt_description.setMinimumHeight(55)
        self._txt_description.setMaximumHeight(85)

        self._txt_homepage = QLineEdit()
        self._txt_homepage.setPlaceholderText("e.g. https://example.com (optional)")

        self._txt_issue_tracker = QLineEdit()
        self._txt_issue_tracker.setPlaceholderText("e.g. https://example.com/issues (optional)")

        details_form.addRow("Mod ID:", self._txt_mod_id)
        details_form.addRow("Mod Name:", self._txt_mod_name)
        details_form.addRow("Mod Version:", self._txt_mod_version)
        details_form.addRow("Group:", self._txt_group)
        details_form.addRow("Authors:", self._txt_authors)
        details_form.addRow("License:", self._txt_license)
        details_form.addRow("Description:", self._txt_description)
        details_form.addRow("Homepage:", self._txt_homepage)
        details_form.addRow("Issue Tracker:", self._txt_issue_tracker)

        layout.addWidget(details_group)

        # --- Targets GroupBox ---
        targets_group = QGroupBox("Generation Targets")
        targets_layout = QVBoxLayout(targets_group)
        targets_layout.setContentsMargins(10, 8, 10, 8)
        targets_layout.setSpacing(8)

        # Targets buttons
        t_buttons = QHBoxLayout()
        self._btn_add_target = QPushButton("Add Target")
        self._btn_add_target.setFixedWidth(100)
        self._btn_add_target.clicked.connect(self._add_target_row)

        self._btn_remove_target = QPushButton("Remove Target")
        self._btn_remove_target.setFixedWidth(130)
        self._btn_remove_target.clicked.connect(self._remove_target_row)

        t_buttons.addWidget(self._btn_add_target)
        t_buttons.addWidget(self._btn_remove_target)
        t_buttons.addStretch()

        targets_layout.addLayout(t_buttons)

        # Targets QTableWidget
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(180)
        self._table.itemChanged.connect(self._on_item_changed)
        targets_layout.addWidget(self._table)

        layout.addWidget(targets_group)

        # --- Mod Icon GroupBox ---
        icon_group = QGroupBox("Mod Icon")
        icon_layout = QVBoxLayout(icon_group)
        icon_layout.setContentsMargins(10, 8, 10, 8)
        icon_layout.setSpacing(8)

        icon_info_row = QHBoxLayout()
        icon_info_row.setSpacing(10)

        self._icon_thumbnail = QLabel()
        self._icon_thumbnail.setFixedSize(64, 64)
        self._icon_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_thumbnail.setStyleSheet(
            "border: 1px solid #ccc; background-color: #f5f5f5;"
        )
        self._icon_thumbnail.setText("No icon")

        self._icon_path_label = QLabel("No icon selected")
        self._icon_path_label.setWordWrap(True)

        icon_info_row.addWidget(self._icon_thumbnail)
        icon_info_row.addWidget(self._icon_path_label, stretch=1)

        icon_layout.addLayout(icon_info_row)

        icon_btn_row = QHBoxLayout()
        icon_btn_row.setSpacing(8)

        self._btn_select_icon = QPushButton("Select Icon")
        self._btn_select_icon.setFixedWidth(100)
        self._btn_select_icon.clicked.connect(self._select_icon)

        self._btn_clear_icon = QPushButton("Clear Icon")
        self._btn_clear_icon.setFixedWidth(100)
        self._btn_clear_icon.clicked.connect(self._clear_icon)

        icon_btn_row.addWidget(self._btn_select_icon)
        icon_btn_row.addWidget(self._btn_clear_icon)
        icon_btn_row.addStretch()

        icon_layout.addLayout(icon_btn_row)
        layout.addWidget(icon_group)

        # Internal icon state (relative path like "ASSETS/icon.png")
        self._icon_value: str = ""

        # First refresh load
        self.refresh()

    def refresh(self, force_prompt: bool = False) -> None:
        """Scan folders and load modsmith.json configuration from disk."""
        current_home = os.environ.get("MODSMITH_HOME", "")
        if current_home != self._last_home_path_for_prompt:
            self._last_home_path_for_prompt = current_home
            self._missing_config_prompt_answered = False

        details_dir = _get_default_dir("WORKSPACE") / "DETAILS"
        json_path = details_dir / "modsmith.json"

        # Safe directory creation
        details_dir.mkdir(parents=True, exist_ok=True)

        if json_path.exists():
            try:
                self._load_from_json(json_path)
            except Exception as exc:
                QMessageBox.critical(self, "Load Config", f"Failed to load modsmith.json:\n{exc}")
        else:
            # If the missing config prompt was already answered and we're not forcing a reload, skip prompting
            if self._missing_config_prompt_answered and not force_prompt:
                return

            # Check for example template file to offer import
            example_path = _get_default_dir("WORKSPACE") / "DETAILS" / "modsmith.example.json"
            if not example_path.exists():
                example_path = Path("modsmith.example.json").resolve()

            if example_path.exists():
                self._missing_config_prompt_answered = True
                reply = QMessageBox.question(
                    self,
                    "Load Example Config",
                    "modsmith.json was not found. Would you like to load example mod values?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        self._load_from_json(example_path)
                        self._log_panel.append_line("Loaded example config values successfully.")
                        return
                    except Exception as exc:
                        self._log_panel.append_line(f"Failed to load example config: {exc}")

            # Blank fallback state
            self._load_blank_defaults()

    @Slot()
    def _on_manual_refresh(self) -> None:
        """User explicitly clicked Load / Refresh, so force prompt again if file is missing."""
        self.refresh(force_prompt=True)

    @Slot()
    def _clear_all(self) -> None:
        """Clear all workspace form fields and reset one default target row after confirmation."""
        reply = QMessageBox.question(
            self,
            "Clear Form",
            "Clear all workspace form values? This will not delete or modify files until you click Save.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._load_blank_defaults()
            self._log_panel.append_line("[INFO] Workspace form cleared. No files were modified.")

    def _load_blank_defaults(self) -> None:
        """Populate GUI fields with clean, empty/default parameters."""
        self._txt_mod_id.setText("")
        self._txt_mod_name.setText("")
        self._txt_mod_version.setText("1.0.0")
        self._txt_group.setText("com.example")
        self._txt_authors.setText("")
        self._txt_license.setText("MIT")
        self._txt_description.setPlainText("")
        self._txt_homepage.setText("")
        self._txt_issue_tracker.setText("")

        self._set_icon_state("")

        self._rebuild_targets_table([])
        self._add_target_row()  # Add one clean row

    def _load_from_json(self, path: Path) -> None:
        """Parse configuration file and populate GUI forms and target grid rows."""
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)

        self._txt_mod_id.setText(data.get("mod_id", ""))
        self._txt_mod_name.setText(data.get("mod_name", ""))
        self._txt_mod_version.setText(data.get("mod_version", ""))
        self._txt_group.setText(data.get("group", ""))
        self._txt_authors.setText(data.get("authors", ""))
        self._txt_license.setText(data.get("license", ""))
        self._txt_description.setPlainText(data.get("description", ""))
        self._txt_homepage.setText(data.get("homepage", ""))
        self._txt_issue_tracker.setText(data.get("issue_tracker", ""))

        self._set_icon_state(data.get("icon", ""))

        raw_targets = data.get("targets", [])
        self._rebuild_targets_table(raw_targets)

    def _rebuild_targets_table(self, targets_list: list[dict]) -> None:
        """Instantiate targets in the table widget, populating template dropdowns defensively."""
        self._table.setRowCount(0)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Loader", "Template", "Branch", "MC Version", "Compatibility", "From", "Through"
        ])

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        # Get list of existing MODTEMPLATES directories to populate dropdown
        tpl_dir = _get_default_dir("MODTEMPLATES")
        available_templates = []
        if tpl_dir.is_dir():
            try:
                available_templates = sorted([c.name for c in tpl_dir.iterdir() if c.is_dir()])
            except Exception:
                pass

        for row_idx, target in enumerate(targets_list):
            self._table.insertRow(row_idx)
            self._setup_row(row_idx, target, available_templates)

    def _setup_row(self, row_idx: int, target: dict, available_templates: list[str]) -> None:
        """Helper to build all cell controls and widgets in a single table row."""
        self._table.blockSignals(True)

        # 1. Loader combo
        loader_combo = QComboBox()
        loader_combo.addItems(["fabric", "forge", "neoforge"])
        loader_val = target.get("loader", "fabric")
        if loader_val in ["fabric", "forge", "neoforge"]:
            loader_combo.setCurrentText(loader_val)
        self._table.setCellWidget(row_idx, 0, loader_combo)

        # 2. Template combo
        template_combo = QComboBox()
        t_val = target.get("template", "")
        items = list(available_templates)
        if t_val and t_val not in items:
            items.append(t_val)
        template_combo.addItems(items)
        if t_val:
            template_combo.setCurrentText(t_val)
        self._table.setCellWidget(row_idx, 1, template_combo)

        # 3. Branch
        self._table.setItem(row_idx, 2, QTableWidgetItem(target.get("branch", "")))

        # 4. MC Version
        mc_ver = target.get("minecraft_version", "")
        self._table.setItem(row_idx, 3, QTableWidgetItem(mc_ver))

        # 5. Compatibility combo
        compat_combo = QComboBox()
        compat_combo.addItems([
            "Exact patch version only",
            "Same minor version",
            "Inclusive custom range"
        ])

        # 6 & 7. From and Through items
        from_item = QTableWidgetItem("")
        through_item = QTableWidgetItem("")
        self._table.setItem(row_idx, 5, from_item)
        self._table.setItem(row_idx, 6, through_item)

        vrange = target.get("minecraft_version_range", "")
        compat_type, parsed_from, parsed_through = parse_version_range(vrange, mc_ver)
        compat_combo.setCurrentText(compat_type)
        if compat_type == "Inclusive custom range":
            from_item.setText(parsed_from)
            through_item.setText(parsed_through)

        self._table.setCellWidget(row_idx, 4, compat_combo)

        self._table.blockSignals(False)

        # Set enabled/disabled state of From and Through items initially
        self._update_row_fields_enabled_state(row_idx)

        # Connect signals
        loader_combo.currentTextChanged.connect(self._on_loader_changed)
        template_combo.currentTextChanged.connect(self._on_template_changed)
        compat_combo.currentTextChanged.connect(self._on_compatibility_changed)

    @Slot()
    def _add_target_row(self) -> None:
        """Insert a default target parameters row to the bottom of the table."""
        row_idx = self._table.rowCount()
        self._table.insertRow(row_idx)

        tpl_dir = _get_default_dir("MODTEMPLATES")
        available_templates = []
        if tpl_dir.is_dir():
            try:
                available_templates = sorted([c.name for c in tpl_dir.iterdir() if c.is_dir()])
            except Exception:
                pass

        default_target = {
            "loader": "fabric",
            "template": available_templates[0] if available_templates else "",
            "branch": "fabric-1.21",
            "minecraft_version": "1.21.0",
            "minecraft_version_range": "[1.21.0,1.21.1)"
        }

        if available_templates:
            inferred = infer_from_template(available_templates[0], tpl_dir)
            default_target["loader"] = inferred["loader"] or "fabric"
            default_target["template"] = available_templates[0]
            default_target["minecraft_version"] = inferred["minecraft_version"] or "1.21"
            default_target["branch"] = inferred["branch"] or f"{default_target['loader']}-{default_target['minecraft_version']}"
            default_target["minecraft_version_range"] = make_exact_patch_range(default_target["minecraft_version"])

        self._setup_row(row_idx, default_target, available_templates)

    def _get_widget_row(self, widget: QWidget) -> int:
        """Find the row index of a given child cell widget."""
        for r in range(self._table.rowCount()):
            for c in range(self._table.columnCount()):
                if self._table.cellWidget(r, c) is widget:
                    return r
        return -1

    def _update_row_fields_enabled_state(self, row: int) -> None:
        """Enable From/Through cells only when 'Inclusive custom range' is selected."""
        compat_combo = self._table.cellWidget(row, 4)
        if not isinstance(compat_combo, QComboBox):
            return
        is_inclusive = compat_combo.currentText() == "Inclusive custom range"

        from_item = self._table.item(row, 5)
        through_item = self._table.item(row, 6)

        for item in [from_item, through_item]:
            if not item:
                continue
            if is_inclusive:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(Qt.ItemFlag.ItemIsSelectable)

    def _update_row_defaults_for_loader(self, row: int) -> None:
        """Update target branch when loader changes."""
        loader_combo = self._table.cellWidget(row, 0)
        if not isinstance(loader_combo, QComboBox):
            return
        loader = loader_combo.currentText()

        self._table.blockSignals(True)
        mc_ver_item = self._table.item(row, 3)
        mc_ver = mc_ver_item.text().strip() if mc_ver_item else "1.21"

        branch_item = self._table.item(row, 2)
        if branch_item:
            branch_item.setText(f"{loader}-{mc_ver}")
        self._table.blockSignals(False)

    def _update_row_defaults_for_template(self, row: int) -> None:
        """Autofill defaults when a template is selected."""
        tpl_combo = self._table.cellWidget(row, 1)
        if not isinstance(tpl_combo, QComboBox):
            return
        tpl_name = tpl_combo.currentText()
        if not tpl_name:
            return

        tpl_dir = _get_default_dir("MODTEMPLATES")
        inferred = infer_from_template(tpl_name, tpl_dir)

        self._table.blockSignals(True)

        # Update loader combo
        loader_combo = self._table.cellWidget(row, 0)
        if isinstance(loader_combo, QComboBox) and inferred["loader"]:
            loader_combo.blockSignals(True)
            loader_combo.setCurrentText(inferred["loader"])
            loader_combo.blockSignals(False)

        # Update MC version
        mc_ver_item = self._table.item(row, 3)
        if mc_ver_item and inferred["minecraft_version"]:
            mc_ver_item.setText(inferred["minecraft_version"])

        # Update branch
        branch_item = self._table.item(row, 2)
        if branch_item and inferred["branch"]:
            branch_item.setText(inferred["branch"])

        self._table.blockSignals(False)

        self._update_row_fields_enabled_state(row)

    @Slot()
    def _on_loader_changed(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QComboBox):
            return
        row = self._get_widget_row(sender)
        if row != -1:
            self._update_row_defaults_for_loader(row)

    @Slot()
    def _on_template_changed(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QComboBox):
            return
        row = self._get_widget_row(sender)
        if row != -1:
            self._update_row_defaults_for_template(row)

    @Slot()
    def _on_compatibility_changed(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QComboBox):
            return
        row = self._get_widget_row(sender)
        if row != -1:
            self._update_row_fields_enabled_state(row)

    @Slot(QTableWidgetItem)
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        # Col 3 is MC Version
        if col == 3:
            loader_combo = self._table.cellWidget(row, 0)
            if isinstance(loader_combo, QComboBox):
                loader = loader_combo.currentText()
                mc_ver = item.text().strip()
                self._table.blockSignals(True)
                branch_item = self._table.item(row, 2)
                if branch_item:
                    branch_item.setText(f"{loader}-{mc_ver}")
                self._table.blockSignals(False)

    @Slot()
    def _remove_target_row(self) -> None:
        """Delete the currently highlighted target row, asking for confirmation if it is the only one."""
        selected_ranges = self._table.selectedRanges()
        if not selected_ranges:
            QMessageBox.warning(self, "Remove Target", "Please select a target row to remove.")
            return

        row = selected_ranges[0].topRow()
        if self._table.rowCount() <= 1:
            reply = QMessageBox.question(
                self,
                "Remove Last Target",
                "You are removing the only target. ModSmith requires at least one target to run. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self._table.removeRow(row)

    def _save_config_quiet(self) -> bool:
        """Gather GUI inputs, backup existing config, and write JSON to modsmith.json.

        Returns:
            True if successfully saved, False otherwise.
        """
        details_dir = _get_default_dir("WORKSPACE") / "DETAILS"
        json_path = details_dir / "modsmith.json"

        mod_id = self._txt_mod_id.text().strip()
        mod_name = self._txt_mod_name.text().strip()
        group = self._txt_group.text().strip()

        # Validate form inputs quickly in Python
        if not mod_id or not mod_name or not group:
            QMessageBox.critical(self, "Save Error", "Required fields Mod ID, Mod Name, and Group must not be empty.")
            return False

        # Derive PascalCase and packages
        main_class = derive_pascal_case(mod_name)
        package = group
        output_repo_name = derive_pascal_case(mod_name)

        # Prepare JSON dict following ModSmith schema exactly
        config_data = {
            "mod_id": mod_id,
            "mod_name": mod_name,
            "main_class": main_class,
            "mod_version": self._txt_mod_version.text().strip(),
            "group": group,
            "package": package,
            "authors": self._txt_authors.text().strip(),
            "license": self._txt_license.text().strip(),
            "description": self._txt_description.toPlainText().strip(),
            "homepage": self._txt_homepage.text().strip(),
            "issue_tracker": self._txt_issue_tracker.text().strip(),
            "output_repo_name": output_repo_name,
            "targets": []
        }

        # Include icon only when set (omit from JSON if cleared)
        if self._icon_value:
            config_data["icon"] = self._icon_value

        # Read targets list
        for r in range(self._table.rowCount()):
            loader_combo = self._table.cellWidget(r, 0)
            tpl_combo = self._table.cellWidget(r, 1)
            compat_combo = self._table.cellWidget(r, 4)

            loader = loader_combo.currentText() if isinstance(loader_combo, QComboBox) else ""
            template = tpl_combo.currentText() if isinstance(tpl_combo, QComboBox) else ""
            compat_type = compat_combo.currentText() if isinstance(compat_combo, QComboBox) else "Exact patch version only"

            branch = self._table.item(r, 2).text().strip() if self._table.item(r, 2) else ""
            mc_ver = self._table.item(r, 3).text().strip() if self._table.item(r, 3) else ""
            from_ver = self._table.item(r, 5).text().strip() if self._table.item(r, 5) else ""
            through_ver = self._table.item(r, 6).text().strip() if self._table.item(r, 6) else ""

            mc_range = derive_mc_range(mc_ver)

            if compat_type == "Exact patch version only":
                minecraft_version_range = make_exact_patch_range(mc_ver)
            elif compat_type == "Same minor version":
                minecraft_version_range = make_same_minor_range(mc_ver)
            else:  # Inclusive custom range
                minecraft_version_range = make_inclusive_range(from_ver, through_ver)

            config_data["targets"].append({
                "loader": loader,
                "template": template,
                "branch": branch,
                "mc_range": mc_range,
                "minecraft_version": mc_ver,
                "minecraft_version_range": minecraft_version_range
            })

        if not config_data["targets"]:
            QMessageBox.critical(self, "Save Error", "Workspace requires at least one target.")
            return False

        # 1. Automatic backup creation (.bak) before overwrite
        if json_path.exists():
            bak_path = json_path.with_suffix(".json.bak")
            try:
                bak_path.write_bytes(json_path.read_bytes())
                self._log_panel.append_line(f"Created config backup at: {bak_path.name}")
            except Exception as exc:
                self._log_panel.append_line(f"[WARNING] Backup failed: {exc}")

        # 2. Serialize pretty-printed JSON with indent=2 in UTF-8
        try:
            details_dir.mkdir(parents=True, exist_ok=True)
            json_text = json.dumps(config_data, indent=2) + "\n"
            json_path.write_text(json_text, encoding="utf-8")
            self._log_panel.append_line(f"Saved modsmith.json successfully to {json_path.name}")
            return True
        except Exception as exc:
            self._log_panel.append_line(f"Failed to write modsmith.json: {exc}")
            QMessageBox.critical(self, "Save Config", f"Failed to save configuration:\n{exc}")
            return False

    @Slot()
    def _save_config(self) -> None:
        """Gather GUI inputs, backup existing config, and write JSON to modsmith.json."""
        if self._save_config_quiet():
            json_path = _get_default_dir("WORKSPACE") / "DETAILS" / "modsmith.json"
            QMessageBox.information(self, "Save Config", f"Saved configuration successfully to:\n{json_path}")

    @Slot()
    def _validate_config(self) -> None:
        """Call the backend's validate logic to scan config for structural errors."""
        json_path = _get_default_dir("WORKSPACE") / "DETAILS" / "modsmith.json"

        self._log_panel.append_line("")
        self._log_panel.append_line("=== Validating Workspace Config ===")

        # Quietly save first so validation runs on current input data!
        if not self._save_config_quiet():
            self._log_panel.append_line("Error: Failed to save the config data. Cannot validate.")
            return

        try:
            load_mod_config(json_path)
            self._log_panel.append_line("✓ Workspace modsmith.json structure is valid and verified.")
            QMessageBox.information(self, "Validate Config", "Workspace config is fully valid!")
        except ConfigError as exc:
            self._log_panel.append_line(f"❌ Configuration error:\n{exc}")
            QMessageBox.critical(self, "Validate Config", f"Validation failed:\n{exc}")

    @Slot()
    def _open_details_folder(self) -> None:
        """Safely open the active details directory in Explorer."""
        details_dir = _get_default_dir("WORKSPACE") / "DETAILS"
        if not details_dir.is_dir():
            QMessageBox.warning(self, "Open Folder", f"Folder does not exist:\n{details_dir}")
            return

        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(details_dir)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(details_dir)])
            else:
                subprocess.Popen(["xdg-open", str(details_dir)])
        except OSError as exc:
            QMessageBox.critical(self, "Open Folder", f"Failed to open directory:\n{exc}")

    @Slot()
    def _validate_inputs(self) -> None:
        """Real-time warning highlight if Mod ID is malformed."""
        mod_id = self._txt_mod_id.text().strip()

        from modsmith.utils import is_valid_mod_id

        # Validate mod ID (letters/digits/underscores only)
        if mod_id and not is_valid_mod_id(mod_id):
            self._txt_mod_id.setStyleSheet("border: 1px solid #b00; background-color: #fce8e6;")
        else:
            self._txt_mod_id.setStyleSheet("")

    # ------------------------------------------------------------------
    # Mod Icon helpers
    # ------------------------------------------------------------------

    def _set_icon_state(self, icon_path: str) -> None:
        """Update icon UI state and internal value.

        Args:
            icon_path: Relative path like ``"ASSETS/icon.png"`` or ``""``.
        """
        # Normalize to forward slashes
        self._icon_value = icon_path.replace("\\", "/") if icon_path else ""

        if self._icon_value:
            self._icon_path_label.setText(self._icon_value)

            # Try to load thumbnail
            abs_path = _get_default_dir("WORKSPACE") / self._icon_value.replace("/", os.sep)
            if abs_path.is_file():
                pixmap = QPixmap(str(abs_path))
                if not pixmap.isNull():
                    self._icon_thumbnail.setPixmap(
                        pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                    )
                else:
                    self._icon_thumbnail.setText("(err)")
            else:
                self._icon_thumbnail.setText("(miss)")
        else:
            self._icon_path_label.setText("No icon selected")
            self._icon_thumbnail.clear()
            self._icon_thumbnail.setText("No icon")

    @Slot()
    def _select_icon(self) -> None:
        """Let user pick an image file, copy it to WORKSPACE/ASSETS, store the reference."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Mod Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp);;All Files (*)",
        )
        if not file_path:
            return

        src = Path(file_path)
        assets_dir = _get_default_dir("WORKSPACE") / "ASSETS"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Warn if not PNG for mod icon injection
        if src.suffix.lower() != ".png":
            QMessageBox.warning(
                self,
                "Icon Format",
                "PNG is recommended for mod icons.\n\n"
                "Non-PNG icons will be stored and previewed, but only PNG "
                "icons are injected into generated mod projects.",
            )

        # Copy to ASSETS (auto-suffix if exists)
        try:
            from modsmith_gui.assets_utils import safe_copy_to_assets
            dest = safe_copy_to_assets(src, assets_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Select Icon", f"Failed to copy icon:\n{exc}")
            return

        # Store relative path with forward slashes
        relative = f"ASSETS/{dest.name}"
        self._set_icon_state(relative)
        self._log_panel.append_line(f"Mod icon set: {relative}")

    @Slot()
    def _clear_icon(self) -> None:
        """Remove the mod icon selection."""
        self._set_icon_state("")
        self._log_panel.append_line("Mod icon cleared.")
