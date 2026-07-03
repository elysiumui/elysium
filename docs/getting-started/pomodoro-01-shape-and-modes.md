# Pomodoro 1. Window shape and mode state

Time: 6 minutes.

## What you are building

Four chapters take you from an empty file to a borderless rounded-
rectangle Pomodoro timer with three modes (Focus / Short Break /
Long Break), an animated radial progress ring, a tap-to-start
gesture, and a settings popover. By the end you will package the
result with `elysium pack`.

This chapter ships the window, the rounded-rect hit region, and the
three-mode StateMachine that drives every subsequent screen.

![Pomodoro chapter 1: rounded-rect window showing mode label "Focus" and a 25:00 timer placeholder](../assets/pomodoro-ch1.png)

## Prerequisites

- Elysium installed (`pip install elysium-ui`).
- Walked through [Aurora Clock chapter 1](aurora-clock-01-window.md)
  recently. This tutorial reuses the borderless-window pattern from
  there and adds new primitives.

## Window + rounded-rect hit region

Create `pomodoro.py`:

```python
import elysium as ely

# 320 x 200 rounded rectangle, corner radius 28.
ROUNDED = (
    "M 28,0 L 292,0 "
    "A 28,28 0 0 1 320,28 L 320,172 "
    "A 28,28 0 0 1 292,200 L 28,200 "
    "A 28,28 0 0 1 0,172 L 0,28 "
    "A 28,28 0 0 1 28,0 Z"
)

app = ely.App(title="Pomodoro", identifier="dev.elysium.pomodoro")
window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(320, 200),
)
window.set_hit_test_path(ROUNDED)

app.run()
```

Run it. A borderless rounded-rectangle window appears.

## Skin: the rounded panel + the mode label + the timer text

Create `pomodoro.esk/manifest.json`:

```json
{
  "schema_version": "1.0",
  "id": "dev.elysium.pomodoro",
  "name": "Pomodoro",
  "version": "0.1.0",
  "color_space": "srgb"
}
```

And `pomodoro.esk/document.json`:

```json
{
  "placements": [
    {
      "id": "panel",
      "kind": "rounded_rect",
      "x": 0, "y": 0,
      "width": 320, "height": 200,
      "radius": 28,
      "fill": "#1e1b4bff"
    },
    {
      "id": "mode_label",
      "kind": "label",
      "x": 0, "y": 32,
      "width": 320, "height": 20,
      "text": "Focus",
      "font_family": "system",
      "font_size": 13,
      "fill": "#c4b5fdff",
      "align": "center"
    },
    {
      "id": "timer_label",
      "kind": "label",
      "x": 0, "y": 78,
      "width": 320, "height": 56,
      "text": "25:00",
      "font_family": "system",
      "font_size": 48,
      "fill": "#ffffffff",
      "align": "center"
    },
    {
      "id": "hint_label",
      "kind": "label",
      "x": 0, "y": 152,
      "width": 320, "height": 16,
      "text": "Tap to start",
      "font_family": "system",
      "font_size": 11,
      "fill": "#a78bfaff",
      "align": "center"
    }
  ]
}
```

Load the skin from Python:

```python
from pathlib import Path

window.load_skin(str(Path(__file__).parent / "pomodoro.esk"))
```

Run again. The panel paints, with "Focus" up top, "25:00" centered,
and "Tap to start" near the bottom.

## The three-mode StateMachine

A Pomodoro cycle is **Focus → Short Break → Focus → Short Break →
Focus → Short Break → Focus → Long Break** (four focuses, then a
long break, then repeat).

The `elysium.anim.StateMachine` is the right primitive: it tracks a
current state, lets you describe transitions declaratively, and
fires callbacks on transition.

```python
from elysium.anim import StateMachine

mode_machine = StateMachine(
    states=["focus", "short_break", "long_break"],
    initial="focus",
)

# After each focus, advance the count and decide which break to take.
focus_count = 0

def advance_after_focus():
    global focus_count
    focus_count += 1
    if focus_count % 4 == 0:
        return "long_break"
    return "short_break"


mode_machine.transition("focus", on_complete=advance_after_focus)
mode_machine.transition("short_break", on_complete=lambda: "focus")
mode_machine.transition("long_break", on_complete=lambda: "focus")
```

The `on_complete` callback is invoked by the timer (chapter 2) when
the countdown for the current mode reaches zero. Its return value
becomes the next state.

## Hook the mode label to the current state

Add a `signal` + `effect` pair that syncs the label whenever the
state machine changes:

```python
from elysium.reactive import signal, effect

mode_signal = signal("focus")

@mode_machine.on_change
def update_mode_signal(new_state):
    mode_signal.set(new_state)


@effect
def push_mode_to_label():
    window.mode_label.text = {
        "focus": "Focus",
        "short_break": "Short Break",
        "long_break": "Long Break",
    }[mode_signal()]
```

The bridge from state machine to signal keeps the reactive
abstraction front-and-center: anything that needs to react to the
mode (the radial ring color in chapter 2, the notification text in
chapter 4) just reads `mode_signal()`.

## Checkpoint

You should see:

- A borderless rounded-rectangle window.
- A "Focus" / "25:00" / "Tap to start" layout.
- A `mode_machine` in code that cycles Focus → Short Break (3 of 4)
  or Focus → Long Break (every 4th).

The mode label will visibly change once we wire the countdown in
the next chapter.

Continue to [chapter 2: radial progress ring](pomodoro-02-radial-progress.md).
