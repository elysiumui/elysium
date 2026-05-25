"""Build a single-file executable for the Designer or any example.

Usage (run on each target OS  PyInstaller does not cross-compile):

    python scripts/build.py designer
    python scripts/build.py example butterfly
    python scripts/build.py example hello
    python scripts/build.py example agent-cursor
    python scripts/build.py example components
    python scripts/build.py example snapshot-relay

    # List every buildable target on stdout (handy for CI matrices).
    python scripts/build.py --list

Output:
    dist/<os>/<AppName>[.exe]

Cross-OS strategy:
    Run this script on each target OS. The GitHub Actions workflow at
    .github/workflows/build-binaries.yml runs it on macos-latest,
    windows-latest, and ubuntu-latest in parallel and uploads the
    artifacts to a Release.

Prerequisites:
    pip install -e ".[build]"       # installs pyinstaller + maturin

The native PyO3 extension is rebuilt automatically on every invocation
(incremental — cargo skips work when nothing changed). Pass
`--skip-native` if you've just rebuilt it yourself.

Why --onefile:
    Produces ONE binary per OS instead of a folder tree. Slower first
    launch (the binary self-extracts into a temp dir), but the
    distribution story is just "ship this file."
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
DESIGNER_DIR = REPO_ROOT / "elysium-designer"
PY_SRC = REPO_ROOT / "python"


# ---------------------------------------------------------------------------
# OS / output naming

def _os_tag() -> str:
    """Short tag used in the dist/ subdir name: macos | windows | linux."""
    sysname = platform.system().lower()
    if sysname == "darwin": return "macos"
    if sysname == "windows": return "windows"
    return "linux"


def _exe_suffix() -> str:
    return ".exe" if _os_tag() == "windows" else ""


# ---------------------------------------------------------------------------
# Hidden-import + bundled-data shared between Designer and every example.

# The native PyO3 extension + every dynamically-imported plugin that
# PyInstaller's static analysis would otherwise miss.
FRAMEWORK_HIDDEN_IMPORTS = [
    "elysium._native",
    "elysium._native._native",
    # `elysium.dock` is lazy-imported by IconFlapper for the animated
    # Dock / Taskbar icon swap; PyInstaller's static analysis misses it.
    "elysium.dock",
    # Brush engines (registered at import time).
    "elysium.brush.engines.round_stamp",
    "elysium.brush.engines.wet_mix",
    "elysium.brush.engines.bristle",
    "elysium.brush.engines.airbrush",
    "elysium.brush.engines.pattern",
    "elysium.brush.engines.texture",
    # AI providers (loaded by name from settings).
    "elysium.ai.anthropic",
    "elysium.ai.openai",
    "elysium.ai.ollama",
    "elysium.ai.stub",
    # Scientific-stack roots. These ARE imported statically by the
    # framework + Designer (image ops, brush math, paint masks, photo
    # asset prep, PBR pipeline), but PyInstaller's static analysis
    # misses them on Windows when numpy is wrapped in try/except for
    # graceful-degradation paths. Enumerating them here is belt-and-
    # suspenders for the .exe — without it, the Designer launches and
    # then dies with "No module named 'numpy'" the first time anything
    # touches an image.
    "numpy",
    "numpy.core._methods",
    "numpy.core._dtype_ctypes",
    "numpy.core.multiarray",
    "scipy",
    "scipy.ndimage",
    "scipy.spatial",
    "scipy.linalg",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFilter",
    "skimage",
    "skimage.color",
    "skimage.filters",
    "skimage.morphology",
    "skimage.transform",
]

# Designer-only hidden imports. The `elysium.aether` subpackage is
# imported lazily from inside `_open_aether_panel` and the bridge
# startup try-block; PyInstaller's static analysis misses both, so we
# enumerate the whole subtree here. Same story for `elysium.codelink`
# (lazy-loaded by the Code menu).
def _aether_submodules() -> list[str]:
    """Walk python/elysium/aether/ and emit every .py module's import
    path. Runs at build time, not at bundle runtime."""
    root = REPO_ROOT / "python" / "elysium" / "aether"
    if not root.is_dir():
        return []
    out = ["elysium.aether"]
    for p in root.rglob("*.py"):
        rel = p.relative_to(root.parent.parent)  # "elysium/aether/.../x.py"
        mod = rel.with_suffix("").as_posix().replace("/", ".")
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        out.append(mod)
    return sorted(set(out))


DESIGNER_HIDDEN_IMPORTS = _aether_submodules() + ["elysium.codelink"]


# ---------------------------------------------------------------------------
# Target definitions

class Target:
    """One buildable app: entry script, source roots, data files, name."""
    def __init__(self, *, name: str, entry: Path,
                  extra_paths: list[Path],
                  datas: list[tuple[str, str]],
                  hidden_imports: list[str],
                  icon: Path | None = None) -> None:
        self.name = name
        self.entry = entry
        self.extra_paths = extra_paths
        self.datas = datas
        self.hidden_imports = hidden_imports
        self.icon = icon


def _designer_icon() -> Path | None:
    """Pick the right icon file for the current OS, or None if the
    pre-generated icon assets are missing (run scripts/generate-icons.py
    first to populate elysium-designer/assets/)."""
    assets = DESIGNER_DIR / "assets"
    by_os = {
        "macos":   assets / "ElysiumDesigner.icns",
        "windows": assets / "ElysiumDesigner.ico",
        "linux":   assets / "ElysiumDesigner.png",
    }
    icon = by_os.get(_os_tag())
    return icon if icon and icon.is_file() else None


def _designer_target() -> Target:
    chrome = DESIGNER_DIR / "designer-chrome.esk"
    datas: list[tuple[str, str]] = [
        # Hyphenated sibling modules — bundled as data + reachable via
        # the runtime hook below.
        (str(DESIGNER_DIR / "menus.py"),     "elysium-designer"),
        (str(DESIGNER_DIR / "importers.py"), "elysium-designer"),
        # The default chrome bundle the Designer loads at launch.
        (str(chrome), "elysium-designer/designer-chrome.esk"),
        # Static icon master + wing-flap frame sequence (read by
        # IconFlapper at runtime to animate the Dock / Taskbar icon).
        (str(DESIGNER_DIR / "assets"),
            "elysium-designer/assets"),
        # Brush presets / thumbnails the first launch needs.
        (str(PY_SRC / "elysium" / "brush" / "builtin"),
            "elysium/brush/builtin"),
        # Ship a couple of bundled example skins so the welcome screen
        # has something to open.
        (str(EXAMPLES_DIR / "hello" / "hello.esk"),
            "examples/hello/hello.esk"),
        (str(EXAMPLES_DIR / "butterfly" / "butterfly.esk"),
            "examples/butterfly/butterfly.esk"),
    ]
    return Target(
        name="ElysiumDesigner",
        entry=DESIGNER_DIR / "__main__.py",
        extra_paths=[PY_SRC, DESIGNER_DIR],
        datas=datas,
        hidden_imports=FRAMEWORK_HIDDEN_IMPORTS + DESIGNER_HIDDEN_IMPORTS,
        icon=_designer_icon(),
    )


def _example_entry(folder: Path) -> Path | None:
    """Pick the example's entry script. Convention: main.py >
    __main__.py > <folder>.py > showcase.py."""
    for cand in (
        folder / "main.py",
        folder / "__main__.py",
        folder / f"{folder.name}.py",
        folder / "showcase.py",
    ):
        if cand.is_file(): return cand
    # Fallback: first non-dunder .py file at top level.
    for p in sorted(folder.glob("*.py")):
        if not p.name.startswith("_"): return p
    return None


def _example_target(folder_name: str) -> Target:
    folder = EXAMPLES_DIR / folder_name
    if not folder.is_dir():
        raise SystemExit(f"Example folder not found: {folder}")
    entry = _example_entry(folder)
    if entry is None:
        raise SystemExit(f"No entry script found in {folder}")
    # Bundle the whole example folder as data so any sibling .esk /
    # .png / .3ds / .blend ships alongside the entry.
    skip = {"__pycache__", ".pytest_cache", "dist", "build"}
    datas: list[tuple[str, str]] = []
    for child in sorted(folder.iterdir()):
        if child.name in skip: continue
        # The entry script itself is loaded by PyInstaller; siblings
        # ship as data.
        if child.resolve() == entry.resolve(): continue
        datas.append((str(child), f"examples/{folder_name}"))
    # PascalCase the folder name for the output binary.
    pretty = "".join(part.capitalize() for part in
                      folder_name.replace("_", "-").split("-"))
    return Target(
        name=f"Elysium-{pretty}",
        entry=entry,
        extra_paths=[PY_SRC],
        datas=datas,
        hidden_imports=FRAMEWORK_HIDDEN_IMPORTS,
    )


def _list_targets() -> list[str]:
    out = ["designer"]
    if EXAMPLES_DIR.is_dir():
        for p in sorted(EXAMPLES_DIR.iterdir()):
            if p.is_dir() and _example_entry(p) is not None:
                out.append(f"example:{p.name}")
    return out


# ---------------------------------------------------------------------------
# Runtime hook  makes hyphenated `elysium-designer/` importable as a
# package by appending the bundled copy to sys.path on first launch.

_RUNTIME_HOOK_TEMPLATE = """\
# Auto-generated by scripts/build.py. Adds the bundled hyphenated
# package directories to sys.path so `import menus` (from inside
# elysium-designer/__main__.py) resolves at runtime.
import sys, os
_base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
for sub in ({paths}):
    p = os.path.join(_base, sub)
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
"""


def _write_runtime_hook(tmp_dir: Path, paths: list[str]) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    hook = tmp_dir / "_elysium_runtime_hook.py"
    hook.write_text(_RUNTIME_HOOK_TEMPLATE.format(
        paths=", ".join(repr(p) for p in paths)))
    return hook


# ---------------------------------------------------------------------------
# Build invocation

def _check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "PyInstaller is not installed in this venv. Run:\n"
            "    pip install pyinstaller>=6")


def _build_native(*, release: bool = True) -> None:
    """Compile the PyO3 extension via `maturin develop` and install it
    into the active venv.  Cargo's incremental build means subsequent
    runs are a few seconds when nothing changed."""
    if shutil.which("maturin") is None and not _maturin_via_python():
        raise SystemExit(
            "maturin is not installed in this venv. Run:\n"
            "    pip install -e \".[build]\"")
    manifest = REPO_ROOT / "elysium-native" / "crates" / "ely-py" / "Cargo.toml"
    if not manifest.is_file():
        raise SystemExit(f"Cargo manifest missing: {manifest}")
    cmd = [sys.executable, "-m", "maturin", "develop",
             "--manifest-path", str(manifest)]
    if release:
        cmd.append("--release")
    print(f"[build] compiling native extension ({'release' if release else 'debug'})", flush=True)
    print(f"[build] cmd: {' '.join(cmd)}", flush=True)
    subprocess.check_call(cmd, cwd=REPO_ROOT, env=_clean_env())


def _clean_env() -> dict[str, str]:
    """Return a copy of os.environ with the Conda-vs-venv collision
    resolved.  Maturin refuses to proceed when both VIRTUAL_ENV and
    CONDA_PREFIX are set — common when the user has a base Conda
    auto-activated and *also* activates a project .venv.  We pick the
    .venv (matches `sys.executable`) and strip the Conda markers for
    this subprocess only."""
    env = os.environ.copy()
    if env.get("VIRTUAL_ENV") and env.get("CONDA_PREFIX"):
        print("[build] both VIRTUAL_ENV and CONDA_PREFIX set — "
                "keeping VIRTUAL_ENV, stripping CONDA_* for maturin",
                flush=True)
        for key in list(env):
            if key.startswith("CONDA_"):
                env.pop(key, None)
    return env


def _maturin_via_python() -> bool:
    """Return True if `python -m maturin` is runnable, even when no
    `maturin` binary is on PATH (common inside venvs on Windows)."""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "maturin", "--version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _check_native() -> None:
    """Confirm the maturin-built native extension is importable after
    a build — PyInstaller's analysis fails confusingly otherwise."""
    try:
        import elysium._native._native  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            f"The native module elysium._native._native is still not "
            f"importable after `maturin develop` ({e}). Check that the "
            f"active interpreter matches the venv maturin installed into.")


def _build(target: Target, *, clean: bool, debug: bool,
            skip_native: bool, native_debug: bool) -> Path:
    _check_pyinstaller()
    if not skip_native:
        _build_native(release=not native_debug)
    _check_native()

    os_tag = _os_tag()
    dist_dir = REPO_ROOT / "dist" / os_tag
    work_dir = REPO_ROOT / "build" / os_tag / target.name
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    if clean and dist_dir.joinpath(target.name + _exe_suffix()).exists():
        dist_dir.joinpath(target.name + _exe_suffix()).unlink()

    runtime_hook = _write_runtime_hook(
        work_dir,
        paths=[".", "elysium-designer"])

    sep = ";" if os_tag == "windows" else ":"
    add_data_args: list[str] = []
    for src, dst in target.datas:
        add_data_args += ["--add-data", f"{src}{sep}{dst}"]

    hidden_args: list[str] = []
    for h in target.hidden_imports:
        hidden_args += ["--hidden-import", h]

    paths_args: list[str] = []
    for p in target.extra_paths:
        paths_args += ["--paths", str(p)]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean" if clean else "--noconfirm",
        "--name", target.name,
        "--distpath", str(dist_dir),
        "--workpath", str(work_dir),
        "--specpath", str(work_dir),
        "--runtime-hook", str(runtime_hook),
    ]
    if not debug:
        # `--windowed` does two things at once: (a) on Windows it
        # hides the cmd.exe console; (b) on macOS it tells PyInstaller
        # to also wrap the binary in a .app bundle so Finder shows
        # the icon and double-click launches without a Terminal popup.
        # On Linux it's --noconsole (hide the launching terminal).
        cmd.append("--windowed")
    if target.icon is not None:
        cmd += ["--icon", str(target.icon)]
        print(f"[build] icon: {target.icon.relative_to(REPO_ROOT)}",
                flush=True)
    cmd += paths_args
    cmd += add_data_args
    cmd += hidden_args
    cmd.append(str(target.entry))

    print(f"[build] {target.name}  {os_tag}", flush=True)
    print(f"[build] cmd: {' '.join(cmd)}", flush=True)

    subprocess.check_call(cmd, cwd=REPO_ROOT)

    # macOS produces a .app bundle (the native single-distributable
    # — Finder treats the folder as one item, shows the icon, and
    # double-click works). Other OSes produce a plain binary.
    if os_tag == "macos":
        app = dist_dir / f"{target.name}.app"
        binary = app / "Contents" / "MacOS" / target.name
        if not app.is_dir() or not binary.is_file():
            raise SystemExit(f"Expected .app not found: {app}")
        binary.chmod(0o755)
        size = sum(p.stat().st_size for p in app.rglob("*") if p.is_file())
        print(f"[build] OK  {app}  ({size / 1_048_576:.1f} MiB)",
                flush=True)
        return app
    out = dist_dir / (target.name + _exe_suffix())
    if not out.exists():
        raise SystemExit(f"Expected output not found: {out}")
    if os_tag != "windows":
        out.chmod(0o755)
    print(f"[build] OK  {out}  ({out.stat().st_size / 1_048_576:.1f} MiB)",
            flush=True)
    return out


# ---------------------------------------------------------------------------
# CLI

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="build.py",
        description="Single-file builds of the Designer + every example.")
    p.add_argument("kind", nargs="?",
                    choices=("designer", "example"),
                    help="Which app family to build.")
    p.add_argument("name", nargs="?",
                    help="Example folder name (required when kind=example).")
    p.add_argument("--list", action="store_true",
                    help="Print every buildable target and exit.")
    p.add_argument("--clean", action="store_true",
                    help="Delete prior build artifacts first.")
    p.add_argument("--debug", action="store_true",
                    help="Keep console + verbose PyInstaller logs.")
    p.add_argument("--skip-native", action="store_true",
                    help="Don't recompile the PyO3 extension. "
                          "Use when you've just run maturin yourself.")
    p.add_argument("--native-debug", action="store_true",
                    help="Build the native extension in debug mode "
                          "(faster compile, larger / slower binary).")
    args = p.parse_args(argv)

    if args.list:
        for t in _list_targets(): print(t)
        return 0

    if args.kind == "designer":
        target = _designer_target()
    elif args.kind == "example":
        if not args.name:
            p.error("`example` requires the folder name "
                     "(e.g. `python scripts/build.py example butterfly`).")
        target = _example_target(args.name)
    else:
        p.print_help()
        return 2

    _build(target, clean=args.clean, debug=args.debug,
            skip_native=args.skip_native,
            native_debug=args.native_debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
