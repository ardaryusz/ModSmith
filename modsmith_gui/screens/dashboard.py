"""Dashboard screen — system overview and doctor launcher.

Shows:
 - ModSmith version
 - MODSMITH_HOME (effective value or 'unset')
 - Resolved workspace / templates / mods paths
 - Latest DIST JARs (if any)
 - Run Doctor button (disabled while running)
 - Doctor result summary badge

The LogPanel is hosted by the main window and passed in so that
doctor output appears in the shared log area at the bottom.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QFormLayout,
    QSizePolicy, QLineEdit,
)
from PySide6.QtCore import Qt, Slot

from modsmith import __version__
from modsmith_gui.widgets.status_badge import StatusBadge
from modsmith_gui.widgets.log_panel import LogPanel
from modsmith_gui.workers import DoctorWorker


def _get_default_dir(subdir: str) -> Path:
    """Mirror cli._get_default_dir — resolves paths under MODSMITH_HOME."""
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


class DashboardScreen(QWidget):
    """Main dashboard / overview screen."""

    def __init__(self, log_panel: LogPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_panel = log_panel
        self._doctor_worker: DoctorWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)

        # --- Environment info group ---
        env_group = QGroupBox("Environment")
        env_form = QFormLayout(env_group)
        env_form.setContentsMargins(10, 8, 10, 8)
        env_form.setSpacing(6)
        env_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._lbl_version = QLabel()
        self._lbl_home = QLineEdit()
        self._lbl_home.setReadOnly(True)
        self._lbl_workspace = QLineEdit()
        self._lbl_workspace.setReadOnly(True)
        self._lbl_templates = QLineEdit()
        self._lbl_templates.setReadOnly(True)
        self._lbl_mods = QLineEdit()
        self._lbl_mods.setReadOnly(True)

        env_form.addRow("ModSmith version:", self._lbl_version)
        env_form.addRow("MODSMITH_HOME:", self._lbl_home)
        env_form.addRow("Workspace:", self._lbl_workspace)
        env_form.addRow("Templates:", self._lbl_templates)
        env_form.addRow("Mods:", self._lbl_mods)

        root.addWidget(env_group)

        # --- Workbench summary group ---
        summary_group = QGroupBox("Workbench Summary")
        summary_form = QFormLayout(summary_group)
        summary_form.setContentsMargins(10, 8, 10, 8)
        summary_form.setSpacing(6)
        summary_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._lbl_summary_templates = QLabel("—")
        self._lbl_summary_recipes = QLabel("—")
        self._lbl_summary_config = QLabel("—")
        self._lbl_summary_readme = QLabel("—")
        self._lbl_summary_assets = QLabel("—")
        self._lbl_summary_icon = QLabel("—")

        summary_form.addRow("Templates:", self._lbl_summary_templates)
        summary_form.addRow("Recipes:", self._lbl_summary_recipes)
        summary_form.addRow("modsmith.json:", self._lbl_summary_config)
        summary_form.addRow("README.md:", self._lbl_summary_readme)
        summary_form.addRow("Assets:", self._lbl_summary_assets)
        summary_form.addRow("Mod Icon:", self._lbl_summary_icon)

        root.addWidget(summary_group)

        # --- DIST JARs group ---
        dist_group = QGroupBox("Latest DIST JARs")
        dist_layout = QVBoxLayout(dist_group)
        dist_layout.setContentsMargins(10, 8, 10, 8)
        self._lbl_dist = QLabel("—")
        self._lbl_dist.setWordWrap(True)
        self._lbl_dist.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        dist_layout.addWidget(self._lbl_dist)
        root.addWidget(dist_group)

        # --- Doctor section ---
        doctor_group = QGroupBox("Doctor")
        doctor_vbox = QVBoxLayout(doctor_group)
        doctor_vbox.setContentsMargins(10, 8, 10, 8)
        doctor_vbox.setSpacing(8)

        # Status badge + button on one row
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._btn_doctor = QPushButton("Run Doctor")
        self._btn_doctor.setFixedWidth(110)
        self._btn_doctor.clicked.connect(self._run_doctor)

        self._doctor_badge = StatusBadge()
        self._doctor_badge.set_neutral("Not run yet")

        action_row.addWidget(self._btn_doctor)
        action_row.addWidget(self._doctor_badge)
        action_row.addStretch()

        doctor_vbox.addLayout(action_row)
        root.addWidget(doctor_group)

        root.addStretch()

        # Populate on first show
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read environment state and update all labels."""
        self._lbl_version.setText(__version__)

        home = os.environ.get("MODSMITH_HOME")
        if home:
            self._lbl_home.setText(home)
            self._lbl_home.setStyleSheet("color: inherit;")
        else:
            self._lbl_home.setText("(unset — using relative defaults)")
            self._lbl_home.setStyleSheet("color: #b87800;")  # amber

        ws = _get_default_dir("WORKSPACE")
        tpl = _get_default_dir("MODTEMPLATES")
        mods = _get_default_dir("MODS")

        self._lbl_workspace.setText(str(ws))
        self._lbl_templates.setText(str(tpl))
        self._lbl_mods.setText(str(mods))

        # Recompute Workbench Summary defensively
        self._refresh_summary(tpl, ws)

        self._refresh_dist(ws)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_summary(self, tpl_dir: Path, workspace_dir: Path) -> None:
        """Scan and display templates and recipes summaries defensively."""
        # 1. Templates summary
        if not tpl_dir.exists():
            self._lbl_summary_templates.setText("Folder missing")
            self._lbl_summary_templates.setStyleSheet("color: #b00; font-weight: bold;")
        else:
            try:
                from modsmith.template_listing import list_templates
                result = list_templates(tpl_dir)
                t_count = len(result.templates)
                t_err = len(result.errors)
                t_warn = len(result.warnings)

                if t_count == 0:
                    text = "0 templates found (empty folder)"
                    color = "#b87800"  # amber
                elif t_err > 0:
                    text = f"{t_count} templates ({t_err} error(s), {t_warn} warning(s))"
                    color = "#b00"  # red
                elif t_warn > 0:
                    text = f"{t_count} templates ({t_warn} warning(s))"
                    color = "#b87800"  # amber
                else:
                    text = f"{t_count} templates (OK)"
                    color = "#060"  # green

                self._lbl_summary_templates.setText(text)
                self._lbl_summary_templates.setStyleSheet(f"color: {color}; font-weight: bold;")
            except Exception as exc:
                self._lbl_summary_templates.setText(f"Scan failed: {exc}")
                self._lbl_summary_templates.setStyleSheet("color: #b00; font-weight: bold;")

        # 2. Recipes summary
        recipes_dir = workspace_dir / "RECIPES"
        if not recipes_dir.exists():
            self._lbl_summary_recipes.setText("Folder missing")
            self._lbl_summary_recipes.setStyleSheet("color: #b00; font-weight: bold;")
        else:
            try:
                recipe_files = list(recipes_dir.glob("*.json"))
                r_count = len(recipe_files)

                if r_count == 0:
                    text = "0 recipes found (empty folder)"
                    color = "#b87800"
                else:
                    r_err = 0
                    for r_file in recipe_files:
                        try:
                            text_data = r_file.read_text(encoding="utf-8")
                            json.loads(text_data)
                        except Exception:
                            r_err += 1

                    if r_err > 0:
                        text = f"{r_count} recipes ({r_err} invalid JSON file(s))"
                        color = "#b00"
                    else:
                        text = f"{r_count} recipes (OK)"
                        color = "#060"

                self._lbl_summary_recipes.setText(text)
                self._lbl_summary_recipes.setStyleSheet(f"color: {color}; font-weight: bold;")
            except Exception as exc:
                self._lbl_summary_recipes.setText(f"Scan failed: {exc}")
                self._lbl_summary_recipes.setStyleSheet("color: #b00; font-weight: bold;")

        # 3. Config (modsmith.json) summary
        config_path = workspace_dir / "DETAILS" / "modsmith.json"
        if not config_path.exists():
            self._lbl_summary_config.setText("Missing modsmith.json")
            self._lbl_summary_config.setStyleSheet("color: #b00; font-weight: bold;")
        else:
            try:
                from modsmith.config import load_mod_config
                cfg = load_mod_config(config_path)
                t_count = len(cfg.targets)
                self._lbl_summary_config.setText(f"Exists ({t_count} target(s) defined)")
                self._lbl_summary_config.setStyleSheet("color: #060; font-weight: bold;")
            except Exception as exc:
                self._lbl_summary_config.setText(f"Exists (invalid config: {exc})")
                self._lbl_summary_config.setStyleSheet("color: #b00; font-weight: bold;")

        # 4. README summary
        readme_path = workspace_dir / "README" / "README.md"
        if not readme_path.exists():
            self._lbl_summary_readme.setText("Missing README.md")
            self._lbl_summary_readme.setStyleSheet("color: #b87800; font-weight: bold;")
        else:
            self._lbl_summary_readme.setText("Exists")
            self._lbl_summary_readme.setStyleSheet("color: #060; font-weight: bold;")

        # 5. Assets folder summary
        assets_dir = workspace_dir / "ASSETS"
        if assets_dir.is_dir():
            try:
                asset_count = sum(1 for f in assets_dir.iterdir() if f.is_file())
                self._lbl_summary_assets.setText(f"Exists ({asset_count} file(s))")
                self._lbl_summary_assets.setStyleSheet("color: #060; font-weight: bold;")
            except Exception:
                self._lbl_summary_assets.setText("Exists")
                self._lbl_summary_assets.setStyleSheet("color: #060; font-weight: bold;")
        else:
            self._lbl_summary_assets.setText("Folder missing (optional)")
            self._lbl_summary_assets.setStyleSheet("color: #b87800; font-weight: bold;")

        # 6. Mod icon summary
        config_path_icon = workspace_dir / "DETAILS" / "modsmith.json"
        icon_text = "None selected"
        icon_color = "#888"
        try:
            if config_path_icon.exists():
                data = json.loads(config_path_icon.read_text(encoding="utf-8"))
                icon_val = data.get("icon", "")
                if icon_val:
                    icon_text = f"Selected: {icon_val}"
                    # Check if the file actually exists
                    icon_abs = workspace_dir / icon_val.replace("/", os.sep)
                    if icon_abs.is_file():
                        icon_color = "#060"
                    else:
                        icon_text += " (file missing)"
                        icon_color = "#b87800"
        except Exception:
            pass
        self._lbl_summary_icon.setText(icon_text)
        self._lbl_summary_icon.setStyleSheet(f"color: {icon_color}; font-weight: bold;")

    def _refresh_dist(self, workspace_dir: Path) -> None:
        dist_dir = workspace_dir / "DIST"
        if not dist_dir.is_dir():
            self._lbl_dist.setText("DIST folder not found")
            return
        jars = sorted(dist_dir.glob("*.jar"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not jars:
            self._lbl_dist.setText("No JARs found in DIST")
            return
        lines = [f"• {j.name}" for j in jars[:10]]
        if len(jars) > 10:
            lines.append(f"  … and {len(jars) - 10} more")
        self._lbl_dist.setText("\n".join(lines))

    @Slot()
    def _run_doctor(self) -> None:
        """Launch the DoctorWorker in the background."""
        if self._doctor_worker is not None and self._doctor_worker.isRunning():
            return  # already running — button should be disabled anyway

        self._btn_doctor.setEnabled(False)
        self._doctor_badge.set_neutral("Running…")
        self._log_panel.append_line("")
        self._log_panel.append_line("=== Doctor started ===")

        ws = _get_default_dir("WORKSPACE")
        tpl = _get_default_dir("MODTEMPLATES")
        mods = _get_default_dir("MODS")

        self._doctor_worker = DoctorWorker(
            workspace_dir=ws,
            templates_dir=tpl,
            mods_dir=mods,
            parent=self,
        )
        self._doctor_worker.log_line.connect(self._log_panel.append_line)
        self._doctor_worker.finished.connect(self._on_doctor_finished)
        self._doctor_worker.start()

    @Slot(bool, str)
    def _on_doctor_finished(self, success: bool, summary: str) -> None:
        self._log_panel.append_line(f"=== {summary} ===")
        self._btn_doctor.setEnabled(True)
        if success:
            self._doctor_badge.set_ok(summary)
        else:
            self._doctor_badge.set_error(summary)
        # Clean up worker reference (it has already finished)
        self._doctor_worker = None
