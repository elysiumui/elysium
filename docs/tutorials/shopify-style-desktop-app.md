# Build a Shopify-style desktop app

This tutorial builds a real data app on Elysium end to end: a **net-profit
dashboard** and a **bulk product editor**, the two screens that back apps like
StoreProfitLens and VariantProof. By the end you will have used charts, KPI
cards, a date bar, an alert inbox, an Excel-grade editable grid, tabular
numerals and a custom font — everything a Shopify-style desktop tool needs.

The finished code is in the repo:

- [`examples/storeprofitlens-dashboard/`](https://github.com/) — the dashboard
- [`examples/variantproof-grid/`](https://github.com/) — the bulk editor

Both split a pure `build_*()` (state) from a pure `paint_*(dl, app, w, h)`
(drawing) so they can be **rendered and tested headlessly**. Follow that split in
your own app — it is what makes the screens unit-testable.

## 0. The shape of an Elysium app

An Elysium component is immediate-mode: each frame you build a `DisplayList` and
the widgets paint into it. Widgets read the active theme at paint time, so the
whole UI recolours when the theme changes.

```python
import elysium as ely
from elysium._native import _native as _n
from elysium import theme as T

def main():
    T.set_theme(T.studio_dark())
    a = ely.App(title="StoreProfitLens", identifier="com.example.spl")
    win = a.window(transparent=True, title_bar=False, resizable=True,
                   initial_size=(1180, 760))

    def on_frame(_dt):
        w, h = win.surface_size()
        dl = _n.DisplayList()
        paint_dashboard(dl, app, w, h)   # <- all your drawing
        win.submit(dl)

    win.on_frame(on_frame)
    a.run()
```

## 1. A custom font and tabular numerals

The spec asks for Plus Jakarta Sans and figures that line up to the cent.
Register the font once, and turn on tabular numerals where you show money:

```python
T.set_ui_font("/path/to/PlusJakartaSans.ttf")   # or register_ui_font_from_file
```

Any `Label(tabular=True)` / `MetricCard(tabular=True)` then renders equal-width
lining digits (the OpenType `tnum` feature). See
[Charts and dashboards → tabular numerals](../guides/charts-and-dashboards.md#tabular-numerals).

## 2. The dashboard

Lay out a left nav, a header with a date bar, a row of KPI cards, a charts row,
and a product table beside an alert inbox. Build the state first:

```python
from elysium.components.dashboard import MetricCard, Alert, NotificationInbox
from elysium.components.daterange import DateRangePicker
from elysium.charts import AreaChart, Series, DonutChart, Legend, format_money

def build_dashboard(w, h):
    T.set_theme(T.studio_dark())
    cards = [
        MetricCard(label="Net profit", value="$4,182", delta="12.4%",
                   delta_dir=1, sub="vs prior day", tabular=True, spark=trend[-8:]),
        MetricCard(label="Refund drag", value="-$1,206", delta="6.2% of rev",
                   delta_dir=1, good_up=False, tabular=True),
        # …
    ]
    inbox = NotificationInbox(title="Needs attention", alerts=[
        Alert(severity="warning", title="4 SKUs missing cost",
              action_label="Fix in COGS wizard →", on_action=open_wizard),
    ])
    return {"date": DateRangePicker(selected=1), "cards": cards, "inbox": inbox,
            "trend": trend, "cost": cost}
```

Then paint it. Each widget is positioned by setting `x/y/w/h` and calling
`paint(dl)`:

```python
def paint_dashboard(dl, app, w, h):
    t = T.current_theme()
    dl.fill_path(_rounded_rect(0, 0, w, h, 0), t.surface)

    # KPI cards across the top
    for i, c in enumerate(app["cards"]):
        c.x, c.y, c.w, c.h = 184 + i * 196, 60, 184, 100
        c.paint(dl)

    # net-profit area chart with a money axis
    AreaChart(series=[Series(values=app["trend"], color=PROFIT)],
              x=200, y=212, w=520, h=120,
              y_format=lambda v: format_money(v)).paint(dl)

    # cost donut + legend
    DonutChart(segments=app["cost"], x=740, y=212, w=110, h=110,
               center_value="$15.4k", center_label="Cost").paint(dl)

    # the alert inbox
    app["inbox"].x, app["inbox"].y, app["inbox"].w, app["inbox"].h = 740, 370, 340, 300
    app["inbox"].paint(dl)
```

Route clicks into the widgets that handle them (`date.on_click`,
`inbox.on_click`) from your window's pointer events.

Full version: [`examples/storeprofitlens-dashboard/main.py`](https://github.com/).
See the [charts and dashboards guide](../guides/charts-and-dashboards.md) for
every chart type and option.

## 3. The bulk editor

The editor is built around a [`DataGrid`](../guides/data-grid.md) over an
`ItemModel`. Pin the identity columns, format prices, and register a validator:

```python
from elysium.modelview import ItemModel, Column
from elysium.modelview.grid import DataGrid

def build_editor(w, h):
    cols = [Column(key="handle", width=160), Column(key="title", width=180),
            Column(key="sku", width=120),
            Column(key="price", width=90, align="right")]
    grid = DataGrid(model=ItemModel(rows=rows, columns=cols), frozen_cols=2,
                    formatter=lambda v, c: f"${v:,.2f}" if c.key == "price" else str(v))
    grid.validators["sku"] = lambda v: "duplicate SKU" if is_dup(v) else None
    return {"grid": grid}
```

Editing marks cells dirty (green) and runs validators (red badge). A bottom tray
reflects the pending state:

```python
grid.set_cell(0, 3, 132.0)                 # pending edit
pending, errors = grid.dirty_count(), grid.error_count()
```

Users copy/paste from Excel (`grid.paste(tsv)`), fill down (`grid.fill_down()`),
and select ranges by dragging — all wired through `grid.on_press/on_drag/
on_release`. When they sync, call `grid.clear_pending()`.

Full version: [`examples/variantproof-grid/main.py`](https://github.com/).

## 4. Test it headlessly

Because drawing is a pure function of state, a smoke test needs no window:

```python
def test_dashboard_paints():
    from elysium._native import _native as n
    app = build_dashboard(1180, 760)
    dl = n.DisplayList(); dl.clear(0.1, 0.11, 0.14, 1.0)
    paint_dashboard(dl, app, 1180, 760)
    layer = n.SkiaLayer(1180, 760); layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
```

See [`tests/test_data_app_demos.py`](https://github.com/) for the real ones.

## 5. Ship it

Package the app with the [packaging guide](../guides/packaging.md) and wire
auto-update per [auto-update](../guides/auto-update.md). For a wizard-driven
import flow (supplier CSV → mapped columns → preview → confirm), see
[wizards and flows](../guides/wizards-and-flows.md).

## Where to go next

- [Charts and dashboards](../guides/charts-and-dashboards.md)
- [The data grid](../guides/data-grid.md)
- [Wizards, steppers and drawers](../guides/wizards-and-flows.md)
- [Component gallery](../resources/component-gallery.md) — everything available
- [Porting from Qt](../guides/porting-from-qt.md) — if you are coming from PySide6
