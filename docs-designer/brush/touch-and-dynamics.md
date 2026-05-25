# Touch and dynamics

The Designer reads pressure, tilt, rotation, velocity, altitude,
distance, and random input channels and routes each into per-
parameter dynamics curves. This page covers the input pipeline, the
default mappings, and how to customize them.

## Supported devices

| Device | Channels |
|---|---|
| Mouse | Velocity only |
| Trackpad | Pressure (Force Touch / Magic Trackpad 2+), Velocity |
| Apple Pencil (any gen) | Pressure, Tilt, Altitude, Velocity |
| Wacom (Intuos, Cintiq, MobileStudio) | Pressure, Tilt, Rotation, Velocity, Altitude |
| Surface Pen | Pressure, Tilt, Velocity |
| Huion | Pressure, Tilt (model-dependent), Velocity |
| XP-Pen | Pressure, Tilt (model-dependent), Velocity |
| Generic HID stylus | Pressure, Velocity |

The Designer auto-detects connected devices and lights up the
matching channels in the dynamics grid. Channels the active device
does not provide are grayed out.

## OS pipelines

| OS | Pipeline |
|---|---|
| macOS | NSEvent tablet event mask + Multi-Touch |
| Windows | WM_POINTER (Pointer Input Stack) with WM_TABLET fallback |
| Linux X11 | XInput2 |
| Linux Wayland | wp_tablet_v2 (where supported), libinput direct otherwise |

The Windows pipeline prefers WM_POINTER because it gives lower
latency and richer data than the legacy WinTab path. WinTab is used
only when WM_POINTER is unavailable.

## Default mappings

When a tablet is detected the Designer auto-binds the most common
channel-to-parameter pairs:

| Channel | Default target | Curve |
|---|---|---|
| Pressure | size_px | Ease-in (floor 0.1, linear to 1.0) |
| Pressure | opacity | Linear (0.0 to 1.0) |
| Tilt | angle_deg (Bristle, Pattern) | Linear (-45 to 45 deg) |
| Rotation | angle_deg (Bristle, Pattern) | Linear (-180 to 180 deg) |
| Velocity | spacing | Inverse (fast → wider spacing) |
| Altitude | hardness | Linear (low altitude → softer) |
| Distance | None by default | (unbound) |
| Random | None by default | (unbound) |

Override any of these in the [Brush Studio](brush-studio.md)
dynamics grid. New presets default to these mappings; existing
presets keep their saved mappings.

## Curve editor

Each channel-target binding has a small editor: x = channel value
(0 - 1), y = multiplier applied to the target parameter (0 - 1).
Click to add a point; drag to move; right-click a point to delete.

Curves must be monotonic on x (no folding back). Non-monotonic
shapes are auto-clamped to their monotonic envelope on save.

## Calibration

`Preferences > Tablet > Calibrate Pressure` opens a small dialog
where you draw three test strokes (soft, medium, hard). The
Designer measures the actual pressure range your hand produces and
remaps the channel so 0% and 100% match your typical light and
firm strokes. Calibration data is per-user and per-device.

## Multi-touch

Two-finger pan + pinch zoom is on by default on Mac trackpads,
Surface touchscreens, and Wacom touch-strip tablets. Configure in
`Preferences > Tablet > Multi-Touch`:

| Gesture | Default action |
|---|---|
| One-finger swipe (drawing area) | Brush stroke (acts like primary mouse) |
| Two-finger pan | Pan view |
| Two-finger pinch | Zoom view |
| Two-finger twist | Rotate view (Off by default; cause of accidents) |
| Three-finger tap | Undo |
| Four-finger tap | Switch menu set |

Disable any gesture per app by unchecking it in Preferences.

## Per-app smoothing

Stroke smoothing is the difference between "natural" and "polished"
output. The Designer's smoothing is a low-pass filter on the input
samples; values 0.0 to 1.0. Defaults:

| Engine | Default smoothing |
|---|---|
| Round Stamp | 0.30 |
| Airbrush | 0.45 |
| Bristle | 0.20 |
| Texture | 0.30 |
| Pattern | 0.10 (preserves stamp positions) |
| Wet Mix | 0.40 |

Override per preset in the Brush Studio.

## Diagnostics

`Help > Tablet Diagnostics…` opens a live readout window showing
all incoming events: position, pressure, tilt, rotation, altitude,
velocity, timestamp. Useful when:

- A new tablet is connected and you want to verify the driver
  provides the channels you expect.
- A specific channel is acting unstable; the readout exposes raw
  noise levels.
- You are filing a bug; the diagnostics window has a "Copy last 10
  seconds" button for attaching to a ticket.

## Per-OS quirks

- **macOS**: Apple Pencil tilt and rotation work natively on iPad-
  hosted screens (using Universal Control or Sidecar). Mac trackpad
  pressure is reported but lower resolution (a 0-3 integer); the
  Designer rescales to 0-1.
- **Windows**: Surface Pen rotation is supported only on Surface
  Pro 9+. Older models report 0 for rotation.
- **Linux**: Wayland devices require `libinput` 1.20+. Some
  compositors (older Sway) limit tablet events to the focused
  window only.
