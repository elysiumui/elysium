"""PyInstaller hook entry-points.

PyInstaller discovers hooks via the ``pyinstaller40`` entry point —
this directory holds the ``hook-elysium.py`` that collects the native
cdylib + Skia data + WGSL shaders so devs who keep using PyInstaller
get a working bundle out of the box. Our own ``elysium pack`` does this
without their help; this module is for the ecosystem.
"""
from pathlib import Path


def get_hook_dirs() -> list[str]:
    return [str(Path(__file__).parent)]


def get_PyInstaller_tests() -> list[str]:
    return []
