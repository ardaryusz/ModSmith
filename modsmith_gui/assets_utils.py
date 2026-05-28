"""Utilities for managing asset files in the WORKSPACE/ASSETS directory."""

from __future__ import annotations

import shutil
from pathlib import Path


def safe_copy_to_assets(src: Path, assets_dir: Path) -> Path:
    """Copy *src* into *assets_dir*, auto-suffixing if destination exists.

    Returns the final destination ``Path``.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    dest = assets_dir / src.name
    if not dest.exists():
        shutil.copy2(src, dest)
        return dest
    stem, ext = src.stem, src.suffix
    counter = 1
    while True:
        candidate = assets_dir / f"{stem}_{counter}{ext}"
        if not candidate.exists():
            shutil.copy2(src, candidate)
            return candidate
        counter += 1
