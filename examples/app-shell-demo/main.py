"""App-shell demo — a docking IDE built from `elysium.shell` (Tier 4).

Composes the Qt-`QMainWindow`-class widgets Elysium gained in Tier 4 into one
screen:

  * `MenuBar`   — File / Edit / View / Help, each opening a dropdown.
  * `ToolBar`   — select / pen / rect / text tools + run, with a checked tool.
  * `DockManager` — Explorer + Outline (left, tabbed), Properties (right),
    Console + Problems (bottom, tabbed), and the editor in the centre. Drag a
    tab to re-dock; drag a splitter handle to resize; the layout round-trips
    through `serialize()` / `restore()`.
  * `StatusBar` — a message + right-aligned cursor / encoding sections.

All on a borderless, GPU-rendered, Studio-themed window.

Run:  python examples/app-shell-demo/main.py
"""
from __future__ import annotations

import sys

from elysium import theme as T
from elysium.components import Label, MenuItem, _rounded_rect
from elysium.shell import (
    MenuBar, ToolBar, ToolButton, DockManager, DockWidget, StatusBar,
)

MENU_H = 28.0
TOOLBAR_H = 40.0
STATUS_H = 24.0


class _Body:
    """A tiny content widget that draws labelled rows — stands in for a real
    panel so the demo stays self-contained."""

    def __init__(self, rows: list[str]):
        self.rows = rows
        self.x = self.y = self.w = self.h = 0.0

    def paint(self, dl) -> None:
        t = T.current_theme()
        for i, row in enumerate(self.rows):
            col = t.on_surface if i == 0 else t.on_surface_muted
            dl.draw_text(row, self.x + 12, self.y + 22 + i * 20, 12, col)


# --- icon painters for the toolbar ----------------------------------------

def _ic_cursor(dl, cx, cy, s, c):
    dl.stroke_path(
        f"M {cx-s*0.3} {cy-s*0.4} L {cx-s*0.3} {cy+s*0.35} L {cx-s*0.05} {cy+s*0.1} "
        f"L {cx+s*0.15} {cy+s*0.45} L {cx+s*0.28} {cy+s*0.38} L {cx+s*0.06} {cy+s*0.05} "
        f"L {cx+s*0.32} {cy+s*0.05} Z", c, 1.6)


def _ic_rect(dl, cx, cy, s, c):
    dl.stroke_path(
        f"M {cx-s*0.4} {cy-s*0.3} L {cx+s*0.4} {cy-s*0.3} L {cx+s*0.4} {cy+s*0.3} "
        f"L {cx-s*0.4} {cy+s*0.3} Z", c, 1.6)


def _ic_text(dl, cx, cy, s, c):
    dl.stroke_path(f"M {cx-s*0.3} {cy-s*0.3} L {cx+s*0.3} {cy-s*0.3} "
                   f"M {cx} {cy-s*0.3} L {cx} {cy+s*0.35}", c, 1.6)


def _ic_run(dl, cx, cy, s, c):
    dl.fill_path(f"M {cx-s*0.25} {cy-s*0.35} L {cx+s*0.35} {cy} "
                 f"L {cx-s*0.25} {cy+s*0.35} Z", c)


def build_shell(w: float, h: float) -> dict:
    """Construct the shell widgets sized to a ``w``×``h`` window. Returns a dict
    so a host (or a headless test) can paint + dispatch into them."""
    status_msg = {"text": "Ready"}

    menubar = MenuBar(x=0, y=0, w=w, h=MENU_H, menus=[
        ("File", [MenuItem(label="New", shortcut="Ctrl+N"),
                  MenuItem(label="Open…", shortcut="Ctrl+O"),
                  MenuItem(label="Save", shortcut="Ctrl+S"),
                  MenuItem(label="Quit", shortcut="Ctrl+Q", danger=True,
                           on_click=lambda: sys.exit(0))]),
        ("Edit", [MenuItem(label="Undo", shortcut="Ctrl+Z"),
                  MenuItem(label="Redo", shortcut="Ctrl+Y")]),
        ("View", [MenuItem(label="Toggle Console")]),
        ("Help", [MenuItem(label="About Elysium")]),
    ])

    sel = ToolButton(icon=_ic_cursor, checked=True, tooltip="Select")
    toolbar = ToolBar(x=0, y=MENU_H, w=w, h=TOOLBAR_H, items=[
        sel,
        ToolButton(icon=_ic_rect, tooltip="Rectangle"),
        ToolButton(icon=_ic_text, tooltip="Text"),
        "separator",
        ToolButton(icon=_ic_run, tooltip="Run",
                   on_click=lambda: status_msg.update(text="Running…")),
        "spacer",
    ])

    docks = DockManager(x=0, y=MENU_H + TOOLBAR_H, w=w,
                        h=h - MENU_H - TOOLBAR_H - STATUS_H)
    docks.add(DockWidget(id="explorer", title="Explorer", content=_Body(
        ["▸ src", "  app.py", "  ui.py", "▸ assets", "  README.md"])), "left")
    docks.add(DockWidget(id="outline", title="Outline", content=_Body(
        ["class App", "  def run()"])), "left")
    docks.add(DockWidget(id="props", title="Properties", content=_Body(
        ["Name   App", "Size   1280×800", "Theme  Studio Dark"])), "right")
    docks.add(DockWidget(id="editor", title="app.py", closable=False, content=_Body(
        ["def main():", "    app = App()", "    win = app.window()",
         "    win.show()"])), "center")
    docks.add(DockWidget(id="console", title="Console", content=_Body(
        ["$ elysium run app.py", "ready."])), "bottom")
    docks.add(DockWidget(id="problems", title="Problems", content=_Body(
        ["0 errors, 0 warnings"])), "bottom")

    statusbar = StatusBar(x=0, y=h - STATUS_H, w=w, h=STATUS_H,
                          message=status_msg["text"],
                          sections=["UTF-8", "Ln 1, Col 1", "Studio Dark"])

    return {"menubar": menubar, "toolbar": toolbar, "docks": docks,
            "statusbar": statusbar, "_status_msg": status_msg}


def paint_shell(dl, shell: dict, w: float, h: float) -> None:
    """Paint the whole shell into a DisplayList (used by the window loop and by
    the headless smoke test)."""
    t = T.current_theme()
    dl.fill_path(_rounded_rect(0, 0, w, h, 0), t.surface)
    shell["statusbar"].message = shell["_status_msg"]["text"]
    shell["docks"].paint(dl)
    shell["toolbar"].paint(dl)
    shell["statusbar"].paint(dl)
    shell["menubar"].paint(dl)
    m = shell["menubar"].open_menu()
    if m is not None:
        m.paint(dl)


def main() -> None:  # pragma: no cover - opens a real window
    import elysium as ely
    from elysium._native import _native as _n

    T.set_theme(T.studio_dark())
    app = ely.App(title="Elysium — App-shell demo", identifier="dev.elysium.shelldemo")
    win = app.window(transparent=True, title_bar=False, resizable=True,
                     initial_size=(1280, 800))
    shell = build_shell(1280, 800)

    def on_frame(_dt):
        ww, wh = win.surface_size()
        shell["menubar"].w = ww
        shell["toolbar"].w = ww
        shell["docks"].w = ww
        shell["docks"].h = wh - MENU_H - TOOLBAR_H - STATUS_H
        shell["statusbar"].w = ww
        shell["statusbar"].y = wh - STATUS_H
        dl = _n.DisplayList()
        paint_shell(dl, shell, ww, wh)
        win.submit(dl)

    win.on_frame(on_frame)
    app.run()


if __name__ == "__main__":
    main()
