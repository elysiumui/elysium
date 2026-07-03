# Pomodoro 4. Notifications and shipping

Time: 6 minutes.

## What we are adding

Two notifications fire when a mode completes:

1. An **in-app Toast** that overlays the window with the new mode's
   name and a short message ("Time for a break!" / "Back to focus!").
2. A **system notification** through the OS notification center so
   the user knows even if the Pomodoro window is hidden.

Then we package the whole thing into a signed standalone app with
`elysium.pack`.

![Pomodoro chapter 4: toast fading in over the panel, system notification visible at the top-right of the desktop](../assets/pomodoro-ch4.gif)

## Add an in-app Toast

The `Toast` component is a brief, dismissible overlay anchored to a
window. Import and create one:

```python
from elysium.components import Toast

toast = Toast(window=window, duration_ms=3000)


def show_mode_done_toast(next_mode: str):
    messages = {
        "focus": ("Back to focus", "Let's go."),
        "short_break": ("Short break", "Take 5."),
        "long_break": ("Long break", "Stretch your legs."),
    }
    title, body = messages[next_mode]
    toast.show(title=title, body=body)
```

Call `show_mode_done_toast(next_state)` inside `countdown_thread`
right after the state machine completes:

```python
if remaining() <= 0:
    running.set(False)
    next_state = mode_machine.complete()
    remaining.set(DURATIONS_S[next_state])
    progress.set(0.0)
    show_mode_done_toast(next_state)
    if auto_cycle():
        running.set(True)
```

The Toast fades in over 200 ms, sits for 3 seconds, fades out, and
disposes itself.

## System notifications

The framework wraps the platform's native notification API in
`elysium.platform.notify`. It does the right thing on each OS:

| Platform | Implementation |
|---|---|
| macOS | `UNUserNotificationCenter` (UserNotifications.framework) |
| Windows | Toast XML through `Windows.UI.Notifications` |
| Linux | `notify-send` via libnotify (or `org.freedesktop.Notifications` DBus directly) |

Use it:

```python
from elysium.platform import notify

def post_system_notification(next_mode: str):
    titles = {
        "focus": "Pomodoro: back to focus",
        "short_break": "Pomodoro: short break",
        "long_break": "Pomodoro: long break",
    }
    notify(
        title=titles[next_mode],
        body=f"{DURATIONS_S[next_mode] // 60} minutes.",
        icon="pomodoro",       # uses the bundled icon
        sound="default",
    )
```

Call it alongside the Toast in `countdown_thread`. On macOS the user
sees the standard banner / alert (depending on Focus mode settings);
on Windows the Action Center receives it; on Linux it surfaces
through whatever DE notification daemon is running.

### macOS permission prompt

The first time `notify` runs on macOS, the OS prompts the user for
permission to deliver notifications. We can ask for it ahead of time
on launch:

```python
import sys
if sys.platform == "darwin":
    from elysium.platform import request_notification_permission
    request_notification_permission()
```

## Package the app

The `elysium pack` CLI uses PyInstaller to produce a per-OS signed
bundle in `./dist/`.

```sh
elysium pack pomodoro.py \
  --name "Pomodoro" \
  --identifier dev.elysium.pomodoro \
  --icon ./pomodoro_icon.png \
  --include pomodoro.esk
```

The flags:

- `--name` is the human-readable name (the Dock title on macOS, the
  Start menu entry on Windows, the `.desktop` Name field on Linux).
- `--identifier` becomes the bundle id on macOS and the AppUserModel
  ID on Windows; it must be a reverse-DNS string.
- `--icon` is a PNG (it is resized to all the per-OS sizes
  automatically; for higher fidelity supply a `.icns`/`.ico`).
- `--include` ships your skin folder inside the bundle.

Outputs per OS:

| OS | Output |
|---|---|
| macOS | `dist/Pomodoro.app` (signed if `ELYSIUM_SIGNING_IDENTITY` is set) |
| Windows | `dist/Pomodoro/Pomodoro.exe` plus an installer `Pomodoro-Setup.exe` |
| Linux | `dist/Pomodoro.AppImage` plus tarball + `.deb` if `dpkg-deb` is on PATH |

For the full signing and notarization story, see
[Packaging](../guides/packaging.md).

## Test from the bundle

After packaging, double-click the produced `.app` / `.exe` /
`.AppImage`. The Pomodoro window opens with no Python interpreter
visible, no terminal, no console. Run a short focus session (drop
`DURATIONS_S["focus"]` to 5 seconds for testing) and confirm:

- The Toast appears in-app.
- The OS notification appears in the notification center.
- The window stays at the same position between launches (because
  the framework persists position by default for borderless windows).
- The settings popover state from chapter 3 still persists.

## What you built

- A **borderless rounded-rectangle window** with a hit-test path.
- A **three-mode StateMachine** with auto-cycling logic.
- A **radial progress ring** driven by reactive signals.
- A **Spring-bounced tap gesture**.
- A **Popover** with three Sliders and a Toggle bound to signals.
- **Persistent settings** via `elysium.platform.user_data_dir`.
- **In-app Toast + OS notification** on mode completion.
- A **signed standalone bundle** built with `elysium pack`.

You exercised StateMachine, Popover, Slider, Toggle, Toast,
`elysium.platform.notify`, and the packaging CLI. Plus everything
from Aurora Clock.

## Bonus: the photoreal Pomodoro reference app

The tutorial above builds the *abstract* Pomodoro UI. If you want to
see how the same idea scales up to a fully photoreal app — actual
tomato photo, clam-open animation, working countdown, audible ding —
look at `examples/pomodoro/main.py` in the framework repository.

It demonstrates two patterns this tutorial intentionally skipped:

1. **Component skins.** The green leaf-cluster button on top of the
   tomato lives in its own bundle, `examples/pomodoro/stem.esk`,
   declared with `"kind": "component"` in its manifest. The host
   loads it natively, compiles it to a DisplayList, and stamps it
   under a `push_transform` / `extend` / `pop_transform` sandwich
   each frame — Python owns the *position* (the cluster animates
   with the clam open/close), the `.esk` owns the *look*. Open
   `stem.esk` in the Designer to recolour leaves or reshape paths
   without touching Python. See [Skins → Skin kinds](../guides/skins.md#skin-kinds-application-vs-component)
   for the full pattern and the runtime guard.

2. **Pre-scaled retina PNGs.** The tomato top and bottom halves are
   rendered at 2× the logical window size (`816×918` for a `408×459`
   logical window) so Skia does a clean 1:1 device-pixel blit
   instead of a 2× upscale — which on macOS retina silently
   truncates the destination beyond ~70% of source height. The
   prep script at `scripts/prepare-pomodoro-assets.py` documents
   the workaround in detail.

## Where to next

- [Stylized Music Player](stylized-music-01-the-faceplate.md) takes
  borderless and animated authoring to its full extent.
- [Aurora Clock Pro tutorial](../tutorials/aurora-clock-pro.md)
  extends the chapter-5 clock into a multi-window app.
- [Auto-update guide](../guides/auto-update.md) wires a Sparkle
  feed so the packaged Pomodoro updates itself.

[Back to Getting Started](index.md)
