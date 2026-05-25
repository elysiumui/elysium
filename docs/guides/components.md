# Building components

Every shipped component (button, slider, checkbox, …) implements the same two-method contract:

```python
class MyButton:
    def update(self, dt: float, state: dict) -> None:
        """Advance any internal animation given dt and an input snapshot
        (hover, pressed, focused, value, ...)."""

    def paint(self, dl) -> None:
        """Emit draw commands into the framework's DisplayList."""
```

That's it. `dl.draw_paragraph(...)`, `dl.fill_path(...)`, `dl.draw_image_file(...)`, and friends are all you need. The framework calls these every frame; the render thread consumes the resulting display list lock-free.

## Hit testing
Components carry their own `hit_test(x, y)`: usually rectangular but Region/Shape can supply path-aware tests. The framework dispatches mouse events to the topmost passing hit.

## State + theming
Use `elysium.theme.current_theme()` to read accent / surface / on-surface colors so your component recolors with the active theme automatically.

## Ripples (Material-style)
Buttons get a ripple via `Button.fire_click(x, y)` which spawns an expanding alpha-decaying circle. Components can inherit this pattern by holding a `list[Ripple]` and aging entries in `update()`.

## Examples in tree
- `python/elysium/components/__init__.py`: 34 reference implementations
- `examples/components/`: runnable showcase
