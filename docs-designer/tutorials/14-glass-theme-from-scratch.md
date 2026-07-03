# Glass theme from scratch

Time: 50 minutes. Difficulty: Advanced.

Author a fully custom dark-glass theme using OKLCH color math  
the cousin theme to Midnight Glass but with your own palette.
Demonstrates the full theme-authoring surface in the Designer.

## Prerequisites

- Designer installed.
- Familiarity with [Themes](../themes/index.md).

## Open the customizer

`Theme > Customize…`. The customizer panel opens with editable
swatches for every theme token (see the
[Theming reference](../reference/theming-reference.md)).

## Pick a hue

Start from a single hue. A coherent glass theme keeps everything
in a narrow hue band:

| Hue | Result |
|---|---|
| 260 (violet) | Like Midnight Glass |
| 220 (blue) | Aurora-blue glass |
| 320 (magenta) | Ultraviolet glass |
| 10 (red) | Ruby glass |

Pick one; we will derive every token from it.

## Author with OKLCH

For each token, the customizer accepts `hsla(hue, sat, lightness,
alpha)` literals. Use OKLCH-equivalent values for perceptually-
consistent results:

```
background      = hsla(260, 0.40, 0.08)     # deep
surface         = hsla(260, 0.30, 0.14)
surface_alt     = hsla(260, 0.30, 0.20)
on_background   = hsla(280, 0.20, 0.96)     # text over deep
on_surface      = hsla(280, 0.20, 0.92)
accent          = hsla(282, 0.70, 0.65)     # primary accent
accent_secondary= hsla(327, 0.75, 0.62)     # complement
on_accent       = hsla(260, 0.10, 0.10)
```

The lightness ladder (0.08 → 0.14 → 0.20) maintains the three-tier
surface hierarchy.

## Material assignment

Set the materials map to use glass throughout:

```
default  = "glass-dark"
panel    = "glass-dark"
popover  = "frosted"
```

## Shadows

```
shadow_default = { color: "#a78bfa66", blur: 18, y: 4 }
```

The shadow color is your accent with 40% alpha so glows feel
intentional.

## Motion

Glass themes typically use **lively** motion:

```
motion = MotionPreset.lively
```

(140 ms duration, cubic-bezier(0.16, 1, 0.3, 1) easing.)

## Preview

The Designer's main window re-skins in real time as you edit.
Confirm:

- Buttons feel right (accent fill, on_accent text).
- Cards read like glass (translucent, lit backdrop).
- Popovers have a frosted backdrop separate from cards.
- Text remains readable over both background and surface.

## Save

`Theme > Save Current as User Theme…`. Name it ("Ultraviolet
Glass", "Ruby Glass", etc.). It appears in the Theme menu under
**User Themes**.

The file lives at
`~/.elysium/themes/<id>.elytheme`: a JSON file you can hand-edit
or distribute.

## Apply at runtime

In a runtime app:

```python
from elysium.theme import Theme, set_theme
import json
theme_data = json.load(open(".../<id>.elytheme"))
set_theme(Theme.from_dict(theme_data))
```

Or via the Designer's Theme menu in any skin that uses
`{theme.…}` token references.

## What you exercised

- The full Theme dataclass surface.
- OKLCH-style color authoring via `hsla`.
- Per-token material assignment.
- User theme save / load.

## See also

- [Themes index](../themes/index.md)
- [Theming reference](../reference/theming-reference.md)
- [Built-in themes](../themes/built-in.md)
