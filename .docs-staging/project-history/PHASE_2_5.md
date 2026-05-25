# Phase 2.5 — premium component library

Spec target: built-in components that look "premium and visually stunning out of the box, competing with the best of Flutter, modern macOS/Windows 11 apps, Figma prototypes, and high-end design systems like Material You or Apple's Human Interface Guidelines."

## What landed

### A complete theme engine

[`elysium.theme`](../python/elysium/theme/__init__.py) exposes:

| API | Purpose |
|---|---|
| `Theme(name, is_dark, primary, on_primary, accent, surface, surface_variant, on_surface, on_surface_muted, edge, overlay, success, warning, danger, radius_*, shadow_close/medium/far, motion, font_size_*)` | A full visual + motion contract |
| `Theme.from_primary(color, dark=False)` | Derive a harmonious 12-colour palette from a single primary via HSL math (accent = hue + 28°; surface lightness/saturation tuned by dark flag) |
| `current_theme() / set_theme(theme)` | Thread-safe global theme swap. Components paint with the new theme on the next frame. |
| Built-ins: `light()`, `dark()`, `midnight_glass()`, `frost()` | Four polished presets out of the box |
| `MotionPreset(hover_rate, press_rate, focus_rate, value_rate)` + `.step(current, target, dt, rate)` | Critically-damped exponential approach with frame-rate-independent dt. The rates (18/24/14/16 per second) give the 180–280 ms snap the spec calls for. |
| `hsla(h, s, l, a)` / `mix(a, b, t)` / `lighten(c, amt)` / `darken(c, amt)` / `with_alpha(c, a)` | HSL-aware colour helpers used throughout the component implementations |

### Every component animates smoothly

The base `Component` dataclass holds four progress floats (`_hover_t`, `_press_t`, `_focus_t`, `_disabled_t`), and the `update(dt, state)` method exponentially decays each toward its target. Paint code reads these floats to interpolate visuals continuously — no jarring colour swaps. The host calls `update(dt, state)` once per frame before `paint(dl)`.

### Polished components

| Component | What this leg added |
|---|---|
| `Button` | 5 variants (`solid`, `outline`, `ghost`, `glass`, `danger`); top-to-bottom gradient fill; layered drop shadow that lifts on hover and sinks on press; 1.035× hover scale, 0.96× press scale; top-edge inner highlight for a sculpted feel; focus ring; smooth colour mix toward darker on press, brighter on hover; disabled fade. |
| `IconCloseButton` | Smooth scale + colour transition between idle scrim and theme `danger` on hover; halo ring fade-in. |
| `Card` | Three elevations (`close`, `medium`, `far`) mapped to the theme's shadow set; subtle gradient surface; top-edge inner highlight on dark themes. |
| `Toggle` | iOS-style pill; knob position tweens via the motion preset (`value_rate`); knob has a drop shadow and radial highlight; inner pill shadow for depth; hover ring. |
| `Slider` | Gradient-filled track (primary → accent); soft glow under the fill, intensifying on hover; thumb is a radial gradient (white centre → primary edge) with drop shadow + ring; hover grows the thumb by 2.5 px; focus ring. |
| `TextField` | Background + edge stroke that colour-mixes to `accent` on focus; floating label animates from inside the field to above it with size + colour interpolation; focus underline expands from centre. |
| `ProgressBar` | Gradient fill (primary → accent); white shine sweep that loops every 1.6 s; indeterminate mode renders a 30 %-wide pulse traversing the track. |
| `Stack` | Layout container, propagates `update(dt, state)` to children. |

### Four built-in themes (all shipped with the framework)

| Theme | Look |
|---|---|
| `light()` | Default Elysium Light — iris primary on near-white surface |
| `dark()` | Default Elysium Dark — brighter iris primary on a deep indigo surface |
| `midnight_glass()` | Premium dark glassmorphic — translucent surface, generous far shadows, light-blue primary, soft white edges |
| `frost()` | Premium light glassmorphic — airy near-white surface, electric blue primary, subtle blue edges |

## Visual evidence

Four PNG goldens committed at `tests/snapshots/darwin/showcase_{light,dark,midnight_glass,frost}.png`. Each renders the full gallery (5 button variants × 4 states + slider at 3 values + 3 toggle states + 3 text field states + 3 progress bar states) under one theme.

![midnight glass showcase](../tests/snapshots/darwin/showcase_midnight_glass.png)

## Tests

| | Before | After |
|---|---|---|
| `pytest tests/` | 67 pass | **75 pass**, 3 skipped |

8 new tests cover:
- Button paints into DisplayList; 5 variants render distinct pixels.
- Smooth state interpolation: hover/press/focused all reach >0.99 after settling, decay to <0.05 after release.
- Toggle's `_value_t` reaches 1.0 after settling.
- TextField focus underline animates in then out.
- ProgressBar paints in both determinate and indeterminate modes.
- Theme HSL palette generation produces a 4-tuple for every semantic slot.
- Light vs dark variants pick correspondingly light vs dark surfaces.
- `set_theme()` is observed by `current_theme()`.
- Colour helpers: `lighten` brightens; `darken` darkens; `mix` linear-interpolates; `with_alpha` swaps the alpha channel.

## What's still pending

Spec items deliberately deferred:

- **Custom WGSL shaders per component** (edge glow, refraction noise) — would need additional shader-uniform plumbing through `DrawCommand`. Phase 3 work.
- **Ripple / particle burst on click** — needs a particle system; deferred.
- **Hot-reloadable theme files** — IPC transport is shipped; wiring `SkinChanged → set_theme` is a one-liner the next leg will add.
- **"Magic Polish" Designer button** — depends on the Designer GUI app.
- **30-component target** — we ship 9 (Label, Button, IconCloseButton, Card, Toggle, Slider, TextField, ProgressBar, Stack). The next 20 (Dropdown, Tabs, Tooltip, Menu, Modal, Toast, Avatar, Chip, Breadcrumb, Pagination, Accordion, Radio, Checkbox, ComboBox, TextArea, Spinner, Divider, Badge, Popover, CommandPalette) follow the same `update(dt, state) → paint(dl)` contract and the theme system, so each is small.

## Demo

```bash
# Render all four themes' showcase galleries to PNG:
python examples/components/showcase.py --static --theme=light
python examples/components/showcase.py --static --theme=dark
python examples/components/showcase.py --static --theme=midnight_glass
python examples/components/showcase.py --static --theme=frost

# Or open a live window:
python examples/components/showcase.py --theme=midnight_glass
```

## Usage from app code

```python
from elysium.components import Button, Toggle, Slider, TextField, ProgressBar
from elysium.theme import set_theme, midnight_glass

set_theme(midnight_glass())   # one line theme swap

btn  = Button(x=20, y=20,  w=160, h=44, label="Play", variant="solid",
              on_click=lambda: print("play"))
tog  = Toggle(x=20, y=80,  w=56, h=30, value=False,
              on_change=lambda v: print("toggle =", v))
sld  = Slider(x=20, y=130, w=240, h=32, value=0.6,
              on_change=lambda v: print("volume =", v))
field = TextField(x=20, y=180, w=280, h=48, label="Email")
prog = ProgressBar(x=20, y=250, w=280, h=10, value=0.4)

# In your per-frame loop:
for c in (btn, tog, sld, field, prog):
    state = {"hover":   c.hit_test(*cursor) if cursor else False,
             "pressed": pressed and c.hit_test(*cursor)}
    c.update(dt, state)
    c.paint(dl)
window.publish_display_list(dl)
```
