"""Tiny in-memory surrogate that satisfies the Session/tool contract
without spinning up the GUI Designer. Lets the agent operate on a
skin from the CLI, in tests, and over the JSON-RPC daemon (Phase 4.2).

The tools call into ``session.designer.placements`` / ``window_doc`` /
``_assign_name`` / ``save_layout`` — we provide minimal stand-ins for
each that read and write the native Designer document schema.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import copy, deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .. import scene_identity
from ..render import collections, mesh_document, scene, scene_lighting, scene_animation, scene_views

# designer_layout.json top-level ``document_version``. Readers accept any
# version <= LAYOUT_VERSION (a missing key means 0) and reject greater ones;
# adding optional keys never bumps it.
LAYOUT_VERSION = 1
_LAYOUT_RESERVED = ("window", "placements", "mesh_document", "document_version")


# Mirror the Designer's Placement + AnimState shapes — the tools import
# these via `session.designer_models`. Kept compatible with the real
# dataclasses by name so saved layouts round-trip.

@dataclass
class AnimState:
    name: str = "rest"
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0
    rotation: float = 0.0
    duration: float = 0.4
    easing: str = "ease_out"

    mesh_flap_target: float | None = None

    def to_json(self) -> dict:
        return {**getattr(self, "_extra_fields", {}), **{k:v for k,v in self.__dict__.items() if not k.startswith("_")}}

    @classmethod
    def from_json(cls, data):
        return _decode_fields(cls, data)



@dataclass
class Placement:
    kind: str = "Shape"
    x: float = 0.0
    y: float = 0.0
    w: float = 100.0
    h: float = 100.0
    name: str = "Item"
    props: dict = field(default_factory=dict)
    shape: str = "rect"
    path_d: str = ""
    points: list = field(default_factory=list)
    gradient_end: tuple | None = None
    gradient_angle: float = 90.0
    fill: tuple = (120, 110, 240, 255)
    stroke: tuple = (0, 0, 0, 0)
    stroke_w: float = 1.0
    color_fill: tuple | None = None
    color_text: tuple | None = None
    color_accent: tuple | None = None
    color_track: tuple | None = None
    image_path: str = ""
    pbr_preset: str = ""
    pbr_metallic: float = 0.0
    pbr_roughness: float = 0.5
    pbr_specular: float = 0.5
    pbr_clearcoat: float = 0.0
    pbr_clearcoat_roughness: float = 0.0
    pbr_anisotropy: float = 0.0
    pbr_use_color_fill: bool = False
    pbr_emissive: tuple = (0, 0, 0, 0)
    pbr_albedo_map: str = ""
    pbr_metallic_rough_map: str = ""
    pbr_normal_map: str = ""
    pbr_ao_map: str = ""
    pbr_emissive_map: str = ""
    mesh_kind: str = "Sphere"
    mesh_wireframe: bool = False
    mesh_yaw: float = 0.4
    mesh_pitch: float = 0.25
    mesh_flap: float = 0.0
    mesh_roll: float = 0.0
    mesh_flap_freq: float = 0.0
    mesh_flap_amp: float = 0.6
    mesh_flip_y: bool = False
    mesh_part_textures: dict = field(default_factory=dict)
    cycle_states: bool = True
    mesh_dist: float = 3.5
    texture_path: str = ""
    texture_scale: float = 1.0
    texture_offset_x: float = 0.0
    texture_offset_y: float = 0.0
    texture_rotation: float = 0.0
    texture_blend: str = "normal"
    texture_tint: tuple | None = None
    texture_layers: list[dict] = field(default_factory=list)
    # Maya-parity foundations (Phase 0).
    view_mode: str = "lit"
    pivot_x_norm: float = 0.5
    pivot_y_norm: float = 0.5
    # Parenting (Phase 7d) — name of the parent placement, or None.
    parent_name: str | None = None
    # G7 Phase 13 — NURBS curve control points (kind == "NURBSCurve").
    nurbs_points: list = field(default_factory=list)
    nurbs_closed: bool = False
    # G8 Phase 16 — Construction History DAG (per-placement op log).
    history: list = field(default_factory=list)
    is_hotspot: bool = False
    on_click_target: str = ""
    on_click_state: int = 0
    states: list[AnimState] = field(default_factory=list)
    current_state: int = 0
    _t_dx: float = 0.0
    _t_dy: float = 0.0
    _t_scale: float = 1.0
    _t_opacity: float = 1.0
    _t_rotation: float = 0.0

    entity_id: str = field(default_factory=scene_identity.new_id)

    def to_json(self) -> dict:
        out = {**deepcopy(getattr(self, "_extra_fields", {})), **{k:deepcopy(v) for k,v in self.__dict__.items() if not k.startswith("_")}}
        out["states"] = [state.to_json() for state in self.states]
        for group, mapping in _PLACEMENT_GROUPS.items():
            values = deepcopy(getattr(self, "_nested_extra", {}).get(group, {}))
            for key, attr in mapping.items():
                if hasattr(self, attr):
                    values[key] = out.pop(attr, deepcopy(getattr(self, attr)))
            out[group] = values
        out["pivot"] = [out.pop("pivot_x_norm"), out.pop("pivot_y_norm")]
        return out

    @classmethod
    def from_json(cls, data):
        obj = _decode_fields(cls, data, excluded={*_PLACEMENT_GROUPS, "pivot", "states"})
        obj.states = [AnimState.from_json(v) for v in data.get("states", [])]
        obj._nested_extra = {}
        for group, mapping in _PLACEMENT_GROUPS.items():
            values = data.get(group, {})
            if not isinstance(values, dict):
                raise ValueError(f"Placement {group} must be an object")
            obj._nested_extra[group] = {k:deepcopy(v) for k,v in values.items() if k not in mapping}
            for key, attr in mapping.items():
                if key in values:
                    setattr(obj, attr, deepcopy(values[key]))
        if "pivot" in data:
            pivot = data["pivot"]
            if not isinstance(pivot, (list, tuple)) or len(pivot) != 2:
                raise ValueError("Placement pivot must contain two values")
            obj.pivot_x_norm, obj.pivot_y_norm = pivot
        obj.entity_id = scene_identity.parse(data.get("entity_id"))
        return obj


@dataclass
class AppWindow:
    name: str = "MainWindow"
    title: str = "App Window"
    w: float = 800
    h: float = 600
    shape: str = "rect"
    path_d: str = ""
    bg_color: tuple = (250, 250, 252, 255)
    gradient_end: tuple | None = None
    gradient_angle: float = 90.0
    border_radius: float = 8
    transparent: bool = False
    show_title_bar: bool = True
    title_bar_color: tuple | None = None
    title_bar_color_end: tuple | None = None
    studio: str = "Default Soft Studio"
    texture_export_mode: str = "referenced"
    code_file: str = ""
    scene_view: bool = False
    scene_shading: str = "solid"
    scene_camera: dict = field(default_factory=scene.camera)
    scene_frame: int = 0
    scene_timeline: dict = field(default_factory=scene_animation.settings)
    scene_actions: dict | None = None
    scene_lighting: dict = field(default_factory=scene_lighting.settings)
    scene_collections: dict = field(default_factory=collections.settings)
    scene_bookmarks: dict = field(default_factory=scene_views.bookmarks)
    scene_references: dict = field(default_factory=scene_views.references)

    def to_json(self) -> dict:
        d = {**deepcopy(getattr(self, "_extra_fields", {})), **{k:deepcopy(v) for k,v in self.__dict__.items() if not k.startswith("_")}}
        d["bg_color"] = list(self.bg_color)
        return d

    @classmethod
    def from_json(cls, data):
        obj = _decode_fields(cls, data)
        obj.scene_camera = scene.camera(obj.scene_camera)
        obj.scene_shading = scene.shading_mode(obj.scene_shading)
        obj.scene_lighting = scene_lighting.settings(obj.scene_lighting)
        obj.scene_timeline = scene_animation.settings(obj.scene_timeline)
        from ..render import scene_actions
        obj.scene_actions = scene_actions.settings(obj.scene_actions)
        obj.scene_collections = collections.settings(obj.scene_collections)
        obj.scene_bookmarks = scene_views.bookmarks(obj.scene_bookmarks)
        obj.scene_references = scene_views.references(obj.scene_references)
        return obj


_PLACEMENT_GROUPS = {
    "mesh": {**{key: "mesh_" + key for key in ("kind", "wireframe", "yaw", "pitch", "roll", "flap", "flap_freq", "flap_amp", "dist", "flip_y", "part_textures")}, "view_mode": "view_mode"},
    "pbr": {key: "pbr_" + key for key in ("metallic", "roughness", "specular", "clearcoat", "clearcoat_roughness", "emissive", "use_color_fill", "anisotropy")},
    "pbr_maps": {key: "pbr_" + key + "_map" for key in ("albedo", "metallic_rough", "normal", "ao", "emissive")},
    "texture": {key: "texture_" + key for key in ("path", "scale", "offset_x", "offset_y", "rotation", "blend", "tint")},
}


def _decode_fields(cls, data, *, excluded=()):
    if not isinstance(data, dict):
        raise ValueError(f"{cls.__name__} must be an object")
    fields = cls.__dataclass_fields__
    obj = cls(**{k:deepcopy(v) for k,v in data.items() if k in fields and k not in excluded and not k.startswith("_")})
    # Unknown persisted JSON is retained as data, never installed as executable
    # instance attributes (which could shadow methods or internal state).
    obj._extra_fields = {k:deepcopy(v) for k,v in data.items() if k not in fields and k not in excluded}
    return obj


def _write_json_atomic(path, data):
    _write_bytes_atomic(path, json.dumps(data, indent=2, allow_nan=False).encode())


def _write_bytes_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _Models:
    Placement = Placement
    AnimState = AnimState
    AppWindow = AppWindow


MODELS = _Models()


# ---------------------------------------------------------------------------
# HeadlessDesigner: the duck-typed Session.designer.
# ---------------------------------------------------------------------------

class HeadlessDesigner:
    def __init__(self, skin_path: Path) -> None:
        self.skin_path = Path(skin_path).resolve()
        self.placements: list[Placement] = []
        self.window_doc = AppWindow()
        self.sel_kind = "none"
        self.sel_idx = -1
        self.sel_set: set[int] = set()
        self.playing = False
        self._play_clock = 0.0
        self.paint_masks: dict[int, Any] = {}
        self._brush_dirty: set[int] = set()
        # entity_id -> (content digest, compressed bytes) of the last mask
        # a snapshot serialised; see _paint_snapshot.
        self._paint_digest_cache: dict[str, tuple] = {}
        self._name_counters: dict[str, int] = {}
        # Whole-document undo history, same raw-list contract as the GUI
        # Designer (execution.run_transaction publishes one entry per
        # committed command and bumps the revision).
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._undo_limit = 100
        self._document_revision = 0
        self._layout_extra: dict = {}
        # Document-owned geometry: exactly the revisions the live placements
        # reference. Undo/redo/rollback rebuild it from self-contained snapshots.
        self.mesh_store = mesh_document.MeshStore()
        # Legacy named mesh keys this process cannot resolve (see
        # _unresolved_mesh_names); the document stays open and usable.
        self.missing_mesh_names: list[str] = []
        # Mirror the GUI Designer's reactive theme index.
        class _Reactive:
            def __init__(self): self.v = 1
            def __call__(self): return self.v
            def set(self, v): self.v = int(v)
        self.theme_index = _Reactive()

    # --- io ----------------------------------------------------------
    @classmethod
    def from_skin(cls, path: Path) -> "HeadlessDesigner":
        d = cls(path)
        if (d.skin_path / "designer_layout.json").is_file():
            d.load_layout()
        else:
            d.skin_path.mkdir(parents=True, exist_ok=True)
        return d

    # --- selection (mirrors the GUI Designer) ----------------------------
    def _select_placement(self, idx: int, additive: bool = False) -> None:
        idx = int(idx)
        if not 0 <= idx < len(self.placements):
            self.sel_kind, self.sel_idx, self.sel_set = "none", -1, set()
            return
        self.sel_kind, self.sel_idx = "placement", idx
        self.sel_set = (self.sel_set | {idx}) if additive else {idx}

    def _window_rect(self):
        return (0.0, 0.0, float(self.window_doc.w), float(self.window_doc.h))

    # --- document payload ---------------------------------------------------
    def _project_relative(self, value: str) -> str:
        """An in-project file becomes a project-relative reference on save.

        Files outside the project keep their absolute path (documented
        limitation), as does anything that is already relative.
        """
        raw = Path(value)
        if not raw.is_absolute():
            return value
        try:
            return raw.resolve().relative_to(self.skin_path).as_posix()
        except ValueError:
            return value

    def _project_absolute(self, value: str) -> str:
        """A project-relative reference becomes absolute again on load."""
        if Path(value).is_absolute():
            return value
        inside = self.skin_path / value
        # Legacy documents may hold working-directory-relative paths;
        # keep those only when the project-relative file is absent.
        return str(inside) if inside.exists() or not Path(value).exists() else value

    def _portable_placement_json(self, p) -> dict:
        """Placement JSON with every in-project asset made project-relative.

        Textures, the texture-layer stack, per-part maps and raster images
        travel with the project exactly as the PBR maps do — see
        ``mesh_document.rewrite_asset_paths`` for the one rule that decides
        what counts as an asset reference. The rewrite runs on a shallow
        copy, so live placement objects are never mutated.
        """
        portable = copy(p)
        mesh_document.rewrite_asset_paths(portable, self._project_relative)
        return portable.to_json()

    def _resolve_asset_paths(self, placements) -> None:
        """Project-relative asset paths become absolute on load."""
        for p in placements:
            mesh_document.rewrite_asset_paths(p, self._project_absolute)

    def _relocation_candidates(self, raw: Path) -> list[Path]:
        """Where a recorded mesh path may have moved to with the project.

        The path a legacy document recorded is usually absolute and was
        written on the authoring machine, so after a clone or a move only
        its *tail* is still meaningful: an asset recorded as
        ``/home/ann/work/examples/butterfly/_3ds/butterfly.3ds`` beside
        ``butterfly.esk`` is exactly ``<project>/../_3ds/butterfly.3ds``
        for everyone else. Joining the absolute path itself is a no-op
        (``Path("x") / "/abs"`` is ``/abs``), which is why only the bare
        filename used to be tried and a project with its assets in a
        subdirectory opened on one machine alone.

        So: drop the anchor, then try progressively shorter tails under
        both the project folder and its parent, longest first — the most
        specific match wins and a bare filename is the last resort.
        """
        parts = raw.parts[1:] if raw.is_absolute() else raw.parts
        candidates: list[Path] = []
        for length in range(len(parts), 0, -1):
            tail = Path(*parts[-length:])
            for root in (self.skin_path, self.skin_path.parent):
                candidate = root / tail
                if candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def _migrate_file_meshes(self, placements, store) -> None:
        """Convert legacy ``file:`` mesh kinds into owned, embedded assets."""
        from ..render import pbr
        for p in placements:
            if p.kind != "Mesh3D" or not str(p.mesh_kind).startswith("file:"):
                continue
            raw = Path(p.mesh_kind[5:]).expanduser()
            name = raw.name
            if raw.is_absolute() and raw.is_file():
                candidates = [raw]
            else:
                candidates = self._relocation_candidates(raw)
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                raise ValueError(f"Missing mesh file {name}; move it next to the project or re-import it")
            found = found.resolve()
            mesh_document.bind(p, pbr.import_mesh_from_file(found), label=found.stem, store=store)
            try:
                location = found.relative_to(self.skin_path).as_posix()
            except ValueError:
                location = str(found)
            p.props = dict(p.props or {})
            p.props["import_source"] = {"name": found.name, "path": location}

    def layout_payload(self) -> dict:
        """The complete persisted document (shared by save and scene.document_hash)."""
        extra = {k: deepcopy(v) for k, v in getattr(self, "_layout_extra", {}).items()
                 if k not in _LAYOUT_RESERVED}
        return {
            **extra,
            "document_version": LAYOUT_VERSION,
            "window": self.window_doc.to_json(),
            "placements": [self._portable_placement_json(p) for p in self.placements],
            "mesh_document": mesh_document.capture(
                self.placements, store=self.mesh_store,
                unresolved=self.missing_mesh_names),
        }

    # --- transaction hooks used by execution.run_transaction ---------------
    def transaction_context(self):
        """Resolve every mesh read/bind inside a command against this
        document's store (bridge, daemon and headless paths alike)."""
        return mesh_document.using(self)

    def after_commit(self) -> None:
        """A committed command drops the owned mesh revisions nothing
        references any more; snapshots are self-contained, so undo/redo and
        rollback never need them."""
        mesh_document.sweep(self.placements, store=self.mesh_store)
        if self.missing_mesh_names:
            # `mesh.register_from_file` is the documented remedy for an
            # unresolved legacy name; once it commits, the name resolves
            # and the next save embeds the real geometry. Stop reporting it.
            #
            # Report only when the set actually *changes*. `after_commit`
            # runs after every committed command, and the reporter writes
            # `menu_status` — the single channel a tool has to say what it
            # just did (`GET /state`, `GET /logs`, `meta.live_menu_status`,
            # the CLI's `# status:` line). Re-announcing an unchanged notice
            # here overwrote every tool's own message for the whole life of
            # a legacy document: the one class of project this is meant to
            # keep usable was the one where no tool feedback ever arrived.
            still = [key for key in self.missing_mesh_names
                     if not self._resolves(key)]
            if still != self.missing_mesh_names:
                self._report_unresolved_meshes(still)

    def _resolves(self, key: str) -> bool:
        try:
            mesh_document.resolve(key, store=self.mesh_store)
        except ValueError:
            return False
        return True

    # --- paint state ---------------------------------------------------
    #
    # ``paint_masks`` / ``_brush_dirty`` are keyed by ``id(placement)``,
    # the GUI Designer's contract. ``_restore`` rebuilds every Placement
    # from JSON, so object identity does not survive it: a snapshot that
    # ignored paint left the masks orphaned under dead ids, and a failed
    # command or an undo silently threw away paint a previous *committed*
    # command had made. Snapshots therefore carry the paint layer keyed by
    # ``entity_id``, which is stable across the rebuild, and ``_restore``
    # re-keys it onto the placements it just built.

    def _paint_snapshot(self) -> dict:
        """Detached, compressed copy of every live placement's paint mask.

        Deflating a mask costs tens to hundreds of milliseconds (a
        2048x2048 mask is a 16 MB buffer), and ``_snapshot`` runs before
        *every* mutating command and on every undo/redo — so a command that
        never touches paint paid the whole bill, 31x measured on one
        ``scene.transform_set``. Each record is therefore memoised against
        a content digest of the mask buffer: digesting 16 MB costs ~5 ms
        against ~30-200 ms to deflate it, so an untouched mask is a dict
        lookup. The digest is over the buffer's exact bytes, so nothing has
        to announce that it painted — a stale record cannot be served.

        Sharing the memoised record also collapses the history: every
        snapshot that holds an unchanged mask now references one immutable
        ``bytes`` object instead of deflating a fresh 13 MB copy into each
        of up to ``_undo_limit`` entries. Records for placements that no
        longer exist are dropped with the same pass.
        """
        entities = {id(p): p.entity_id for p in self.placements}
        dirty = getattr(self, "_brush_dirty", None) or set()
        cached = getattr(self, "_paint_digest_cache", None) or {}
        out, digests = {}, {}
        for key, mask in (getattr(self, "paint_masks", None) or {}).items():
            entity, buf = entities.get(key), getattr(mask, "buf", None)
            if entity is None or buf is None:
                continue  # a mask for a placement that no longer exists
            buf = np.ascontiguousarray(buf)
            w, h = int(buf.shape[1]), int(buf.shape[0])
            digest = (w, h, hashlib.sha256(buf).digest())
            previous = cached.get(entity)
            # PaintMask.to_bytes is the one serialisation of a mask; the
            # snapshot reads it back through PaintMask.from_bytes.
            data = previous[1] if previous is not None and previous[0] == digest \
                else mask.to_bytes()
            digests[entity] = (digest, data)
            out[entity] = {"w": w, "h": h, "data": data, "dirty": key in dirty}
        self._paint_digest_cache = digests
        return out

    def _restore_paint(self, paint, placements) -> None:
        """Rebuild the paint layer against freshly restored placements."""
        from elysium.render.texture import PaintMask
        masks, dirty = {}, set()
        for p in placements:
            record = (paint or {}).get(p.entity_id)
            if record is None:
                continue
            masks[id(p)] = PaintMask.from_bytes(record["data"], record["w"], record["h"])
            if record.get("dirty"):
                dirty.add(id(p))
        self.paint_masks, self._brush_dirty = masks, dirty

    def _snapshot(self):
        return deepcopy({
            "window": self.window_doc.to_json(),
            "placements": [p.to_json() for p in self.placements],
            "mesh_document": mesh_document.capture(
                self.placements, store=self.mesh_store,
                unresolved=self.missing_mesh_names),
            "layout_extra": getattr(self, "_layout_extra", {}),
            "selection": (self.sel_kind, self.sel_idx, self.sel_set),
            "paint": self._paint_snapshot(),
        })

    def _restore(self, data):
        window = AppWindow.from_json(data["window"])
        placements = [Placement.from_json(p) for p in data["placements"]]
        scene_identity.validate(placements)
        # A fresh store per restore is the eviction: it holds exactly what the
        # snapshot embeds. Named keys (mesh.register_from_file) belong to the
        # process, not to a revision, so they ride along; the superseded
        # store then drops the revisions the snapshot does not carry.
        store = mesh_document.MeshStore()
        mesh_document.restore(data["mesh_document"], placements, store=store)
        previous = self.mesh_store
        store.adopt_named(previous)
        self.window_doc, self.placements, self.mesh_store = window, placements, store
        self._layout_extra = deepcopy(data["layout_extra"])
        self.sel_kind, self.sel_idx, self.sel_set = deepcopy(data["selection"])
        self._restore_paint(data.get("paint"), placements)
        self._rebuild_counters()
        previous.retain(store.keys())

    # --- history -----------------------------------------------------
    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        popped = self._undo_stack.pop()
        current = self._snapshot()
        self._restore(popped)
        self._redo_stack.append(current)
        self._document_revision += 1
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        popped = self._redo_stack.pop()
        current = self._snapshot()
        self._restore(popped)
        self._undo_stack.append(current)
        self._document_revision += 1
        return True

    def dispatch_persistent_tool(self, call, session, registry, *, confirmed=None):
        """Commit a CLI document mutation before reporting tool success."""
        from .execution import confirmation_required, run_transaction, validate_args
        from .types import ToolResult
        tool = registry.get(call.name)
        try:
            if tool is None:
                raise ValueError(f"unknown tool {call.name}")
            validate_args(tool, call.args)
        except Exception as exc:
            return ToolResult(id=call.id, ok=False, error=f"Cannot checkpoint command: {exc}")
        if confirmed is not None and confirmation_required(tool, session.trust, confirmed):
            return ToolResult(id=call.id, ok=False,
                              error="confirmation_required: resubmit with confirm=true and a new id")
        return run_transaction(self, session, tool, call, registry=registry, persist=True)

    def save_layout(self) -> None:
        layout = self.skin_path / "designer_layout.json"
        with mesh_document.using(self):
            payload = self.layout_payload()
        # Encode/validate every payload before touching files. The source
        # document is committed last; preserve any existing runtime export.
        files = [(self.skin_path / "document.designer.json", self._build_document())]
        manifest = self.skin_path / "manifest.json"
        if not manifest.is_file():
            files.append((manifest, {"schema_version": "1.0", "id": f"dev.elysium.{self.skin_path.stem}",
                "name": self.window_doc.title or self.skin_path.stem, "version": "0.1.0", "color_space": "srgb"}))
        files.append((layout, payload))
        for _, value in files:
            json.dumps(value, allow_nan=False)
        backups = {path: path.read_bytes() if path.exists() else None for path,_ in files}
        written = []
        try:
            for path, value in files:
                _write_json_atomic(path, value)
                written.append(path)
        except Exception:
            for path in reversed(written):
                original = backups[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _write_bytes_atomic(path, original)
            raise

    def load_layout(self) -> None:
        """Validate and resolve a complete document before publishing any of it."""
        layout = self.skin_path / "designer_layout.json"
        if not layout.is_file(): return
        data = json.loads(layout.read_text())
        if not isinstance(data, dict):
            raise ValueError("designer_layout.json must contain an object")
        version = data.get("document_version", 0)
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError("designer_layout.json document_version must be a nonnegative integer")
        if version > LAYOUT_VERSION:
            raise ValueError(f"designer_layout.json document_version {version} requires a newer "
                             f"Elysium (this build reads up to {LAYOUT_VERSION})")
        window = AppWindow.from_json(data.get("window", {}))
        placements = [Placement.from_json(p) for p in data.get("placements", [])]
        scene_identity.validate(placements)
        embedded = data.get("mesh_document")
        store = mesh_document.MeshStore()
        mesh_document.restore(embedded, placements, store=store)
        self._migrate_file_meshes(placements, store)
        self._resolve_asset_paths(placements)
        self._prune_collections(window, placements)
        # Names registered in this process (mesh.register_from_file) outlive
        # a reload, exactly as the old process-wide library did.
        previous = self.mesh_store
        store.adopt_named(previous)
        unresolved = self._unresolved_mesh_names(placements, store)
        self.window_doc, self.placements, self.mesh_store = window, placements, store
        self._layout_extra = {k:deepcopy(v) for k,v in data.items() if k not in _LAYOUT_RESERVED}
        self.sel_kind, self.sel_idx, self.sel_set = "none", -1, set()
        self._rebuild_counters()
        self._report_unresolved_meshes(unresolved)
        previous.retain(store.keys())

    def _unresolved_mesh_names(self, placements, store) -> list[str]:
        """Resolve every referenced mesh before the document is published.

        An owned ``mesh:`` revision exists nowhere but the document that
        carries it, so one that will not resolve is a broken document and
        the load fails with the in-memory document untouched.

        A **named** key is a different matter. A skin saved before geometry
        was embedded carries only the name of its mesh — "Butterfly" —
        which used to live in the process-wide ``MESH_LIBRARY`` and is
        simply absent in a fresh process. Named keys still resolve through
        the document store, the process store and the presets, exactly as
        they did before; a name none of them knows is *reported*, not
        fatal, whether or not the document embeds geometry for its other
        meshes. Refusing to open would strand every skin shipped in that
        format (``examples/hello`` included) on a name the user can rebind
        at any time with ``mesh.register_from_file`` — and a document that
        opens must also be writable, so ``capture`` omits exactly these
        names rather than failing every checkpoint and every save (see
        ``layout_payload`` / ``_snapshot``).

        The set is taken from ``mesh_document.referenced_keys`` — the very
        keys ``capture`` adopts, ``mesh_kind`` *and*
        ``props["skin_source_mesh"]`` — so what is tolerated here is
        exactly what will be asked for there. Re-walking ``mesh_kind``
        alone left a document whose skin source names an unregistered mesh
        opening with nothing reported and then raising ``missing mesh
        asset`` out of every ``_snapshot()`` and every save: the same
        freeze, reached through the other key.
        """
        missing: list[str] = []
        for key in mesh_document.referenced_keys(placements):
            try:
                mesh_document.resolve(key, store=store)
            except ValueError:
                if key.startswith(mesh_document.OWNED_PREFIX):
                    raise
                missing.append(key)
        return missing

    def _report_unresolved_meshes(self, missing: list[str]) -> None:
        """Surface unresolved legacy mesh names where a user can see them.

        ``missing_mesh_names`` is the machine-readable form (and the set
        ``capture`` is allowed to leave unembedded); ``menu_status`` is what
        the bridge already reports through ``GET /state`` and ``GET /logs``.

        Writing ``menu_status`` is a *report*, so every caller owes it a
        state change to report: opening (or reloading) a document always
        has one to make, while ``after_commit`` calls this only when the
        set it recomputed differs from the one already published.
        """
        previous, self.missing_mesh_names = self.missing_mesh_names, missing
        if missing:
            self.menu_status = (
                "Unresolved mesh names in this project: " + ", ".join(missing)
                + " — the document is fully editable and saves with each name "
                  "intact, but their geometry is missing, so the preview draws "
                  "a placeholder. Rebind each with "
                  "mesh.register_from_file(path, name) to restore it.")
        elif previous:
            self.menu_status = (
                "Every unresolved mesh name is bound again; the document "
                "embeds their geometry from the next save on.")

    def _prune_collections(self, window, placements) -> None:
        """Drop collection members whose objects no longer exist."""
        collections.prune(window, placements)

    def _build_document(self) -> dict:
        children = []
        for p in self.placements:
            if p.is_hotspot: continue
            if p.kind == "Shape" and p.path_d:
                children.append({"type": "path", "id": p.name,
                                  "d": p.path_d,
                                  "fill": {"type": "color",
                                            "value": _hex(p.fill)}})
            elif p.kind == "Image" and p.image_path:
                children.append({"type": "image", "id": p.name,
                                  "src": p.image_path,
                                  "d": _rect_d(p.x, p.y, p.w, p.h)})
            else:
                children.append({"type": "path", "id": p.name,
                                  "d": _round_d(p.x, p.y, p.w, p.h, 8),
                                  "fill": {"type": "color",
                                            "value": "#5B3FF5"}})
                if "label" in (p.props or {}):
                    children.append({"type": "text",
                                      "id": f"{p.name}_label",
                                      "value": str(p.props["label"]),
                                      "x": p.x + 12, "y": p.y + p.h / 2 + 4,
                                      "size": 14, "color": "#FFFFFF"})
        return {
            "root": {
                "type": "scene", "id": "root",
                "size": {"w": self.window_doc.w, "h": self.window_doc.h},
                "background": {"type": "color",
                                "value": _hex(self.window_doc.bg_color)},
                "children": children,
            }
        }

    # --- helpers ----------------------------------------------------
    def _assign_name(self, kind: str) -> str:
        n = self._name_counters.get(kind, 0) + 1
        self._name_counters[kind] = n
        return f"{kind}{n}"

    def _rebuild_counters(self) -> None:
        self._name_counters.clear()
        for p in self.placements:
            base = p.kind
            n = self._name_counters.get(base, 0) + 1
            self._name_counters[base] = n

    def _get_paint_mask(self, p):
        from elysium.render.texture import PaintMask
        key = id(p)
        m = self.paint_masks.get(key)
        if m is None:
            m = PaintMask(int(max(1, p.w)), int(max(1, p.h)))
            self.paint_masks[key] = m
        return m

    def _all_skin_hooks(self) -> list[str]:
        out = []
        for p in self.placements:
            h = (p.props or {}).get("hook")
            if h: out.append(h)
        return out

    def _render_final_selected(self) -> None:
        # Headless: skip the worker spawn the GUI Designer uses;
        # the agent's `mesh.render_final` returns `queued=True` either
        # way, and the actual render happens via render_mesh on demand.
        pass


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------

def _hex(c) -> str:
    if len(c) == 4: return "#{:02X}{:02X}{:02X}{:02X}".format(*c)
    return "#{:02X}{:02X}{:02X}".format(*c)

def _rect_d(x, y, w, h) -> str:
    return f"M {x} {y} L {x+w} {y} L {x+w} {y+h} L {x} {y+h} Z"

def _round_d(x, y, w, h, r) -> str:
    return (f"M {x+r} {y} L {x+w-r} {y} Q {x+w} {y} {x+w} {y+r} "
            f"L {x+w} {y+h-r} Q {x+w} {y+h} {x+w-r} {y+h} "
            f"L {x+r} {y+h} Q {x} {y+h} {x} {y+h-r} "
            f"L {x} {y+r} Q {x} {y} {x+r} {y} Z")
