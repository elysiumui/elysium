# Aurora Clock Pro

Time: 60 minutes. Difficulty: Advanced.

Evolve the [Aurora Clock](../getting-started/aurora-clock-01-window.md)
from a single-window widget into a multi-window productivity app
with a clock, a timer, a stopwatch, and a shared settings window.
Demonstrates app-scale composition.

## What you build

| Window | Purpose |
|---|---|
| Clock | The original ellipse clock (now smaller) |
| Timer | Rounded-rect countdown |
| Stopwatch | Rounded-rect count-up |
| Settings | Modal for theme, sounds, default durations |

All three primary windows share a theme; toggling theme in Settings
re-skins everything.

## Prerequisites

- Finished [Aurora Clock](../getting-started/aurora-clock-05-theme-and-events.md).
- Finished [Pomodoro](../getting-started/pomodoro-04-notifications-and-shipping.md).
- `pip install elysium-ui`.

## Project layout

```
aurora_pro/
  main.py
  clock.esk/         (the lead-tutorial Aurora Clock skin)
  timer.esk/         (new)
  stopwatch.esk/     (new)
  settings.esk/      (new)
```

## main.py: app + three persistent windows

```python
import elysium as ely
from elysium.theme import set_theme, midnight_glass

app = ely.App(title="Aurora Pro", identifier="dev.example.aurora-pro")

clock = app.window(transparent=True, title_bar=False, resizable=False,
                   initial_size=(280, 280))
clock.set_hit_test_path(
    "M 0,140 A 140,140 0 1 0 280,140 A 140,140 0 1 0 0,140 Z")
clock.load_skin("clock.esk/")

timer = app.window(transparent=True, title_bar=False, resizable=False,
                   initial_size=(280, 180))
timer.set_hit_test_path(rounded_rect(280, 180, 24))
timer.load_skin("timer.esk/")

stopwatch = app.window(transparent=True, title_bar=False, resizable=False,
                       initial_size=(280, 180))
stopwatch.set_hit_test_path(rounded_rect(280, 180, 24))
stopwatch.load_skin("stopwatch.esk/")

set_theme(midnight_glass())
```

`rounded_rect(w, h, r)` is a small helper that builds an SVG
rounded-rect path string given width / height / radius: define it
once.

## Settings window: modal pattern

```python
def open_settings():
    settings = app.window(
        transparent=True, title_bar=False, resizable=False,
        initial_size=(420, 320),
        parent=clock, modal=True,
    )
    settings.set_hit_test_path(rounded_rect(420, 320, 24))
    settings.load_skin("settings.esk/")

    @settings.on("close_btn.click")
    def close(event):
        settings.close()

    return settings
```

Open from any window's gear icon.

## Cross-window signals

All four windows share a single set of reactive signals:

```python
from elysium.reactive import signal

current_theme = signal("midnight_glass")
sound_enabled = signal(True)
default_focus_minutes = signal(25)
```

Each window's effect reads these:

```python
@effect
def push_theme():
    name = current_theme()
    set_theme({
        "midnight_glass": midnight_glass(),
        "frost": frost(),
        "oled": oled(),
    }[name])
    # Re-skin the placement colors that aren't theme tokens.
    clock.background.fill = theme.background
    timer.panel.fill = theme.background
    stopwatch.panel.fill = theme.background
```

The Settings window's theme dropdown calls `current_theme.set(...)`;
every window re-skins in one frame.

## Position windows together

When the user moves the Clock, the other two windows should follow
in a fixed offset. Use a "dock" group:

```python
DOCK = [clock, timer, stopwatch]
DOCK_OFFSETS = [(0, 0), (300, 0), (600, 0)]    # px from clock


@clock.on("window.moved")
def reposition_others(event):
    cx, cy = clock.outer_position
    for win, (dx, dy) in zip(DOCK, DOCK_OFFSETS):
        if win is clock:
            continue
        win.set_outer_position(cx + dx, cy + dy)
```

A drag of the clock takes the timer + stopwatch with it. For
independent dragging, omit this handler.

## Timer + stopwatch behavior

Each is a small state machine with a `running` signal and a
worker thread that ticks a `remaining` (or `elapsed`) signal at
20 Hz. The pattern is the same as the Pomodoro tutorial; see
[chapter 2](../getting-started/pomodoro-02-radial-progress.md).

## Save and restore layout

```python
import json
from elysium import platform

layout_path = platform.user_data_dir("aurora-pro") / "layout.json"


def save_layout():
    layout_path.parent.mkdir(parents=True, exist_ok=True)
    layout_path.write_text(json.dumps({
        "clock":     clock.outer_position,
        "timer":     timer.outer_position,
        "stopwatch": stopwatch.outer_position,
        "theme":     current_theme(),
    }))


@clock.on("window.closed")
def on_close(event):
    save_layout()
    app.quit()


def load_layout():
    if not layout_path.exists():
        return
    g = json.loads(layout_path.read_text())
    clock.set_outer_position(*g["clock"])
    timer.set_outer_position(*g["timer"])
    stopwatch.set_outer_position(*g["stopwatch"])
    current_theme.set(g["theme"])


load_layout()
```

## Ship

```sh
elysium pack main.py --name "Aurora Pro" \
  --identifier dev.example.aurora-pro \
  --include clock.esk timer.esk stopwatch.esk settings.esk
```

## What you exercised

- Multi-window composition.
- Cross-window shared signals.
- A modal settings dialog.
- Window dock-and-follow positioning.
- Layout persistence.
- A unified theme cascade across windows.

## See also

- [Aurora Clock lead tutorial](../getting-started/aurora-clock-01-window.md)
- [Windowing](../guides/windowing.md)
- [Reactive](../guides/reactive.md)
