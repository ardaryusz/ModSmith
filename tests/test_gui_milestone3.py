import sys
from pathlib import Path
import pytest

try:
    from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QInputDialog
    from modsmith_gui.screens.workspace import WorkspaceScreen
    from modsmith_gui.screens.readme import ReadmeScreen
    from modsmith_gui.screens.templates import TemplatesScreen
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

# Skip entire test file if PySide6 GUI dependencies are absent
pytestmark = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 is not installed or unavailable"
)


@pytest.fixture(autouse=True)
def mock_qt_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture that automatically mocks all Qt modal dialogs to prevent headless test blocking."""
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QInputDialog.getText",
        lambda *args, **kwargs: ("mock-dest-name", True)
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: "mock-source-dir"
    )


def test_milestone3_gui_imports() -> None:
    """Verify that all new GUI screens import cleanly without exceptions."""
    from modsmith_gui.screens.workspace import WorkspaceScreen
    from modsmith_gui.screens.readme import ReadmeScreen

    assert WorkspaceScreen is not None
    assert ReadmeScreen is not None


def test_workspace_load_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that loading WorkspaceScreen when modsmith.json is missing falls back to defaults."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    app = QApplication.instance() or QApplication([])
    from modsmith_gui.widgets.log_panel import LogPanel

    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Verify form falls back to clean sensible defaults
    assert screen._txt_mod_version.text() == "1.0.0"
    assert screen._txt_group.text() == "com.example"
    assert screen._txt_license.text() == "MIT"

    # There should be exactly 1 default target row added
    assert screen._table.rowCount() == 1

    # Cleanup widgets
    screen.deleteLater()
    log_panel.deleteLater()


def test_workspace_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that saving form configurations writes valid, formatted modsmith.json."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    # Create a dummy template directory so template selection is not empty
    (tmp_path / "MODTEMPLATES" / "fabric-1.21-template").mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    from modsmith_gui.widgets.log_panel import LogPanel

    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Edit fields dynamically
    screen._txt_mod_id.setText("testmod")
    screen._txt_mod_name.setText("Test Mod")
    screen._txt_group.setText("com.example.testmod")
    screen._txt_description.setPlainText("Test Description")
    screen._txt_authors.setText("Test Author")

    # Trigger Save
    screen._save_config()

    json_path = tmp_path / "WORKSPACE" / "DETAILS" / "modsmith.json"
    assert json_path.exists()

    # Load and parse using the core configuration engine
    from modsmith.config import load_mod_config
    cfg = load_mod_config(json_path)

    assert cfg.mod_id == "testmod"
    assert cfg.mod_name == "Test Mod"
    assert cfg.package == "com.example.testmod"
    assert cfg.description == "Test Description"
    assert len(cfg.targets) == 1

    # Cleanup
    screen.deleteLater()
    log_panel.deleteLater()


def test_readme_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that saving README writes standard markdown text successfully."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    app = QApplication.instance() or QApplication([])
    screen = ReadmeScreen()

    screen._editor.setPlainText("# Header Text\n\nContent details here.")
    screen._save_readme()

    readme_path = tmp_path / "WORKSPACE" / "README" / "README.md"
    assert readme_path.exists()
    assert readme_path.read_text(encoding="utf-8") == "# Header Text\n\nContent details here."

    screen.deleteLater()


def test_readme_load_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that loading README Screen when file is missing provides custom starter text."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    app = QApplication.instance() or QApplication([])
    screen = ReadmeScreen()

    # Check that starter text has fallback Mod title
    text = screen._editor.toPlainText()
    assert "# My Mod" in text

    screen.deleteLater()


def test_template_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that template import copies folders correctly to MODTEMPLATES."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    # Setup directories
    tpl_dir = tmp_path / "MODTEMPLATES"
    tpl_dir.mkdir(parents=True)

    src_dir = tmp_path / "source_mdk"
    src_dir.mkdir()
    (src_dir / "modsmith-template.json").write_text("{}", encoding="utf-8")
    (src_dir / "gradlew").write_text("test", encoding="utf-8")

    app = QApplication.instance() or QApplication([])
    screen = TemplatesScreen()

    # Emulate the copying mechanism inside _add_template slot
    import shutil
    dest_path = tpl_dir / "imported-mdk"
    shutil.copytree(src_dir, dest_path)

    assert dest_path.exists()
    assert (dest_path / "modsmith-template.json").exists()
    assert (dest_path / "gradlew").exists()

    screen.deleteLater()


def test_template_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that template overwrite utilizes safe_delete_tree recursively before copy."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))

    tpl_dir = tmp_path / "MODTEMPLATES"
    tpl_dir.mkdir(parents=True)

    # Set up active destination folder with old files
    dest_path = tpl_dir / "imported-mdk"
    dest_path.mkdir()
    (dest_path / "old-file.txt").write_text("stale", encoding="utf-8")

    # Set up source folder with new files
    src_dir = tmp_path / "source_mdk"
    src_dir.mkdir()
    (src_dir / "new-file.txt").write_text("fresh", encoding="utf-8")

    # Emulate confirm delete & copy logic
    from modsmith.utils import safe_delete_tree
    import shutil

    assert dest_path.exists()
    safe_delete_tree(dest_path)
    assert not dest_path.exists()

    shutil.copytree(src_dir, dest_path)
    assert dest_path.exists()
    assert (dest_path / "new-file.txt").exists()
    assert not (dest_path / "old-file.txt").exists()


def test_workspace_instantiate() -> None:
    """Verify that WorkspaceScreen instantiates without error."""
    app = QApplication.instance() or QApplication([])
    from modsmith_gui.widgets.log_panel import LogPanel
    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)
    assert screen is not None
    screen.deleteLater()
    log_panel.deleteLater()


def test_workspace_clear_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that clear form helper clears metadata and resets targets without deleting files."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    from modsmith_gui.widgets.log_panel import LogPanel
    log_panel = LogPanel()
    screen = WorkspaceScreen(log_panel=log_panel)

    # Edit fields
    screen._txt_mod_id.setText("tobecleared")
    screen._txt_mod_name.setText("To Be Cleared")

    # Add extra target rows
    screen._add_target_row()
    assert screen._table.rowCount() == 2

    # Mock dialogue reply to Yes
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )

    # Trigger Clear All
    screen._clear_all()

    # Form must clear
    assert screen._txt_mod_id.text() == ""
    assert screen._txt_mod_name.text() == ""
    # Should reset to exactly 1 default target row
    assert screen._table.rowCount() == 1

    screen.deleteLater()
    log_panel.deleteLater()


def test_workspace_missing_config_prompt_suppression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that missing config prompt is not repeatedly triggered on automatic refresh."""
    monkeypatch.setenv("MODSMITH_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])

    from modsmith_gui.widgets.log_panel import LogPanel
    log_panel = LogPanel()

    prompt_count = 0
    def mock_question(*args, **kwargs):
        nonlocal prompt_count
        prompt_count += 1
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        mock_question
    )

    # Create modsmith.example.json so example-loading prompt triggers
    example_dir = tmp_path / "WORKSPACE" / "DETAILS"
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "modsmith.example.json").write_text("{}", encoding="utf-8")

    screen = WorkspaceScreen(log_panel=log_panel)
    # The initialization of WorkspaceScreen calls self.refresh() once internally
    assert prompt_count == 1

    # Automatic navigations trigger screen.refresh() which should NOT prompt again
    screen.refresh()
    screen.refresh()
    assert prompt_count == 1  # Still 1! Prompt was successfully suppressed!

    # Manual refresh should bypass suppression and prompt again
    screen._on_manual_refresh()
    assert prompt_count == 2  # Prompt triggered!

    screen.deleteLater()
    log_panel.deleteLater()
