# Brush

The brush system is the painting backend used by the Designer's
painting tools and by any Elysium app that wants paintable
surfaces. Six engines, parametric presets, dynamics curves driven
by tablet pressure / tilt / rotation, and import of `.abr`
(Photoshop), `.sut` (Clip Studio Paint), and `.elybrush` (native)
brush packs.

The Designer's [Brush system](https://designer.elysiumui.com/brush/)
section covers the authoring side. This guide covers the framework's
Python API for embedding brush surfaces in apps.

## Engines

| Engine id | Best for |
|---|---|
| `round_stamp` | Pencil, marker, hard-edge |
| `airbrush` | Soft falloff, gradients |
| `bristle` | Oil, ink, gestural |
| `texture` | Concept art, photo-based |
| `pattern` | Decals, stamps, scatter |
| `wet_mix` | Watercolor, smudge, blend |

```python
from elysium import brush
for engine in brush.list_engines():
    print(engine.id, engine.name)
```

## Library

The Library manages presets:

```python
lib = brush.library()
preset = lib.get("elysium.round.hard")    # Round Stamp "Hard Edge"
print(preset.engine, preset.params)
```

`library()` returns the live Library: built-ins from
`builtin_brushes_dir()` plus user presets from `user_brushes_dir()`.

```python
print(brush.user_brushes_dir())     # ~/.elysium/brushes/user/ or platform equivalent
print(brush.builtin_brushes_dir())  # bundled with the framework
```

## Preset

```python
preset = brush.Preset(
    id="my.preset",
    name="My Preset",
    engine="round_stamp",
    params={"size_px": 20, "opacity": 0.8, "hardness": 0.9},
    dynamics={"size_px": {"channel": "pressure", "curve": [[0, 0.1], [1, 1]]}},
    tags=["sketch", "dry"],
    color="#222222ff",
)

brush.save_preset(preset)
```

Load:

```python
preset = brush.load_preset("path/to/my.elybrush")
```

## Painting from code

For programmatic painting (no GUI involved):

```python
from elysium.render.texture import PaintMask
from elysium.brush import get_engine, apply_dynamics

mask = PaintMask(512, 512)
engine = get_engine("round_stamp")
params = {"size_px": 20, "opacity": 0.8, "hardness": 0.9}

# Apply dynamics for one sample
sample = {"pressure": 0.7, "velocity": 0.0}
stamped = apply_dynamics(params, preset.dynamics, sample)

# Stamp at a position
engine.stamp(mask.canvas, x=100, y=100, params=stamped, color=(255, 0, 0, 255))
```

For interactive painting, hook to the framework's pointer events:

```python
@window.on("paint_target.drag")
def paint(event):
    sample = {
        "pressure": event.pressure or 1.0,
        "velocity": event.velocity_magnitude(),
    }
    stamped = apply_dynamics(params, preset.dynamics, sample)
    engine.stamp(window.paint_target.mask, event.local_x, event.local_y, stamped, brush_color)
```

## Reload on skin change

When the active skin changes, the user brushes folder may move:

```python
brush.reload_with_skin(skin_path)
```

This is automatic when you use `window.load_skin(...)`.

## Custom engines

Register a Python class implementing `BrushEngine`:

```python
class DottedLineEngine(brush.BrushEngine):
    id = "dotted_line"
    name = "Dotted Line"
    params = [brush.ParamSpec("size_px", min=1, max=200, default=12)]
    accepts = ("size_px",)

    def stamp(self, canvas, x, y, params, color):
        canvas.draw_circle(cx=x, cy=y, r=params["size_px"] / 2.0,
                           color=color, opacity=1.0)

    def stroke_step(self, params):
        return params["size_px"] * 3.0


brush.register_engine(DottedLineEngine())
```

The Designer's
[Authoring custom brushes](https://designer.elysiumui.com/brush/authoring-custom-brushes/)
page covers the full surface.

## Imports

```python
from elysium.brush.abr import import_abr
from elysium.brush.sut import import_sut

presets = import_abr("/path/to/photoshop.abr")
for p in presets:
    brush.save_preset(p)
```

`.abr` and `.sut` files become regular `.elybrush` presets after
import.

## See also

- [API: elysium.brush](../api/brush.md)
- [Designer > Brush system](https://designer.elysiumui.com/brush/)
- [Textures](textures.md): `PaintMask` and the texture pipeline.
