# PyInstaller spec for the Elysium Designer.
#
# Builds a standalone executable per OS:
#   macOS   .app  (signed + notarized when ELYSIUM_SIGN_ID is set)
#   Windows .exe  (signed when ELYSIUM_SIGN_PFX + ELYSIUM_SIGN_PASS are set)
#   Linux   ./ElysiumDesigner  (wrapped into AppImage / .deb / .rpm by
#                                .github/workflows/release-designer.yml)
#
# Build locally (from the repo root):
#
#   pyinstaller scripts/build-designer.spec --noconfirm
#
# CI runs the same command on macOS / Windows / Linux runners and uploads
# the per-OS artifacts to GitHub Releases. See
# docs-designer/installation/build-from-source.md for the contributor walkthrough.
#
# Notes on the bundled native module: `elysium._native._native` is a
# maturin-built extension that ships compiled bytes (`.so` on Linux, `.dylib`
# on macOS, `.pyd` on Windows). PyInstaller picks it up automatically once
# it's on `sys.path` at analysis time, so we do `pip install -e .` (or
# `maturin develop`) before running this spec.

# ruff: noqa  (PyInstaller spec files are exec'd, not imported)

import os
import sys
from pathlib import Path

block_cipher = None

REPO_ROOT = Path(SPEC).resolve().parent.parent
APP_NAME = "Elysium Designer"
APP_ID = "dev.elysium.designer"
APP_VERSION = os.environ.get("ELYSIUM_VERSION", "0.1.0")

# Source modules the Designer pulls in at runtime. `elysium-designer` is a
# hyphenated package directory so PyInstaller can't auto-discover it via the
# usual import dance; we point at __main__ explicitly.
DESIGNER_ENTRY = REPO_ROOT / "elysium-designer" / "__main__.py"

# Bundle every file under examples/butterfly/ so the lead tutorial works
# out of the box. The user can delete or replace these via the File menu.
TUTORIAL_ASSETS = [
    (str(REPO_ROOT / "examples" / "butterfly"), "examples/butterfly"),
]

# Bundle every brush preset + thumbnail so the first launch experience has
# the full library available.
BRUSH_ASSETS = [
    (str(REPO_ROOT / "python" / "elysium" / "brush" / "builtin"),
     "elysium/brush/builtin"),
]

# Designer-specific data files: menus.py is read at runtime to compose the
# menu bar; the maya-migration + brush-system docs ship inside the app for
# the in-app Help menu.
DESIGNER_DATA = [
    (str(REPO_ROOT / "elysium-designer" / "menus.py"), "elysium-designer"),
]

# Hidden imports: PyInstaller's static analysis misses dynamically imported
# modules (Aether tool plugins, every brush engine, the AI provider stubs).
HIDDEN_IMPORTS = [
    # Brush engines all register themselves at import time.
    "elysium.brush.engines.round_stamp",
    "elysium.brush.engines.wet_mix",
    "elysium.brush.engines.bristle",
    "elysium.brush.engines.airbrush",
    "elysium.brush.engines.pattern",
    "elysium.brush.engines.texture",
    # Aether tool modules.
    "elysium.aether.tools.animation",
    "elysium.aether.tools.brush",
    "elysium.aether.tools.code",
    "elysium.aether.tools.codelink",
    "elysium.aether.tools.hook",
    "elysium.aether.tools.material",
    "elysium.aether.tools.mesh",
    "elysium.aether.tools.meta",
    "elysium.aether.tools.placement",
    "elysium.aether.tools.render",
    "elysium.aether.tools.run",
    "elysium.aether.tools.shape",
    "elysium.aether.tools.snapshot",
    "elysium.aether.tools.tester",
    "elysium.aether.tools.texture",
    "elysium.aether.tools.window",
    # AI providers.
    "elysium.ai.anthropic",
    "elysium.ai.openai",
    "elysium.ai.ollama",
    "elysium.ai.stub",
    # Native PyO3 module.
    "elysium._native",
    "elysium._native._native",
]

a = Analysis(
    [str(DESIGNER_ENTRY)],
    pathex=[str(REPO_ROOT / "python")],
    binaries=[],
    datas=TUTORIAL_ASSETS + BRUSH_ASSETS + DESIGNER_DATA,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Per-OS icons. We rely on environment-provided icon paths when present
# so the CI release job can swap branded vs nightly icons.
ICON_MAC = os.environ.get("ELYSIUM_ICON_MAC", "")
ICON_WIN = os.environ.get("ELYSIUM_ICON_WIN", "")

if sys.platform == "darwin":
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=APP_NAME.replace(" ", ""),
        debug=False, bootloader_ignore_signals=False,
        strip=False, upx=False, console=False,
        icon=ICON_MAC or None,
    )
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=False, upx_exclude=[],
        name=APP_NAME.replace(" ", ""),
    )
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=ICON_MAC or None,
        bundle_identifier=APP_ID,
        version=APP_VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleIdentifier": APP_ID,
            "CFBundleVersion": APP_VERSION,
            "CFBundleShortVersionString": APP_VERSION,
            "LSMinimumSystemVersion": "13.0",
            # Designer needs Screen Recording for the in-app preview window
            # and for the texture-transfer pipeline's reference-image grabs.
            "NSScreenCaptureUsageDescription": (
                "Elysium Designer captures the screen so the Aether agent "
                "and the preview window can render your skin in real time."
            ),
            # Tablet / pen / touch input via PointerEvents on macOS 13+.
            "NSDesktopFolderUsageDescription": (
                "Elysium Designer needs access to user folders to save and "
                "load .esk skin bundles."
            ),
            "LSApplicationCategoryType": "public.app-category.graphics-design",
            "NSHighResolutionCapable": True,
            "NSSupportsAutomaticGraphicsSwitching": True,
        },
    )
elif sys.platform.startswith("win"):
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name="ElysiumDesigner",
        debug=False, bootloader_ignore_signals=False,
        strip=False, upx=False, console=False,
        icon=ICON_WIN or None,
        version=str(REPO_ROOT / "scripts" / "windows-version-info.txt")
            if (REPO_ROOT / "scripts" / "windows-version-info.txt").exists()
            else None,
    )
else:
    # Linux: standalone executable. release-designer.yml wraps the COLLECT
    # output into AppImage, .deb, and .rpm artifacts.
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="ElysiumDesigner",
        debug=False, bootloader_ignore_signals=False,
        strip=False, upx=False, console=False,
    )
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=False, upx_exclude=[],
        name="ElysiumDesigner",
    )
