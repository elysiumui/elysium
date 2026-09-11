"""Tiny in-memory surrogate that satisfies the Session/tool contract
without spinning up the GUI Designer. Lets the agent operate on a
skin from the CLI, in tests, and over the JSON-RPC daemon (Phase 4.2).

The tools call into ``session.designer.placements`` / ``window_doc`` /
``_assign_name`` / ``save_layout`` — we provide minimal stand-ins for
each that read and write the native Designer document schema.
"""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import scene_identity
from ..render import mesh_document, scene, scene_lighting


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
    scene_lighting: dict = field(default_factory=scene_lighting.settings)

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
        self._name_counters: dict[str, int] = {}
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

    def _snapshot(self):
        return deepcopy({
            "window": self.window_doc.to_json(),
            "placements": [p.to_json() for p in self.placements],
            "mesh_document": mesh_document.capture(self.placements),
            "layout_extra": getattr(self, "_layout_extra", {}),
            "selection": (self.sel_kind, self.sel_idx, self.sel_set),
        })

    def _restore(self, data):
        window = AppWindow.from_json(data["window"])
        placements = [Placement.from_json(p) for p in data["placements"]]
        scene_identity.validate(placements)
        mesh_document.restore(data["mesh_document"], placements)
        self.window_doc, self.placements = window, placements
        self._layout_extra = deepcopy(data["layout_extra"])
        self.sel_kind, self.sel_idx, self.sel_set = deepcopy(data["selection"])
        self._rebuild_counters()

    def dispatch_persistent_tool(self, call, session, registry):
        """Commit a CLI document mutation before reporting tool success."""
        from jsonschema import Draft202012Validator
        from .types import ToolResult
        before = None
        try:
            Draft202012Validator(registry.get(call.name).input_schema).validate(call.args)
            before = self._snapshot()
            snap = session.snapshots.capture(session, action=call.name)
        except Exception as exc:
            return ToolResult(id=call.id, ok=False, error=f"Cannot checkpoint command: {exc}")
        result = registry.dispatch(call, session)
        result.snapshot_id = snap.id
        if result.ok:
            try:
                self.save_layout()
            except Exception as exc:
                result.ok, result.error, result.value = False, f"Cannot persist command: {exc}", None
        if not result.ok:
            self._restore(before)
        return result

    def save_layout(self) -> None:
        layout = self.skin_path / "designer_layout.json"
        payload = {
            **deepcopy(getattr(self, "_layout_extra", {})),
            "window": self.window_doc.to_json(),
            "placements": [p.to_json() for p in self.placements],
            "mesh_document": mesh_document.capture(self.placements),
        }
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
        layout = self.skin_path / "designer_layout.json"
        if not layout.is_file(): return
        data = json.loads(layout.read_text())
        window = AppWindow.from_json(data.get("window", {}))
        placements = [Placement.from_json(p) for p in data.get("placements", [])]
        scene_identity.validate(placements)
        mesh_document.restore(data.get("mesh_document"), placements)
        for p in placements:
            if p.kind == "Mesh3D":
                mesh_document.resolve(p.mesh_kind)
        self.window_doc, self.placements = window, placements
        self._layout_extra = {k:deepcopy(v) for k,v in data.items() if k not in ("window", "placements", "mesh_document")}
        self.sel_kind, self.sel_idx, self.sel_set = "none", -1, set()
        self._rebuild_counters()

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
