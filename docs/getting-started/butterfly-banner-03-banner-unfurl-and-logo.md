# Butterfly Banner 3. Unfurl the wordmark

Time: 8 minutes.

## What we are adding

After the butterfly settles, the Elysium wordmark unfurls behind it
from a single point under the abdomen to its full width, with a
soft ribbon flutter. Then we capture the full animation as the
official logo gif and mp4 for use in the docs.

![Butterfly Banner chapter 3: wordmark unfurling behind the settled butterfly, frame-by-frame](../assets/butterfly-banner-ch3.gif)

## Resize the window for the unfurl

The descent landed the butterfly in a 960x540 window. The full
banner needs more horizontal room for the wordmark. Resize the
window after the descent completes:

```python
BANNER_W, BANNER_H = 1600, 540

def expand_for_banner():
    window.resize(BANNER_W, BANNER_H)
    new_x = (primary.width - BANNER_W) // 2
    window.set_outer_position(new_x, end_y)
    # The hover thread reads end_y; keep it valid.

descent.on_complete(expand_for_banner)
```

Borderless transparent windows resize without flicker.

## Add the wordmark placement to the loaded skin

The Designer's chapter 8 export includes the butterfly + light. For
the banner we add the wordmark at runtime so the same `.esk` works
in apps that do not need the wordmark.

```python
wordmark = window.add_placement({
    "id": "wordmark",
    "kind": "label",
    "x": 0, "y": 200,
    "width": BANNER_W,
    "height": 140,
    "text": "Elysium",
    "font_family": "system-display",
    "font_weight": 200,
    "font_size": 140,
    "fill": "linear-gradient(135deg, #f0abfc 0%, #a78bfa 50%, #6b21a8 100%)",
    "align": "center",
    "letter_spacing": 18,
    "opacity": 0.0,
    "scale_x": 0.0,
})
```

`window.add_placement` injects a new placement into the live skin
without re-loading. `scale_x` of 0 collapses it to a single point
under the butterfly so the "unfurl" can grow it outward.

## Tween the unfurl

The unfurl is two Tweens: one for the horizontal expansion, one for
the opacity ramp. Run them in parallel via a Timeline:

```python
from elysium.anim import Tween, Timeline, cubic_bezier

unfurl_scale = Tween(
    target=lambda v: setattr(wordmark, "scale_x", v),
    start=0.0,
    end=1.0,
    duration=1.2,
    easing=cubic_bezier(0.16, 1.0, 0.3, 1.0),  # smooth ease-out
)
unfurl_alpha = Tween(
    target=lambda v: setattr(wordmark, "opacity", v),
    start=0.0,
    end=0.92,
    duration=0.9,
    easing="ease_out_sine",
)

unfurl = Timeline([
    (0.0, unfurl_scale),
    (0.3, unfurl_alpha),
])

clock.add(unfurl_scale)
clock.add(unfurl_alpha)


def begin_unfurl():
    unfurl.start()


descent.on_complete(begin_unfurl)
```

We register both Tweens with the same clock, then sequence them with
the Timeline. The 0.3 second offset on the alpha tween gives the
wordmark a brief invisible expansion before it fades in: it reads
as the wordmark "unrolling".

## Ribbon flutter

After the unfurl finishes, give the wordmark a subtle horizontal
wave so it looks like fabric:

```python
import math
import time

def ribbon_thread():
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        # Light skew oscillation that reads like a flag.
        skew = math.sin(t * 1.8) * 1.5
        wordmark.skew_y = skew
        time.sleep(1.0 / 60.0)


import threading
threading.Thread(target=ribbon_thread, daemon=True).start()
```

The skew animation runs forever in the background; on idle the
wordmark gently waves.

## Export as the official logo gif / mp4

The framework's `Recorder` captures the window output to a video
file. Use it once you are happy with the timing:

```python
from elysium.render import Recorder

recorder = Recorder(window=window, fps=60, format="mp4")
recorder.start("elysium_banner.mp4")

# Run the full descent + unfurl + 4 seconds of idle.
import time
time.sleep(2.4 + 1.5 + 4.0)

recorder.stop()
```

For a gif: `format="gif"` and pick a lower fps (24 is plenty for a
banner gif). The recorder writes the file when `stop()` is called.

For the official Elysium logo we ship both the mp4 (for embeds and
the docs hero) and the gif (for README badges).

## Use the banner as the docs hero

This gif is the page-load animation for `docs.elysiumui.com` itself.
Drop the produced file into `docs/assets/butterfly-banner.gif` and
reference it from `docs/index.md`:

```markdown
![Elysium](assets/butterfly-banner.gif)
```

## What you built

Across the three chapters:

- Loaded a Designer-authored `.esk` (chapter 1).
- Sequenced a 3D scene to descend from offscreen with a cubic-bezier
  ease (chapter 2).
- Added wing-flap rate adjustments and a reduced-motion fallback
  (chapter 2).
- Resized the window mid-animation to make room for the wordmark
  (this chapter).
- Injected a wordmark placement at runtime and ran two parallel
  Tweens to unfurl it (this chapter).
- Recorded the result as the official logo gif and mp4 (this
  chapter).

You exercised: `load_skin`, `set_outer_position`, `resize`,
`add_placement`, `Tween` with `cubic_bezier`, `Timeline`,
`AnimationClock`, `run_animation_thread`, `accessibility.current`,
the Designer-Framework cross-site arc, and `Recorder`.

## The cross-site arc closes here

This three-chapter tutorial together with the Designer's nine-
chapter Blue Morpho to Monarch tutorial is the canonical Elysium
end-to-end story: authoring tool ships a skin → framework loads it,
animates it, and renders the result. Both halves of the company
ship as one continuous learning arc.

## Where to next

- [Recipes](../recipes/index.md): quick "how do I X?" answers for
  common patterns.
- [Tutorials](../tutorials/index.md): longer follow-on builds.
- [Guides](../guides/index.md): topic deep dives.
- [API Reference](../api/index.md): every class explained.

[Back to Getting Started](index.md)
