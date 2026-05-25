"""Importers for external design formats → list[Placement].

Each importer returns (placements, app_window_overrides_or_None).

Supported formats (this phase):
  • SVG       — `<rect>`, `<circle>`, `<ellipse>`, `<polygon>`, `<path>`
  • Figma     — REST API `/v1/files/{key}` (needs FIGMA_TOKEN env var)
  • Lottie    — shape layers; static snapshot at t=0
  • glTF/OBJ  — flat silhouette of the mesh, projected to XY
  • Canva     — public design export endpoint via Canva Connect API
"""
from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
import urllib.request
import urllib.parse


# Lazily import the Designer's Placement at call time to avoid circular deps.
def _placement_cls():
    import importlib
    mod = sys.modules.get("_designer_main") or importlib.import_module("__main__")
    return mod.Placement, mod.AnimState


# --- SVG -------------------------------------------------------------------

def import_svg(path: Path, name_factory) -> list:
    ns = "{http://www.w3.org/2000/svg}"
    tree = ET.parse(str(path))
    root = tree.getroot()
    Placement, _ = _placement_cls()
    out = []

    def parse_color(raw: str, default=(120, 120, 120, 255)):
        raw = (raw or "").strip()
        if not raw or raw == "none":
            return (0, 0, 0, 0)
        if raw.startswith("#"):
            h = raw.lstrip("#")
            if len(h) == 3: h = "".join(c * 2 for c in h)
            if len(h) == 6:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        if raw.startswith("rgb"):
            nums = re.findall(r"[\d.]+", raw)
            if len(nums) >= 3:
                r, g, b = (int(float(x)) for x in nums[:3])
                a = int(float(nums[3]) * 255) if len(nums) == 4 else 255
                return (r, g, b, a)
        return default

    for el in root.iter():
        tag = el.tag.replace(ns, "")
        fill = parse_color(el.get("fill", ""), (122, 88, 244, 255))
        stroke = parse_color(el.get("stroke", ""), (0, 0, 0, 0))
        sw = float(el.get("stroke-width", "1") or 1)
        if tag == "rect":
            x = float(el.get("x", 0)); y = float(el.get("y", 0))
            w = float(el.get("width", 0)); h = float(el.get("height", 0))
            out.append(Placement("Shape", x, y, w, h, name_factory("Shape"),
                                 shape="rect", fill=fill, stroke=stroke,
                                 stroke_w=sw))
        elif tag in ("circle", "ellipse"):
            cx = float(el.get("cx", 0)); cy = float(el.get("cy", 0))
            rx = float(el.get("rx", el.get("r", 0)))
            ry = float(el.get("ry", el.get("r", 0)))
            out.append(Placement("Shape", cx - rx, cy - ry, rx * 2, ry * 2,
                                 name_factory("Shape"),
                                 shape="ellipse", fill=fill, stroke=stroke,
                                 stroke_w=sw))
        elif tag == "polygon":
            pts = [tuple(map(float, p.split(",")))
                   for p in el.get("points", "").split() if "," in p]
            if pts:
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                out.append(Placement("Shape", min(xs), min(ys),
                                     max(xs) - min(xs), max(ys) - min(ys),
                                     name_factory("Shape"),
                                     shape="polygon", points=pts,
                                     fill=fill, stroke=stroke, stroke_w=sw))
        elif tag == "path":
            d = el.get("d", "")
            if d:
                from re import findall
                nums = list(map(float, findall(r"-?\d+(?:\.\d+)?", d)))
                xs = nums[0::2]; ys = nums[1::2]
                bx = min(xs) if xs else 0; by = min(ys) if ys else 0
                bw = (max(xs) - bx) if xs else 100
                bh = (max(ys) - by) if ys else 100
                out.append(Placement("Shape", bx, by, bw, bh,
                                     name_factory("Shape"),
                                     shape="path", path_d=d,
                                     fill=fill, stroke=stroke, stroke_w=sw))
    return out


# --- .esk document.json (framework-native) ---------------------------------

def import_esk_document(skin_path: Path, name_factory) -> tuple[list, tuple[float, float] | None, tuple[int, int, int, int] | None]:
    """Import an existing `.esk` bundle's `document.json` as Placements.

    Used when the user does File > Open Skin on a bundle that was
    authored outside the Designer (no `designer_layout.json` yet).
    Otherwise the Designer would silently overwrite the existing
    `document.json` content with its default empty-skin template the
    first time the user hit Save.

    Returns `(placements, (scene_w, scene_h) or None, scene_bg or None)`:
      * `placements` — list of Designer Placement objects.
      * `scene_size` — authored canvas dims; lets the caller resize the
        App Window to match.
      * `scene_bg` — the scene's authored background colour as RGBA;
        used by the caller to decide whether this is a chrome-less
        sub-component (alpha == 0) or a standalone-app skin.
    """
    doc_file = skin_path / "document.json"
    if not doc_file.is_file():
        return [], None, None
    try:
        doc = json.loads(doc_file.read_text())
    except Exception:
        return [], None, None

    Placement, _ = _placement_cls()

    def parse_fill(spec, default=(122, 88, 244, 255)):
        """Resolve `{"type":"color","value":"#RRGGBB[AA]"}` or a bare
        hex string to a (r,g,b,a) tuple."""
        if isinstance(spec, dict):
            spec = spec.get("value", "")
        if isinstance(spec, str) and spec.startswith("#"):
            h = spec.lstrip("#")
            if len(h) == 3: h = "".join(c * 2 for c in h)
            if len(h) == 6:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
            if len(h) == 8:
                return (int(h[0:2], 16), int(h[2:4], 16),
                        int(h[4:6], 16), int(h[6:8], 16))
        return default

    def path_bbox(d: str) -> tuple[float, float, float, float]:
        # Cheap bbox: take every numeric pair, treat as (x, y). Good
        # enough for placement; live-render uses the raw `d`.
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
        if len(nums) < 2:
            return 0.0, 0.0, 100.0, 100.0
        xs, ys = nums[0::2], nums[1::2]
        return (min(xs), min(ys),
                (max(xs) - min(xs)) or 1.0,
                (max(ys) - min(ys)) or 1.0)

    out: list = []
    scene_size: tuple[float, float] | None = None
    scene_bg: tuple[int, int, int, int] | None = None

    def walk(node: dict) -> None:
        nonlocal scene_size, scene_bg
        if not isinstance(node, dict):
            return
        kind = node.get("type", "")
        if kind == "scene":
            sz = node.get("size") or {}
            try:
                scene_size = (float(sz.get("w", 0)), float(sz.get("h", 0)))
            except Exception:
                pass
            bg = node.get("background")
            if bg is not None:
                scene_bg = parse_fill(bg, default=(0, 0, 0, 0))
            for c in node.get("children", []) or []:
                walk(c)
            return
        if kind == "group":
            # Groups don't yet have a 1:1 Placement representation —
            # flatten their children. (Transforms on group nodes would
            # need to be baked into the children; we leave that for the
            # framework's compile.rs to handle at draw time.)
            for c in node.get("children", []) or []:
                walk(c)
            return
        node_id = str(node.get("id") or "")
        if kind == "path":
            d = node.get("d", "")
            if not d:
                return
            x, y, w, h = path_bbox(d)
            fill = parse_fill(node.get("fill"))
            out.append(Placement(
                "Shape", x, y, w, h,
                name=name_factory("Shape") if not node_id else node_id,
                shape="path", path_d=d, fill=fill,
                stroke=(0, 0, 0, 0), stroke_w=1.0))
        elif kind == "image":
            d = node.get("d", "")
            x, y, w, h = path_bbox(d) if d else (0.0, 0.0, 100.0, 100.0)
            src = node.get("src", "")
            out.append(Placement(
                "Image", x, y, w, h,
                name=name_factory("Image") if not node_id else node_id,
                image_path=src))
        elif kind == "text":
            txt = node.get("text", "")
            tr = node.get("transform") or {}
            tx = float(tr.get("x", 0)); ty = float(tr.get("y", 0))
            sz = float(node.get("size", 16))
            out.append(Placement(
                "Label", tx, ty, max(80.0, len(txt) * sz * 0.55), sz * 1.4,
                name=name_factory("Label") if not node_id else node_id,
                props={"text": txt, "font_size": sz},
                fill=parse_fill(node.get("fill"), (32, 32, 32, 255))))
        # Webview / Component nodes — skipped for now; rare in
        # hand-authored bundles and would need their own Placement kind.

    walk(doc.get("root") or {})
    return out, scene_size, scene_bg


# --- Figma (REST API) ------------------------------------------------------

FIGMA_FILE_RE = re.compile(r"figma\.com/(?:file|design)/([A-Za-z0-9]+)")


def import_figma(url_or_key: str, name_factory, token: str | None = None) -> list:
    """Pull a Figma file's first page's frames + shapes. Vector glyphs are
    materialized by calling `/v1/images?ids=…&format=svg`, downloading each
    SVG, and parsing its `<path>` elements."""
    token = token or os.environ.get("FIGMA_TOKEN") or os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set FIGMA_TOKEN to your Figma personal access token.")
    m = FIGMA_FILE_RE.search(url_or_key)
    key = m.group(1) if m else url_or_key.strip()
    req = urllib.request.Request(
        f"https://api.figma.com/v1/files/{urllib.parse.quote(key)}",
        headers={"X-Figma-Token": token},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    Placement, _ = _placement_cls()
    out: list = []
    vector_node_ids: list[str] = []
    vector_meta: dict[str, dict] = {}

    def color_from(paints, default=(122, 88, 244, 255)):
        if not paints: return default
        p = paints[0]
        if p.get("type") != "SOLID": return default
        c = p.get("color", {}); a = c.get("a", 1.0) * p.get("opacity", 1.0)
        return (int(c.get("r", 0) * 255), int(c.get("g", 0) * 255),
                int(c.get("b", 0) * 255), int(a * 255))

    def walk(node):
        bb = node.get("absoluteBoundingBox") or {}
        x = bb.get("x", 0); y = bb.get("y", 0)
        w = bb.get("width", 0); h = bb.get("height", 0)
        fill = color_from(node.get("fills"))
        stroke = color_from(node.get("strokes"), (0, 0, 0, 0))
        sw = float(node.get("strokeWeight", 1))
        t = node.get("type")
        nid = node.get("id", "")
        if t == "RECTANGLE":
            out.append(Placement("Shape", x, y, w, h, name_factory("Shape"),
                                 shape="rect", fill=fill, stroke=stroke,
                                 stroke_w=sw))
        elif t == "ELLIPSE":
            out.append(Placement("Shape", x, y, w, h, name_factory("Shape"),
                                 shape="ellipse", fill=fill, stroke=stroke,
                                 stroke_w=sw))
        elif t == "TEXT":
            text = node.get("characters", "")
            out.append(Placement("Label", x, y, max(w, 80), max(h, 18),
                                 name_factory("Label"),
                                 props={"label": text}))
        elif t in ("VECTOR", "BOOLEAN_OPERATION", "STAR", "POLYGON", "LINE", "REGULAR_POLYGON"):
            placeholder = Placement("Shape", x, y, w, h, name_factory("Shape"),
                                    shape="rect", fill=fill, stroke=stroke,
                                    stroke_w=sw)
            out.append(placeholder)
            vector_node_ids.append(nid)
            vector_meta[nid] = {"placement": placeholder, "x": x, "y": y,
                                "w": w, "h": h, "fill": fill,
                                "stroke": stroke, "stroke_w": sw}
        for child in node.get("children", []) or []:
            walk(child)

    doc = data.get("document", {})
    pages = doc.get("children", [])
    if pages:
        walk(pages[0])

    # Resolve vector glyphs by fetching SVG renders for each node ID.
    if vector_node_ids:
        ids = ",".join(vector_node_ids[:100])     # API limits ~100 per call
        req = urllib.request.Request(
            f"https://api.figma.com/v1/images/{urllib.parse.quote(key)}"
            f"?ids={urllib.parse.quote(ids)}&format=svg",
            headers={"X-Figma-Token": token},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                images = json.loads(resp.read()).get("images", {})
            for nid, svg_url in images.items():
                if not svg_url:
                    continue
                meta = vector_meta.get(nid)
                if not meta:
                    continue
                try:
                    with urllib.request.urlopen(svg_url, timeout=15) as resp:
                        svg_bytes = resp.read()
                    # Extract the first <path d=…/>.
                    m = re.search(rb'<path[^>]*\sd="([^"]+)"', svg_bytes)
                    if m:
                        d = m.group(1).decode()
                        meta["placement"].shape = "path"
                        meta["placement"].path_d = d
                except Exception:
                    pass
        except Exception:
            pass    # fall back to the placeholder rect
    return out


# --- Lottie ---------------------------------------------------------------

def import_lottie(path: Path, name_factory) -> list:
    """Import a Lottie file. For each shape layer we walk its shape groups
    and convert ellipses / rects / Bezier paths into our Shape model. For
    image and text layers, layout follows the t=0 transform. Animated
    transforms produce a second AnimState capturing the end keyframe."""
    Placement, AnimState = _placement_cls()
    with open(path, "r") as f:
        data = json.load(f)
    out: list = []

    def shape_to_placement(shape, base_x, base_y) -> Placement | None:
        ty = shape.get("ty")
        if ty == "el":
            sz = (shape.get("s") or {}).get("k", [0, 0])
            pos = (shape.get("p") or {}).get("k", [0, 0])
            sw, sh = sz if isinstance(sz, list) else (0, 0)
            px, py = pos if isinstance(pos, list) else (0, 0)
            return Placement("Shape",
                             base_x + px - sw/2, base_y + py - sh/2, sw, sh,
                             name_factory("Shape"),
                             shape="ellipse",
                             fill=(122, 88, 244, 255))
        if ty == "rc":
            sz = (shape.get("s") or {}).get("k", [0, 0])
            pos = (shape.get("p") or {}).get("k", [0, 0])
            sw, sh = sz if isinstance(sz, list) else (0, 0)
            px, py = pos if isinstance(pos, list) else (0, 0)
            return Placement("Shape",
                             base_x + px - sw/2, base_y + py - sh/2, sw, sh,
                             name_factory("Shape"),
                             shape="rect", fill=(122, 88, 244, 255))
        if ty == "sh":   # Bezier shape
            ks = (shape.get("ks") or {}).get("k", {})
            verts = ks.get("v") if isinstance(ks, dict) else None
            if isinstance(verts, list) and verts:
                pts = [(base_x + p[0], base_y + p[1]) for p in verts]
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                bx, by = min(xs), min(ys)
                bw, bh = max(xs) - bx, max(ys) - by
                return Placement("Shape", bx, by, bw, bh,
                                 name_factory("Shape"),
                                 shape="polygon", points=pts,
                                 fill=(122, 88, 244, 255))
        return None

    def walk_shapes(items, base_x, base_y):
        for item in items or []:
            if item.get("ty") == "gr":
                walk_shapes(item.get("it", []), base_x, base_y)
                continue
            ph = shape_to_placement(item, base_x, base_y)
            if ph: out.append(ph)

    for layer in data.get("layers", []):
        ty = layer.get("ty")
        name = layer.get("nm", name_factory("Shape"))
        ks = layer.get("ks", {})
        pos = ks.get("p", {}).get("k", [0, 0])
        size = layer.get("ks", {}).get("s", {}).get("k", [100, 100])
        if isinstance(pos, list) and pos and isinstance(pos[0], dict):
            # Animated position with keyframes.
            kfs = pos
            x = kfs[0].get("s", [0, 0])[0]
            y = kfs[0].get("s", [0, 0])[1]
        else:
            x, y = pos[0] if isinstance(pos, list) else 0, pos[1] if isinstance(pos, list) else 0
        sw, sh = (size[0] if isinstance(size, list) else 100,
                  size[1] if isinstance(size, list) else 100)
        if ty == 4:   # shape layer
            walk_shapes(layer.get("shapes", []), x, y)
        elif ty == 5:  # text
            txt = ""
            try:
                txt = layer["t"]["d"]["k"][0]["s"]["t"]
            except Exception:
                pass
            out.append(Placement("Label", x, y, max(sw, 80), max(sh, 18),
                                 name_factory("Label"), props={"label": txt}))
        elif ty == 2:  # image
            out.append(Placement("Image", x - sw/2, y - sh/2, sw, sh,
                                 name_factory("Image")))
        # If position is animated, append a state with the end keyframe.
        if isinstance(pos, list) and pos and isinstance(pos[0], dict) and len(pos) > 1:
            try:
                end = pos[-1].get("s") or pos[-2].get("e") or pos[0].get("s")
                if end and len(end) >= 2:
                    dx = end[0] - pos[0].get("s", [0, 0])[0]
                    dy = end[1] - pos[0].get("s", [0, 0])[1]
                    out[-1].states.append(AnimState(name="end", dx=dx, dy=dy,
                                                    duration=1.0))
            except Exception:
                pass
    return out


# --- glTF / OBJ silhouette ------------------------------------------------

def import_gltf(path: Path, name_factory) -> list:
    """Extract vertex positions + triangle indices, project to XY. Emit:
    (a) the convex-hull silhouette as one polygon Shape; (b) up to 800
    individual triangles as polygon Shapes so the mesh's interior detail
    survives."""
    Placement, _ = _placement_cls()
    suffix = path.suffix.lower()
    pts: list[tuple[float, float]] = []
    tris: list[tuple[int, int, int]] = []
    if suffix == ".obj":
        for line in path.read_text().splitlines():
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 3:
                    pts.append((float(parts[1]), float(parts[2])))
            elif line.startswith("f "):
                idx = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
                # Triangulate fans for n-gons.
                for i in range(1, len(idx) - 1):
                    tris.append((idx[0], idx[i], idx[i + 1]))
    elif suffix in (".gltf", ".glb"):
        try:
            if suffix == ".gltf":
                data = json.loads(path.read_text())
                pts, tris = _gltf_extract_geom(path, data)
        except Exception as e:
            raise RuntimeError(f"glTF parse failed: {e}")
    if not pts:
        raise RuntimeError("No vertex positions recovered")

    # Normalize to ~400 px and center.
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    bx, by = min(xs), min(ys)
    bw = max(xs) - bx or 1; bh = max(ys) - by or 1
    scale = 400.0 / max(bw, bh, 1.0)
    norm = [((p[0] - bx) * scale + 200, (p[1] - by) * scale + 200) for p in pts]

    out: list = []
    # Silhouette first.
    hull = _convex_hull(norm)
    if hull:
        xs = [p[0] for p in hull]; ys = [p[1] for p in hull]
        out.append(Placement("Shape", min(xs), min(ys),
                             max(xs) - min(xs), max(ys) - min(ys),
                             name_factory("Shape"),
                             shape="polygon", points=hull,
                             fill=(122, 88, 244, 90),  # translucent silhouette
                             stroke=(0, 0, 0, 0)))
    # Triangle interior.
    for i, (a, b, c) in enumerate(tris[:800]):
        try:
            ts = [norm[a], norm[b], norm[c]]
        except IndexError:
            continue
        txs = [p[0] for p in ts]; tys = [p[1] for p in ts]
        out.append(Placement("Shape", min(txs), min(tys),
                             max(txs) - min(txs), max(tys) - min(tys),
                             name_factory("Shape"),
                             shape="polygon", points=ts,
                             fill=(80, 60, 200, 200),
                             stroke=(255, 255, 255, 30), stroke_w=0.5))
    return out


def _gltf_extract_geom(path: Path, data) -> tuple[list[tuple[float, float]], list[tuple[int, int, int]]]:
    """Tiny glTF reader: positions + triangle indices from the first mesh."""
    import base64, struct
    buffers = []
    for b in data.get("buffers", []):
        uri = b.get("uri", "")
        if uri.startswith("data:"):
            head, _, payload = uri.partition(",")
            buffers.append(base64.b64decode(payload))
        else:
            buffers.append((path.parent / uri).read_bytes())
    bufviews = data.get("bufferViews", [])
    accessors = data.get("accessors", [])
    for mesh in data.get("meshes", []):
        for prim in mesh.get("primitives", []):
            ai = prim.get("attributes", {}).get("POSITION")
            if ai is None: continue
            acc = accessors[ai]
            bv = bufviews[acc["bufferView"]]
            buf = buffers[bv["buffer"]]
            offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            count = acc["count"]
            pts: list[tuple[float, float]] = []
            for i in range(count):
                base = offset + i * 12
                x, y, z = struct.unpack_from("<fff", buf, base)
                pts.append((x, y))
            # Indices.
            tris: list[tuple[int, int, int]] = []
            ii = prim.get("indices")
            if ii is not None:
                iacc = accessors[ii]
                ibv = bufviews[iacc["bufferView"]]
                ibuf = buffers[ibv["buffer"]]
                ioffset = ibv.get("byteOffset", 0) + iacc.get("byteOffset", 0)
                icount = iacc["count"]
                # Skia's component types: 5121=u8, 5123=u16, 5125=u32
                ctype = iacc.get("componentType", 5123)
                cw = {5121: 1, 5123: 2, 5125: 4}[ctype]
                fmt = {5121: "B", 5123: "<H", 5125: "<I"}[ctype]
                idx = []
                for k in range(icount):
                    (v,) = struct.unpack_from(fmt, ibuf, ioffset + k * cw)
                    idx.append(v)
                for k in range(0, len(idx) - 2, 3):
                    tris.append((idx[k], idx[k + 1], idx[k + 2]))
            return pts, tris
    return [], []


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2: return pts
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0: lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0: upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# --- Canva ---------------------------------------------------------------

def canva_oauth_login(client_id: str, client_secret: str,
                      scopes: str = "design:meta:read design:content:read") -> str:
    """Run the Canva Connect OAuth authorization-code flow locally.
    Opens the user's browser, listens on http://localhost:8123/callback for
    the redirect, exchanges the code for an access token and returns it."""
    import http.server, threading, urllib.parse, urllib.request
    import webbrowser, secrets, base64, hashlib
    redirect_uri = "http://127.0.0.1:8123/callback"
    state = secrets.token_urlsafe(16)
    code_verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    auth_url = ("https://www.canva.com/api/oauth/authorize?" +
                urllib.parse.urlencode({
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": scopes,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }))
    received: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a, **kw): return
        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            received.update(urllib.parse.parse_qs(qs))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write("<h2>Canva OAuth complete — return to Elysium</h2>".encode("utf-8"))

    srv = http.server.HTTPServer(("127.0.0.1", 8123), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    webbrowser.open(auth_url)
    # Wait up to 5 min.
    import time
    deadline = time.time() + 300
    while time.time() < deadline and "code" not in received:
        time.sleep(0.2)
    srv.server_close()
    if "code" not in received:
        raise RuntimeError("OAuth timed out / cancelled")
    code = received["code"][0]
    if received.get("state", [""])[0] != state:
        raise RuntimeError("OAuth state mismatch")
    # Exchange code for token.
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }).encode()
    req = urllib.request.Request(
        "https://api.canva.com/rest/v1/oauth/token",
        data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        token = json.loads(resp.read()).get("access_token")
    if not token:
        raise RuntimeError("OAuth: no access_token in token response")
    return token


def import_canva(url_or_id: str, name_factory, token: str | None = None) -> list:
    """Fetch a Canva design's PNG export via the Canva Connect API and import
    it as a single Image placement."""
    token = token or os.environ.get("CANVA_TOKEN") or os.environ.get("CANVA_ACCESS_TOKEN")
    if not token:
        # Try OAuth login if app credentials are provided.
        cid = os.environ.get("CANVA_CLIENT_ID")
        csec = os.environ.get("CANVA_CLIENT_SECRET")
        if cid and csec:
            token = canva_oauth_login(cid, csec)
        else:
            raise RuntimeError(
                "Canva import needs CANVA_TOKEN (or CANVA_CLIENT_ID + "
                "CANVA_CLIENT_SECRET to run the OAuth flow). See "
                "https://www.canva.com/developers.")
    # Extract design ID from a canva.com URL or accept the raw ID.
    m = re.search(r"design/([A-Za-z0-9_-]+)", url_or_id)
    design_id = m.group(1) if m else url_or_id
    # Start an export job.
    body = json.dumps({"design_id": design_id, "format": {"type": "png"}}).encode()
    req = urllib.request.Request(
        "https://api.canva.com/rest/v1/exports",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        job = json.loads(resp.read()).get("job", {})
    job_id = job.get("id")
    if not job_id:
        raise RuntimeError(f"Canva export job not created: {job}")
    # Poll until finished.
    import time
    url = None
    for _ in range(20):
        time.sleep(1.5)
        req = urllib.request.Request(
            f"https://api.canva.com/rest/v1/exports/{job_id}",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = json.loads(resp.read()).get("job", {})
        if status.get("status") == "success":
            urls = status.get("urls") or []
            if urls: url = urls[0]; break
        elif status.get("status") in ("failed", "cancelled"):
            raise RuntimeError(f"Canva job ended: {status}")
    if not url:
        raise RuntimeError("Canva export timed out")
    # Download the image into the skin folder.
    out_path = Path("/tmp") / f"canva_{design_id}.png"
    with urllib.request.urlopen(url, timeout=30) as resp:
        out_path.write_bytes(resp.read())
    Placement, _ = _placement_cls()
    return [Placement("Image", 200, 200, 800, 600, name_factory("Image"),
                      image_path=str(out_path))]
