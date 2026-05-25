"""PyInstaller hook for the `elysium` package.

Collects every sibling needed for the runtime to boot:

* The native cdylib at ``elysium/_native/_native.{so,pyd}``.
* WGSL shader sources under ``elysium/render/shaders/``.
* Skin schema JSON under ``elysium/skin/`` (when present).
* Component assets and default themes.

Generated bundle layout matches what ``elysium pack`` produces by hand,
so a PyInstaller-built ``--onedir`` distribution boots identically.
"""
from PyInstaller.utils.hooks import (    # type: ignore[import-not-found]
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Pull in every Python submodule so dynamic imports (component lookups,
# theme resolution by name, render backend selection) keep working
# under PyInstaller's import auditing.
hiddenimports = collect_submodules("elysium")

# Native cdylib and any vendored Skia shared libraries.
binaries = collect_dynamic_libs("elysium")

# Data: WGSL shaders, JSON schemas, theme assets, the .pyi stub.
datas = collect_data_files(
    "elysium",
    includes=[
        "_native/*.pyi",
        "render/shaders/*.wgsl",
        "skin/*.json",
        "theme/*",
        "assets/*",
        "components/*.json",
    ],
)
