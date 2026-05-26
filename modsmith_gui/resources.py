"""Resource and asset resolution utilities for the ModSmith GUI.

Supports development (source run) and PyInstaller frozen execution modes.
"""

import sys
from pathlib import Path


def resolve_icon_path() -> str | None:
    """Resolve the absolute path to modsmith.ico.

    Returns the path string if found, otherwise None (fails gracefully).
    """
    # 1. PyInstaller single-file mode (_MEIPASS temp directory)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        path = Path(sys._MEIPASS) / "assets" / "modsmith.ico"
        if path.is_file():
            return str(path)

    # 2. PyInstaller folder mode (relative to executable)
    if getattr(sys, "frozen", False):
        path = Path(sys.executable).parent / "assets" / "modsmith.ico"
        if path.is_file():
            return str(path)

    # 3. Development mode (relative to source folder layout)
    path = Path(__file__).resolve().parent.parent / "assets" / "modsmith.ico"
    if path.is_file():
        return str(path)

    return None
