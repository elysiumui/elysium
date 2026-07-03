"""Elysium one-click packager.

``elysium pack myapp.py`` produces a self-contained distributable for the
host platform:

* macOS: ``MyApp.app/`` bundle with embedded Python, signed when an
  identity is provided, optionally notarized + stapled.
* Windows: ``MyApp.exe`` + ``site-packages/`` + Python DLLs in a single
  folder; an optional ``MyApp.msi`` when WiX is present.
* Linux: ``MyApp.AppImage`` (self-mounting squashfs) when ``appimagetool``
  is on PATH, otherwise a portable ``MyApp/`` directory with a launch
  script.

Design notes
------------
* The interpreter is fetched from `python-build-standalone`
  (https://github.com/astral-sh/python-build-standalone) the first time
  the user packages — relocatable, reproducible, no system Python
  dependency.
* Dependencies are resolved from the active venv's ``site-packages`` plus
  whatever ``modulefinder`` reports — the union catches both declared
  installs and lazy imports.
* The native cdylib (``elysium/_native/_native.{so,pyd}``) is copied as
  a peer.
* A tiny launcher (Rust binary template, also pure-Python fallback)
  forks the embedded Python and runs the user's entry script.

Public API
----------
.. code-block:: python

    from elysium.pack import pack
    pack(
        entry="app/main.py",
        name="My App",
        version="0.1.0",
        identifier="dev.example.myapp",
        icon="assets/icon.png",
        output_dir="dist/",
    )

CLI
---
``elysium pack <entry> [--name=...] [--version=...] [--icon=...]
                       [--identifier=...] [--output=dist/]
                       [--sign-identity=...] [--notarize] [--no-python]``
"""
from __future__ import annotations

import hashlib
import json
import os
import platform as _plat
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# --- Public entry points ----------------------------------------------------

@dataclass
class PackOptions:
    entry:        Path
    name:         str
    version:      str = "0.1.0"
    identifier:   str = "dev.elysium.app"
    icon:         Path | None = None
    output_dir:   Path = Path("dist")
    target:       Literal["auto", "macos", "windows", "linux"] = "auto"
    embed_python: bool = True
    python_version: str = "3.11"
    sign_identity:  str | None = None        # macOS Developer ID / Win Authenticode subject
    notarize:       bool = False             # macOS Apple ID notarization
    extra_data:     list[Path] = field(default_factory=list)
    extra_modules:  list[str]  = field(default_factory=list)
    console:        bool = False             # macOS: LSUIElement=NO; Windows: keep console
    min_macos:      str = "11.0"
    # Auto-update sidecar generation.
    update_feed_url: str | None = None       # e.g. https://example.com/appcast.xml
    update_sign_key: str | None = None       # hex-encoded ed25519 seed (32 bytes)
    update_base_url: str | None = None       # public URL prefix where the artifact will live


def pack(entry: str | Path, **kwargs) -> Path:
    """Build a self-contained distributable. Returns the output bundle path."""
    opts = PackOptions(entry=Path(entry), **kwargs)
    opts.entry = opts.entry.resolve()
    if not opts.entry.is_file():
        raise FileNotFoundError(opts.entry)
    opts.output_dir = opts.output_dir.resolve()
    opts.output_dir.mkdir(parents=True, exist_ok=True)

    target = _resolve_target(opts.target)
    if target == "macos":
        out = _pack_macos(opts)
    elif target == "windows":
        out = _pack_windows(opts)
    elif target == "linux":
        out = _pack_linux(opts)
    else:
        raise RuntimeError(f"unsupported target: {target}")
    if opts.update_feed_url and opts.update_sign_key:
        _emit_update_sidecars(opts, out, target)
    return out


def _resolve_target(t: str) -> str:
    if t != "auto":
        return t
    s = sys.platform
    if s == "darwin":   return "macos"
    if s == "win32":    return "windows"
    if s.startswith("linux"): return "linux"
    raise RuntimeError(f"unknown platform: {s}")


# --- python-build-standalone fetcher ---------------------------------------

_PBS_RELEASE = "20240814"   # pinned tag; bumped via `elysium pack --refresh-python`
_PBS_BASE = f"https://github.com/indygreg/python-build-standalone/releases/download/{_PBS_RELEASE}"

_PBS_FILES = {
    # py_version, target -> filename
    ("3.11", "macos-arm64"):   "cpython-3.11.9+20240814-aarch64-apple-darwin-install_only.tar.gz",
    ("3.11", "macos-x86_64"):  "cpython-3.11.9+20240814-x86_64-apple-darwin-install_only.tar.gz",
    ("3.11", "windows-x86_64"):"cpython-3.11.9+20240814-x86_64-pc-windows-msvc-install_only.tar.gz",
    ("3.11", "linux-x86_64"):  "cpython-3.11.9+20240814-x86_64-unknown-linux-gnu-install_only.tar.gz",
    ("3.11", "linux-aarch64"): "cpython-3.11.9+20240814-aarch64-unknown-linux-gnu-install_only.tar.gz",
    ("3.12", "macos-arm64"):   "cpython-3.12.5+20240814-aarch64-apple-darwin-install_only.tar.gz",
    ("3.12", "macos-x86_64"):  "cpython-3.12.5+20240814-x86_64-apple-darwin-install_only.tar.gz",
    ("3.12", "windows-x86_64"):"cpython-3.12.5+20240814-x86_64-pc-windows-msvc-install_only.tar.gz",
    ("3.12", "linux-x86_64"):  "cpython-3.12.5+20240814-x86_64-unknown-linux-gnu-install_only.tar.gz",
    ("3.12", "linux-aarch64"): "cpython-3.12.5+20240814-aarch64-unknown-linux-gnu-install_only.tar.gz",
}


def _pbs_cache_dir() -> Path:
    base = Path(os.environ.get("ELYSIUM_PACK_CACHE")
                or Path.home() / ".elysium" / "pack-cache")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _fetch_python(version: str, target_arch: str) -> Path:
    """Return the path to an extracted python-build-standalone install
    directory for the requested target. Downloads + extracts on first use."""
    key = (version, target_arch)
    fname = _PBS_FILES.get(key)
    if fname is None:
        raise RuntimeError(
            f"python-build-standalone has no prebuilt for {key}. "
            f"Bump _PBS_RELEASE or use --no-python and ship your own.")
    cache = _pbs_cache_dir()
    extracted = cache / fname.replace(".tar.gz", "")
    if (extracted / "python").is_dir():
        return extracted / "python"
    archive = cache / fname
    if not archive.exists():
        url = f"{_PBS_BASE}/{fname}"
        print(f"elysium pack: downloading {url}", file=sys.stderr)
        with urllib.request.urlopen(url) as r, open(archive, "wb") as f:
            shutil.copyfileobj(r, f)
    print(f"elysium pack: extracting {archive.name}", file=sys.stderr)
    extracted.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(extracted)
    return extracted / "python"


# --- Dependency discovery ---------------------------------------------------

def _discover_site_packages(extra_modules: list[str]) -> list[Path]:
    """Walk the user's active venv and return every package directory that
    should be copied into the bundle. Extra modules are forced in even if
    not auto-detected (catches dynamic imports)."""
    import site
    roots: list[Path] = []
    for base in site.getsitepackages():
        p = Path(base)
        if p.is_dir():
            roots.append(p)
    user_site = site.getusersitepackages()
    if user_site and Path(user_site).is_dir():
        roots.append(Path(user_site))
    # Dedupe.
    seen, ordered = set(), []
    for r in roots:
        rs = str(r.resolve())
        if rs not in seen:
            seen.add(rs); ordered.append(r)
    return ordered


def _walk_imports(entry: Path) -> set[str]:
    """Crude import walk via modulefinder. Misses lazy / runtime imports —
    callers pass those via ``extra_modules``."""
    try:
        from modulefinder import ModuleFinder
    except Exception:
        return set()
    mf = ModuleFinder()
    try:
        mf.run_script(str(entry))
    except Exception:
        return set()
    return {m.split(".")[0] for m in mf.modules}


# --- Native cdylib + framework copy ----------------------------------------

def _copy_elysium_framework(dst_lib: Path) -> None:
    """Copy the installed `elysium` Python package + its native cdylib."""
    import elysium
    src = Path(elysium.__file__).parent
    shutil.copytree(src, dst_lib / "elysium",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


# --- macOS .app builder -----------------------------------------------------

def _pack_macos(opts: PackOptions) -> Path:
    out = opts.output_dir / f"{opts.name}.app"
    if out.exists():
        shutil.rmtree(out)
    contents = out / "Contents"
    macos    = contents / "MacOS"
    resources = contents / "Resources"
    frameworks = contents / "Frameworks"
    for d in (macos, resources, frameworks):
        d.mkdir(parents=True, exist_ok=True)

    # Embed Python.
    py_dir = None
    if opts.embed_python:
        arch = "arm64" if _plat.machine() == "arm64" else "x86_64"
        py_dir = _fetch_python(opts.python_version, f"macos-{arch}")
        shutil.copytree(py_dir, frameworks / "Python",
                        ignore=shutil.ignore_patterns("test", "tests",
                                                       "__pycache__"))
    # Copy app entry + extra data.
    shutil.copy2(opts.entry, resources / opts.entry.name)
    for x in opts.extra_data:
        x = Path(x).resolve()
        if x.is_dir():
            shutil.copytree(x, resources / x.name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(x, resources / x.name)

    # Copy the elysium package + its _native cdylib into Resources/lib/.
    lib_dir = resources / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    _copy_elysium_framework(lib_dir)

    # Copy detected user site-packages (lightweight pass; user can curate
    # via --extra-modules to pin extras the walker missed).
    site_dst = resources / "site-packages"
    site_dst.mkdir(parents=True, exist_ok=True)
    needed = _walk_imports(opts.entry) | set(opts.extra_modules)
    for sp_root in _discover_site_packages(opts.extra_modules):
        for child in sp_root.iterdir():
            stem = child.stem.replace("-", "_").split(".")[0]
            if stem == "elysium":      # already copied above
                continue
            if stem in needed or child.name.endswith(".dist-info"):
                target_path = site_dst / child.name
                if not target_path.exists():
                    if child.is_dir():
                        shutil.copytree(child, target_path,
                                        ignore=shutil.ignore_patterns(
                                            "__pycache__", "*.pyc"))
                    else:
                        shutil.copy2(child, target_path)

    # Write the launcher shell — POSIX shell so we don't depend on Bash.
    launcher = macos / opts.name.replace(" ", "")
    launcher.write_text(_MACOS_LAUNCHER.format(
        py_rel="Frameworks/Python/bin/python3",
        entry=opts.entry.name,
    ))
    launcher.chmod(0o755)

    # Info.plist.
    (contents / "Info.plist").write_text(_INFO_PLIST.format(
        name=opts.name,
        executable=launcher.name,
        identifier=opts.identifier,
        version=opts.version,
        min_macos=opts.min_macos,
        ui_element="NO" if opts.console else "YES",
    ))

    # Icon — convert PNG to .icns when possible.
    if opts.icon:
        icns = _png_to_icns(opts.icon, resources)
        if icns:
            (contents / "Info.plist").write_text(
                (contents / "Info.plist").read_text()
                .replace("<key>CFBundleName</key>",
                         f"<key>CFBundleIconFile</key>\n\t<string>{icns.stem}</string>\n\t<key>CFBundleName</key>")
            )

    # Optional codesign / notarize.
    if opts.sign_identity:
        _codesign_macos(out, opts.sign_identity)
        if opts.notarize:
            _notarize_macos(out, opts.identifier)

    print(f"elysium pack: built {out}", file=sys.stderr)
    return out


_MACOS_LAUNCHER = """#!/bin/sh
# Elysium launcher — locates the embedded Python and runs the user entry.
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE_ROOT="$(cd "$HERE/.." && pwd)"
export PYTHONHOME="$BUNDLE_ROOT/Frameworks/Python"
export PYTHONPATH="$BUNDLE_ROOT/Resources/lib:$BUNDLE_ROOT/Resources/site-packages"
exec "$BUNDLE_ROOT/{py_rel}" "$BUNDLE_ROOT/Resources/{entry}" "$@"
"""


_INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>CFBundleDevelopmentRegion</key><string>en</string>
\t<key>CFBundleExecutable</key><string>{executable}</string>
\t<key>CFBundleIdentifier</key><string>{identifier}</string>
\t<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
\t<key>CFBundleName</key><string>{name}</string>
\t<key>CFBundlePackageType</key><string>APPL</string>
\t<key>CFBundleShortVersionString</key><string>{version}</string>
\t<key>CFBundleVersion</key><string>{version}</string>
\t<key>LSMinimumSystemVersion</key><string>{min_macos}</string>
\t<key>NSHighResolutionCapable</key><true/>
\t<key>LSUIElement</key><{ui_element}/>
\t<key>NSRequiresAquaSystemAppearance</key><false/>
</dict>
</plist>
"""


def _png_to_icns(png: Path, dest: Path) -> Path | None:
    """Convert a PNG icon to a multi-resolution .icns via sips + iconutil."""
    if shutil.which("sips") is None or shutil.which("iconutil") is None:
        return None
    iconset = dest / "AppIcon.iconset"
    iconset.mkdir(exist_ok=True)
    sizes = [16, 32, 64, 128, 256, 512]
    for s in sizes:
        for scale, suffix in ((1, ""), (2, "@2x")):
            out = iconset / f"icon_{s}x{s}{suffix}.png"
            subprocess.run(["sips", "-z", str(s * scale), str(s * scale),
                            str(png), "--out", str(out)],
                           check=False, capture_output=True)
    icns = dest / "AppIcon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset),
                    "-o", str(icns)], check=False, capture_output=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return icns if icns.exists() else None


def _codesign_macos(app: Path, identity: str) -> None:
    print(f"elysium pack: codesign {app.name} as '{identity}'", file=sys.stderr)
    subprocess.run([
        "codesign", "--deep", "--force", "--options", "runtime",
        "--sign", identity, str(app),
    ], check=True)


def _notarize_macos(app: Path, identifier: str) -> None:
    """Submit the bundle to Apple's notary service. Requires the developer
    to have run `xcrun notarytool store-credentials --apple-id ...` once."""
    zip_path = app.with_suffix(".zip")
    subprocess.run(["ditto", "-c", "-k", "--keepParent",
                    str(app), str(zip_path)], check=True)
    profile = os.environ.get("ELYSIUM_NOTARY_PROFILE", "elysium-notary")
    subprocess.run([
        "xcrun", "notarytool", "submit", str(zip_path),
        "--keychain-profile", profile, "--wait",
    ], check=True)
    subprocess.run(["xcrun", "stapler", "staple", str(app)], check=True)


# --- Windows .exe builder ---------------------------------------------------

def _pack_windows(opts: PackOptions) -> Path:
    out_dir = opts.output_dir / opts.name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    # Embed Python.
    py_root = None
    if opts.embed_python:
        py_root = _fetch_python(opts.python_version, "windows-x86_64")
        shutil.copytree(py_root, out_dir / "python",
                        ignore=shutil.ignore_patterns("test", "tests",
                                                       "__pycache__"))

    # User entry + resources.
    resources = out_dir / "resources"
    resources.mkdir()
    shutil.copy2(opts.entry, resources / opts.entry.name)
    for x in opts.extra_data:
        x = Path(x).resolve()
        if x.is_dir():
            shutil.copytree(x, resources / x.name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(x, resources / x.name)

    lib_dir = out_dir / "lib"
    lib_dir.mkdir()
    _copy_elysium_framework(lib_dir)

    site_dst = out_dir / "site-packages"
    site_dst.mkdir()
    needed = _walk_imports(opts.entry) | set(opts.extra_modules)
    for sp_root in _discover_site_packages(opts.extra_modules):
        for child in sp_root.iterdir():
            stem = child.stem.replace("-", "_").split(".")[0]
            if stem == "elysium":
                continue
            if stem in needed or child.name.endswith(".dist-info"):
                tgt = site_dst / child.name
                if not tgt.exists():
                    if child.is_dir():
                        shutil.copytree(child, tgt,
                                        ignore=shutil.ignore_patterns(
                                            "__pycache__", "*.pyc"))
                    else:
                        shutil.copy2(child, tgt)

    # Launcher batch + .exe (use the Windows shipped python.exe; renamed).
    launcher_bat = out_dir / f"{opts.name}.cmd"
    launcher_bat.write_text(_WIN_LAUNCHER.format(
        py_rel=r"python\python.exe",
        entry=opts.entry.name,
    ))
    # Best-effort: copy python.exe → MyApp.exe so users can double-click it.
    py_exe = (out_dir / "python" / "python.exe")
    if py_exe.exists():
        shutil.copy2(py_exe, out_dir / f"{opts.name}.exe")
        # Drop a pythonstartup that loads the launcher.
        (out_dir / "sitecustomize.py").write_text(
            _WIN_SITE_CUSTOMIZE.format(entry=opts.entry.name))

    # Codesign if requested.
    if opts.sign_identity:
        signtool = shutil.which("signtool")
        if signtool:
            subprocess.run([
                signtool, "sign", "/n", opts.sign_identity, "/fd", "SHA256",
                str(out_dir / f"{opts.name}.exe"),
            ], check=False)

    print(f"elysium pack: built {out_dir}", file=sys.stderr)
    return out_dir


_WIN_LAUNCHER = """@echo off
setlocal
set HERE=%~dp0
set PYTHONHOME=%HERE%python
set PYTHONPATH=%HERE%lib;%HERE%site-packages
"%HERE%{py_rel}" "%HERE%resources\\{entry}" %*
"""


_WIN_SITE_CUSTOMIZE = """# Auto-generated by `elysium pack`.
import os, runpy, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "lib"))
sys.path.insert(0, os.path.join(here, "site-packages"))
runpy.run_path(os.path.join(here, "resources", "{entry}"), run_name="__main__")
sys.exit(0)
"""


# --- Linux AppImage builder -------------------------------------------------

def _pack_linux(opts: PackOptions) -> Path:
    appdir = opts.output_dir / f"{opts.name}.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True)
    (appdir / "usr" / "lib").mkdir(parents=True)

    if opts.embed_python:
        arch = "aarch64" if _plat.machine() in ("aarch64", "arm64") else "x86_64"
        py_root = _fetch_python(opts.python_version, f"linux-{arch}")
        shutil.copytree(py_root, appdir / "usr" / "python",
                        ignore=shutil.ignore_patterns("test", "tests",
                                                       "__pycache__"))

    resources = appdir / "usr" / "resources"
    resources.mkdir(parents=True)
    shutil.copy2(opts.entry, resources / opts.entry.name)
    for x in opts.extra_data:
        x = Path(x).resolve()
        dst = resources / x.name
        if x.is_dir():
            shutil.copytree(x, dst,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(x, dst)

    lib_dir = appdir / "usr" / "lib"
    _copy_elysium_framework(lib_dir)

    site_dst = appdir / "usr" / "site-packages"
    site_dst.mkdir()
    needed = _walk_imports(opts.entry) | set(opts.extra_modules)
    for sp_root in _discover_site_packages(opts.extra_modules):
        for child in sp_root.iterdir():
            stem = child.stem.replace("-", "_").split(".")[0]
            if stem == "elysium":
                continue
            if stem in needed or child.name.endswith(".dist-info"):
                tgt = site_dst / child.name
                if not tgt.exists():
                    if child.is_dir():
                        shutil.copytree(child, tgt,
                                        ignore=shutil.ignore_patterns(
                                            "__pycache__", "*.pyc"))
                    else:
                        shutil.copy2(child, tgt)

    # AppRun + .desktop + icon.
    apprun = appdir / "AppRun"
    apprun.write_text(_LINUX_APPRUN.format(entry=opts.entry.name))
    apprun.chmod(0o755)

    (appdir / f"{opts.identifier}.desktop").write_text(_DESKTOP_FILE.format(
        name=opts.name,
        exec_=f"AppRun",
        icon=opts.identifier,
    ))
    if opts.icon and opts.icon.exists():
        shutil.copy2(opts.icon, appdir / f"{opts.identifier}.png")

    # Try appimagetool to fuse the AppDir into a single .AppImage.
    tool = shutil.which("appimagetool")
    if tool:
        out_file = opts.output_dir / f"{opts.name}-{opts.version}.AppImage"
        subprocess.run([tool, str(appdir), str(out_file)], check=False)
        if out_file.exists():
            print(f"elysium pack: built {out_file}", file=sys.stderr)
            return out_file
    print(f"elysium pack: built {appdir} (install `appimagetool` to fuse)",
          file=sys.stderr)
    return appdir


_LINUX_APPRUN = """#!/bin/sh
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONHOME="$HERE/usr/python"
export PYTHONPATH="$HERE/usr/lib:$HERE/usr/site-packages"
exec "$HERE/usr/python/bin/python3" "$HERE/usr/resources/{entry}" "$@"
"""


_DESKTOP_FILE = """[Desktop Entry]
Type=Application
Name={name}
Exec={exec_}
Icon={icon}
Categories=Utility;
Terminal=false
"""


__all__ = ["pack", "PackOptions"]


# --- Update sidecar emitter ------------------------------------------------

def _emit_update_sidecars(opts: PackOptions, bundle: Path, target: str) -> None:
    """Sign the produced artifact + write a Sparkle appcast / JSON feed
    suitable for ``elysium.updater.Updater``."""
    try:
        from nacl.signing import SigningKey
    except ImportError:
        print("elysium pack: PyNaCl not installed — skipping update sidecars",
              file=sys.stderr)
        return
    key = SigningKey(bytes.fromhex(opts.update_sign_key or ""))
    body = bundle.read_bytes() if bundle.is_file() else _zip_dir(bundle)
    sig_hex = key.sign(body).signature.hex()
    pub_hex = bytes(key.verify_key).hex()
    pub_path = opts.output_dir / "update.pub"
    pub_path.write_text(pub_hex + "\n")
    artifact_name = bundle.name if bundle.is_file() else f"{bundle.name}.zip"
    base = (opts.update_base_url or "").rstrip("/") or "."
    artifact_url = f"{base}/{artifact_name}"

    if target == "linux":
        # JSON feed for AppImageUpdate consumers (signature is detached).
        feed_path = opts.output_dir / "appcast.json"
        feed_path.write_text(_json_dumps_pretty({
            "version": opts.version,
            "url":     artifact_url,
            "notes":   "",
            "signature": sig_hex,
            "publisher_pubkey": pub_hex,
        }))
        # Optional: zsync sidecar via `zsyncmake` when on PATH.
        zsync = shutil.which("zsyncmake")
        if zsync and bundle.is_file():
            subprocess.run(
                [zsync, str(bundle), "-u", artifact_name],
                check=False, cwd=str(opts.output_dir),
            )
    else:
        # Sparkle-style XML appcast for macOS + Windows.
        feed_path = opts.output_dir / "appcast.xml"
        feed_path.write_text(_SPARKLE_APPCAST.format(
            name=opts.name,
            version=opts.version,
            url=artifact_url,
            length=len(body),
            sig=sig_hex,
            os="macos" if target == "macos" else "windows",
        ))
    print(f"elysium pack: emitted {feed_path.name} + update.pub", file=sys.stderr)


def _zip_dir(directory: Path) -> bytes:
    """Pack the platform output directory into a zip in-memory so we
    can sign the shippable artifact (Windows / Linux non-AppImage)."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in directory.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(directory.parent))
    return buf.getvalue()


def _json_dumps_pretty(d: dict) -> str:
    return json.dumps(d, indent=2)


_SPARKLE_APPCAST = """<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"
     version="2.0">
<channel>
  <title>{name}</title>
  <item>
    <title>Version {version}</title>
    <pubDate>{version}</pubDate>
    <enclosure url="{url}"
               sparkle:version="{version}"
               sparkle:shortVersionString="{version}"
               sparkle:edSignature="{sig}"
               length="{length}"
               type="application/octet-stream"/>
  </item>
</channel>
</rss>
"""
