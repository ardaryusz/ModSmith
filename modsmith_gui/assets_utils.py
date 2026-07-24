"""Utilities for managing asset files in the WORKSPACE/ASSETS directory."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AssetImportResult:
    """Result of importing an asset into WORKSPACE/ASSETS."""

    absolute_path: Path
    relative_path: Path
    copied: bool
    reused_existing: bool


def _calculate_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_file_identical(file_a: Path, file_b: Path) -> bool:
    """Return True if file_a and file_b refer to the same file or have identical size and SHA-256."""
    try:
        if file_a.samefile(file_b):
            return True
    except (OSError, ValueError):
        pass

    res_a, res_b = file_a.resolve(), file_b.resolve()
    if res_a == res_b:
        return True

    if file_a.stat().st_size != file_b.stat().st_size:
        return False

    return _calculate_sha256(file_a) == _calculate_sha256(file_b)


def import_asset(src: Path, assets_dir: Path) -> AssetImportResult:
    """Import *src* into *assets_dir*, avoiding unwanted duplicates.

    - If *src* is already inside *assets_dir*, reuses it without copying.
    - If *src* is outside *assets_dir* and collides with an existing file name,
      compares contents via SHA-256 hash to reuse identical files or auto-suffixes
      for different files.

    Returns an :class:`AssetImportResult`.
    """
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Source asset file not found: {src}")

    assets_dir.mkdir(parents=True, exist_ok=True)
    res_assets = assets_dir.resolve()
    res_src = src.resolve()

    # Check if src is already inside assets_dir
    try:
        rel_inside = res_src.relative_to(res_assets)
        rel_path = Path("ASSETS") / rel_inside
        return AssetImportResult(
            absolute_path=res_src,
            relative_path=rel_path,
            copied=False,
            reused_existing=True,
        )
    except ValueError:
        pass

    # Source is outside assets_dir. Check destination collision.
    dest = assets_dir / src.name
    if dest.exists():
        if _is_file_identical(src, dest):
            return AssetImportResult(
                absolute_path=dest.resolve(),
                relative_path=Path("ASSETS") / dest.name,
                copied=False,
                reused_existing=True,
            )

        # Dest exists but contents differ. Check numbered collision candidates.
        stem, ext = src.stem, src.suffix
        counter = 1
        while True:
            candidate = assets_dir / f"{stem}_{counter}{ext}"
            if candidate.exists():
                if _is_file_identical(src, candidate):
                    return AssetImportResult(
                        absolute_path=candidate.resolve(),
                        relative_path=Path("ASSETS") / candidate.name,
                        copied=False,
                        reused_existing=True,
                    )
            else:
                shutil.copy2(src, candidate)
                return AssetImportResult(
                    absolute_path=candidate.resolve(),
                    relative_path=Path("ASSETS") / candidate.name,
                    copied=True,
                    reused_existing=False,
                )
            counter += 1

    # No collision, copy directly
    shutil.copy2(src, dest)
    return AssetImportResult(
        absolute_path=dest.resolve(),
        relative_path=Path("ASSETS") / dest.name,
        copied=True,
        reused_existing=False,
    )


def safe_copy_to_assets(src: Path, assets_dir: Path) -> Path:
    """Copy *src* into *assets_dir*, auto-suffixing if destination exists.

    Returns the final destination ``Path``. Backward-compatible wrapper for import_asset.
    """
    result = import_asset(src, assets_dir)
    return result.absolute_path
