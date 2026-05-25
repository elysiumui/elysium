# How do I draw on a Canvas with a Path?

Build a `DisplayList` containing one or more `Path` operations,
then publish it to a `canvas` placement.

```python
import elysium as ely

# Author the path
path = ely.Path()
path.move_to(20, 20)
path.line_to(180, 20)
path.curve_to(220, 60, 220, 140, 180, 180)
path.line_to(20, 180)
path.close()

dl = ely.DisplayList()
dl.fill_color((0.65, 0.55, 0.98, 1.0))
dl.fill_path(path)
dl.stroke_color((1, 1, 1, 0.6))
dl.stroke_width(2.0)
dl.stroke_path(path)

window.my_canvas.publish_display_list(dl)
```

`my_canvas` is a placement with `kind: "canvas"` in your skin
document. Each `publish_display_list` swaps the canvas's contents
for a new list; old lists are released.

For per-frame redraw (visualizers, particles), call
`publish_display_list` once per frame from an animation thread.

See [Rendering](../guides/rendering.md).
