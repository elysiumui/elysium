# Scale, scrolling & virtualization

Tier-2 makes Elysium hold frame rate at scale: a dirty-rect render path, real
scroll widgets, and reusable virtualization.

## Dirty-rect compositing

The render thread no longer redraws the whole surface every frame. It diffs the
new display list against the last one, computes the smallest damaged rectangle,
and **clips its raster + GPU upload to that rect** — and skips the frame
entirely when nothing changed (idle UIs cost ~nothing). Output is pixel-identical
to a full redraw; set `ELYSIUM_DIRTY_RECT=0` to force the legacy full redraw.

This is automatic — you don't do anything. It pairs with virtualization: editing
one row of a table damages only that row.

## Scroll

```python
from elysium.components.scroll import ScrollView, ScrollBar

view = ScrollView(x=0, y=0, w=400, h=300, content_w=400, content_h=4000)

# Register it so the InputRouter delivers wheel events:
router.set_scrollables([view])

# Each frame:
view.update(dt)                       # momentum
view.paint(dl, paint_content=draw_my_content)   # clips + translates content
```

`ScrollView` owns `scroll_x/scroll_y`, clips + translates its content, shows
scrollbars when content overflows, and supports wheel, drag, flick momentum, and
`scroll_to_rect`. `ScrollBar` is also usable standalone.

## Virtualization

For long lists/forms, build + paint only what's visible:

```python
from elysium.components.virtual import VirtualList, VirtualForm

rows = VirtualList(
    x=0, y=0, w=400, h=300, item_count=100_000, item_height=28.0,
    render_item=lambda dl, i, x, y, w, h: draw_row(dl, i, x, y, w, h),
)
router.set_scrollables([rows])
rows.paint(dl)        # paints ~11 rows regardless of item_count
```

`VirtualForm` does the same for variable-height rows. The Tier-1 `TableView` /
`ListView` already virtualize via the shared `row_window` / `visible_window`
helpers in `elysium.components.virtual`.
