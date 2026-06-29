# Wizards, steppers and drawers

Multi-step flows (a supplier import, a COGS-coverage setup) and slide-out side
panels (an order-detail drawer) are common in data apps. These live in
`elysium.shell` alongside the rest of the app-shell frame.

## Stepper

`Stepper` renders a numbered progress header: completed steps show a check,
the active step is accented, future steps are muted.

```python
from elysium.shell import Stepper

stepper = Stepper(steps=["Upload", "Map columns", "Preview", "Confirm"],
                  current=1, x=0, y=0, w=600, h=48)
stepper.paint(dl)
```

## Wizard

`Wizard` wraps a `Stepper` header, a routed content area, and a Back / Next /
Finish footer. Each step is `(title, paint_fn)`; the wizard calls the matching
`paint_fn(dl, rect)` for the current step. `on_change(i)` fires on navigation and
`on_finish()` on the last step.

```python
from elysium.shell import Wizard

def paint_upload(dl, rect):  ...
def paint_map(dl, rect):     ...
def paint_preview(dl, rect): ...

wizard = Wizard(
    steps=[("Upload", paint_upload), ("Map columns", paint_map),
           ("Preview", paint_preview)],
    current=0,
    next_label="Next", finish_label="Import",
    on_change=lambda i: log(f"step {i}"),
    on_finish=run_import,
    x=0, y=0, w=720, h=520,
)
wizard.paint(dl)

# drive it from input:
wizard.on_click(mx, my)      # handles the Back / Next / Finish buttons
wizard.next(); wizard.back() # or navigate programmatically
wizard.is_last()             # True on the final step
wizard.content_rect()        # the routed content box, if you lay out yourself
```

## Drawer

`Drawer` is a slide-out panel anchored to a `side` (`left` / `right` / `bottom`)
with an animated offset and a scrim. Toggle it with `set_open(True/False)`; its
`update(dt, state)` animates the slide, and `on_click` closes it when the scrim
or the × is clicked.

```python
from elysium.shell import Drawer

drawer = Drawer(side="right", size=380, title="Order #1042",
                content=paint_order_detail, on_close=lambda: None,
                x=0, y=0, w=1180, h=760)

drawer.set_open(True)
# per frame:
drawer.update(dt, state)
drawer.paint(dl)
# input:
drawer.on_click(mx, my)      # scrim / close button
panel = drawer.panel_rect()  # the (animating) panel rectangle
body  = drawer.content_rect()
```

Use a `Drawer` for transient detail/inspector panels. For permanent, dockable
panels use [`DockManager` / `DockWidget`](app-shell.md); for small anchored
menus use `Popover` in `elysium.components`.

## See also

- API: [`elysium.shell`](../api/shell.md)
- [App shell](app-shell.md) — toolbars, docks, tabs, status bar
- [Build a Shopify-style desktop app](../tutorials/shopify-style-desktop-app.md)
