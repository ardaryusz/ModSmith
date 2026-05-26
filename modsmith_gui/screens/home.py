"""Home screen — manage MODSMITH_HOME environment variable.

Uses the existing ``modsmith.home`` backend directly:
 - ``get_effective_home()``
 - ``set_user_home()``
 - ``unset_user_home()``
 - ``open_home()``

After a Set or Unset operation, ``os.environ`` is updated in-process
immediately (home.py already does this), and then a ``home_changed``
signal is emitted so the main window can propagate a refresh() to all
screens without requiring a restart.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QFormLayout,
    QFileDialog, QMessageBox, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, Slot

from modsmith_gui.widgets.status_badge import StatusBadge


def _get_default_dir(subdir: str) -> Path:
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


class HomeScreen(QWidget):
    """Screen for viewing and managing the MODSMITH_HOME directory."""

    #: Emitted after a successful Set or Unset so other screens can refresh.
    home_changed: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Home")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)

        # --- Current home group ---
        home_group = QGroupBox("MODSMITH_HOME")
        home_form = QFormLayout(home_group)
        home_form.setContentsMargins(10, 8, 10, 8)
        home_form.setSpacing(6)
        home_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._badge_home = StatusBadge()
        self._lbl_home_value = QLineEdit()
        self._lbl_home_value.setReadOnly(True)

        home_form.addRow("Status:", self._badge_home)
        home_form.addRow("Effective path:", self._lbl_home_value)

        root.addWidget(home_group)

        # --- Resolved paths group ---
        paths_group = QGroupBox("Resolved Paths")
        paths_form = QFormLayout(paths_group)
        paths_form.setContentsMargins(10, 8, 10, 8)
        paths_form.setSpacing(6)
        paths_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._lbl_workspace = QLineEdit()
        self._lbl_workspace.setReadOnly(True)
        self._lbl_templates = QLineEdit()
        self._lbl_templates.setReadOnly(True)
        self._lbl_mods = QLineEdit()
        self._lbl_mods.setReadOnly(True)

        paths_form.addRow("Workspace:", self._lbl_workspace)
        paths_form.addRow("Templates:", self._lbl_templates)
        paths_form.addRow("Mods:", self._lbl_mods)

        root.addWidget(paths_group)

        # --- Actions group ---
        actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setContentsMargins(10, 8, 10, 8)
        actions_layout.setSpacing(8)

        self._btn_open = QPushButton("Open Home")
        self._btn_open.setToolTip("Open the home directory in File Explorer")
        self._btn_open.clicked.connect(self._open_home)

        self._btn_change = QPushButton("Change Home…")
        self._btn_change.setToolTip("Pick a new MODSMITH_HOME directory")
        self._btn_change.clicked.connect(self._change_home)

        self._btn_unset = QPushButton("Unset Home")
        self._btn_unset.setToolTip("Remove MODSMITH_HOME from the user environment")
        self._btn_unset.clicked.connect(self._unset_home)

        actions_layout.addWidget(self._btn_open)
        actions_layout.addWidget(self._btn_change)
        actions_layout.addWidget(self._btn_unset)
        actions_layout.addStretch()

        root.addWidget(actions_group)

        # --- Info note ---
        note = QLabel(
            "Note: Setting or unsetting the home directory writes to the Windows "
            "registry (HKCU\\Environment) and broadcasts a WM_SETTINGCHANGE message. "
            "New terminal sessions will pick up the change automatically. "
            "The GUI refreshes immediately within this session."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(note)

        root.addStretch()

        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read current environment and update all labels."""
        from modsmith.home import get_effective_home
        effective = get_effective_home()

        if effective:
            self._badge_home.set_ok("Set")
            self._lbl_home_value.setText(effective)
            self._lbl_home_value.setStyleSheet("color: inherit;")
            self._btn_open.setEnabled(True)
            self._btn_unset.setEnabled(True)
        else:
            self._badge_home.set_warning("Unset — relative defaults active")
            self._lbl_home_value.setText("(unset)")
            self._lbl_home_value.setStyleSheet("color: #b87800;")
            # Open/Unset still allowed (opens CWD / no-op unset)
            self._btn_open.setEnabled(True)
            self._btn_unset.setEnabled(False)

        self._lbl_workspace.setText(str(_get_default_dir("WORKSPACE")))
        self._lbl_templates.setText(str(_get_default_dir("MODTEMPLATES")))
        self._lbl_mods.setText(str(_get_default_dir("MODS")))

    # ------------------------------------------------------------------
    # Slot implementations
    # ------------------------------------------------------------------

    @Slot()
    def _open_home(self) -> None:
        """Open the effective home (or CWD if unset) in the system file manager."""
        from modsmith.home import get_effective_home
        target = get_effective_home() or str(Path.cwd())
        path = Path(target)
        if not path.is_dir():
            QMessageBox.warning(
                self,
                "Open Home",
                f"Directory does not exist:\n{path}",
            )
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            QMessageBox.critical(self, "Open Home", f"Failed to open folder:\n{exc}")

    @Slot()
    def _change_home(self) -> None:
        """Show a directory picker then persist the new MODSMITH_HOME."""
        from modsmith.home import set_user_home, ensure_home_structure

        start = os.environ.get("MODSMITH_HOME") or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose ModSmith Home Directory",
            start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not chosen:
            return  # User cancelled

        target = Path(chosen)
        try:
            ensure_home_structure(target)
            set_user_home(target)
        except SystemExit:
            # set_user_home calls sys.exit(1) on non-Windows platforms
            QMessageBox.critical(
                self,
                "Set Home",
                "Persistent home setting is only supported on Windows.\n"
                f"You can set MODSMITH_HOME manually:\n\n"
                f'  export MODSMITH_HOME="{target}"',
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, "Set Home", f"Failed to set home:\n{exc}")
            return

        QMessageBox.information(
            self,
            "Home Updated",
            f"MODSMITH_HOME set to:\n{target}\n\n"
            "Workspace folders created/verified.",
        )
        self.refresh()
        self.home_changed.emit()

    @Slot()
    def _unset_home(self) -> None:
        """Remove MODSMITH_HOME persistently after user confirmation."""
        from modsmith.home import unset_user_home

        reply = QMessageBox.question(
            self,
            "Unset Home",
            "Remove MODSMITH_HOME from the user environment?\n\n"
            "Existing data folders will not be deleted.\n"
            "ModSmith will fall back to relative defaults (WORKSPACE, MODTEMPLATES, MODS).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            unset_user_home()
        except SystemExit:
            QMessageBox.critical(
                self,
                "Unset Home",
                "Persistent unset is only supported on Windows.\n"
                "Remove MODSMITH_HOME from your shell profile manually.",
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, "Unset Home", f"Failed to unset home:\n{exc}")
            return

        QMessageBox.information(
            self,
            "Home Unset",
            "MODSMITH_HOME has been removed.\n"
            "Open a new terminal for the change to appear in shell sessions.\n"
            "The GUI has refreshed immediately.",
        )
        self.refresh()
        self.home_changed.emit()
