# Aurora Clock 3. Drive the dial with a reactive signal

Time: 6 minutes.

## What we are adding

A reactive `signal` that holds the current time, an `effect` that
updates the label whenever the signal changes, and a 1 Hz background
thread that ticks the signal. By the end of this chapter the clock
shows real wall-clock time.

![Aurora Clock chapter 3 result: the dial shows the current local time, updating every second](../assets/aurora-clock-ch3.gif)

## Why reactive

Elysium's reactive layer (`elysium.reactive`) is a small
synchronously-tracking system: a `signal` is a mutable value; a
`computed` is a derived read; an `effect` is a side-effecting
callback that re-runs whenever any signal it read last time
changes.

For the clock that means: write `time_signal` once per second; the
effect that sets `window.time_label.text` re-runs automatically.

## Wire the signal

Update `aurora_clock.py`:

```python
import threading
import time
from datetime import datetime
from pathlib import Path

import elysium as ely
from elysium.reactive import signal, effect

ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"
SKIN_PATH = str(Path(__file__).parent / "aurora_clock.esk")

app = ely.App(title="Aurora Clock", identifier="dev.elysium.aurora-clock")

window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(360, 360),
)
window.set_hit_test_path(ELLIPSE)
window.load_skin(SKIN_PATH)

time_signal = signal(datetime.now().strftime("%H:%M:%S"))

@effect
def push_time_to_label():
    window.time_label.text = time_signal()


def tick_forever():
    while True:
        time.sleep(1.0)
        time_signal.set(datetime.now().strftime("%H:%M:%S"))


threading.Thread(target=tick_forever, daemon=True).start()
app.run()
```

Run it. The label now shows the current local time and updates
every second.

## What just happened

Three pieces collaborated:

1. **`signal(...)`** created a reactive cell holding the formatted
   time string.
2. **`@effect`** ran `push_time_to_label` once immediately, which
   recorded that it depends on `time_signal`. Setting
   `window.time_label.text` reached through the dotted-hook proxy
   into the native skin's `time_label` placement and changed its
   text in place.
3. **`tick_forever`** runs on a background thread. Each `signal.set`
   queues a re-run of every effect that read this signal. The
   framework drains the queue on the next render tick, so the label
   updates within ~16 ms of the `set` call at 60 fps.

You can also write `time_signal.set("foo")` from inside an event
handler (`@window.on(...)`) and the effect fires the same way.

## Format the time however you like

Replace `"%H:%M:%S"` with anything `datetime.strftime` accepts. For
12-hour with AM/PM: `"%I:%M:%S %p"`. To show only HH:MM, drop the
seconds (we will use seconds in chapter 4 for the second-hand arc).

## A computed for the seconds value

Chapter 4 needs the current seconds as a float. Add a `computed`
that derives that from a separate `now_seconds` signal:

```python
from elysium.reactive import signal, computed, effect

now_seconds = signal(0.0)

@computed
def sweep_angle():
    return (now_seconds() / 60.0) * 360.0
```

Update `tick_forever` to push a float as well:

```python
def tick_forever():
    while True:
        now = datetime.now()
        time_signal.set(now.strftime("%H:%M:%S"))
        now_seconds.set(now.second + now.microsecond / 1_000_000.0)
        time.sleep(0.05)   # update 20x per second so the sweep is smooth
```

The 20 Hz tick rate gives a noticeably smoother sweep without
visible jitter. The label still effectively updates once per second
because the string only changes at second boundaries.

## Thread safety

Signal `.set()` and effect re-runs use a lock internally, so calling
`.set` from any thread is safe. Effects always run on the render
thread (the one `app.run()` blocks on), so when an effect mutates
window state it is doing so on the correct thread for the GPU.

## Checkpoint

You should see:

- The label updating once per second to the local time.
- (After the optional `now_seconds` step) a signal that updates 20
  times per second, ready for the sweep in chapter 4.

Continue to [chapter 4: animations](aurora-clock-04-animation.md).
