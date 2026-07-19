"""GUI test verifying Output Log maximum expansion, Clear, Copy All, and navigation in MainWindow."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from modsmith_gui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_output_log_maximum_expansion_and_gui_features(qapp):
    """Verify Output Log maximum expansion, Clear, Copy All, and screen navigation."""
    window = MainWindow()
    window.resize(900, 620)
    window.show()
    qapp.processEvents()

    splitter = window._splitter
    assert splitter is not None

    total_height = splitter.height()
    assert total_height > 200, f"Splitter height unexpectedly small: {total_height}"

    # 1. Expand log to maximum (1 px for top pane, remainder for log pane)
    splitter.setSizes([1, total_height])
    qapp.processEvents()

    sizes = splitter.sizes()
    top_height, log_height = sizes[0], sizes[1]
    usable_height = top_height + log_height

    log_percentage = (log_height / usable_height) * 100.0
    assert log_percentage >= 90.0, (
        f"Log pane height ({log_height}px, {log_percentage:.1f}%) "
        f"is less than 90% of usable height ({usable_height}px)."
    )

    # 2. Test Clear and Copy All buttons
    window.log_panel.append_log("Test log entry line 1")
    window.log_panel.append_log("Test log entry line 2")
    qapp.processEvents()

    assert "Test log entry line 1" in window.log_panel.log_edit.toPlainText()

    # Test Copy All (invokes clipboard copy)
    window.log_panel.copy_all_btn.click()
    qapp.processEvents()
    clipboard_text = QApplication.clipboard().text()
    assert "Test log entry line 1" in clipboard_text

    # Test Clear button
    window.log_panel.clear_btn.click()
    qapp.processEvents()
    assert window.log_panel.log_edit.toPlainText() == ""

    # 3. Restore default sizes
    splitter.setSizes([460, 140])
    qapp.processEvents()
    restored_sizes = splitter.sizes()
    assert restored_sizes[0] > 200
    assert restored_sizes[1] > 50

    # 4. Screen navigation testing
    window._on_nav_changed(0)  # Workspace
    qapp.processEvents()
    assert window._stack.currentIndex() == 0

    window._on_nav_changed(1)  # Targets
    qapp.processEvents()
    assert window._stack.currentIndex() == 1

    window._on_nav_changed(2)  # Recipes
    qapp.processEvents()
    assert window._stack.currentIndex() == 2

    window.close()
