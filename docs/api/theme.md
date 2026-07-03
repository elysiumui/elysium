# `elysium.theme`

Themes, color math (OKLab / OKLCH), shadows, motion presets.

## Core classes

| Class | Purpose |
|---|---|
| `Color` | An RGBA color value |
| `Theme` | Dataclass of design tokens (see [Theming](../guides/theming.md)) |
| `Shadow` | Drop / inset shadow descriptor |
| `MotionPreset` | Default duration + easing |

## Built-in themes

| Function | Returns |
|---|---|
| `light()` | The Light theme |
| `dark()` | The Dark theme |
| `oled()` | Pure black OLED theme |
| `midnight_glass()` | Blurred dark glass with violet glow |
| `frost()` | Cool white frosted glass |

## Color helpers

| Function | Purpose |
|---|---|
| `hsla(hue, sat, lightness, alpha=1)` | Construct from perceptual HSLA |
| `mix(a, b, t)` | Interpolate in OKLab |
| `lighten(c, amount)` / `darken(c, amount)` | Adjust lightness in OKLab |
| `with_alpha(c, alpha)` | Replace the alpha channel |
| `rgb_to_oklab(r, g, b)` / `oklab_to_rgb(L, a, b)` | Round-trip via OKLab |

## Switching themes

| Function | Purpose |
|---|---|
| `set_theme(theme)` | Activate a theme runtime-wide |
| `current_theme()` | Get the active theme |
| `on_theme_changed(fn)` | Subscribe to theme changes |

## Auto-rendered details

::: elysium.theme

## See also

- [Theming](../guides/theming.md)
- [Recipes: switch themes](../recipes/12-switch-themes-runtime.md)
