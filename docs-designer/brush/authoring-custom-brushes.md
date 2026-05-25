# Authoring custom brushes in Python

The [Brush Studio](brush-studio.md) covers ~95% of authoring needs.
For the remaining 5%: engines with novel math, unusual stamping
patterns, or compute-shader paths: you author in Python against
the `elysium.brush` API.

## When to drop down to Python

Author a Python engine when:

- You want a **new stamping algorithm** the six built-in engines do
  not give you (e.g. a custom particle scatter, a Bezier-tangent-
  aware stamp).
- You need to **read pixel state** at the stroke head and react
  (e.g. erase that respects mask alpha, blur that ignores fully-
  saturated pixels).
- You want to **drive a compute shader** (e.g. fluid sim integrated
  into stroke).

The Studio is the right tool for parameter tweaks and dynamics
curves on existing engines.

## The `BrushEngine` class

`elysium.brush.engine.BrushEngine` is the protocol. A minimal
engine implements three methods:

```python
from elysium.brush import BrushEngine, ParamSpec, register_engine


class DottedLineEngine(BrushEngine):
    id = "dotted_line"
    name = "Dotted Line"
    params = [
        ParamSpec("size_px", min=1, max=200, default=12),
        ParamSpec("dot_spacing", min=1.0, max=10.0, default=3.0),
        ParamSpec("opacity", min=0.0, max=1.0, default=1.0),
    ]
    accepts = ("size_px", "opacity")  # accept dynamics on these

    def stamp(self, canvas, x, y, params, color):
        canvas.draw_circle(
            cx=x, cy=y,
            r=params["size_px"] / 2.0,
            color=color, opacity=params["opacity"],
        )

    def stroke_step(self, params):
        # Decide how far apart stamps fall along the stroke.
        return params["size_px"] * params["dot_spacing"]


register_engine(DottedLineEngine())
```

After `register_engine(...)`, the new engine appears in:

- The [Quick Wheel](quick-start.md#switch-engines-instantly) (a 7th
  slice).
- The [Brush Studio](brush-studio.md) engine dropdown.
- The Library's "Source: Custom Python" filter.

## ParamSpec

`ParamSpec` declares one parameter:

```python
ParamSpec(
    name="size_px",
    min=1,
    max=500,
    default=20,
    kind="float",         # or "int" | "color" | "bool" | "vec2"
    label="Size",         # display label; defaults to name.title()
    hint="In pixels",     # tooltip in the Studio
    accepts_dynamics=True,
)
```

Every parameter you declare shows up in the Studio's left column
and (if `accepts_dynamics=True`) in the dynamics grid.

## The `stamp(canvas, x, y, params, color)` method

Called once per stamp position. The framework computes positions
from your `stroke_step(...)` return value and calls `stamp` at each
one. The canvas argument exposes:

| Method | Purpose |
|---|---|
| `canvas.draw_circle(cx, cy, r, color, opacity)` | Filled circle |
| `canvas.draw_path(path, color, ...)` | Arbitrary Skia path |
| `canvas.draw_image(image, x, y, scale, rotation)` | Stamp an image |
| `canvas.read_pixel(x, y) -> (r, g, b, a)` | Sample current canvas |
| `canvas.compute(shader, x, y, w, h)` | Dispatch a WGSL shader |

The full API is in [Engines reference](engines-reference.md).

## Reading pixels and stamping conditionally

Example: erase that respects mask alpha (only deletes where the
current alpha is > 0.5).

```python
class SmartEraseEngine(BrushEngine):
    id = "smart_erase"
    name = "Smart Erase"
    params = [
        ParamSpec("size_px", min=1, max=200, default=24),
    ]

    def stamp(self, canvas, x, y, params, color):
        r = params["size_px"] / 2.0
        # Only erase pixels that are mostly opaque.
        a = canvas.read_pixel(x, y)[3]
        if a < 0.5:
            return
        canvas.draw_circle(cx=x, cy=y, r=r,
                          color=(0, 0, 0, 0),
                          composite="erase")


register_engine(SmartEraseEngine())
```

## Compute shaders

For high-performance fluid / blur / displacement effects, the
`canvas.compute(shader, ...)` path dispatches a WGSL compute shader
that operates on the canvas's GPU texture directly. Sample:

```python
class FluidStrokeEngine(BrushEngine):
    id = "fluid"
    name = "Fluid"
    params = [ParamSpec("size_px", min=4, max=200, default=64)]

    SHADER = """
    @group(0) @binding(0) var src: texture_storage_2d<rgba8unorm, read>;
    @group(0) @binding(1) var dst: texture_storage_2d<rgba8unorm, write>;
    @compute @workgroup_size(8, 8)
    fn diffuse(@builtin(global_invocation_id) id: vec3<u32>) {
        // ... your fluid simulation step here
    }
    """

    def stamp(self, canvas, x, y, params, color):
        s = int(params["size_px"])
        canvas.compute(self.SHADER, x=x - s // 2, y=y - s // 2,
                       w=s, h=s, entry="diffuse")


register_engine(FluidStrokeEngine())
```

The compute path is the fastest tier; expect ~30,000 stamps/sec on
discrete GPUs.

## Where to put the file

`elysium.brush.library.user_brushes_dir()` returns the user
brushes folder. Python engines under `<user_dir>/engines/*.py` load
on Designer startup. Use this folder so your engines persist
through Designer updates.

## Testing

Custom engines can be unit-tested without the Designer:

```python
import unittest
from elysium.brush import get_engine
from your_engine import DottedLineEngine, register_engine

class TestDottedLine(unittest.TestCase):
    def test_step(self):
        e = DottedLineEngine()
        self.assertEqual(e.stroke_step({"size_px": 10, "dot_spacing": 3.0}),
                         30.0)
```

## Sharing

Save your engine + a default preset that uses it via the Brush
Studio's **Save** button. Right-click in the Library and **Export
to .elybrush** to produce a single-file shareable. The recipient
gets the Python engine plus the parameter values; their Designer
loads the engine and adds the preset to their Library.
