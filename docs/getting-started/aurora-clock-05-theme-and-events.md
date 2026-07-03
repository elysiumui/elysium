# Aurora Clock 5. Theme toggle and event wiring

Time: 5 minutes.

## What we are adding

A small button below the time label that toggles between Midnight
Glass (the current dark indigo) and Frost (a pale frosted look),
wired through `@window.on(...)`. By the end of this chapter you have
a complete, polished Aurora Clock that ships.

![Aurora Clock chapter 5: toggle button cycles the theme between Midnight Glass and Frost](../assets/aurora-clock-ch5.gif)

## Add the toggle button placement

Append one more placement to `aurora_clock.esk/document.json`:

```json
{
  "id": "theme_toggle",
  "kind": "button",
  "x": 144, "y": 220,
  "width": 72, "height": 28,
  "label": "Frost",
  "font_size": 11,
  "fill": "#a78bfaff",
  "text_fill": "#0f0d1eff",
  "radius": 14
}
```

The button is a rounded rectangle sitting below the time label.
`kind: "button"` makes it click-receivable; the framework wires a
`theme_toggle.click` hook automatically.

## Hook up the click handler

Add this near your other `@effect` definitions:

```python
from elysium.theme import midnight_glass, frost, set_theme

theme_is_dark = True

@window.on("theme_toggle.click")
def cycle_theme(event):
    global theme_is_dark
    theme_is_dark = not theme_is_dark
    if theme_is_dark:
        set_theme(midnight_glass())
        window.background.fill = "#0f0d1eff"
        window.time_label.fill = "#ffffffff"
        window.theme_toggle.label = "Frost"
    else:
        set_theme(frost())
        window.background.fill = "#f5f3ffff"
        window.time_label.fill = "#312e81ff"
        window.theme_toggle.label = "Midnight"
```

The handler runs on the input thread for the OS click but mutates
placements through the same thread-safe proxy you have been using.

## Why pair `set_theme` with explicit fills?

`set_theme(...)` swaps the design tokens that built-in components
read (button hover colors, focus rings, system fonts). Our hand-
authored ellipse placements use explicit color values, so we
override those manually here. In a Designer-authored skin those same
fills would be bound to theme tokens and would update automatically
when `set_theme` ran.

## Polish: blur behind on macOS

On macOS the dark theme looks especially good with vibrancy. Add
this once after `load_skin`:

```python
import sys

if sys.platform == "darwin":
    window.set_blur_behind(True, material=12)  # HUD vibrancy
```

The HUD material is dark and soft; if you switch to the Frost theme
permanently, swap to material 7 (sidebar) or 21 (under-window) for a
lighter blur.

## Final file

Your finished `aurora_clock.py` should now contain (in order):

1. Imports (`elysium`, `elysium.reactive`, `elysium.anim`,
   `elysium.theme`).
2. `app = ely.App(...)`, `window = app.window(...)`,
   `window.set_hit_test_path(...)`, `window.load_skin(...)`.
3. The two signals (`time_signal`, `now_seconds`) and three effects
   (`push_time`, `push_sweep`, plus the theme-toggle handler).
4. The `tick_forever` background thread.
5. The glow `Tween` and `AnimationClock`.
6. (Optional) `window.set_blur_behind` on macOS.
7. `app.run()`.

The full script is about 60 lines. That is the entire Aurora Clock.

## What you built

- A **borderless transparent ellipse** desktop widget (chapter 1).
- A **declarative skin** describing every shape (chapter 2).
- A **reactive signal** driving the time label (chapter 3).
- A **Tween + AnimationClock** breathing aurora glow (chapter 4).
- A **`@window.on` event handler** that runtime-swaps themes (this
  chapter).

You exercised `App`, `Window`, `load_skin`, the dotted hook proxy,
`signal`, `effect`, `Tween`, `AnimationClock`, `set_theme`,
`midnight_glass`, `frost`, and `@window.on`: the spine of the
Framework's public API.

## Ship it

To distribute the clock as a standalone app, see
[Packaging](../guides/packaging.md). The short version:

```sh
elysium pack aurora_clock.py --name "Aurora Clock"
```

The CLI produces a signed bundle per OS in `./dist/`.

## Where to next

- [Pomodoro](pomodoro-01-shape-and-modes.md) layers state machines,
  popovers, and notifications on top of the patterns from this
  tutorial.
- [Stylized Music Player](stylized-music-01-the-faceplate.md) is the
  most elaborate borderless app in the docs and pushes the brush
  and theming systems to their limits.
- [Butterfly Banner](butterfly-banner-01-load-the-skin.md) loads a
  full Designer-authored `.esk` and animates it as the Elysium logo.

[Back to Getting Started](index.md)
