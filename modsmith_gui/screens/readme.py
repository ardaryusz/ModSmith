"""README screen — markdown editor and compiled rich text preview workshop."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QPlainTextEdit, QTextBrowser, QMessageBox,
)
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QFont


def _get_default_dir(subdir: str) -> Path:
    """Helper to resolve directory relative to MODSMITH_HOME or CWD."""
    home = os.environ.get("MODSMITH_HOME")
    if home:
        return Path(home) / subdir
    return Path(subdir).resolve()


def _get_starter_readme() -> str:
    """Derive custom starting text defensively from modsmith.json if present."""
    try:
        json_path = _get_default_dir("WORKSPACE") / "DETAILS" / "modsmith.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            name = data.get("mod_name", "My Mod")
            desc = data.get("description", "Adds crafting recipes and content to Minecraft.")
            return f"# {name}\n\n{desc}\n"
    except Exception:
        pass
    return "# My Mod\n\nAdds crafting recipes and content to Minecraft.\n"


class ReadmeScreen(QWidget):
    """Screen for loading, editing, saving, and previewing README.md in Markdown."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("README Workshop")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(title)

        # --- Top control row ---
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._btn_refresh = QPushButton("Load / Refresh")
        self._btn_refresh.setFixedWidth(100)
        self._btn_refresh.clicked.connect(self.refresh)

        self._btn_save = QPushButton("Save README")
        self._btn_save.setFixedWidth(100)
        self._btn_save.clicked.connect(self._save_readme)

        self._btn_open_folder = QPushButton("Open README Folder")
        self._btn_open_folder.clicked.connect(self._open_readme_folder)

        controls.addWidget(self._btn_refresh)
        controls.addWidget(self._btn_save)
        controls.addWidget(self._btn_open_folder)
        controls.addStretch()

        root.addLayout(controls)

        # --- Tab Layout (Edit vs Preview) ---
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # 1. Edit Tab
        self._editor = QPlainTextEdit()
        # Monospace font for code editing
        font = QFont("Courier New", 10)
        self._editor.setFont(font)
        self._tabs.addTab(self._editor, "Edit Markdown")

        # 2. Preview Tab
        self._preview = QTextBrowser()
        self._tabs.addTab(self._preview, "Preview HTML")

        root.addWidget(self._tabs, stretch=1)

        # --- Note label at the bottom ---
        note = QLabel(
            "⚠️ Note: Markdown image/asset previews are not supported in this milestone. "
            "Images and asset folders will render in a later update."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(note)

        # First refresh
        self.refresh()

    def refresh(self) -> None:
        """Scan folders and load README.md configuration from disk."""
        readme_dir = _get_default_dir("WORKSPACE") / "README"
        readme_path = readme_dir / "README.md"

        # Safe directory creation
        readme_dir.mkdir(parents=True, exist_ok=True)

        if readme_path.exists():
            try:
                text = readme_path.read_text(encoding="utf-8")
                self._editor.setPlainText(text)
            except Exception as exc:
                QMessageBox.critical(self, "Load README", f"Failed to load README.md:\n{exc}")
        else:
            # Starter fallback template
            self._editor.setPlainText(_get_starter_readme())

        # Update preview if active
        if self._tabs.currentIndex() == 1:
            self._preview.setMarkdown(self._editor.toPlainText())

    @Slot()
    def _save_readme(self) -> None:
        """Serialize text to WORKSPACE/README/README.md safely in UTF-8."""
        readme_dir = _get_default_dir("WORKSPACE") / "README"
        readme_path = readme_dir / "README.md"

        try:
            readme_dir.mkdir(parents=True, exist_ok=True)
            text = self._editor.toPlainText()
            readme_path.write_text(text, encoding="utf-8")
            QMessageBox.information(self, "Save README", f"Saved README successfully to:\n{readme_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save README", f"Failed to save README:\n{exc}")

    @Slot()
    def _open_readme_folder(self) -> None:
        """Safely open the active readme directory in Explorer."""
        readme_dir = _get_default_dir("WORKSPACE") / "README"
        if not readme_dir.is_dir():
            QMessageBox.warning(self, "Open Folder", f"Folder does not exist:\n{readme_dir}")
            return

        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(readme_dir)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(readme_dir)])
            else:
                subprocess.Popen(["xdg-open", str(readme_dir)])
        except OSError as exc:
            QMessageBox.critical(self, "Open Folder", f"Failed to open directory:\n{exc}")

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        """Triggered on tab selection. If preview is clicked, render Markdown using built-in setMarkdown."""
        if index == 1:
            self._preview.setMarkdown(self._editor.toPlainText())
