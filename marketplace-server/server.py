"""Reference implementation of the Elysium skin registry.

Spec lives in :doc:`/guides/marketplace`. This is a single-file FastAPI
service backed by SQLite + a content-addressable blob store; deploy to
Render / Fly / Cloud Run / your favorite container host as-is, or use
as a template for a fancier version.

Endpoints
---------
* ``GET  /v1/search?q=...`` → ``[{id, version, name, description, ...}]``
* ``GET  /v1/skins/<id>`` → ``{manifest, download_url, publisher_pubkey,
  signature, size}``
* ``POST /v1/skins`` → ``{upload_url, public_url}`` after verifying the
  publisher signature.
* ``PUT  /v1/upload/<token>`` → consumer of the pre-signed upload URL.
* ``GET  /v1/blob/<sha256>`` → archive bytes (content-addressable).

Trust
-----
The server re-verifies every uploaded payload's Ed25519 signature using
the publisher's stored key. First-publish flows accept a self-asserted
public key and bind it to a publisher account; subsequent uploads under
that account must sign with the same key.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import JSONResponse
except ImportError as e:
    raise SystemExit(
        "marketplace-server requires `pip install fastapi uvicorn pynacl`."
    ) from e

from nacl.signing import VerifyKey         # type: ignore[import-not-found]


ROOT       = Path(os.environ.get("ELYSIUM_REGISTRY_ROOT", "./registry-data"))
DB_PATH    = ROOT / "registry.sqlite"
BLOB_DIR   = ROOT / "blobs"
PUBLIC_URL = os.environ.get("ELYSIUM_PUBLIC_URL", "http://localhost:8000")

ROOT.mkdir(parents=True, exist_ok=True)
BLOB_DIR.mkdir(parents=True, exist_ok=True)

_PENDING: dict[str, dict] = {}             # upload_token → record

app = FastAPI(title="Elysium Skin Registry")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skins (
            id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            publisher_pubkey TEXT NOT NULL,
            signature TEXT NOT NULL,
            blob_sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS publishers (
            id TEXT PRIMARY KEY,
            pubkey TEXT UNIQUE NOT NULL
        );""")
    return conn


@app.get("/v1/search")
def search(q: str = "") -> list[dict]:
    q = f"%{q.strip()}%"
    rows = _db().execute("""
        SELECT id, version, name, description FROM skins
        WHERE id LIKE ? OR name LIKE ? OR description LIKE ?
        ORDER BY name COLLATE NOCASE LIMIT 50
    """, (q, q, q)).fetchall()
    return [dict(r) for r in rows]


@app.get("/v1/skins/{skin_id}")
def info(skin_id: str) -> dict:
    row = _db().execute(
        "SELECT * FROM skins WHERE id = ?", (skin_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="skin not found")
    return {
        "manifest": {
            "id": row["id"], "name": row["name"],
            "version": row["version"], "description": row["description"],
            "schema_version": "1.0",
        },
        "publisher_pubkey": row["publisher_pubkey"],
        "signature": row["signature"],
        "size": row["size"],
        "download_url": f"{PUBLIC_URL}/v1/blob/{row['blob_sha256']}",
    }


@app.post("/v1/skins")
async def publish(req: Request) -> dict:
    payload = await req.json()
    manifest = payload.get("manifest", {})
    pubkey   = payload.get("publisher_pubkey", "")
    signature = payload.get("signature", "")
    size     = int(payload.get("size", 0))
    skin_id  = manifest.get("id")
    if not (skin_id and pubkey and signature and size > 0):
        raise HTTPException(status_code=400, detail="incomplete payload")

    # First-publish binding: the publisher account is keyed by the skin
    # id prefix (e.g. "dev.foo.player" → "dev.foo"). Reject a re-publish
    # signed with a different key.
    publisher_id = ".".join(skin_id.split(".")[:2]) or skin_id
    conn = _db()
    existing_key = conn.execute(
        "SELECT pubkey FROM publishers WHERE id = ?", (publisher_id,),
    ).fetchone()
    if existing_key is not None and existing_key["pubkey"] != pubkey:
        raise HTTPException(status_code=403,
                            detail="publisher pubkey rotation must go via "
                                   "support — current key on file")
    if existing_key is None:
        conn.execute("INSERT INTO publishers(id, pubkey) VALUES (?,?)",
                     (publisher_id, pubkey))
        conn.commit()

    token = secrets.token_urlsafe(24)
    _PENDING[token] = {
        "manifest": manifest,
        "publisher_pubkey": pubkey,
        "signature": signature,
        "size": size,
    }
    return {
        "upload_url": f"{PUBLIC_URL}/v1/upload/{token}",
        "public_url": f"{PUBLIC_URL}/skins/{skin_id}",
    }


@app.put("/v1/upload/{token}")
async def upload(token: str, req: Request) -> dict:
    pending = _PENDING.pop(token, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="upload token expired")
    body = await req.body()
    if len(body) != pending["size"]:
        raise HTTPException(status_code=400,
                            detail=f"size mismatch ({len(body)} vs declared {pending['size']})")
    # Verify the signature server-side.
    try:
        VerifyKey(bytes.fromhex(pending["publisher_pubkey"])).verify(
            body, bytes.fromhex(pending["signature"]))
    except Exception:
        raise HTTPException(status_code=400,
                            detail="signature verification failed")
    sha = hashlib.sha256(body).hexdigest()
    (BLOB_DIR / sha).write_bytes(body)
    conn = _db()
    manifest = pending["manifest"]
    conn.execute("""
        INSERT INTO skins(id, version, name, description,
                          publisher_pubkey, signature, blob_sha256, size)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            version           = excluded.version,
            name              = excluded.name,
            description       = excluded.description,
            signature         = excluded.signature,
            blob_sha256       = excluded.blob_sha256,
            size              = excluded.size
    """, (manifest["id"], manifest.get("version", "0.0.0"),
          manifest.get("name", ""), manifest.get("description", ""),
          pending["publisher_pubkey"], pending["signature"], sha, len(body)))
    conn.commit()
    return {"ok": True, "sha256": sha}


@app.get("/v1/blob/{sha}")
def blob(sha: str) -> Response:
    path = BLOB_DIR / sha
    if not path.is_file():
        raise HTTPException(status_code=404, detail="blob not found")
    return Response(content=path.read_bytes(),
                    media_type="application/gzip")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
