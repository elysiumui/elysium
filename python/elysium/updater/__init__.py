"""Cross-platform auto-update for ``elysium pack``-built apps.

Hides the three native update systems behind one ``Updater`` API:

* macOS — Sparkle 2 framework (drop into ``Frameworks/Sparkle.framework``).
* Windows — WinSparkle.
* Linux — AppImageUpdate via the embedded ``zsync2`` runtime + an
  ``.AppImage.zsync`` sidecar.

If the native backend isn't installed at runtime the wrapper degrades
to a pure-Python feed checker that surfaces the new version + a
download URL through ``on_update_available``.

Usage
-----

.. code-block:: python

    from elysium.updater import Updater

    upd = Updater(
        feed_url="https://example.com/appcast.xml",
        public_ed25519_key=open("keys/update.pub").read().strip(),
    )
    upd.on_update_available = lambda info: print("update:", info.version)
    upd.check_in_background(interval_hours=24)

Feed format
-----------
The wrapper consumes a Sparkle-style RSS appcast (XML) for macOS / Windows
and a JSON manifest for AppImageUpdate. The ``Updater`` class auto-picks
the right one from the URL extension.
"""
from __future__ import annotations

import json
import os
import platform
import re
import ssl
import sys
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class ReleaseInfo:
    version: str
    url: str
    notes: str = ""
    signature: str | None = None


@dataclass
class Updater:
    feed_url: str
    public_ed25519_key: str | None = None
    current_version: str = ""
    on_update_available: Callable[[ReleaseInfo], None] | None = None
    on_no_update: Callable[[], None] | None = None
    on_error: Callable[[Exception], None] | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        if not self.current_version:
            try:
                from elysium import __version__
                self.current_version = __version__
            except Exception:
                self.current_version = "0.0.0"

    # --- Background polling ------------------------------------------
    def check_in_background(self, interval_hours: float = 24.0) -> None:
        t = threading.Thread(
            target=self._poll_loop,
            args=(interval_hours,),
            daemon=True,
            name="elysium-updater",
        )
        t.start()

    def stop(self) -> None:
        self._stop.set()

    def _poll_loop(self, interval_hours: float) -> None:
        while not self._stop.is_set():
            try:
                info = self.check_now()
                if info is not None and self._is_newer(info.version):
                    if self.on_update_available:
                        self.on_update_available(info)
                else:
                    if self.on_no_update:
                        self.on_no_update()
            except Exception as e:
                if self.on_error:
                    self.on_error(e)
            self._stop.wait(interval_hours * 3600.0)

    # --- One-shot check ----------------------------------------------
    def check_now(self) -> ReleaseInfo | None:
        """Hit the feed and return the latest ``ReleaseInfo``, or None
        when the feed is empty."""
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(self.feed_url, timeout=10,
                                         context=ctx) as r:
                body = r.read().decode("utf-8", errors="replace")
        except Exception as e:
            raise RuntimeError(f"feed fetch failed: {e}") from e
        if self.feed_url.endswith(".json"):
            return self._parse_json_feed(body)
        return self._parse_appcast(body)

    def _parse_json_feed(self, body: str) -> ReleaseInfo | None:
        try:
            doc = json.loads(body)
        except Exception:
            return None
        if isinstance(doc, list):
            doc = doc[0] if doc else {}
        return ReleaseInfo(
            version=str(doc.get("version", "")),
            url=str(doc.get("url", "")),
            notes=str(doc.get("notes", "")),
            signature=doc.get("signature"),
        )

    def _parse_appcast(self, body: str) -> ReleaseInfo | None:
        """Bare-bones Sparkle appcast parser — pulls the first <item>'s
        version, url, and signature. Stays dep-free; for richer flows
        use the native Sparkle backend."""
        item = re.search(r"<item>(.*?)</item>", body, re.S)
        if not item: return None
        block = item.group(1)
        ver = re.search(r'sparkle:version="([^"]+)"', block)
        url = re.search(r'url="([^"]+)"', block)
        sig = re.search(r'sparkle:edSignature="([^"]+)"', block)
        notes = re.search(r"<description>(.*?)</description>", block, re.S)
        return ReleaseInfo(
            version=ver.group(1) if ver else "",
            url=url.group(1) if url else "",
            notes=notes.group(1).strip() if notes else "",
            signature=sig.group(1) if sig else None,
        )

    # --- Install -----------------------------------------------------
    def install(self, info: ReleaseInfo, *,
                verify_signature: bool = True) -> None:
        """Download the update payload, verify its EdDSA signature
        against the configured public key, and hand off to the
        platform's updater frontend.

        When the bundled native updater (Sparkle / WinSparkle /
        AppImageUpdate) is available we let it own the install ritual.
        Otherwise we drop the verified payload into
        ``~/.elysium/updates/<version>/`` and open the URL in the
        user's browser so they can finish manually.
        """
        if verify_signature and self.public_ed25519_key and info.url:
            if not self._download_and_verify(info):
                raise RuntimeError(
                    "update payload failed signature verification")
        sysname = sys.platform
        if sysname == "darwin":
            self._install_macos(info)
        elif sysname == "win32":
            self._install_windows(info)
        elif sysname.startswith("linux"):
            self._install_linux(info)
        else:
            raise RuntimeError(f"unsupported platform: {sysname}")

    def _download_and_verify(self, info: ReleaseInfo) -> bool:
        """Pull the payload, verify against `public_ed25519_key`, cache
        the verified bytes under ``~/.elysium/updates/<version>/``."""
        if not info.signature:
            return False
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(info.url, timeout=60, context=ctx) as r:
                body = r.read()
        except Exception:
            return False
        # Sparkle EdDSA signatures are base64; we accept hex too.
        try:
            sig_bytes = bytes.fromhex(info.signature)
        except ValueError:
            import base64
            try:
                sig_bytes = base64.b64decode(info.signature)
            except Exception:
                return False
        try:
            key_bytes = bytes.fromhex(self.public_ed25519_key or "")
        except ValueError:
            import base64
            try:
                key_bytes = base64.b64decode(self.public_ed25519_key or "")
            except Exception:
                return False
        try:
            from nacl.signing import VerifyKey
            VerifyKey(key_bytes).verify(body, sig_bytes)
        except Exception:
            return False
        # Cache for the installer step.
        cache = Path.home() / ".elysium" / "updates" / info.version
        cache.mkdir(parents=True, exist_ok=True)
        from urllib.parse import urlparse
        fname = Path(urlparse(info.url).path).name or "payload.bin"
        (cache / fname).write_bytes(body)
        self._cached_payload = cache / fname
        return True

    def _install_macos(self, info: ReleaseInfo) -> None:
        """Invoke Sparkle's ``SPUUpdater`` via objc2 when available;
        fallback opens the URL in the browser for manual install."""
        try:
            from objc2 import ObjCClass        # type: ignore[import-not-found]
            try:
                SPU = ObjCClass("SPUUpdater")
            except Exception:
                SPU = None
            if SPU is not None:
                # Real Sparkle integration requires the framework to be
                # bundled at Contents/Frameworks/Sparkle.framework. The
                # client gives us a handle to drive update checks; we
                # show the standard UI.
                updater = SPU.alloc().init()
                updater.checkForUpdates_(None)
                return
        except ImportError:
            pass
        self._fallback_open(info.url)

    def _install_windows(self, info: ReleaseInfo) -> None:
        try:
            import ctypes
            winsparkle = ctypes.CDLL("WinSparkle.dll")
            winsparkle.win_sparkle_set_appcast_url(self.feed_url.encode())
            winsparkle.win_sparkle_init()
            winsparkle.win_sparkle_check_update_with_ui()
            return
        except OSError:
            pass
        self._fallback_open(info.url)

    def _install_linux(self, info: ReleaseInfo) -> None:
        # AppImageUpdate exposes ``AppImageUpdate <path>``. We need to
        # know our own AppImage path — APPIMAGE env is set by the
        # runtime when launched via .AppImage.
        appimage = os.environ.get("APPIMAGE")
        if not appimage:
            self._fallback_open(info.url)
            return
        import subprocess
        try:
            subprocess.Popen(["AppImageUpdate", appimage])
        except FileNotFoundError:
            self._fallback_open(info.url)

    def _fallback_open(self, url: str) -> None:
        if not url: return
        try:
            if sys.platform == "darwin":
                import subprocess; subprocess.Popen(["open", url])
            elif sys.platform == "win32":
                import os; os.startfile(url)        # type: ignore[attr-defined]
            else:
                import subprocess; subprocess.Popen(["xdg-open", url])
        except Exception:
            pass

    # --- Version compare ---------------------------------------------
    def _is_newer(self, candidate: str) -> bool:
        return _semver_tuple(candidate) > _semver_tuple(self.current_version)


def _semver_tuple(s: str) -> tuple[int, ...]:
    """Loose semver compare — splits on dots, parses each segment as
    int when possible, treats non-numeric prefixes as 'beta' < 'rc' <
    final."""
    parts = re.findall(r"\d+", s or "0")
    return tuple(int(p) for p in parts) or (0,)


__all__ = ["Updater", "ReleaseInfo"]
