"""Home directory management logic for ModSmith."""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

# Try importing winreg on Windows
try:
    import winreg
except ImportError:
    winreg = None

try:
    import ctypes
except ImportError:
    ctypes = None


def get_effective_home() -> str | None:
    """Return the value of MODSMITH_HOME environment variable, or None if unset."""
    return os.environ.get("MODSMITH_HOME")


def ensure_home_structure(path: Path | str) -> None:
    """Resolve path and create the standard ModSmith folder structure there.

    Creates:
      <home>/WORKSPACE
      <home>/WORKSPACE/DETAILS
      <home>/WORKSPACE/RECIPES
      <home>/WORKSPACE/README
      <home>/WORKSPACE/DIST
      <home>/MODTEMPLATES
      <home>/MODS
    Does not overwrite existing files or delete directories.
    """
    home_path = Path(path).expanduser()
    resolved_str = os.path.expandvars(str(home_path))
    home_path = Path(resolved_str).resolve()

    subdirs = [
        "WORKSPACE",
        "WORKSPACE/DETAILS",
        "WORKSPACE/RECIPES",
        "WORKSPACE/README",
        "WORKSPACE/DIST",
        "MODTEMPLATES",
        "MODS",
    ]
    for subdir in subdirs:
        (home_path / subdir).mkdir(parents=True, exist_ok=True)


def set_user_home(path: Path | str) -> None:
    """Set the MODSMITH_HOME environment variable persistently for the user.

    On Windows, writes to HKCU\\Environment using winreg and broadcasts WM_SETTINGCHANGE.
    On non-Windows, prints manual environment export instructions and exits 1.
    """
    home_path = Path(path).expanduser()
    resolved_str = os.path.expandvars(str(home_path))
    resolved_path = Path(resolved_str).resolve()

    # Update current process environment
    os.environ["MODSMITH_HOME"] = str(resolved_path)

    if sys.platform == "win32":
        if winreg is None:
            print("[ERROR] winreg module is not available.")
            sys.exit(1)

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
            try:
                winreg.SetValueEx(key, "MODSMITH_HOME", 0, winreg.REG_SZ, str(resolved_path))
            finally:
                winreg.CloseKey(key)
        except OSError as exc:
            print(f"[ERROR] Failed to write registry key: {exc}")
            sys.exit(1)

        # Broadcast WM_SETTINGCHANGE
        if ctypes is not None:
            try:
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST,
                    WM_SETTINGCHANGE,
                    0,
                    "Environment",
                    0x0002,  # SMTO_ABORTIFHUNG
                    5000,    # 5 seconds
                    ctypes.byref(ctypes.c_size_t()),
                )
            except Exception:
                pass
    else:
        print("[ERROR] Persistent set is not supported on this platform.")
        print("To configure MODSMITH_HOME manually, add this to your shell profile:")
        print(f'  export MODSMITH_HOME="{resolved_path}"')
        sys.exit(1)


def unset_user_home() -> None:
    """Remove the MODSMITH_HOME environment variable from user environment settings.

    On Windows, removes from HKCU\\Environment using winreg and broadcasts WM_SETTINGCHANGE.
    On non-Windows, prints manual unset instructions and exits 1.
    """
    if "MODSMITH_HOME" in os.environ:
        del os.environ["MODSMITH_HOME"]

    if sys.platform == "win32":
        if winreg is None:
            print("[ERROR] winreg module is not available.")
            sys.exit(1)

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
            try:
                winreg.DeleteValue(key, "MODSMITH_HOME")
            except FileNotFoundError:
                # If it doesn't exist, that is fine
                pass
            finally:
                winreg.CloseKey(key)
        except OSError as exc:
            print(f"[ERROR] Failed to delete registry key: {exc}")
            sys.exit(1)

        # Broadcast WM_SETTINGCHANGE
        if ctypes is not None:
            try:
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST,
                    WM_SETTINGCHANGE,
                    0,
                    "Environment",
                    0x0002,  # SMTO_ABORTIFHUNG
                    5000,    # 5 seconds
                    ctypes.byref(ctypes.c_size_t()),
                )
            except Exception:
                pass
    else:
        print("[ERROR] Persistent unset is not supported on this platform.")
        print("To unset MODSMITH_HOME manually, remove the export statement from your shell profile.")
        sys.exit(1)


def open_home(path: Path | str) -> None:
    """Open the home directory in file explorer.

    If the directory does not exist, prints an error and exits 1.
    """
    home_path = Path(path).expanduser()
    resolved_str = os.path.expandvars(str(home_path))
    resolved_path = Path(resolved_str).resolve()

    if not resolved_path.is_dir():
        print(f"[ERROR] Home directory does not exist: {resolved_path}")
        sys.exit(1)

    if sys.platform == "win32":
        subprocess.run(["explorer", str(resolved_path)], check=True)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(resolved_path)], check=True)
    else:
        # Linux / other Unix-like
        subprocess.run(["xdg-open", str(resolved_path)], check=True)
