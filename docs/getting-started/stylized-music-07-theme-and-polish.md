# Stylized Music Player 7. Theme and polish

Time: 10 minutes.

## What we are adding

A custom dark-glass theme that gives the whole skin a coherent
identity, then one pass of `magic_polish` to let the AI nudge
colors, glows, and material choices for visual harmony.

![Stylized Music Player chapter 7: finished player with cohesive dark-glass theme and AI-tuned highlights](../assets/stylized-music-ch7.png)

## Author a custom Theme

`elysium.theme.Theme` is a dataclass of design tokens: background,
surface, accents, on-* (text colors over each surface), motion
presets, and a `materials` map for the glass variants. Subclass it
or instantiate directly:

```python
from elysium.theme import Theme, MotionPreset, Shadow, set_theme, hsla

violet_glass = Theme(
    name="Violet Glass",
    background=hsla(260, 0.40, 0.08),
    surface=hsla(260, 0.30, 0.14),
    surface_alt=hsla(260, 0.30, 0.20),
    on_background=hsla(280, 0.20, 0.96),
    on_surface=hsla(280, 0.20, 0.92),
    accent=hsla(282, 0.70, 0.65),       # violet
    accent_secondary=hsla(327, 0.75, 0.62),  # pink
    on_accent=hsla(260, 0.10, 0.10),
    shadow_default=Shadow(color="#a78bfa66", blur=18, y=4),
    motion=MotionPreset.lively,
    materials={
        "default": "glass-dark",
        "panel": "glass-dark",
        "popover": "frosted",
    },
)


set_theme(violet_glass)
```

`hsla(hue, sat, lightness, alpha=1)` gives a quick way to author
colors that stay perceptually consistent across the theme: under
the hood the framework converts to OKLCH so a slight bump in
saturation does not also shift hue.

## Bind skin tokens to the theme

The skin file's color literals (`"#a78bfaff"`, `"#ec4899ff"`, etc.)
can be replaced with token references that read from the theme at
load time. Update `player.esk/document.json` placements that use
your accent colors:

```json
"stroke": "{theme.accent}",
"fill": "{theme.surface}",
"shadow": { "color": "{theme.accent}66", "blur": 18 }
```

The framework resolves `{theme.X}` against the active theme when
the skin is loaded or `set_theme` is called.

Now your `set_theme(violet_glass)` cascades automatically through
the whole player. Try defining a second theme:

```python
ember = Theme(
    name="Ember",
    background=hsla(20, 0.50, 0.08),
    surface=hsla(20, 0.40, 0.14),
    surface_alt=hsla(20, 0.40, 0.22),
    on_background=hsla(30, 0.30, 0.96),
    on_surface=hsla(30, 0.30, 0.92),
    accent=hsla(20, 0.85, 0.55),       # ember orange
    accent_secondary=hsla(45, 0.90, 0.60),  # gold
    on_accent=hsla(20, 0.10, 0.10),
    shadow_default=Shadow(color="#f9731666", blur=18),
    motion=MotionPreset.calm,
    materials={"default": "glass-dark", "panel": "vibrancy-dark"},
)
```

And bind a tiny theme-cycle button to swap between them at runtime.
The whole player re-skins itself live.

## Apply Magic Polish

The `magic_polish` workflow takes your current skin and uses the
configured AI provider to suggest small, low-stakes refinements:
gradient angle tweaks, shadow blur radii, accent saturation,
material choices. It returns a `SkinDiff` you can review and apply.

```python
from elysium.ai import magic_polish

diff = magic_polish(
    skin_path="player.esk",
    notes="Late-1990s stylized music player aesthetic; "
          "violet glass with pink accents; "
          "make the glow on Play feel warmer; "
          "tighten the equalizer bar attack curve.",
)

print(diff.summary())
diff.apply(skin_path="player.esk")
```

`SkinDiff.summary()` prints something like:

```
+ btn_play.shadow.color  #ec489966 -> #f97316cc
+ btn_play.shadow.blur   22 -> 28
+ eq_canvas.glow_alpha   0.40 -> 0.55
* faceplate_back.fill    gradient stop 2: #0a0820 -> #1b0a3a
```

You can prune entries by passing a list of placement IDs into
`diff.apply(only=[...])` to keep only the changes you want.

To opt out of AI entirely, skip this step. The previous chapters
plus the custom theme already produce a finished-looking player.

## Polish details by hand

A few micro-tweaks that lift the result:

- Add a subtle reflection across the faceplate top edge:

```json
{
  "id": "faceplate_reflection",
  "kind": "path",
  "path_d": "M 40,16 L 480,28",
  "fill": "transparent",
  "stroke": "linear-gradient(90deg, #ffffff00 0%, #ffffff66 50%, #ffffff00 100%)",
  "stroke_width": 1.2
}
```

- Lower the `eq_canvas` opacity to `0.85` while the player is paused
  so the bars feel "asleep":

```python
@effect
def push_eq_alpha():
    window.eq_canvas.opacity = 1.0 if is_playing() else 0.65
```

- Give the album art frame a very faint inner shadow when no track
  is loaded:

```python
@effect
def push_art_inner_shadow():
    if album_art_path() == "assets/art_placeholder.png":
        window.art_glow.inner_shadow = {"color": "#1a0f3c80", "blur": 12}
    else:
        window.art_glow.inner_shadow = None
```

## Checkpoint

- Theme tokens drive every color on the player.
- One `magic_polish` pass (or the by-hand tweaks) lifts the
  visual coherence.
- The result feels like a finished product, not a tutorial.

Continue to [chapter 8: package and ship](stylized-music-08-package-and-ship.md).
