"""Entry point for `python -m modsmith_gui`.

Handles ``--version`` and ``--help`` before touching PySide6 so that
build-script smoke tests work on headless machines.  Gracefully handles
missing PySide6 by printing a readable install instruction rather than
an ugly ImportError traceback.
"""

from __future__ import annotations

import sys


def _attach_console() -> None:
    """Attach to the parent console so print() works from a windowed exe.

    When PyInstaller builds with ``console=False``, the process has no
    console.  If the user runs ``modsmith.exe --version`` from a
    terminal, we need to re-attach to the parent console for output to
    be visible.  This is a no-op when running from source or as a
    console executable.
    """
    if not getattr(sys, "frozen", False):
        return  # Running from source — stdout already works
    if sys.stdout is not None and hasattr(sys.stdout, "write"):
        # Some frozen windowed builds set stdout to None or a devnull
        try:
            sys.stdout.write("")
            return  # stdout is functional
        except (OSError, AttributeError, ValueError):
            pass
    try:
        import ctypes  # noqa: PLC0415
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ATTACH_PARENT_PROCESS = -1  # noqa: N806
        if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
    except Exception:  # noqa: BLE001
        pass  # Fail silently — not critical


def main() -> None:
    """Launch the ModSmith GUI workbench."""
    # --- Re-attach console for windowed .exe CLI flags --------------------
    _attach_console()

    # --- lightweight CLI flags (no PySide6 needed) -----------------------
    if "--version" in sys.argv:
        from modsmith import __version__  # noqa: PLC0415

        print(f"modsmith {__version__}")
        sys.exit(0)

    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "Usage: modsmith [--version] [--help]\n"
            "\n"
            "Launch the ModSmith GUI workbench.\n"
            "\n"
            "Options:\n"
            "  --version   Show version and exit\n"
            "  --help, -h  Show this message and exit",
        )
        sys.exit(0)

    # --- PySide6 availability check --------------------------------------
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
