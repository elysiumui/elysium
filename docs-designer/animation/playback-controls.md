# Playback controls

The transport at the left of the [time slider](../interface/time-slider.md)
plus the Animate menu's playback entries control how the canvas
plays back animation during authoring.

## Buttons (left to right)

| Button | Hotkey | Action |
|---|---|---|
| Go to Start | Home | Jump to the first frame of the range |
| Step Back Key | , | Jump to the previous key on the selected channel |
| Step Back Frame | Left Arrow | Jump back one frame |
| Play / Pause | Space | Toggle playback |
| Step Forward Frame | Right Arrow | Jump forward one frame |
| Step Forward Key | . | Jump to next key on the selected channel |
| Go to End | End | Jump to the last frame of the range |

The Animate menu's `Go to Start`, `Step Backward Frame`,
`Step Forward Frame`, `Step Backward Key`, and `Step Forward Key`
entries are the same actions if you prefer not to use hotkeys.

## Playback rate

| Path | Default |
|---|---|
| Time slider's rate dropdown | 24 fps |
| `Animate > Playback > Set Rate…` | Same |

Options: 12 / 24 / 30 / 48 / 60 fps, or **Realtime** which honors
wall-clock and skips frames if the GPU cannot keep up.

For tight key-stepping work, **Realtime** is unhelpful because
the GPU may drop frames that affect your visual read; switch to
24 or 30 fps for predictable scrubbing.

## Loop mode

`Animate > Playback > Loop Mode`:

| Mode | Behavior |
|---|---|
| Once | Stop at the end of the range |
| Loop | Wrap to the start at the end |
| Ping-pong | Reverse direction at each end |

Loop mode applies to the canvas's preview only; runtime playback
in the framework uses its own per-`Tween` loop modes.

## Playback range vs project range

Two ranges:

- **Playback range**: the sub-range you scrub within. Edit on the
  time slider via the small bracket handles.
- **Project range**: the full timeline. Edit in `Animate >
  Playback > Project Range…`.

Playback range is for "audition this section"; project range is
"this is the actual length of the animation".

## Onion skinning

`Animate > Onion Skin > Show` paints the previous and next frames
in faded overlays. Configure how many frames are shown and their
opacities in the dialog.

Useful for animating cycles: you can see the in-between poses
relative to the previous and next ones, making spacing
adjustments much easier.

## Scrub modes

The time slider supports two scrub modes:

- **Live**: every drag updates the canvas. Default.
- **Quick**: only snaps on release. Fast on heavy scenes.

Toggle in `Animate > Playback > Scrub Mode`.

## Audio scrubbing

If the project has an audio track (added via `File > Import >
Audio`), scrubbing plays the audio synced to the cursor. Useful
for lip-sync or musical timing work.

Toggle in `Animate > Playback > Scrub Audio`.

## See also

- [Time slider](../interface/time-slider.md): the transport's
  home.
- [Keyframes](keyframes.md): what step-by-key navigates between.
- [Run > Preview Skin](../hot-reload/preview-skin.md): the
  separate borderless preview window.
