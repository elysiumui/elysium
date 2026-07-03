"""window.* tools: chrome, size, background, theme, studio."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="window.set_chrome",
    description="Toggle the OS window chrome. `shape` is 'rect' / "
                "'ellipse' / 'path'; pass `path_d` when shape='path'.",
    input_schema={
        "type": "object",
        "properties": {
            "transparent":  {"type": "boolean"},
            "title_bar":    {"type": "boolean"},
            "shape":        {"type": "string"},
            "path_d":       {"type": "string"},
        },
    },
)
def window_set_chrome(session, transparent: bool | None = None,
                       title_bar: bool | None = None,
                       shape: str | None = None,
                       path_d: str | None = None) -> dict:
    w = session.designer.window_doc
    if transparent is not None: w.transparent = bool(transparent)
    if title_bar   is not None: w.show_title_bar = bool(title_bar)
    if shape       is not None: w.shape = shape
    if path_d      is not None: w.path_d = path_d
    return {"transparent": w.transparent,
             "title_bar": w.show_title_bar,
             "shape": w.shape}


@register_tool(
    name="window.set_size",
    description="Resize the design canvas.",
    input_schema={"type": "object",
                   "properties": {"w": {"type": "number"},
                                   "h": {"type": "number"}},
                   "required": ["w", "h"]},
)
def window_set_size(session, w: float, h: float) -> dict:
    win = session.designer.window_doc
    win.w, win.h = float(w), float(h)
    return {"w": win.w, "h": win.h}


@register_tool(
    name="window.set_bg",
    description="Set the window background. `color` is an [r,g,b,a] "
                "0-255 tuple; pass `gradient_end` to switch to a linear "
                "gradient with `angle` degrees.",
    input_schema={
        "type": "object",
        "properties": {
            "color":         {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
            "gradient_end":  {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
            "angle":         {"type": "number"},
        },
        "required": ["color"],
    },
)
def window_set_bg(session, color: list,
                   gradient_end: list | None = None,
                   angle: float = 90.0) -> dict:
    w = session.designer.window_doc
    def _c(t): return tuple(int(v) for v in t)[:4] + ((255,) if len(t) < 4 else ())
    w.bg_color = _c(color) if len(color) == 4 else _c(list(color) + [255])
    w.gradient_end = _c(gradient_end) if gradient_end else None
    w.gradient_angle = float(angle)
    return {"bg_color": w.bg_color, "gradient_end": w.gradient_end}


@register_tool(
    name="window.set_studio",
    description="Pick one of the lighting studios (see "
                "agent.list_studios). Affects every PBR/Mesh3D placement.",
    input_schema={"type": "object",
                   "properties": {"name": {"type": "string"}},
                   "required": ["name"]},
)
def window_set_studio(session, name: str) -> dict:
    session.designer.window_doc.studio = name
    # Flush PBR caches so the lighting change shows up immediately.
    for cache_attr in ("_pbr_cache", "_mesh_cache"):
        cache = getattr(session.designer, cache_attr, None)
        if cache: cache.clear()
    return {"studio": name}


@register_tool(
    name="window.set_theme",
    description="Switch the active theme (Light / Dark / OLED / Glass / Frost).",
    input_schema={"type": "object",
                   "properties": {"name": {"type": "string"}},
                   "required": ["name"]},
)
def window_set_theme(session, name: str) -> dict:
    themes = ("Light", "Dark", "OLED", "Glass", "Frost")
    if name not in themes:
        raise ValueError(f"unknown theme: {name} (one of {themes})")
    session.designer.theme_index.set(themes.index(name))
    return {"theme": name}


@register_tool(
    name="window.read",
    description="Dump the current window definition.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def window_read(session) -> dict:
    return session.designer.window_doc.to_json()


@register_tool(
    name="view.set_zoom",
    description="Set the canvas (form-area) zoom factor (1.0 = 100%). "
                "Equivalent to Cmd+= / Cmd+- / Cmd+0 keyboard shortcuts and "
                "trackpad pinch. Clamped to the Designer's zoom limits.",
    input_schema={"type": "object",
                   "properties": {"zoom": {"type": "number"}},
                   "required": ["zoom"]},
)
def view_set_zoom(session, zoom: float) -> dict:
    d = session.designer
    setter = getattr(d, "_set_canvas_zoom", None)
    if setter is None:
        # Fallback for older builds.
        d.canvas_zoom = max(0.25, min(6.0, float(zoom)))
    else:
        setter(float(zoom))
    return {"zoom": getattr(d, "canvas_zoom", 1.0)}


@register_tool(
    name="view.read_zoom",
    description="Read the current canvas zoom factor (1.0 = 100%).",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def view_read_zoom(session) -> dict:
    return {"zoom": float(getattr(session.designer, "canvas_zoom", 1.0))}
