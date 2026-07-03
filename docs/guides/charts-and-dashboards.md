# Charts and dashboards

Elysium ships the building blocks for a data dashboard — the class of UI Qt
covers with QtCharts plus a pile of hand-rolled widgets. Everything here is pure
Python drawn on the `DisplayList`, reads the active [theme](theming.md) at paint
time, and lays out to an `x / y / w / h` box so it is responsive.

- **`elysium.charts`** — `LineChart`, `AreaChart`, `BarChart`,
  `DonutChart` / `PieChart`, `Sparkline`, `Legend`, plus the `nice_ticks`
  helper and the `format_money` / `format_pct` / `format_compact` formatters.
- **`elysium.components.dashboard`** — `MetricCard` (KPI tile),
  `Alert` and `NotificationInbox` (a persistent "needs attention" panel).
- **`elysium.components.daterange`** — `SegmentedControl` and `DateRangePicker`
  (the preset + custom date bar).

See the runnable reference app at
[`examples/storeprofitlens-dashboard/`](https://github.com/) which assembles all
of these into a true-net-profit dashboard.

## Series and formatters

A `Series` is a labelled list of values with an optional colour. Charts take one
or more series. The formatters turn raw numbers into axis/label strings:

```python
from elysium.charts import Series, format_money, format_pct, format_compact

revenue = Series(values=[3200, 4100, 3800, 5200, 6100], name="Revenue",
                 color=(0x1F, 0x9D, 0x6B, 0xFF))

format_money(19540)      # "$19,540"
format_pct(0.214)        # "21.4%"
format_compact(15400)    # "15.4k"
```

`chart_palette(n)` returns `n` distinct theme-aware colours when you do not want
to pick them by hand.

## Line and area charts

`LineChart` and `AreaChart` share the same fields. Set `stacked=True` to stack
multiple series; pass `y_format` to label the y-axis, and `show_grid` /
`show_axis` to toggle the gridlines and axis. Padding fields (`pad_left`, …)
reserve room for labels.

```python
from elysium.charts import AreaChart, Series, format_money

chart = AreaChart(
    series=[Series(values=trend, color=(0x1F, 0x9D, 0x6B, 0xFF))],
    x=16, y=48, w=560, h=180,
    y_format=lambda v: format_money(v),   # money axis
    show_grid=True,
)
chart.paint(dl)
```

`plot_rect()` returns the inner plotting rectangle (inside the padding) if you
need to overlay annotations.

## Bar charts

`BarChart` takes a list of `categories` and one or more series. `stacked=True`
stacks the series per category; `radius` rounds the bar caps.

```python
from elysium.charts import BarChart, Series

BarChart(
    categories=["Mon", "Tue", "Wed", "Thu", "Fri"],
    series=[Series(values=[12, 19, 14, 22, 18], color=(0x5B, 0x8D, 0xEF, 0xFF))],
    x=16, y=48, w=420, h=200,
).paint(dl)
```

## Donut and pie charts

`DonutChart` takes `segments` as `(label, value, color)` tuples and draws annular
wedges (via SVG arc paths). `inner_ratio` controls the hole size, `gap_deg` the
slice spacing, and `center_value` / `center_label` fill the hole. `PieChart` is
the same with no hole.

```python
from elysium.charts import DonutChart, Legend, format_money

cost = [("COGS", 8920, (0x5B, 0x8D, 0xEF, 0xFF)),
        ("Ad spend", 3640, (0xF4, 0xA9, 0x3C, 0xFF)),
        ("Refunds", 1206, (0xFB, 0x71, 0x85, 0xFF))]

DonutChart(segments=cost, x=16, y=48, w=120, h=120,
           center_value="$15.4k", center_label="Cost").paint(dl)

# A matching legend: (label, color, value-string) rows.
Legend(entries=[(n, c, format_money(v)) for n, v, c in cost],
       x=150, y=56, w=200, row_h=22).paint(dl)
```

## KPI metric cards

`MetricCard` is the dashboard headline tile: a small `label`, a big `value`
(you format it), an optional `delta` badge with a `delta_dir` (+1 ▲ / −1 ▼ / 0),
an optional `sub` note, and an optional inline `spark` sparkline.

`good_up` decides the badge colour direction — "Net profit ▲" is profit-green,
but "Refund drag ▲" is loss-red, so set `good_up=False` there. Set
`tabular=True` so the figure uses [tabular numerals](#tabular-numerals).

```python
from elysium.components.dashboard import MetricCard

MetricCard(label="Net profit", value="$4,182", delta="12.4%", delta_dir=1,
           sub="vs prior day", tabular=True, spark=trend[-8:],
           x=16, y=16, w=200, h=100).paint(dl)

MetricCard(label="Refund drag", value="-$1,206", delta="6.2% of rev",
           delta_dir=1, good_up=False, tabular=True,
           x=232, y=16, w=200, h=100).paint(dl)
```

## Alerts and the notification inbox

`Alert` is a persistent, dismissible row with a `severity`
(`info` / `success` / `warning` / `danger`), an optional `action_label` +
`on_action`, and an `on_dismiss`. `NotificationInbox` stacks a list of alerts
into a "needs attention" panel and routes clicks/dismissals.

```python
from elysium.components.dashboard import Alert, NotificationInbox

inbox = NotificationInbox(title="Needs attention", x=16, y=16, w=340, h=300,
    alerts=[
        Alert(severity="warning", title="4 SKUs missing cost",
              body="Profit on 38 orders is overstated.",
              action_label="Fix in COGS wizard →",
              on_action=open_cogs_wizard),
        Alert(severity="danger", title="Refund rate up 2.1 pts",
              body="Wool Runner Rug drove most of the increase."),
    ])
inbox.paint(dl)
# forward clicks so dismiss/action buttons work:
# inbox.on_click(mx, my)
```

These are distinct from the transient `Toast` / `Snackbar` in
`elysium.components` — use those for ephemeral feedback, the inbox for state that
persists until the user resolves it.

## The date bar

`SegmentedControl` is a generic single-choice toggle. `DateRangePicker` builds on
it with the presets `Today / Yesterday / Last 7 days / Last 30 days / Custom`
(`PRESETS`) and resolves to a concrete `(start, end)` range:

```python
from elysium.components.daterange import DateRangePicker
import datetime

picker = DateRangePicker(selected=2, x=16, y=16, w=320, h=30,   # Last 7 days
                         on_change=lambda i: refresh())
picker.paint(dl)

start, end = picker.current_range(datetime.date.today())
```

Switching to **Custom** carries the prior range until you clear `start` / `end`
and set your own (e.g. from a `CalendarWidget` popover).

## Tabular numerals

Monetary and metric columns only line up if every digit is the same width.
Pass `tabular=True` to a `Label` or `MetricCard`, or call `draw_paragraph` with
`tabular=True` directly, to enable the OpenType `tnum` + `lnum` features:

```python
from elysium.components import Label

Label(text="$19,540.00", size=20, align="right", tabular=True,
      x=0, y=0, w=160, h=24).paint(dl)
```

Combine with [Plus Jakarta Sans](theming.md) (or any registered
font) for the spec look. See the [theming guide](theming.md) for
`set_ui_font` / `register_ui_font_from_file`.

## See also

- API: [`elysium.charts`](../api/charts.md),
  [`elysium.components.dashboard`](../api/dashboard.md),
  [`elysium.components.daterange`](../api/daterange.md)
- [The data grid](data-grid.md) — the other half of a data app
- [Build a Shopify-style desktop app](../tutorials/shopify-style-desktop-app.md)
