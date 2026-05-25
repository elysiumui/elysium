"""Tiny in-memory surrogate that satisfies the Session/tool contract
without spinning up the GUI Designer. Lets the agent operate on a
skin from the CLI, in tests, and over the JSON-RPC daemon (Phase 4.2).

The tools call into ``session.designer.placements`` / ``window_doc`` /
``_assign_name`` / ``save_layout`` — we provide minimal stand-ins for
each that share the same dataclasses the real Designer uses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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

    def to_json(self) -> dict: return dict(self.__dict__)


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
    fill: tuple = (120, 110, 240, 255)
    stroke: tuple = (0, 0, 0, 0)
    stroke_w: float = 1.0
    color_fill: tuple = (120, 110, 240, 255)
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

    def to_json(self) -> dict:
        out = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        out["states"] = [s.to_json() for s in self.states]
        return out


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

    def to_json(self) -> dict:
        d = dict(self.__dict__)
        d["bg_color"] = list(self.bg_color)
        return d


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
        layout = d.skin_path / "designer_layout.json"
        if layout.is_file():
            data = json.loads(layout.read_text())
            d.window_doc = AppWindow(**{k: v for k, v in
                                         data.get("window", {}).items()
                                         if k in AppWindow.__dataclass_fields__})
            for p in data.get("placements", []):
                d.placements.append(Placement(**{k: v for k, v in p.items()
                                                  if k in Placement.__dataclass_fields__}))
        else:
            d.skin_path.mkdir(parents=True, exist_ok=True)
        d._rebuild_counters()
        return d

    def save_layout(self) -> None:
        layout = self.skin_path / "designer_layout.json"
        layout.parent.mkdir(parents=True, exist_ok=True)
        layout.write_text(json.dumps({
            "window": self.window_doc.to_json(),
            "placements": [p.to_json() for p in self.placements],
        }, indent=2))
        # Mirror the GUI Designer's behavior — emit manifest+document
        # so signature verify / preview render work.
        manifest = self.skin_path / "manifest.json"
        if not manifest.is_file():
            manifest.write_text(json.dumps({
                "schema_version": "1.0",
                "id": f"dev.elysium.{self.skin_path.stem}",
                "name": self.window_doc.title or self.skin_path.stem,
                "version": "0.1.0",
                "color_space": "srgb",
            }, indent=2))
        document = self.skin_path / "document.json"
        document.write_text(json.dumps(self._build_document(), indent=2))

    def load_layout(self) -> None:
        layout = self.skin_path / "designer_layout.json"
        if not layout.is_file(): return
        data = json.loads(layout.read_text())
        self.window_doc = AppWindow(**{k: v for k, v in
                                          data.get("window", {}).items()
                                          if k in AppWindow.__dataclass_fields__})
        self.placements = [
            Placement(**{k: v for k, v in p.items()
                          if k in Placement.__dataclass_fields__})
            for p in data.get("placements", [])
        ]
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
