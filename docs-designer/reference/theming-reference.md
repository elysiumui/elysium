# Theming reference

The complete list of theme tokens, the OKLab color math behind
them, and the override hooks Designer offers.

## Token names

Every token a skin can reference via `{theme.…}`:

| Token | Purpose |
|---|---|
| `theme.background` | Window background fill |
| `theme.surface` | Card / panel fill |
| `theme.surface_alt` | Secondary surface (popovers, drawers) |
| `theme.on_background` | Text over background |
| `theme.on_surface` | Text over surface |
| `theme.accent` | Primary accent (buttons, focus rings, selection) |
| `theme.accent_secondary` | Secondary accent |
| `theme.on_accent` | Text / glyphs over accent |
| `theme.shadow_default.color` / `.blur` / `.x` / `.y` | Default drop shadow |
| `theme.motion.duration` | Default animation duration |
| `theme.motion.easing` | Default easing |
| `theme.materials.default` | Default surface material id |
| `theme.materials.panel` | Material for panels |
| `theme.materials.popover` | Material for popovers |

## Built-in themes

| Theme | Tokens (selected) |
|---|---|
| Light | bg #ffffff, surface #f7f7f9, accent #6d28d9 |
| Dark | bg #1a1a1f, surface #232328, accent #a78bfa |
| OLED | bg #000000, surface #0a0a0c, accent #c4b5fd |
| Midnight Glass | bg #14122b, surface #1e1b4b, accent #a78bfa, glass-dark |
| Frost | bg #f5f3ff, surface #ffffff, accent #6d28d9, frosted |

Exact hex values are in `python/elysium/theme/__init__.py`.

## OKLab pipeline

All theme color operations (mix, lighten, darken) round-trip
through OKLab. This keeps lightness adjustments perceptually
uniform: bumping `lighten(surface, 0.1)` produces what humans
read as "10% lighter" rather than "0.1 added to RGB lightness".

Internally:

```
sRGB → linear sRGB → OKLab → (operation) → OKLab → linear sRGB → sRGB
```

The framework caches OKLab conversions per-color so repeated
operations are fast.

## Override hooks

A skin variant in `variants/<name>/document.json` overrides the
root document when the matching condition triggers. Variants ship
for:

| Variant | Trigger |
|---|---|
| `variants/dark/` | System reports dark mode |
| `variants/light/` | System reports light mode |
| `variants/high_contrast/` | High contrast accessibility setting |
| `variants/reduce_motion/` | Reduce motion accessibility setting |
| `variants/<theme_id>/` | A specific theme is active |

## Authoring a custom theme

`Theme > Customize…` in the Designer opens a token editor with the
above token list. Drag any color swatch to pick; save as a user
theme with `Theme > Save Current as User Theme…`.

User themes live at `~/.elysium/themes/<id>.elytheme` (JSON).
Distribute by sharing the file directly.

## Programmatic

```python
from elysium.theme import Theme, set_theme, hsla, MotionPreset, Shadow

custom = Theme(
    name="Custom",
    background=hsla(260, 0.40, 0.08),
    surface=hsla(260, 0.30, 0.14),
    # ...remaining theme tokens...
)
set_theme(custom)
```

See [Theming](https://docs.elysiumui.com/guides/theming/) (framework).

## See also

- [Themes](../themes/index.md)
- [Built-in themes](../themes/built-in.md)
- [Customize and save](../themes/customize-and-save.md)
