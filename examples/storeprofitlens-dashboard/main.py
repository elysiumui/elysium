"""StoreProfitLens dashboard — a reference data app on Elysium.

Reproduces the true-net-profit dashboard screen from the product spec using the
Tier-8 widgets: a date-range bar, a row of KPI `MetricCard`s (with tabular
figures + sparklines), a net-profit `AreaChart`, a cost `DonutChart` + `Legend`,
a product-profit table, and a `NotificationInbox` for "needs attention".

`build_dashboard()` / `paint_dashboard()` keep it headlessly testable; `main()`
opens the real borderless, Studio-themed window. Set ELYSIUM_FONT to a Plus
Jakarta Sans `.ttf` to match the spec's typography exactly.

Run:  python examples/storeprofitlens-dashboard/main.py
"""
from __future__ import annotations

import math
import os

from elysium import theme as T
from elysium.components import _rounded_rect, Label
from elysium.components.dashboard import MetricCard, Alert, NotificationInbox
from elysium.components.daterange import DateRangePicker
from elysium.charts import (
    AreaChart, Series, DonutChart, Legend, format_money,
)

NAV_W = 168.0
TOP_H = 64.0
PAD = 16.0

# cost-category colours from the spec
COGS = (0x5B, 0x8D, 0xEF, 0xFF)
ADS = (0xF4, 0xA9, 0x3C, 0xFF)
REF = (0xFB, 0x71, 0x85, 0xFF)
SHIP = (0x2D, 0xC4, 0xA7, 0xFF)
FEES = (0xA7, 0x8B, 0xFA, 0xFF)
PROFIT = (0x1F, 0x9D, 0x6B, 0xFF)


def build_dashboard(w: float, h: float) -> dict:
    if os.environ.get("ELYSIUM_FONT"):
        T.set_ui_font(os.environ["ELYSIUM_FONT"])
    T.set_theme(T.studio_dark())
    trend = [3000 + 700 * math.sin(i / 3) + i * 22 for i in range(30)]
    cards = [
        MetricCard(label="Net profit", value="$4,182", delta="12.4%",
                   delta_dir=1, sub="vs prior day", tabular=True,
                   spark=trend[-8:]),
        MetricCard(label="Net margin", value="21.4%", delta="1.8 pts",
                   delta_dir=1, tabular=True),
        MetricCard(label="Revenue", value="$19,540", delta="6.1%", delta_dir=1,
                   sub="142 orders", tabular=True),
        MetricCard(label="Ad spend", value="$3,640", sub="3.2× ROAS",
                   tabular=True),
        MetricCard(label="Refund drag", value="-$1,206", delta="6.2% of rev",
                   delta_dir=1, good_up=False, tabular=True, spark=trend[-6:]),
    ]
    cost = [("COGS", 8920, COGS), ("Ad spend", 3640, ADS),
            ("Refunds", 1206, REF), ("Shipping", 980, SHIP), ("Fees", 612, FEES)]
    inbox = NotificationInbox(title="Needs attention", alerts=[
        Alert(severity="warning", title="4 SKUs missing cost",
              body="Profit on 38 orders is overstated.",
              action_label="Fix in COGS wizard →"),
        Alert(severity="danger", title="Refund rate up 2.1 pts",
              body="Wool Runner Rug drove most of the increase."),
        Alert(severity="info", title="Ad ROAS dipped to 3.2×",
              body="Down from 3.9× last week."),
    ])
    products = [("Cedar Candle 8oz", 84, "$2,016", "62%", "$1,250"),
                ("Linen Throw — Sand", 31, "$2,790", "44%", "$1,228"),
                ("Ceramic Mug Set", 52, "$1,560", "51%", "$796"),
                ("Wool Runner Rug", 9, "$1,620", "38%", "$616"),
                ("Brass Card Holder", 63, "$945", "57%", "$539")]
    return {
        "date": DateRangePicker(selected=1),     # Yesterday
        "cards": cards,
        "trend": trend,
        "cost": cost,
        "inbox": inbox,
        "products": products,
    }


def paint_dashboard(dl, app: dict, w: float, h: float) -> None:
    t = T.current_theme()
    dl.fill_path(_rounded_rect(0, 0, w, h, 0), t.surface)
    # Left nav.
    dl.fill_path(_rounded_rect(0, 0, NAV_W, h, 0), t.surface_variant)
    for i, item in enumerate(["Dashboard", "Orders", "Products", "Ad spend",
                              "Reports"]):
        iy = 70 + i * 30
        if i == 0:
            dl.fill_path(_rounded_rect(10, iy - 16, NAV_W - 20, 26, 7),
                         T.with_alpha(t.primary, 0.18))
        dl.draw_text(item, 22, iy, 13,
                     t.on_surface if i == 0 else t.on_surface_muted)
    cx = NAV_W + PAD
    cw = w - NAV_W - 2 * PAD
    # Header + date range.
    Label(x=cx, y=16, w=400, h=24, text="Good morning, Kenley", size=18).paint(dl)
    dr = app["date"]
    dr.x, dr.y, dr.w, dr.h = w - 300, 20, 284, 30
    dr.paint(dl)
    # KPI cards.
    n = len(app["cards"])
    card_w = (cw - (n - 1) * 12) / n
    for i, c in enumerate(app["cards"]):
        c.x, c.y, c.w, c.h = cx + i * (card_w + 12), 60, card_w, 100
        c.paint(dl)
    # Charts row.
    chart_y = 176
    chart_h = 170
    aw = cw * 0.6
    dl.fill_path(_rounded_rect(cx, chart_y, aw - 8, chart_h, 12), t.surface_variant)
    dl.draw_text("Net profit trend", cx + 16, chart_y + 24, 13, t.on_surface)
    AreaChart(series=[Series(values=app["trend"], color=PROFIT)],
              x=cx + 4, y=chart_y + 36, w=aw - 24, h=chart_h - 48,
              y_format=lambda v: format_money(v)).paint(dl)
    dx = cx + aw + 4
    dw = cw - aw - 4
    dl.fill_path(_rounded_rect(dx, chart_y, dw, chart_h, 12), t.surface_variant)
    dl.draw_text("Where the money went", dx + 16, chart_y + 24, 13, t.on_surface)
    DonutChart(segments=app["cost"], x=dx + 12, y=chart_y + 36, w=110, h=110,
               center_value="$15.4k", center_label="Cost").paint(dl)
    Legend(entries=[(c[0], c[2], format_money(c[1])) for c in app["cost"]],
           x=dx + 140, y=chart_y + 44, w=dw - 156, row_h=22).paint(dl)
    # Product table + inbox.
    ty = chart_y + chart_h + 12
    tw = cw * 0.6 - 8
    dl.fill_path(_rounded_rect(cx, ty, tw, h - ty - 12, 12), t.surface_variant)
    dl.draw_text("Product profitability", cx + 16, ty + 22, 13, t.on_surface)
    for i, (name, units, rev, margin, profit) in enumerate(app["products"]):
        ry = ty + 44 + i * 24
        dl.draw_text(name, cx + 16, ry, 12, t.on_surface)
        dl.draw_text(str(units), cx + tw - 220, ry, 12, t.on_surface_muted)
        dl.draw_text(rev, cx + tw - 170, ry, 12, t.on_surface_muted)
        dl.draw_text(margin, cx + tw - 100, ry, 12, PROFIT)
        dl.draw_text(profit, cx + tw - 56, ry, 12, t.on_surface)
    inbox = app["inbox"]
    inbox.x, inbox.y = dx, ty
    inbox.w, inbox.h = dw, h - ty - 12
    inbox.paint(dl)


def main() -> None:  # pragma: no cover - opens a real window
    import elysium as ely
    from elysium._native import _native as _n
    app_widgets = build_dashboard(1180, 760)
    a = ely.App(title="StoreProfitLens", identifier="com.storeprofitlens.app")
    win = a.window(transparent=True, title_bar=False, resizable=True,
                   initial_size=(1180, 760))

    def on_frame(_dt):
        ww, wh = win.surface_size()
        dl = _n.DisplayList()
        paint_dashboard(dl, app_widgets, ww, wh)
        win.submit(dl)

    win.on_frame(on_frame)
    a.run()


if __name__ == "__main__":
    main()
