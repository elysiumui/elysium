# Particle pet

Time: 35 minutes. Difficulty: Intermediate.

A small borderless transparent window with a glowing creature that
follows your cursor (with delay, via a Spring), blinks
occasionally, and emits a particle trail. Lives at level 3, ignores
clicks (passes through to the desktop). The "tamagotchi for the
modern desktop" app.

## Prerequisites

- Walked through [Aurora Clock](../getting-started/aurora-clock-01-window.md).
- `pip install elysium-ui`.

## The window

The window is just a transparent rectangle big enough to hold the
pet plus some particle headroom:

```python
import elysium as ely

app = ely.App(title="Pet", identifier="dev.example.pet")
window = app.window(
    transparent=True, title_bar=False, resizable=False,
    initial_size=(180, 180),
    level=3,                # floating
)
window.set_ignores_mouse(True)   # clicks pass through to the desktop
```

`set_ignores_mouse(True)` is the magic: the pet is purely visual;
clicks land on whatever is underneath.

## Skin

```json
// pet.esk/document.json
{
  "placements": [
    { "id": "glow", "kind": "ellipse",
      "x": 30, "y": 30, "width": 120, "height": 120,
      "fill": "#a78bfaff", "blur": 36, "opacity": 0.4 },
    { "id": "body", "kind": "ellipse",
      "x": 60, "y": 60, "width": 60, "height": 60,
      "fill": "radial-gradient(circle at 35% 30%, #fde68a, #a78bfa, #6b21a8)" },
    { "id": "eye_l", "kind": "ellipse",
      "x": 76, "y": 78, "width": 8, "height": 8,
      "fill": "#1a0f3cff" },
    { "id": "eye_r", "kind": "ellipse",
      "x": 96, "y": 78, "width": 8, "height": 8,
      "fill": "#1a0f3cff" },
    { "id": "trail", "kind": "canvas",
      "x": 0, "y": 0, "width": 180, "height": 180 }
  ]
}
```

## Follow the cursor

The cursor reports in screen coordinates; the pet should chase
with a Spring lag.

```python
from elysium import platform
from elysium.anim import Spring, AnimationClock, run_animation_thread
import threading, time

clock = AnimationClock()
run_animation_thread(clock, fps=60)

x_spring = Spring(stiffness=80, damping=12)
y_spring = Spring(stiffness=80, damping=12)


def cursor_thread():
    while True:
        time.sleep(1.0 / 60.0)
        x, y = platform.global_cursor_position()
        # Position the window's center near the cursor.
        x_spring.target(x - 90)
        y_spring.target(y - 90)
        window.set_outer_position(int(x_spring.value), int(y_spring.value))


threading.Thread(target=cursor_thread, daemon=True).start()
```

The springs lag the cursor smoothly. Stiffness 80 / damping 12
gives a "balloon following you" feel.

## Blinking

```python
import random

def blink_thread():
    while True:
        time.sleep(random.uniform(2.5, 5.5))
        window.eye_l.height = 1
        window.eye_r.height = 1
        time.sleep(0.12)
        window.eye_l.height = 8
        window.eye_r.height = 8


threading.Thread(target=blink_thread, daemon=True).start()
```

## Particle trail

Each frame, drop a faint puff at the pet's last position and fade
existing puffs:

```python
import elysium as ely

trail_puffs = []   # list of (x, y, alpha)


def trail_thread():
    while True:
        time.sleep(1.0 / 30.0)
        # Drop a new puff near the pet body (window-local 90, 90)
        trail_puffs.append([90, 90, 1.0])
        # Fade and trim
        new_list = []
        dl = ely.DisplayList()
        for x, y, a in trail_puffs:
            a -= 0.04
            if a > 0:
                new_list.append([x, y, a])
                path = ely.Path()
                path.circle(x, y, r=10 * a)
                dl.fill_color((0.65, 0.55, 0.98, 0.4 * a))
                dl.fill_path(path)
        trail_puffs[:] = new_list
        window.trail.publish_display_list(dl)


threading.Thread(target=trail_thread, daemon=True).start()
```

## Run

```python
app.run()
```

A glowing puff follows your cursor; eyes blink; a trail fades
behind it.

## Ship

```sh
elysium pack pet.py --name "Pet" --identifier dev.example.pet --include pet.esk
```

## Variations

- Increase Spring stiffness for a peppier pet.
- Swap the body gradient for a custom photo for an "interactive
  mascot" version.
- Add `@window.on("body.click")` (turn off `set_ignores_mouse`)
  for a tap-to-interact feature.

## See also

- [Recipes: hover spring scale](../recipes/09-hover-spring-scale.md)
- [Animation guide](../guides/animation.md)
- [Rendering guide](../guides/rendering.md)
