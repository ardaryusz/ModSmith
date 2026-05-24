# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ModSmith.

Produces a one-folder distribution at dist/ModSmith/ with the main
executable named modsmith.exe.

Usage::

    pyinstaller modsmith.spec
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='modsmith',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ModSmith',
)
