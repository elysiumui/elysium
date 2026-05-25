# Touch and pen input

Per-OS pipeline and per-device channel support.

## Per-OS pipeline

| OS | Pipeline |
|---|---|
| macOS | NSEvent tablet event mask + Multi-Touch |
| Windows | WM_POINTER (Pointer Input Stack), WM_TABLET fallback |
| Linux X11 | XInput2 |
| Linux Wayland | wp_tablet_v2 (where supported), libinput direct otherwise |

WM_POINTER is preferred on Windows for lower latency and richer
data than the legacy WinTab path. WinTab is used only when
WM_POINTER is unavailable.

## Per-device channels

| Device | Pressure | Tilt | Rotation | Velocity | Altitude |
|---|---|---|---|---|---|
| Mouse | ✗ | ✗ | ✗ | ✓ | ✗ |
| Trackpad (Force Touch) | ✓ | ✗ | ✗ | ✓ | ✗ |
| Apple Pencil 1 / 2 / 3 | ✓ | ✓ | ✗ | ✓ | ✓ |
| Apple Pencil Pro | ✓ | ✓ | ✓ | ✓ | ✓ |
| Wacom Intuos / Cintiq / MobileStudio | ✓ | ✓ | ✓ | ✓ | ✓ |
| Surface Pen (Pro 9+) | ✓ | ✓ | ✓ | ✓ | ✗ |
| Surface Pen (earlier) | ✓ | ✓ | ✗ | ✓ | ✗ |
| Huion (modern) | ✓ | ✓ | model | ✓ | ✗ |
| XP-Pen (modern) | ✓ | ✓ | model | ✓ | ✗ |
| Generic HID stylus | ✓ | ✗ | ✗ | ✓ | ✗ |

## Default channel mappings

When a stylus is detected, the Designer auto-binds:

| Channel | Default target |
|---|---|
| Pressure | size_px (with floor 0.1, ease-in curve) |
| Pressure | opacity (linear) |
| Tilt | angle_deg (Bristle, Pattern engines) |
| Rotation | angle_deg (Bristle, Pattern) |
| Velocity | spacing (inverse: fast → wider) |
| Altitude | hardness (low alt → softer) |

Override per brush in the [Brush Studio](../brush/brush-studio.md).

## Calibration

`Preferences > Tablet > Calibrate Pressure` runs a small wizard:
draw three test strokes (soft, medium, hard) and the Designer
remaps 0-100% to your hand's actual range.

Calibration data is per-user, per-device.

## Multi-touch gestures

Default bindings:

| Gesture | Action |
|---|---|
| Two-finger pan | Pan view |
| Two-finger pinch | Zoom view |
| Two-finger twist | Rotate view (off by default) |
| Three-finger tap | Undo |
| Four-finger tap | Switch menu set |

Configure in `Preferences > Tablet > Multi-Touch`.

## Diagnostics

`Help > Tablet Diagnostics…` opens a live event readout: position,
pressure, tilt, rotation, altitude, velocity, timestamp. Use to
verify channel coverage of a new tablet, or to attach to a bug
report (the window has a "Copy last 10 seconds" button).

## Limitations

- Wayland tablet events require `libinput` 1.20+.
- Older Sway compositors limit tablet events to the focused window
  only; the Designer warns at runtime.

## See also

- [Brush > Touch and dynamics](../brush/touch-and-dynamics.md)
- [Render and GPU troubleshooting](../troubleshooting/render-and-gpu.md)
