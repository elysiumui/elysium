"""Elysium skin marketplace MVP.

Local registry mirror at ``~/.elysium/skins/`` plus a small HTTP client
that talks to the canonical ``skins.elysium.dev`` index.

CLI flows
---------
::

    elysium skins init <name>     # scaffold a publishable skin
    elysium skins list            # what's installed locally
    elysium skins search <q>      # query the registry
    elysium skins info <name>     # registry metadata for one skin
    elysium skins add <name>      # download + signature-verify + install
    elysium skins publish <path>  # tar + sign + POST to the registry
    elysium skins migrate <name>  # bump <name> to the latest schema_version

Trust model
-----------
* Every published skin carries an Ed25519 detached signature
  (``signature.json``). The native loader verifies it via
  ``ely_skin::signature::verify`` (Phase 1.3).
* The registry stores only the publisher's verified public key — never
  the private key. ``publish`` reads the private key from
  ``$ELYSIUM_SIGN_KEY`` so CI flows don't need an interactive prompt.
"""
from __future__ import annotations

import json
import os
import sys
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

REGISTRY_URL = os.environ.get("ELYSIUM_REGISTRY",
                               "https://skins.elysium.dev/v1")


def _skins_root() -> Path:
    base = Path.home() / ".elysium" / "skins"
    base.mkdir(parents=True, exist_ok=True)
    return base


def list_installed() -> list[dict]:
    out = []
    for d in sorted(_skins_root().iterdir()):
        if not d.is_dir(): continue
        manifest = d / "manifest.json"
        if not manifest.is_file(): continue
        try:
            m = json.loads(manifest.read_text())
            out.append({
                "id": m.get("id", d.name),
                "version": m.get("version", "?"),
                "path": str(d),
                "name": m.get("name", d.name),
            })
        except Exception:
            pass
    return out


def search(query: str) -> list[dict]:
    url = f"{REGISTRY_URL}/search?q={urllib.parse.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"elysium skins search: {e}", file=sys.stderr)
        return []


def info(name: str) -> dict | None:
    url = f"{REGISTRY_URL}/skins/{urllib.parse.quote(name)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"elysium skins info: {e}", file=sys.stderr)
        return None


def add(name: str) -> Path | None:
    """Download + verify + install a skin from the registry."""
    meta = info(name)
    if not meta:
        return None
    archive_url = meta.get("download_url")
    pubkey_hex  = meta.get("publisher_pubkey")
    sig_hex     = meta.get("signature")
    if not archive_url or not pubkey_hex or not sig_hex:
        print(f"elysium skins add: registry entry is incomplete",
              file=sys.stderr)
        return None
    # Download archive.
    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as f:
        tmp = Path(f.name)
        with urllib.request.urlopen(archive_url, timeout=30) as r:
            shutil.copyfileobj(r, f)
    # Verify signature.
    try:
        if not _verify_archive(tmp, pubkey_hex, sig_hex):
            print(f"elysium skins add: signature verification failed!",
                  file=sys.stderr)
            return None
    except Exception as e:
        print(f"elysium skins add: signature check error: {e}",
              file=sys.stderr)
        return None
    # Extract into the local store.
    dest = _skins_root() / name
    if dest.exists(): shutil.rmtree(dest)
    with tarfile.open(tmp, "r:gz") as tar:
        tar.extractall(dest)
    print(f"installed {name} → {dest}")
    return dest


def init(name: str) -> Path:
    """Scaffold a new publishable skin under ./<name>.esk/."""
    if not name:
        raise ValueError("`elysium skins init` needs a name")
    root = Path.cwd() / f"{name}.esk"
    if root.exists():
        raise FileExistsError(root)
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0",
        "id":      f"dev.elysium.{name}",
        "name":    name,
        "version": "0.1.0",
        "color_space": "srgb",
        "author":  os.environ.get("USER", "anonymous"),
        "license": "Apache-2.0",
        "description": f"A skin called {name}.",
    }, indent=2))
    (root / "document.json").write_text(json.dumps({
        "root": {
            "type": "scene",
            "size": {"w": 800, "h": 600},
            "background": {"type": "color", "value": "#0E0B1A"},
            "children": [
                {"type": "path", "id": "card",
                 "d": "M 40 40 L 760 40 L 760 560 L 40 560 Z",
                 "fill": {"type": "linear_gradient",
                          "stops": [[0, "#5B3FF5"], [1, "#FF5C8A"]],
                          "angle": 135}}
            ]
        }
    }, indent=2))
    print(f"scaffolded {root}")
    return root


def publish(path: str) -> str | None:
    """Tar, sign, and POST a skin to the registry. Requires
    ``$ELYSIUM_SIGN_KEY`` (hex-encoded 32-byte ed25519 private seed)."""
    skin = Path(path).resolve()
    if not (skin / "manifest.json").is_file():
        print(f"elysium skins publish: not a skin directory: {skin}",
              file=sys.stderr)
        return None
    key_hex = os.environ.get("ELYSIUM_SIGN_KEY")
    if not key_hex:
        print("elysium skins publish: set $ELYSIUM_SIGN_KEY "
              "(hex-encoded 32-byte ed25519 seed)", file=sys.stderr)
        return None

    # Tar + sign locally before upload — the registry re-verifies before
    # accepting; double-sign keeps publishers honest.
    archive = Path(tempfile.gettempdir()) / f"{skin.name}.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(skin, arcname=skin.name)
    sig_hex, pub_hex = _sign_archive(archive, key_hex)
    if not sig_hex:
        print("elysium skins publish: signing failed", file=sys.stderr)
        return None

    manifest = json.loads((skin / "manifest.json").read_text())
    payload = {
        "manifest": manifest,
        "publisher_pubkey": pub_hex,
        "signature": sig_hex,
        "size": archive.stat().st_size,
    }
    req = urllib.request.Request(
        f"{REGISTRY_URL}/skins",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            response = json.loads(r.read())
        upload_url = response.get("upload_url")
        if upload_url:
            req2 = urllib.request.Request(upload_url,
                                          data=archive.read_bytes(),
                                          method="PUT")
            urllib.request.urlopen(req2, timeout=120)
        listing = response.get("public_url",
                                f"{REGISTRY_URL.replace('/v1', '')}/{manifest['id']}")
        print(f"published → {listing}")
        return listing
    except Exception as e:
        print(f"elysium skins publish: {e}", file=sys.stderr)
        return None


def migrate(name: str) -> Path | None:
    """Apply schema migrations to a local skin."""
    target = _skins_root() / name if name else Path.cwd()
    if not (target / "manifest.json").is_file():
        print(f"elysium skins migrate: no manifest at {target}",
              file=sys.stderr)
        return None
    m = json.loads((target / "manifest.json").read_text())
    current = m.get("schema_version", "0.0")
    if current == "1.0":
        print(f"{target.name} already at schema 1.0")
        return target
    # 0.x → 1.0: rename a handful of legacy fields. The migration is
    # additive — we keep the old `name` field around for compatibility.
    if "displayName" in m: m["name"] = m.pop("displayName")
    if "uuid"        in m: m["id"]   = m.pop("uuid")
    m["schema_version"] = "1.0"
    (target / "manifest.json").write_text(json.dumps(m, indent=2))
    print(f"migrated {target.name} → schema 1.0")
    return target


# --- Signing helpers ---------------------------------------------------------

def _verify_archive(archive: Path, pubkey_hex: str, sig_hex: str) -> bool:
    try:
        from elysium._native import _native as _n
        # Native crate exposes verify on raw bytes (Phase 1.3).
        verify = getattr(_n, "verify_signature", None)
        if verify is None:
            # Pure-Python fallback via PyNaCl if installed.
            return _verify_pynacl(archive, pubkey_hex, sig_hex)
        return verify(bytes.fromhex(pubkey_hex),
                      archive.read_bytes(),
                      bytes.fromhex(sig_hex))
    except Exception:
        return _verify_pynacl(archive, pubkey_hex, sig_hex)


def _verify_pynacl(archive: Path, pubkey_hex: str, sig_hex: str) -> bool:
    try:
        from nacl.signing import VerifyKey
        VerifyKey(bytes.fromhex(pubkey_hex)).verify(
            archive.read_bytes(), bytes.fromhex(sig_hex))
        return True
    except Exception:
        return False


def _sign_archive(archive: Path, key_hex: str) -> tuple[str | None, str | None]:
    try:
        from nacl.signing import SigningKey
        sk = SigningKey(bytes.fromhex(key_hex))
        sig = sk.sign(archive.read_bytes()).signature
        return sig.hex(), bytes(sk.verify_key).hex()
    except Exception:
        return None, None


# --- CLI ----------------------------------------------------------------------

def cli(action: str, name: str | None) -> int:
    if action == "list":
        for s in list_installed():
            print(f"{s['id']:40s} {s['version']:10s} {s['path']}")
        return 0
    if action == "search":
        if not name:
            print("usage: elysium skins search <query>", file=sys.stderr)
            return 1
        for s in search(name):
            print(f"{s.get('id'):40s} {s.get('version','?'):10s} "
                  f"{s.get('description', '')}")
        return 0
    if action == "info":
        if not name:
            print("usage: elysium skins info <name>", file=sys.stderr); return 1
        meta = info(name)
        if not meta:
            return 1
        print(json.dumps(meta, indent=2))
        return 0
    if action == "init":
        if not name:
            print("usage: elysium skins init <name>", file=sys.stderr); return 1
        init(name); return 0
    if action == "add":
        if not name:
            print("usage: elysium skins add <name>", file=sys.stderr); return 1
        return 0 if add(name) else 1
    if action == "publish":
        if not name:
            print("usage: elysium skins publish <path>", file=sys.stderr); return 1
        return 0 if publish(name) else 1
    if action == "migrate":
        if not name:
            print("usage: elysium skins migrate <name>", file=sys.stderr); return 1
        return 0 if migrate(name) else 1
    print(f"unknown skins action: {action}", file=sys.stderr)
    return 1
