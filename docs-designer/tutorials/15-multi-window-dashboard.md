# Multi-window dashboard

Time: 75 minutes. Difficulty: Advanced.

Author a four-window dashboard skin: a metrics card, a chart card,
a recent-activity card, and a header window. Each window is a
separate `.esk` that snaps together via window dock-and-follow
logic on the runtime side. The Designer side authors the four
skins consistently.

## Prerequisites

- Designer installed.
- Familiarity with the [Borderless music widget tutorial](02-borderless-music-widget.md).

## Plan the layout

| Window | Size | Position |
|---|---|---|
| Header | 760 x 60 | (0, 0) |
| Metrics card | 240 x 320 | (0, 80) |
| Chart card | 520 x 320 | (260, 80) |
| Activity card | 760 x 220 | (0, 420) |

Total bounding box: 760 x 640.

## Author the four skins

For each window:

1. `File > New Skin` with the size above.
2. Drop a rounded rectangle (radius 16) filling the canvas;
   `material = "glass-dark"`.
3. Use the [Aether scaffold a settings panel](08-aether-scaffold-settings-panel.md)
   workflow to fill in the card's content: describe the card to
   the agent.
4. `Window > Set Shape From Selection` on the rounded rectangle.
5. `File > Save As` to `header.esk/`, `metrics.esk/`, etc.

The Aether-scaffolded content keeps the four cards visually
consistent (same paddings, same heading sizes, same accent usage).

## Theme

Use the same Theme across all four. Pick one in
`Theme > Built-In > Midnight Glass`; the `{theme.…}` references
in each skin resolve to identical values.

## Test alignment

Run all four side by side via `Run > Preview Skin` (one at a time
in v1: the Designer's preview is single-window). Verify each card
looks consistent in isolation.

## Runtime side

The runtime app opens four windows and positions them according to
the table:

```python
app = ely.App(...)
windows = []
for name, (x, y, w, h) in LAYOUT:
    win = app.window(transparent=True, title_bar=False, resizable=False,
                     initial_size=(w, h))
    win.set_outer_position(x, y)
    win.load_skin(f"{name}.esk/")
    windows.append(win)
```

Dock-and-follow: when the header is dragged, the other three move
in lockstep. Use `@header.on("window.moved")` to reposition the
rest (see [Aurora Clock Pro](https://docs.elysiumui.com/tutorials/aurora-clock-pro/)
for the pattern).

## Inter-window state

Share signals across windows:

```python
selected_period = signal("today")    # used by all three cards
```

Each card's effect reads the signal; changing the period in the
header propagates instantly.

## Animate transitions

When the user clicks a period button, fade the chart card's
content over 200 ms via a Tween. Author the placeholder in the
Designer, animate in code.

## Export

Each `.esk` is independent. Ship the four together as a folder:

```
dashboard/
  header.esk/
  metrics.esk/
  chart.esk/
  activity.esk/
  main.py
```

`elysium pack main.py --include header.esk metrics.esk chart.esk activity.esk`.

## What you exercised

- Multi-skin composition.
- Aether-scaffolded card content for visual consistency.
- Window dock-and-follow positioning.
- Cross-window signal sharing.
- Theme-token cascading across four skins.

## See also

- [Aurora Clock Pro framework tutorial](https://docs.elysiumui.com/tutorials/aurora-clock-pro/)
- [Aether scaffold a settings panel](08-aether-scaffold-settings-panel.md)
- [Themes](../themes/index.md)
