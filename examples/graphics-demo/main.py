"""Graphics demo — a mini flowchart editor on `elysium.graphics` (Tier 5).

A `Scene` of node + connector items inside a pan/zoom `GraphicsView`, with a
`SceneController` providing the interaction Qt's `QGraphicsView` gives you:

  * Click a node to select it (Shift-click to multi-select); drag empty space
    to rubber-band a group.
  * Drag a node to move it (snapped to an 8px grid); drag a corner/edge handle
    to resize a single selected box.
  * Mouse-wheel zooms about the cursor; middle-drag (or space-drag) pans.

`build_editor()` / `paint_editor()` keep it headlessly testable; `main()` opens
the real borderless, Studio-themed window.

Run:  python examples/graphics-demo/main.py
"""
from __future__ import annotations

from elysium import theme as T
from elysium.components import _rounded_rect
from elysium.graphics import (
    Scene, RectItem, EllipseItem, LineItem, TextItem, GraphicsView,
    SceneController,
)
from elysium.shell import ToolBar, ToolButton, StatusBar

TOOLBAR_H = 40.0
STATUS_H = 24.0


def _node(scene: Scene, x: float, y: float, w: float, h: float, label: str,
          accent: bool = False) -> RectItem:
    t = T.current_theme()
    fill = T.with_alpha(t.primary, 0.18) if accent else t.surface_variant
    stroke = t.primary if accent else t.edge
    box = scene.add(RectItem(x=x, y=y, w=w, h=h, fill=fill, stroke=stroke,
                             stroke_width=1.6, radius=10, z=2))
    scene.add(TextItem(x=x + 14, y=y + h / 2 - 9, w=w - 20, h=18, text=label,
                       size=13, z=3, selectable=False))
    return box


def build_editor(w: float, h: float) -> dict:
    """Build the scene + view + controller sized to a ``w``×``h`` window."""
    T.set_theme(T.studio_dark())
    scene = Scene()
    # Connectors first (drawn under the nodes).
    scene.add(LineItem(x1=180, y1=110, x2=260, y2=160, stroke=None,
                       stroke_width=2.0, z=1))
    scene.add(LineItem(x1=380, y1=185, x2=460, y2=160, stroke=None,
                       stroke_width=2.0, z=1))
    _node(scene, 60, 80, 120, 60, "Start", accent=True)
    _node(scene, 260, 130, 120, 60, "Process")
    scene.add(EllipseItem(x=460, y=130, w=130, h=70,
                          fill=T.with_alpha(T.current_theme().accent, 0.16),
                          stroke=T.current_theme().accent, stroke_width=1.6, z=2))
    scene.add(TextItem(x=485, y=156, w=90, h=18, text="Decision", size=13,
                       z=3, selectable=False))
    _node(scene, 260, 250, 120, 60, "Done")

    view = GraphicsView(scene=scene, x=0, y=TOOLBAR_H, w=w,
                        h=h - TOOLBAR_H - STATUS_H)
    controller = SceneController(view=view, snap=8)

    toolbar = ToolBar(x=0, y=0, w=w, h=TOOLBAR_H, items=[
        ToolButton(icon=_ic_select, checked=True, tooltip="Select"),
        ToolButton(icon=_ic_node, tooltip="Add node"),
        ToolButton(icon=_ic_link, tooltip="Connect"),
        "separator",
        ToolButton(icon=_ic_fit, tooltip="Fit",
                   on_click=lambda: view.fit(margin=40)),
        "spacer",
    ])
    statusbar = StatusBar(x=0, y=h - STATUS_H, w=w, h=STATUS_H,
                          message="Drag to move · handles to resize · "
                                  "rubber-band to multi-select",
                          sections=["100%"])
    return {"scene": scene, "view": view, "controller": controller,
            "toolbar": toolbar, "statusbar": statusbar}


def _ic_select(dl, cx, cy, s, c):
    dl.stroke_path(
        f"M {cx-s*0.3} {cy-s*0.4} L {cx-s*0.3} {cy+s*0.35} L {cx-s*0.05} {cy+s*0.1} "
        f"L {cx+s*0.15} {cy+s*0.45} L {cx+s*0.28} {cy+s*0.38} L {cx+s*0.06} {cy+s*0.05} "
        f"L {cx+s*0.32} {cy+s*0.05} Z", c, 1.6)


def _ic_node(dl, cx, cy, s, c):
    dl.stroke_path(f"M {cx-s*0.4} {cy-s*0.25} L {cx+s*0.4} {cy-s*0.25} "
                   f"L {cx+s*0.4} {cy+s*0.25} L {cx-s*0.4} {cy+s*0.25} Z", c, 1.6)


def _ic_link(dl, cx, cy, s, c):
    dl.stroke_path(f"M {cx-s*0.35} {cy+s*0.2} L {cx+s*0.35} {cy-s*0.2}", c, 1.6)
    dl.fill_path(f"M {cx-s*0.35} {cy+s*0.2} m -2 -2 l 4 0 l -2 4 Z", c)


def _ic_fit(dl, cx, cy, s, c):
    for sx in (-1, 1):
        for sy in (-1, 1):
            dl.stroke_path(
                f"M {cx+sx*s*0.4} {cy+sy*s*0.18} L {cx+sx*s*0.4} {cy+sy*s*0.4} "
                f"L {cx+sx*s*0.18} {cy+sy*s*0.4}", c, 1.6)


def paint_editor(dl, ed: dict, w: float, h: float) -> None:
    t = T.current_theme()
    dl.fill_path(_rounded_rect(0, 0, w, h, 0), t.surface)
    ed["view"].paint(dl)
    ed["controller"].paint_overlay(dl)
    ed["toolbar"].paint(dl)
    ed["statusbar"].message = (
        f"{len(ed['scene'].selected_items())} selected · "
        f"drag to move · handles to resize")
    ed["statusbar"].sections = [f"{int(ed['view'].zoom * 100)}%"]
    ed["statusbar"].paint(dl)


def main() -> None:  # pragma: no cover - opens a real window
    import elysium as ely
    from elysium._native import _native as _n

    T.set_theme(T.studio_dark())
    app = ely.App(title="Elysium — Graphics demo",
                  identifier="dev.elysium.graphicsdemo")
    win = app.window(transparent=True, title_bar=False, resizable=True,
                     initial_size=(900, 600))
    ed = build_editor(900, 600)

    def on_frame(_dt):
        ww, wh = win.surface_size()
        ed["toolbar"].w = ww
        ed["view"].w = ww
        ed["view"].h = wh - TOOLBAR_H - STATUS_H
        ed["statusbar"].w = ww
        ed["statusbar"].y = wh - STATUS_H
        dl = _n.DisplayList()
        paint_editor(dl, ed, ww, wh)
        win.submit(dl)

    win.on_frame(on_frame)
    app.run()


if __name__ == "__main__":
    main()
