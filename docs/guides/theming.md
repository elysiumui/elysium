# Theming

`elysium.theme` exposes a `Theme` dataclass of design tokens
(background, surface, accents, motion, shadows, materials), five
built-in themes, and helpers for perceptually-uniform color math
(OKLab / OKLCH).

## The five built-in themes

| Theme | Vibe |
|---|---|
| `light()` | Clean white surfaces |
| `dark()` | Charcoal surfaces with soft accents |
| `oled()` | Pure black background; max contrast |
| `midnight_glass()` | Blurred dark glass with violet glow |
| `frost()` | Cool white frosted glass |

Activate:

```python
from elysium.theme import set_theme, midnight_glass
set_theme(midnight_glass())
```

The change cascades through every component and skin token in one
frame.

## Theme tokens

```python
@dataclass
class Theme:
    name: str
    background: Color
    surface: Color
    surface_alt: Color
    on_background: Color    # text over background
    on_surface: Color
    accent: Color
    accent_secondary: Color
    on_accent: Color
    shadow_default: Shadow
    motion: MotionPreset
    materials: dict[str, str]  # default / panel / popover / etc → material name
```

The full schema is on [`elysium.theme`](../api/theme.md).

## Token references in skins

Skin documents can reference theme tokens with `{theme.…}`:

```json
"stroke": "{theme.accent}",
"fill": "{theme.surface}",
"shadow": { "color": "{theme.accent}66", "blur": 18 }
```

The framework resolves these on `load_skin` and on every
`set_theme` call so theme switches re-style automatically.

## Color helpers

### `hsla(hue, sat, lightness, alpha=1.0)`

```python
from elysium.theme import hsla
accent = hsla(282, 0.70, 0.65)
```

Hue 0..360, sat / lightness 0..1. Authors theme palettes that
stay perceptually consistent: adjusting saturation does not also
shift hue.

### `mix(a, b, t)`

```python
from elysium.theme import mix
mid = mix(theme.background, theme.surface, 0.5)
```

Interpolates two colors in OKLab. Cleaner than RGB lerp.

### `lighten(c, amount)`, `darken(c, amount)`

Adjust lightness in OKLab. `lighten(theme.surface, 0.1)` makes it
10% lighter without shifting hue.

### `with_alpha(c, alpha)`

```python
with_alpha(theme.accent, 0.5)
```

Replace the alpha channel.

## Author a custom theme

```python
from elysium.theme import Theme, MotionPreset, Shadow, hsla

violet_glass = Theme(
    name="Violet Glass",
    background=hsla(260, 0.40, 0.08),
    surface=hsla(260, 0.30, 0.14),
    surface_alt=hsla(260, 0.30, 0.20),
    on_background=hsla(280, 0.20, 0.96),
    on_surface=hsla(280, 0.20, 0.92),
    accent=hsla(282, 0.70, 0.65),
    accent_secondary=hsla(327, 0.75, 0.62),
    on_accent=hsla(260, 0.10, 0.10),
    shadow_default=Shadow(color="#a78bfa66", blur=18, y=4),
    motion=MotionPreset.lively,
    materials={"default": "glass-dark", "panel": "glass-dark", "popover": "frosted"},
)

set_theme(violet_glass)
```

The Stylized Music Player tutorial chapter 7 demonstrates this in
context.

## MotionPreset

`MotionPreset` controls the default durations and easings used by
components when no per-component override is set:

| Preset | Default duration | Easing |
|---|---|---|
| `MotionPreset.calm` | 0.30 s | ease_out |
| `MotionPreset.standard` | 0.20 s | ease_in_out_sine |
| `MotionPreset.lively` | 0.15 s | cubic_bezier(0.16, 1, 0.3, 1) |
| `MotionPreset.snappy` | 0.10 s | cubic_bezier(0.2, 0.8, 0.2, 1) |

Components blend their internal animations with this preset, so
swapping themes can swap the "feel" of the app.

## Subscribing to theme changes

```python
from elysium.theme import on_theme_changed

@on_theme_changed
def react(theme: Theme):
    print("now using", theme.name)
```

Useful when you have non-theme-bound colors that should still
update on theme switch.

## Detect system dark mode

```python
from elysium import platform

if platform.system_is_dark():
    set_theme(midnight_glass())
else:
    set_theme(frost())

platform.on_system_theme_change(lambda dark: set_theme(midnight_glass() if dark else frost()))
```

See [Recipes: react to system dark mode](../recipes/13-react-to-system-dark-mode.md).

## See also

- [Components overview](components-overview.md): what reads the
  tokens.
- [Skins](skins.md): `{theme.…}` references in skin docs.
- [Recipes: switch themes at runtime](../recipes/12-switch-themes-runtime.md)
