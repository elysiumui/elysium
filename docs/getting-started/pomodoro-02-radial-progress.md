# Pomodoro 2. Radial progress ring

Time: 7 minutes.

## What we are adding

A radial progress ring that wraps the timer label, plus a Spring-
driven tap-to-start gesture. The ring fills with the mode's accent
color as the countdown progresses.

![Pomodoro chapter 2: radial ring filling around the 25:00 timer, tap to start animation](../assets/pomodoro-ch2.gif)

## Add the ring to the skin

Append three placements to `pomodoro.esk/document.json` (after
`panel`, before `mode_label`):

```json
{
  "id": "ring_track",
  "kind": "arc",
  "cx": 160, "cy": 100,
  "radius": 76,
  "start_angle": 0,
  "end_angle": 360,
  "stroke": "#312e81ff",
  "stroke_width": 6.0,
  "cap": "round"
},
{
  "id": "ring_progress",
  "kind": "arc",
  "cx": 160, "cy": 100,
  "radius": 76,
  "start_angle": -90,
  "end_angle": -90,
  "stroke": "#a78bfaff",
  "stroke_width": 6.0,
  "cap": "round"
}
```

`ring_track` is the static background ring (always a full circle).
`ring_progress` is the colored progress arc that grows as time
elapses. Both share the same center and radius.

## Drive the ring from a signal

Add a `progress` signal in `pomodoro.py` (0.0 = just started, 1.0 =
done) plus an effect that maps it to the arc's `end_angle`:

```python
from elysium.reactive import signal, effect

progress = signal(0.0)

@effect
def push_progress_to_arc():
    end_angle = -90 + progress() * 360.0
    window.ring_progress.end_angle = end_angle
```

While we are here, tint the ring with the mode's accent color:

```python
@effect
def push_mode_to_arc_color():
    color = {
        "focus": "#a78bfaff",        # violet
        "short_break": "#34d399ff",  # emerald
        "long_break": "#60a5faff",   # sky
    }[mode_signal()]
    window.ring_progress.stroke = color
```

Both effects re-run whenever their inputs change, so the ring color
swaps the moment the state machine transitions.

## The countdown

The Pomodoro state has three durations:

```python
DURATIONS_S = {
    "focus": 25 * 60,
    "short_break": 5 * 60,
    "long_break": 15 * 60,
}
```

Run the countdown on a background thread. Each tick decrements a
remaining-seconds signal; an effect formats it into the label.

```python
import threading
import time

remaining = signal(DURATIONS_S["focus"])
running = signal(False)


@effect
def push_timer_label():
    secs = remaining()
    mm, ss = divmod(secs, 60)
    window.timer_label.text = f"{mm:02d}:{ss:02d}"


def countdown_thread():
    while True:
        time.sleep(0.05)
        if not running():
            continue
        total = DURATIONS_S[mode_signal()]
        remaining.set(max(0, remaining() - 0.05))
        progress.set(1.0 - remaining() / total)
        if remaining() <= 0:
            running.set(False)
            next_state = mode_machine.complete()  # fires on_complete callbacks
            remaining.set(DURATIONS_S[next_state])
            progress.set(0.0)


threading.Thread(target=countdown_thread, daemon=True).start()
```

The thread runs at 20 Hz so the radial ring updates smoothly even
during long focus sessions. The `running` signal acts as the pause
gate.

## Tap-to-start with a Spring

When the user clicks anywhere on the panel, we want a small scale-
bounce, then to start (or pause) the timer. The `Spring` primitive
from `elysium.anim` gives the classic critically-damped feel.

Add a hit-test region on the panel by binding to `panel.click`:

```python
from elysium.anim import Spring

bounce_spring = Spring(stiffness=180.0, damping=18.0, mass=1.0)


@window.on("panel.click")
def tap(event):
    running.set(not running())
    bounce_spring.pulse(from_value=0.96, to_value=1.0)
    window.hint_label.text = "Tap to pause" if running() else "Tap to start"


@bounce_spring.on_update
def apply_scale(value: float):
    window.panel.scale = value
```

`Spring.pulse(from, to)` snaps the spring to `from_value` and then
animates it toward `to_value` with the configured stiffness and
damping. The `on_update` callback receives every frame's value and
applies it to `window.panel.scale`.

## Tying off the mode change

Earlier we defined `mode_machine.complete()`-style transitions but
never wired a path back to `mode_signal`. The `on_change` hook from
chapter 1 already does that. When the countdown thread calls
`complete()`, the state machine fires `on_change`, the signal
updates, the mode label changes, and the ring color and remaining
time follow.

## Checkpoint

You should see:

- A track ring + colored progress ring around the timer label.
- Tap (left-click) the panel: timer starts, progress fills, label
  ticks down each second.
- Tap again: timer pauses; the hint label flips.
- After 25 minutes (or shorten `DURATIONS_S` for testing): mode
  flips to Short Break, color shifts to emerald, timer resets.

Continue to [chapter 3: settings popover](pomodoro-03-settings-popover.md).
