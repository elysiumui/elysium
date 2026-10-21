#!/usr/bin/env python3
"""Fetch WebView2Loader.dll for the Windows WebView backend.

Usage:  python scripts/fetch-webview2-loader.py [--cache DIR]

Downloads the pinned Microsoft.Web.WebView2 NuGet package, checks its
SHA-256, and copies the loader for x64 and arm64 plus its licence into
``python/elysium/webview/_win/`` (gitignored; ``pyproject.toml`` includes
it in the wheel explicitly). Run it before ``maturin build`` on Windows;
CI does. The loader is BSD-licensed and redistributable with its notice,
which travels next to it as ``WebView2Loader.LICENSE.txt``.

It also re-checks ``python/elysium/webview/_webview2_abi.py`` against the
package's ``WebView2.h``: every vtable slot and IID the backend uses must
match the header, or the script fails instead of a COM call landing on
the wrong method at runtime. Works on any OS.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import runpy
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.0.4258.31"
SHA256 = "56f7f4b8bf9aee4b8efefbbdd4f67d5f74ebd1b100ed0806da71bf76af481aa9"
URL = (f"https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{VERSION}/"
       f"microsoft.web.webview2.{VERSION}.nupkg")

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "python" / "elysium" / "webview" / "_win"
ABI = ROOT / "python" / "elysium" / "webview" / "_webview2_abi.py"
LOADERS = {
    "x64": "runtimes/win-x64/native/WebView2Loader.dll",
    "arm64": "runtimes/win-arm64/native/WebView2Loader.dll",
}


def fetch(cache: Path) -> bytes:
    cached = cache / f"microsoft.web.webview2.{VERSION}.nupkg"
    if cached.is_file():
        data = cached.read_bytes()
        if hashlib.sha256(data).hexdigest() == SHA256:
            return data
    with urllib.request.urlopen(URL, timeout=120) as r:
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        sys.exit(f"SHA-256 mismatch for {URL}: got {digest}, expected {SHA256}")
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def check_abi(header: str) -> list[str]:
    abi = runpy.run_path(str(ABI))
    if abi["SDK_VERSION"] != VERSION:
        return [f"_webview2_abi.SDK_VERSION is {abi['SDK_VERSION']}, the pinned SDK is {VERSION}"]
    problems = []
    for iface, methods in abi["SLOTS"].items():
        m = re.search(r"typedef struct %sVtbl\s*\{(.*?)END_INTERFACE" % re.escape(iface), header, re.S)
        if not m:
            problems.append(f"{iface}: no vtable in WebView2.h")
            continue
        order = re.findall(r"\*\s*(\w+)\s*\)\s*\(", m.group(1))
        for method, slot in methods.items():
            actual = order.index(method) if method in order else None
            if actual != slot:
                problems.append(f"{iface}.{method}: slot {slot} in _webview2_abi.py, {actual} in WebView2.h")
    for iface, iid in abi["IIDS"].items():
        m = re.search(r'MIDL_INTERFACE\("([0-9a-fA-F-]+)"\)\s*%s\s*:' % re.escape(iface), header)
        if not m or m.group(1).lower() != iid:
            problems.append(f"{iface}: IID {iid} in _webview2_abi.py, {m.group(1) if m else None} in WebView2.h")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=ROOT / "build" / "webview2",
                    help="where the downloaded package is kept (default: build/webview2)")
    args = ap.parse_args()

    package = zipfile.ZipFile(io.BytesIO(fetch(args.cache)))
    problems = check_abi(package.read("build/native/include/WebView2.h").decode("utf-8", "replace"))
    if problems:
        sys.exit("WebView2 ABI table does not match the SDK header:\n  " + "\n  ".join(problems))

    for arch, member in LOADERS.items():
        target = DEST / arch / "WebView2Loader.dll"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(package.read(member))
    (DEST / "WebView2Loader.LICENSE.txt").write_bytes(package.read("LICENSE.txt"))
    print(f"WebView2 SDK {VERSION}: ABI table verified; loader for {', '.join(LOADERS)} in {DEST}")


if __name__ == "__main__":
    main()
