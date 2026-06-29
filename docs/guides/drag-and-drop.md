# Drag and drop

`elysium.dnd` provides inter-widget drag-and-drop — Qt's `QDrag` / `QMimeData`
plus drop events. A drag carries typed payload (`MimeData`) from a press to a
registered `DropZone`.

## Payload

`MimeData` is a small typed bag — set text or arbitrary named formats:

```python
from elysium.dnd import MimeData

md = MimeData()
md.set_text("AMC-NVY-S")
md.set_data("application/x-sku", b"AMC-NVY-S")
md.has_format("application/x-sku")   # True
```

## Zones and the controller

Register `DropZone`s with a `DragController`. A zone has a `rect`, an `accept`
predicate (given the drag's `MimeData`), and an `on_drop` callback. Drive the
controller from pointer events; it tracks the threshold, the active drag and the
hovered zone, and paints the drag affordance:

```python
from elysium.dnd import DragController, DropZone

drag = DragController(threshold=6)
drag.add_zone(DropZone(
    rect=(400, 0, 200, 600),
    accept=lambda md: md.has_format("application/x-sku"),
    on_drop=lambda md: add_to_collection(md.data("application/x-sku")),
))

# per frame / input:
drag.press(mx, my, lambda: md)   # start a potential drag with a payload factory
drag.move(mx, my)
drag.release(mx, my)             # fires on_drop on the hovered zone
drag.paint(dl)                   # the drag ghost + drop highlight
drag.is_dragging(); drag.current_target()
```

The payload factory passed to `press` is only invoked once the pointer moves past
`threshold`, so a click is never mistaken for a drag.

## See also

- API: [`elysium.dnd`](../api/dnd.md)
- [Events](events.md), [Focus](focus.md)
