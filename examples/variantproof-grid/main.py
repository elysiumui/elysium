"""VariantProof bulk editor — a reference data app on Elysium.

Reproduces the Product Grid screen from the product spec using the Tier-8
`DataGrid`: frozen Handle/Title columns, a column chooser, inline edits shown as
green pending cells, per-cell validation badges, and a bottom pending-changes
tray, plus a `ToolBar` of transforms and a saved-views sidebar.

`build_editor()` / `paint_editor()` keep it headlessly testable; `main()` opens
the real window.

Run:  python examples/variantproof-grid/main.py
"""
from __future__ import annotations

import os

from elysium import theme as T
from elysium.components import _rounded_rect, Label
from elysium.shell import ToolBar, ToolButton, StatusBar
from elysium.modelview import ItemModel, Column
from elysium.modelview.grid import DataGrid

NAV_W = 190.0
TOOLBAR_H = 40.0
TRAY_H = 34.0

_CATALOG = [
    ("aurora-merino-crew", "Aurora Merino Crew", "AMC-NVY-S", "Northwind", "Knitwear", 128.0, 42),
    ("trailhead-shell-jkt", "Trailhead Shell Jacket", "TSJ-OLV-L", "Crestline", "Outerwear", 245.0, 8),
    ("cove-linen-shirt", "Cove Linen Shirt", "CLS-WHT-M", "Harbor Co.", "Shirts", 78.0, 120),
    ("summit-wool-beanie", "Summit Wool Beanie", "SWB-CHR-OS", "Crestline", "Accessories", 34.0, 240),
    ("meadow-poplin-dress", "Meadow Poplin Dress", "MPD-SGE-8", "Fernweh", "Dresses", 156.0, 33),
    ("drift-knit-joggers", "Drift Knit Joggers", "DKJ-BLK-M", "Fernweh", "Bottoms", 92.0, 54),
    ("glade-flannel-shirt", "Glade Flannel Shirt", "GFS-RED-L", "Crestline", "Shirts", 88.0, 73),
    ("cirrus-down-vest", "Cirrus Down Vest", "CDV-SLT-M", "Crestline", "Outerwear", 164.0, 19),
]
_KEYS = ["handle", "title", "sku", "vendor", "type", "price", "inv"]


def _ic_dot(dl, cx, cy, s, c):
    dl.fill_path(_rounded_rect(cx - s / 2, cy - s / 2, s, s, 3), c)


def build_editor(w: float, h: float) -> dict:
    if os.environ.get("ELYSIUM_FONT"):
        T.set_ui_font(os.environ["ELYSIUM_FONT"])
    T.set_theme(T.studio_dark())
    cols = [Column(key="handle", width=160), Column(key="title", width=180),
            Column(key="sku", width=120), Column(key="vendor", width=120),
            Column(key="type", width=120),
            Column(key="price", width=90, align="right"),
            Column(key="inv", width=60, align="right")]
    rows = [dict(zip(_KEYS, r)) for r in _CATALOG] * 4  # ~32 rows
    grid = DataGrid(model=ItemModel(rows=rows, columns=cols),
                    frozen_cols=2,
                    sortable=True,      # click a header to sort (asc→desc→off)
                    filterable=True,    # per-column search row under the headers
                    formatter=lambda v, c: (f"${v:,.2f}" if c.key == "price"
                                            else str(v)))
    grid.validators["sku"] = lambda v: ("duplicate SKU" if str(v).endswith("DUP")
                                        else None)
    # Seed a few pending edits + a validation error so the screen is alive.
    grid.set_cell(0, 5, 132.0)
    grid.set_cell(3, 5, 36.0)
    grid.set_cell(2, 2, "CLS-WHT-DUP")
    grid.select(1, 3)
    grid.select(2, 5, extend=True)

    toolbar = ToolBar(w=w, h=TOOLBAR_H, items=[
        ToolButton(label="Fill down", icon=_ic_dot, tooltip="Fill down"),
        ToolButton(label="Find/replace", icon=_ic_dot),
        ToolButton(label="% price", icon=_ic_dot),
        "separator",
        ToolButton(label="Bulk transform", icon=_ic_dot),
        "spacer",
    ])
    statusbar = StatusBar(message="Local snapshot · 12,480 products",
                          sections=["1,204 rows", "9,612 variants"])
    views = [("All products", 12480), ("FW25 drop", 1204),
             ("Needs metafields", 842), ("Low inventory", 316),
             ("Missing handles", 12)]
    return {"grid": grid, "toolbar": toolbar, "statusbar": statusbar,
            "views": views, "active_view": 1}


def paint_editor(dl, app: dict, w: float, h: float) -> None:
    t = T.current_theme()
    dl.fill_path(_rounded_rect(0, 0, w, h, 0), t.surface)
    # Toolbar.
    tb = app["toolbar"]
    tb.w = w
    tb.paint(dl)
    # Saved-views sidebar.
    sy = TOOLBAR_H
    dl.fill_path(_rounded_rect(0, sy, NAV_W, h - sy - TRAY_H, 0), t.surface_variant)
    dl.draw_text("SAVED VIEWS", 16, sy + 22, 10, t.on_surface_muted)
    for i, (name, count) in enumerate(app["views"]):
        ry = sy + 40 + i * 30
        if i == app["active_view"]:
            dl.fill_path(_rounded_rect(8, ry - 16, NAV_W - 16, 26, 7),
                         T.with_alpha(t.primary, 0.18))
        dl.draw_text(name, 18, ry, 12,
                     t.on_surface if i == app["active_view"] else t.on_surface_muted)
        Label(x=NAV_W - 60, y=ry - 14, w=46, h=18, text=f"{count:,}", size=11,
              align="right", color=t.on_surface_muted, tabular=True).paint(dl)
    # Grid.
    g = app["grid"]
    g.x, g.y = NAV_W, TOOLBAR_H
    g.w, g.h = w - NAV_W, h - TOOLBAR_H - TRAY_H
    g.paint(dl)
    # Pending-changes tray.
    ty = h - TRAY_H
    dl.fill_path(_rounded_rect(0, ty, w, TRAY_H, 0), lighten_surface(t))
    dl.fill_path(_rounded_rect(0, ty, w, 1, 0), T.with_alpha(t.edge, 0.8))
    pending = g.dirty_count()
    errors = g.error_count()
    dl.filled_circle(18, ty + TRAY_H / 2, 4, t.success if not errors else t.warning)
    dl.draw_text(f"{pending} pending edits · {errors} need attention",
                 30, ty + TRAY_H * 0.64, 12, t.on_surface_muted)
    # Sync button (right).
    bw = 140
    dl.fill_path(_rounded_rect(w - bw - 12, ty + 6, bw, TRAY_H - 12, 8), t.primary)
    dl.draw_text("Sync to Shopify", w - bw + 14, ty + TRAY_H * 0.64, 12,
                 (255, 255, 255, 255))


def lighten_surface(t):
    return T.lighten(t.surface, 0.02)


def main() -> None:  # pragma: no cover - opens a real window
    import elysium as ely
    from elysium._native import _native as _n
    app = build_editor(1180, 720)
    a = ely.App(title="VariantProof", identifier="com.variantproof.app")
    win = a.window(transparent=True, title_bar=False, resizable=True,
                   initial_size=(1180, 720))

    def on_frame(_dt):
        ww, wh = win.surface_size()
        dl = _n.DisplayList()
        paint_editor(dl, app, ww, wh)
        win.submit(dl)

    win.on_frame(on_frame)
    a.run()


if __name__ == "__main__":
    main()
