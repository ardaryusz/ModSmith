"""Workspace screen — edit modsmith.json configuration with form fields and targets table."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QPlainTextEdit, QComboBox,
    QMessageBox, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Slot

from modsmith.config import load_mod_config, ConfigError
from modsmith_gui.widgets.log_panel import LogPanel


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

        self._txt_main_class = QLineEdit()
        self._txt_main_class.setPlaceholderText("e.g. EasyPeasyGunpowder (defaults to derived name)")
        self._txt_main_class.textChanged.connect(self._validate_inputs)

        self._txt_mod_version = QLineEdit()
        self._txt_mod_version.setPlaceholderText("e.g. 1.0.0")

        self._txt_group = QLineEdit()
        self._txt_group.setPlaceholderText("e.g. com.example")

        self._txt_package = QLineEdit()
        self._txt_package.setPlaceholderText("e.g. com.example.easypeasygunpowder")
        self._txt_package.textChanged.connect(self._validate_inputs)

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

        self._txt_output_repo_name = QLineEdit()
        self._txt_output_repo_name.setPlaceholderText("e.g. EasyPeasyGunpowder")

        details_form.addRow("Mod ID:", self._txt_mod_id)
        details_form.addRow("Mod Name:", self._txt_mod_name)
        details_form.addRow("Main Class:", self._txt_main_class)
        details_form.addRow("Mod Version:", self._txt_mod_version)
        details_form.addRow("Group:", self._txt_group)
        details_form.addRow("Package:", self._txt_package)
        details_form.addRow("Authors:", self._txt_authors)
        details_form.addRow("License:", self._txt_license)
        details_form.addRow("Description:", self._txt_description)
        details_form.addRow("Homepage:", self._txt_homepage)
        details_form.addRow("Issue Tracker:", self._txt_issue_tracker)
        details_form.addRow("Output Repo Name:", self._txt_output_repo_name)

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
        targets_layout.addWidget(self._table)

        layout.addWidget(targets_group)

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
        self._txt_main_class.setText("")
        self._txt_mod_version.setText("1.0.0")
        self._txt_group.setText("com.example")
        self._txt_package.setText("")
        self._txt_authors.setText("")
        self._txt_license.setText("MIT")
        self._txt_description.setPlainText("")
        self._txt_homepage.setText("")
        self._txt_issue_tracker.setText("")
        self._txt_output_repo_name.setText("")

        self._rebuild_targets_table([])
        self._add_target_row()  # Add one clean row

    def _load_from_json(self, path: Path) -> None:
        """Parse configuration file and populate GUI forms and target grid rows."""
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)

        self._txt_mod_id.setText(data.get("mod_id", ""))
        self._txt_mod_name.setText(data.get("mod_name", ""))
        self._txt_main_class.setText(data.get("main_class", ""))
        self._txt_mod_version.setText(data.get("mod_version", ""))
        self._txt_group.setText(data.get("group", ""))
        self._txt_package.setText(data.get("package", ""))
        self._txt_authors.setText(data.get("authors", ""))
        self._txt_license.setText(data.get("license", ""))
        self._txt_description.setPlainText(data.get("description", ""))
        self._txt_homepage.setText(data.get("homepage", ""))
        self._txt_issue_tracker.setText(data.get("issue_tracker", ""))
        self._txt_output_repo_name.setText(data.get("output_repo_name", ""))

        raw_targets = data.get("targets", [])
        self._rebuild_targets_table(raw_targets)

    def _rebuild_targets_table(self, targets_list: list[dict]) -> None:
        """Instantiate targets in the table widget, populating template dropdowns defensively."""
        self._table.setRowCount(0)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Loader", "Template", "Branch", "MC Range", "MC Version", "MC Version Range"
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
            # Ensure the selected value exists in the dropdown list even if it is not a valid folder on disk
            items = list(available_templates)
            if t_val and t_val not in items:
                items.append(t_val)
            template_combo.addItems(items)
            if t_val:
                template_combo.setCurrentText(t_val)
            self._table.setCellWidget(row_idx, 1, template_combo)

            # 3. Branch
            self._table.setItem(row_idx, 2, QTableWidgetItem(target.get("branch", "")))
            # 4. MC Range
            self._table.setItem(row_idx, 3, QTableWidgetItem(target.get("mc_range", "")))
            # 5. MC Version
            self._table.setItem(row_idx, 4, QTableWidgetItem(target.get("minecraft_version", "")))
            # 6. MC Version Range
            self._table.setItem(row_idx, 5, QTableWidgetItem(target.get("minecraft_version_range", "")))

            # Wire combo events to default update helpers
            loader_combo.currentTextChanged.connect(
                lambda _, r=row_idx: self._update_row_defaults(r)
            )

    @Slot()
    def _add_target_row(self) -> None:
        """Insert a default target parameters row to the bottom of the table."""
        row_idx = self._table.rowCount()
        self._table.insertRow(row_idx)

        # 1. Loader combo
        loader_combo = QComboBox()
        loader_combo.addItems(["fabric", "forge", "neoforge"])
        self._table.setCellWidget(row_idx, 0, loader_combo)

        # 2. Template combo populated defensively
        tpl_dir = _get_default_dir("MODTEMPLATES")
        available_templates = []
        if tpl_dir.is_dir():
            try:
                available_templates = sorted([c.name for c in tpl_dir.iterdir() if c.is_dir()])
            except Exception:
                pass
        template_combo = QComboBox()
        template_combo.addItems(available_templates)
        self._table.setCellWidget(row_idx, 1, template_combo)

        # 3. Basic default editable items
        self._table.setItem(row_idx, 2, QTableWidgetItem("fabric-1.21"))
        self._table.setItem(row_idx, 3, QTableWidgetItem("1.21"))
        self._table.setItem(row_idx, 4, QTableWidgetItem("1.21.0"))
        self._table.setItem(row_idx, 5, QTableWidgetItem("[1.21,1.22)"))

        loader_combo.currentTextChanged.connect(
            lambda _, r=row_idx: self._update_row_defaults(r)
        )

    def _update_row_defaults(self, row: int) -> None:
        """Autofill row defaults based on loader changes if the user hasn't explicitly edited them."""
        loader_combo = self._table.cellWidget(row, 0)
        if not isinstance(loader_combo, QComboBox):
            return
        loader = loader_combo.currentText()

        # Update branch defaults dynamically e.g. forge-1.20.1
        mc_ver_item = self._table.item(row, 4)
        mc_ver = mc_ver_item.text() if mc_ver_item else "1.21"

        branch_item = self._table.item(row, 2)
        if branch_item:
            branch_item.setText(f"{loader}-{mc_ver}")

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

    @Slot()
    def _save_config(self) -> None:
        """Gather GUI inputs, backup existing config, and write JSON to modsmith.json."""
        details_dir = _get_default_dir("WORKSPACE") / "DETAILS"
        json_path = details_dir / "modsmith.json"

        # Prepare JSON dict following ModSmith schema exactly
        config_data = {
            "mod_id": self._txt_mod_id.text().strip(),
            "mod_name": self._txt_mod_name.text().strip(),
            "main_class": self._txt_main_class.text().strip(),
            "mod_version": self._txt_mod_version.text().strip(),
            "group": self._txt_group.text().strip(),
            "package": self._txt_package.text().strip(),
            "authors": self._txt_authors.text().strip(),
            "license": self._txt_license.text().strip(),
            "description": self._txt_description.toPlainText().strip(),
            "homepage": self._txt_homepage.text().strip(),
            "issue_tracker": self._txt_issue_tracker.text().strip(),
            "output_repo_name": self._txt_output_repo_name.text().strip(),
            "targets": []
        }

        # Read targets list
        for r in range(self._table.rowCount()):
            loader_combo = self._table.cellWidget(r, 0)
            tpl_combo = self._table.cellWidget(r, 1)

            loader = loader_combo.currentText() if isinstance(loader_combo, QComboBox) else ""
            template = tpl_combo.currentText() if isinstance(tpl_combo, QComboBox) else ""

            branch = self._table.item(r, 2).text().strip() if self._table.item(r, 2) else ""
            mc_range = self._table.item(r, 3).text().strip() if self._table.item(r, 3) else ""
            mc_ver = self._table.item(r, 4).text().strip() if self._table.item(r, 4) else ""
            mc_ver_range = self._table.item(r, 5).text().strip() if self._table.item(r, 5) else ""

            config_data["targets"].append({
                "loader": loader,
                "template": template,
                "branch": branch,
                "mc_range": mc_range,
                "minecraft_version": mc_ver,
                "minecraft_version_range": mc_ver_range
            })

        # Validate form inputs quickly in Python
        if not config_data["mod_id"] or not config_data["mod_name"] or not config_data["package"]:
            QMessageBox.critical(self, "Save Error", "Required fields Mod ID, Mod Name, and Package must not be empty.")
            return

        if not config_data["targets"]:
            QMessageBox.critical(self, "Save Error", "Workspace requires at least one target.")
            return

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
            QMessageBox.information(self, "Save Config", f"Saved configuration successfully to:\n{json_path}")
        except Exception as exc:
            self._log_panel.append_line(f"Failed to write modsmith.json: {exc}")
            QMessageBox.critical(self, "Save Config", f"Failed to save configuration:\n{exc}")

    @Slot()
    def _validate_config(self) -> None:
        """Call the backend's validate logic to scan config for structural errors."""
        json_path = _get_default_dir("WORKSPACE") / "DETAILS" / "modsmith.json"

        self._log_panel.append_line("")
        self._log_panel.append_line("=== Validating Workspace Config ===")
        if not json_path.exists():
            self._log_panel.append_line("Error: modsmith.json not found on disk. Please save the config first!")
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
        """Real-time warning highlight if Mod ID, Package, or Main Class are malformed."""
        mod_id = self._txt_mod_id.text().strip()
        package = self._txt_package.text().strip()
        main_class = self._txt_main_class.text().strip()

        from modsmith.utils import is_valid_mod_id, is_valid_java_package, is_valid_java_identifier

        # Validate mod ID (letters/digits/underscores only)
        if mod_id and not is_valid_mod_id(mod_id):
            self._txt_mod_id.setStyleSheet("border: 1px solid #b00; background-color: #fce8e6;")
        else:
            self._txt_mod_id.setStyleSheet("")

        # Validate java package
        if package and not is_valid_java_package(package):
            self._txt_package.setStyleSheet("border: 1px solid #b00; background-color: #fce8e6;")
        else:
            self._txt_package.setStyleSheet("")

        # Validate main class
        if main_class and not is_valid_java_identifier(main_class):
            self._txt_main_class.setStyleSheet("border: 1px solid #b00; background-color: #fce8e6;")
        else:
            self._txt_main_class.setStyleSheet("")
