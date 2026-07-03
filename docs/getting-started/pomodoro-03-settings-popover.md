# Pomodoro 3. Settings popover

Time: 6 minutes.

## What we are adding

A small gear icon in the corner of the panel that opens a Popover
with three sliders (Focus / Short Break / Long Break durations) and
a Toggle for "Auto-cycle" (whether to start the next mode
automatically when the current one ends).

![Pomodoro chapter 3: settings popover open showing three duration sliders and an auto-cycle toggle](../assets/pomodoro-ch3.gif)

## Add the gear icon

Append to `pomodoro.esk/document.json`:

```json
{
  "id": "gear",
  "kind": "icon_button",
  "x": 286, "y": 10,
  "width": 24, "height": 24,
  "icon": "settings",
  "fill": "#a78bfaff",
  "background": "transparent",
  "tooltip": "Settings"
}
```

`kind: "icon_button"` is the framework's built-in icon-only button.
The `icon` field accepts any name from the bundled icon catalog.

## Wire the popover

The `Popover` is a Component from `elysium.components`. It opens
attached to an anchor placement and closes on outside-click or Esc.

```python
from elysium.components import Popover, Slider, Toggle

popover = Popover(
    anchor=window.gear,
    width=260,
    height=200,
    placement="bottom-end",
)
```

The Popover defines a small sub-document (a nested skin) for its
content. The Slider and Toggle components are added directly:

```python
focus_minutes = signal(25)
short_break_minutes = signal(5)
long_break_minutes = signal(15)
auto_cycle = signal(True)

popover.content.append(Slider(
    id="focus_slider",
    label="Focus",
    min=10, max=60, step=1,
    value=focus_minutes,
    suffix=" min",
))
popover.content.append(Slider(
    id="short_slider",
    label="Short break",
    min=3, max=15, step=1,
    value=short_break_minutes,
    suffix=" min",
))
popover.content.append(Slider(
    id="long_slider",
    label="Long break",
    min=10, max=30, step=1,
    value=long_break_minutes,
    suffix=" min",
))
popover.content.append(Toggle(
    id="auto_cycle_toggle",
    label="Auto-cycle modes",
    value=auto_cycle,
))
```

Each Slider takes a signal as its `value`: dragging the slider calls
`signal.set(new_value)` for you, and any effect that reads the
signal re-runs.

## React to slider changes

Wire `DURATIONS_S` to the signals:

```python
@effect
def push_durations():
    DURATIONS_S["focus"] = focus_minutes() * 60
    DURATIONS_S["short_break"] = short_break_minutes() * 60
    DURATIONS_S["long_break"] = long_break_minutes() * 60
    # If we are not currently running, refresh the displayed time to
    # reflect the new default for the current mode.
    if not running():
        remaining.set(DURATIONS_S[mode_signal()])
```

## Open and close

Bind the gear's click:

```python
@window.on("gear.click")
def toggle_settings(event):
    popover.toggle()
```

`Popover.toggle()` opens if closed, closes if open. The framework
handles outside-clicks and Esc automatically.

## Respect auto_cycle

In the `countdown_thread` from chapter 2, change the post-completion
behavior:

```python
if remaining() <= 0:
    running.set(False)
    next_state = mode_machine.complete()
    remaining.set(DURATIONS_S[next_state])
    progress.set(0.0)
    if auto_cycle():
        running.set(True)   # auto-start next mode
```

Now toggling **Auto-cycle modes** in the popover controls whether
the timer immediately starts the next mode or waits for a tap.

## Persist settings between launches

Use `elysium.platform.user_data_dir()` to find a place to save the
four signals:

```python
import json
from elysium.platform import user_data_dir

settings_path = user_data_dir("pomodoro") / "settings.json"


def load_settings():
    if not settings_path.exists():
        return
    data = json.loads(settings_path.read_text())
    focus_minutes.set(data.get("focus", 25))
    short_break_minutes.set(data.get("short_break", 5))
    long_break_minutes.set(data.get("long_break", 15))
    auto_cycle.set(data.get("auto_cycle", True))


@effect
def persist_settings():
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "focus": focus_minutes(),
        "short_break": short_break_minutes(),
        "long_break": long_break_minutes(),
        "auto_cycle": auto_cycle(),
    }))


load_settings()
```

The `persist_settings` effect re-runs whenever any of the four
signals changes, so settings save on every slider drag. The next
launch picks up where you left off.

## Checkpoint

You should see:

- A gear icon in the top-right.
- Click it: a popover appears below it with three sliders and a
  toggle.
- Drag a slider: the timer's mode duration updates live.
- Toggle Auto-cycle off; the timer waits for a tap between modes.
- Close, relaunch: settings persist.

Continue to [chapter 4: notifications + shipping](pomodoro-04-notifications-and-shipping.md).
