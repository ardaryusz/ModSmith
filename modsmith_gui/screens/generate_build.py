"""Generate & Build screen — drive the full ModSmith workflow from the GUI.

Actions available:
  Validate            — run validate_workspace and show errors/warnings
  Generate            — run generate (normal mode)
  Generate --force    — run generate with force=True (with confirmation)
  Build               — run Gradle build on all generated branches
  Clean               — delete the generated output repo (with confirmation)
  Open MODS Folder    — open MODS/ in the system file manager
  Open DIST Folder    — open WORKSPACE/DIST/ in the system file manager

All long-running operations run in QThread workers so the UI stays responsive.
Only one worker may run at a time; all buttons are disabled while busy.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox,
    QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt, Slot

from modsmith_gui.widgets.log_panel import LogPanel
from modsmith_gui.widgets.status_badge import StatusBadge
from modsmith_gui.workers import (
    ValidateWorker,
    GenerateWorker,
    BuildWorker,
    CleanWorker,
)


# ---------------------------------------------------------------------------
# Path helpers (mirrors cli._get_default_dir logic)
# ---------------------------------------------------------------------------


def _resolve_dir(subdir: str) -> Path:
    """Resolve a path relative to MODSMITH_HOME (or cwd if unset)."""
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


def _open_folder(path: Path, log_panel: LogPanel) -> None:
    """Open *path* in the system file manager.  Logs a warning if not found."""
    if not path.exists():
        log_panel.append_line(
            f"[WARN]  Folder does not exist yet: {path}"
        )
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        log_panel.append_line(f"[ERROR] Could not open folder {path}: {exc}")


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class GenerateBuildScreen(QWidget):
    """Generate & Build workflow screen."""

    def __init__(self, log_panel: LogPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_panel = log_panel
        self._worker: ValidateWorker | GenerateWorker | BuildWorker | CleanWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # Title
        title = QLabel("Generate & Build")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        root.addWidget(title)

        subtitle = QLabel(
            "Run the ModSmith workflow: validate your workspace, generate the mod "
            "repository, build with Gradle, or clean up the output."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #555; font-size: 12px;")
        root.addWidget(subtitle)

        # Status row — badge (dot + text) left-aligned, stretch fills the rest
        status_row = QHBoxLayout()
        status_row.setSpacing(0)
        self._status_badge = StatusBadge()
        status_row.addWidget(self._status_badge)
        status_row.addStretch()
        root.addLayout(status_row)

        # ------------------------------------------------------------------
        # Validation group
        # ------------------------------------------------------------------
        val_group = QGroupBox("Validation")
        val_layout = QHBoxLayout(val_group)
        val_layout.setSpacing(8)

        self._btn_validate = QPushButton("Validate")
        self._btn_validate.setMinimumWidth(120)
        self._btn_validate.setToolTip(
            "Run validate_workspace to check for configuration and recipe errors."
        )
        self._btn_validate.clicked.connect(self._on_validate)
        val_layout.addWidget(self._btn_validate)
        val_layout.addStretch()
        root.addWidget(val_group)

        # ------------------------------------------------------------------
        # Generation group
        # ------------------------------------------------------------------
        gen_group = QGroupBox("Generation")
        gen_layout = QHBoxLayout(gen_group)
        gen_layout.setSpacing(8)

        self._btn_generate = QPushButton("Generate")
        self._btn_generate.setMinimumWidth(120)
        self._btn_generate.setToolTip(
            "Generate the mod repository (normal mode). Fails if the output repo "
            "already exists — use Generate --force to overwrite."
        )
        self._btn_generate.clicked.connect(self._on_generate)
        gen_layout.addWidget(self._btn_generate)

        self._btn_generate_force = QPushButton("Generate --force")
        self._btn_generate_force.setMinimumWidth(140)
        self._btn_generate_force.setToolTip(
            "Delete any existing output repo and regenerate from scratch. "
            "You will be asked to confirm before proceeding."
        )
        self._btn_generate_force.clicked.connect(self._on_generate_force)
        gen_layout.addWidget(self._btn_generate_force)
        gen_layout.addStretch()
        root.addWidget(gen_group)

        # ------------------------------------------------------------------
        # Build group
        # ------------------------------------------------------------------
        build_group = QGroupBox("Build")
        build_layout = QHBoxLayout(build_group)
        build_layout.setSpacing(8)

        self._btn_build = QPushButton("Build")
        self._btn_build.setMinimumWidth(120)
        self._btn_build.setToolTip(
            "Build all generated branches with Gradle. Requires Java and the "
            "generated repository to exist."
        )
        self._btn_build.clicked.connect(self._on_build)
        build_layout.addWidget(self._btn_build)
        build_layout.addStretch()
        root.addWidget(build_group)

        # ------------------------------------------------------------------
        # Clean group
        # ------------------------------------------------------------------
        clean_group = QGroupBox("Clean")
        clean_layout = QHBoxLayout(clean_group)
        clean_layout.setSpacing(8)

        self._btn_clean = QPushButton("Clean")
        self._btn_clean.setMinimumWidth(120)
        self._btn_clean.setToolTip(
            "Delete the generated output repository in MODS/. "
            "You will be asked to confirm before anything is deleted."
        )
        self._btn_clean.clicked.connect(self._on_clean)
        clean_layout.addWidget(self._btn_clean)
        clean_layout.addStretch()
        root.addWidget(clean_group)

        # ------------------------------------------------------------------
        # Folder shortcuts group
        # ------------------------------------------------------------------
        folder_group = QGroupBox("Open Folders")
        folder_layout = QHBoxLayout(folder_group)
        folder_layout.setSpacing(8)

        self._btn_open_mods = QPushButton("Open MODS Folder")
        self._btn_open_mods.setMinimumWidth(140)
        self._btn_open_mods.setToolTip("Open the MODS/ directory in your file manager.")
        self._btn_open_mods.clicked.connect(self._on_open_mods)
        folder_layout.addWidget(self._btn_open_mods)

        self._btn_open_dist = QPushButton("Open DIST Folder")
        self._btn_open_dist.setMinimumWidth(140)
        self._btn_open_dist.setToolTip(
            "Open the WORKSPACE/DIST/ directory in your file manager."
        )
        self._btn_open_dist.clicked.connect(self._on_open_dist)
        folder_layout.addWidget(self._btn_open_dist)
        folder_layout.addStretch()
        root.addWidget(folder_group)

        root.addStretch()

        # Initial idle state
        self._set_idle(ok=True, message="Ready")

    # ------------------------------------------------------------------
    # Path resolution helpers
    # ------------------------------------------------------------------

    def _workspace_dir(self) -> Path:
        return _resolve_dir("WORKSPACE")

    def _templates_dir(self) -> Path:
        return _resolve_dir("MODTEMPLATES")

    def _mods_dir(self) -> Path:
        return _resolve_dir("MODS")

    # ------------------------------------------------------------------
    # UI state helpers
    # ------------------------------------------------------------------

    @property
    def _action_buttons(self) -> list[QPushButton]:
        return [
            self._btn_validate,
            self._btn_generate,
            self._btn_generate_force,
            self._btn_build,
            self._btn_clean,
        ]

    def _set_busy(self, message: str) -> None:
        """Disable all action buttons and show a busy status."""
        for btn in self._action_buttons:
            btn.setEnabled(False)
        self._status_badge.set_neutral(message)

    def _set_idle(self, *, ok: bool, message: str) -> None:
        """Re-enable all action buttons and set status badge."""
        for btn in self._action_buttons:
            btn.setEnabled(True)
        if ok:
            self._status_badge.set_ok(message)
        else:
            self._status_badge.set_error(message)

    # ------------------------------------------------------------------
    # Worker wiring
    # ------------------------------------------------------------------

    def _wire_worker(self, worker: ValidateWorker | GenerateWorker | BuildWorker | CleanWorker) -> None:
        """Connect common signals and store reference so GC doesn't kill it."""
        worker.log_line.connect(self._log_panel.append_line)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker

    @Slot(bool, str)
    def _on_worker_finished(self, success: bool, summary: str) -> None:
        self._log_panel.append_line(
            f"[INFO]  {'✓' if success else '✗'} {summary}"
        )
        self._set_idle(ok=success, message=summary)
        self._worker = None

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    @Slot()
    def _on_validate(self) -> None:
        """Start a ValidateWorker."""
        self._log_panel.append_line("[INFO]  — Validate ———————————————————————")
        self._set_busy("Validating…")
        worker = ValidateWorker(
            workspace_dir=self._workspace_dir(),
            templates_dir=self._templates_dir(),
            mods_dir=self._mods_dir(),
            force=False,
        )
        self._wire_worker(worker)
        worker.start()

    @Slot()
    def _on_generate(self) -> None:
        """Start a GenerateWorker (normal mode)."""
        self._log_panel.append_line("[INFO]  — Generate ——————————————————————")
        self._set_busy("Generating…")
        worker = GenerateWorker(
            workspace_dir=self._workspace_dir(),
            templates_dir=self._templates_dir(),
            mods_dir=self._mods_dir(),
            force=False,
        )
        self._wire_worker(worker)
        worker.start()

    @Slot()
    def _on_generate_force(self) -> None:
        """Confirm, then start a GenerateWorker with force=True."""
        answer = QMessageBox.question(
            self,
            "Generate --force",
            "This will DELETE the existing generated repository and regenerate "
            "it from scratch.\n\nAre you sure you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._log_panel.append_line("[INFO]  — Generate --force ————————————————")
        self._set_busy("Generating (force)…")
        worker = GenerateWorker(
            workspace_dir=self._workspace_dir(),
            templates_dir=self._templates_dir(),
            mods_dir=self._mods_dir(),
            force=True,
        )
        self._wire_worker(worker)
        worker.start()

    @Slot()
    def _on_build(self) -> None:
        """Start a BuildWorker."""
        self._log_panel.append_line("[INFO]  — Build —————————————————————————")
        self._set_busy("Building (Gradle)…")
        worker = BuildWorker(
            workspace_dir=self._workspace_dir(),
            mods_dir=self._mods_dir(),
        )
        self._wire_worker(worker)
        worker.start()

    @Slot()
    def _on_clean(self) -> None:
        """Confirm deletion, then start a CleanWorker."""
        mods_dir = self._mods_dir()
        answer = QMessageBox.question(
            self,
            "Clean — Confirm Deletion",
            f"This will permanently delete the generated repository inside:\n\n"
            f"  {mods_dir}\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._log_panel.append_line("[INFO]  — Clean —————————————————————————")
        self._set_busy("Cleaning…")
        worker = CleanWorker(
            workspace_dir=self._workspace_dir(),
            mods_dir=mods_dir,
        )
        self._wire_worker(worker)
        worker.start()

    @Slot()
    def _on_open_mods(self) -> None:
        """Open the MODS/ folder in the system file manager."""
        _open_folder(self._mods_dir(), self._log_panel)

    @Slot()
    def _on_open_dist(self) -> None:
        """Open the WORKSPACE/DIST/ folder in the system file manager."""
        _open_folder(self._workspace_dir() / "DIST", self._log_panel)

    # ------------------------------------------------------------------
    # Refresh (called by MainWindow on nav / home change)
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """No persistent state to reload, but reset status label."""
        if self._worker is None:
            self._set_idle(ok=True, message="Ready")
