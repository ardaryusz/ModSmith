"""Entry point for `python -m modsmith_gui`.

Gracefully handles missing PySide6 by printing a readable install
instruction rather than an ugly ImportError traceback.
"""

from __future__ import annotations

import sys


def main() -> None:
    """Launch the ModSmith GUI workbench."""
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401 — probe only
    except ModuleNotFoundError:
        print(
            "ModSmith GUI requires PySide6, which is not installed.\n"
            "\n"
            "Install GUI dependencies with:\n"
            "    pip install .[gui]\n"
            "\n"
            "Or, if you installed ModSmith from a release:\n"
            "    pip install PySide6>=6.5.0",
            file=sys.stderr,
        )
        sys.exit(1)

    # Deferred imports so the PySide6 check above shows the friendly message
    # before any Qt import cascade can produce a raw traceback.
    from modsmith_gui.app import run_app  # noqa: PLC0415

    sys.exit(run_app())


if __name__ == "__main__":
    main()
