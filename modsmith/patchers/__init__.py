"""Patcher package — one module per supported mod loader."""

from __future__ import annotations

from modsmith.patchers.base import BasePatcher
from modsmith.patchers.forge import ForgePatcher
from modsmith.patchers.neoforge import NeoForgePatcher
from modsmith.patchers.fabric import FabricPatcher


def get_patcher(loader: str) -> BasePatcher:
    """Return the concrete patcher for the given loader.

    Raises ValueError if the loader is not supported.
    """
    norm_loader = loader.lower().strip()
    if norm_loader == "forge":
        return ForgePatcher()
    elif norm_loader == "neoforge":
        return NeoForgePatcher()
    elif norm_loader == "fabric":
        return FabricPatcher()
    else:
        raise ValueError(f"Unsupported mod loader: '{loader}'")


__all__ = [
    "BasePatcher",
    "ForgePatcher",
    "NeoForgePatcher",
    "FabricPatcher",
    "get_patcher",
]
