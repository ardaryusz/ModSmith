# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ModSmith (CLI + GUI).

Produces a one-folder distribution at dist/ModSmith/ containing:
  modsmith.exe      — windowed PySide6 GUI
  modsmith_cli.exe  — console CLI
  _internal/        — shared runtime libraries

Usage::

    pyinstaller modsmith.spec
"""

import sys
from pathlib import Path

block_cipher = None

# ======================================================================
# Common excludes — modules neither target needs
# ======================================================================
_COMMON_EXCLUDES = [
    'tkinter',
    'matplotlib',
    'numpy',
    'scipy',
    'PIL',
    'cv2',
    'unittest',
]

# ======================================================================
# Analysis — CLI  (console, no PySide6)
# ======================================================================
a_cli = Analysis(
    ['modsmith/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'modsmith',
        'modsmith.cli',
        'modsmith.config',
        'modsmith.context',
        'modsmith.generator',
        'modsmith.git_ops',
        'modsmith.builder',
        'modsmith.cleaner',
        'modsmith.recipes',
        'modsmith.templates',
        'modsmith.utils',
        'modsmith.validator',
        'modsmith.verifier',
        'modsmith.patchers',
        'modsmith.patchers.base',
        'modsmith.patchers.forge',
        'modsmith.patchers.neoforge',
        'modsmith.patchers.fabric',
        'modsmith.home',
        'modsmith.doctor',
        'modsmith.template_listing',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_COMMON_EXCLUDES + [
        # CLI must NOT pull in PySide6 — keep it console-focused
        'PySide6',
        'shiboken6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ======================================================================
# Analysis — GUI  (windowed, includes PySide6)
# ======================================================================
a_gui = Analysis(
    ['modsmith_gui/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle the branding icon so resources.py can find it at runtime
        (str(Path('assets', 'modsmith.ico')), 'assets'),
    ],
    hiddenimports=[
        # --- Backend (the GUI drives the CLI engine) ---
        'modsmith',
        'modsmith.cli',
        'modsmith.config',
        'modsmith.context',
        'modsmith.generator',
        'modsmith.git_ops',
        'modsmith.builder',
        'modsmith.cleaner',
        'modsmith.recipes',
        'modsmith.templates',
        'modsmith.utils',
        'modsmith.validator',
        'modsmith.verifier',
        'modsmith.patchers',
        'modsmith.patchers.base',
        'modsmith.patchers.forge',
        'modsmith.patchers.neoforge',
        'modsmith.patchers.fabric',
        'modsmith.home',
        'modsmith.doctor',
        'modsmith.template_listing',
        # --- GUI package ---
        'modsmith_gui',
        'modsmith_gui.app',
        'modsmith_gui.main_window',
        'modsmith_gui.resources',
        'modsmith_gui.assets_utils',
        'modsmith_gui.workers',
        'modsmith_gui.workspace_utils',
        'modsmith_gui.template_descriptor_utils',
        'modsmith_gui.screens.dashboard',
        'modsmith_gui.screens.home',
        'modsmith_gui.screens.templates',
        'modsmith_gui.screens.recipes',
        'modsmith_gui.screens.workspace',
        'modsmith_gui.screens.generate_build',
        'modsmith_gui.widgets.log_panel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_COMMON_EXCLUDES + [
        # Heavy Qt modules we never use
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DAnimation',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtRemoteObjects',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtQml',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtXml',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtStateMachine',
        'PySide6.QtScxml',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ======================================================================
# MERGE — let PyInstaller share common binaries between targets
# ======================================================================
MERGE(
    (a_cli, 'modsmith_cli', 'modsmith_cli'),
    (a_gui, 'modsmith', 'modsmith'),
)

# ======================================================================
# PYZ archives
# ======================================================================
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)
pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)

# ======================================================================
# EXE — CLI (console)
# ======================================================================
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name='modsmith_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(Path('assets/modsmith.ico').resolve()),
)

# ======================================================================
# EXE — GUI (windowed, no console)
# ======================================================================
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name='modsmith',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(Path('assets/modsmith.ico').resolve()),
)

# ======================================================================
# COLLECT — single output folder with both executables
# ======================================================================
coll = COLLECT(
    exe_cli,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    exe_gui,
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ModSmith',
)
