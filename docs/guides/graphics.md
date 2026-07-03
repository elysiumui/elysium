# Interactive 2D canvas

`elysium.graphics` is an item scene graph — Qt's `QGraphicsScene` /
`QGraphicsView` / `QGraphicsItem`. Use it for diagram, node, and vector tools:
anything where the user manipulates a collection of shapes on a pannable,
zoomable canvas.

See [`examples/graphics-demo/`](https://github.com/elysiumui/elysium/tree/main/examples/graphics-demo)
for a mini flowchart editor and the [Qt porting guide](porting-from-qt.md#interactive-2d-canvas-tier-5)
for the class map.

## Pieces

| | Role |
| --- | --- |
| `Scene` | Owns a z-ordered list of `Item`s. Paints back-to-front; hit-tests front-to-back. Queries: `items_at`, `items_in_rect`, `bounding_rect`, z-order + selection helpers. |
| `Item` (+ `RectItem` / `EllipseItem` / `LineItem` / `PathItem` / `TextItem`) | A shape with scene-space bounds, a `contains()` hit-test, and a `paint(dl)` **in scene coordinates**. Subclass `Item` for custom drawing. |
| `GraphicsView` | A viewport that pans/zooms over a scene and renders it (with off-screen culling). |
| `SceneController` | The interaction layer: select, rubber-band, move, resize. |

## Coordinates

An item paints in **scene** coordinates and never sees the pan/zoom — the view
applies the transform around it. To go between spaces:

```python
view.to_view(scene_x, scene_y)   # scene → screen
view.to_scene(screen_x, screen_y)  # screen → scene
```

Always map a pointer event to scene coordinates (`to_scene`) before querying the
scene. `SceneController` does this for you.

## A minimal canvas

```python
from elysium.graphics import Scene, RectItem, GraphicsView, SceneController

scene = Scene()
scene.add(RectItem(x=40, y=40, w=120, h=80))
scene.add(RectItem(x=220, y=120, w=120, h=80))

view = GraphicsView(scene=scene, x=0, y=0, w=900, h=600)
controller = SceneController(view=view, snap=8)   # 8px grid snap

# per frame:
view.paint(dl)                # scene, culled + transformed
controller.paint_overlay(dl)  # rubber-band rect + resize handles

# pointer (screen-space coords):
controller.on_press(mx, my, additive=shift_held)
controller.on_drag(mx, my)
controller.on_release()

# wheel zoom about the cursor; middle/space drag to pan:
view.zoom_at(mx, my, 1.1 if wheel_up else 1/1.1)
view.begin_pan(mx, my); view.drag_pan(mx, my); view.end_pan()
view.fit(margin=40)           # frame the whole scene
```

## Interaction details

* **Select** — `on_press` over an item selects the topmost (clearing others);
  pass `additive=True` (Shift) to toggle multi-select. Pressing empty space
  starts a **rubber-band** that selects everything it intersects on release.
* **Move** — dragging a selected item moves the whole selection; set
  `controller.snap` for grid snapping.
* **Resize** — a single *resizable* selection shows 8 handles (drawn in screen
  space, constant size at any zoom); drag one to resize the item's bounds.
  `LineItem`/`PathItem` are `resizable=False` (they move but don't box-resize,
  since that wouldn't reshape them).

## Custom items

Subclass `Item`, keep `x/y/w/h` as your scene bounds, and override `paint` (and
usually `contains` for a shape-accurate hit-test):

```python
from elysium.graphics import Item
from elysium.theme import current_theme, with_alpha

class StarItem(Item):
    def paint(self, dl):
        t = current_theme()
        dl.fill_path(self._star_path(), with_alpha(t.primary, self.opacity))
    def contains(self, sx, sy):
        return super().contains(sx, sy)  # or a precise star test
```

## Notes

* Per-item rotation/scale transforms and Skia path-`contains` hit-testing for
  arbitrary `PathItem`s are tracked follow-ups; axis-aligned bounds, ellipse,
  and line hit-tests are exact today.
