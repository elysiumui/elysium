# Keyframes

A keyframe is one (frame, value) record on an animatable channel.
The Designer records keys, evaluates the curve between them, and
plays back during scrub or runtime.

## Set a key

| Path | Effect |
|---|---|
| `Animate > Set Key` | Key every keyable channel on the selection at the current frame |
| `S` | Same as the menu |
| Right-click a value in the [Channel Box](../interface/channel-box.md) > **Key** | Key only that channel |

A diamond appears on the time slider for each newly keyed channel.

## Set a breakdown

A breakdown is a "soft" key that nudges interpolation between two
neighboring keys without becoming a full pose stop.

| Path | Effect |
|---|---|
| `Animate > Set Breakdown` | Insert a breakdown at the current frame |
| `Shift+S` | Same |

Breakdowns appear as smaller green diamonds (vs the orange diamonds
of full keys).

## Auto Key

The red dot on the time slider, or `Animate > Toggle Auto Key`,
turns on automatic keying. Any value change at any frame writes a
key on that channel.

Useful for blocking; the cadence is fast (drag-to-key).

Turn off before polish so a stray nudge does not commit a new key
on top of carefully tuned ones.

## Delete a key

Select the diamond on the time slider (click; Shift-click extends
the selection); press Backspace.

To delete every key on a channel: right-click the field in the
Channel Box > **Delete All Keys**.

## Move a key

Drag the diamond horizontally on the time slider. Shift-drag
constrains to whole frames; Cmd+drag (macOS) or Ctrl+drag (other)
snaps to the nearest existing key.

To move multiple keys together: drag a box across them in the
time slider, then drag the resulting selection.

## Default tangent type

Newly-set keys use the tangent type set in `Preferences >
Animation > Default Tangent`. Options:

| Tangent | Behavior |
|---|---|
| Auto | Smooth tangent, auto-computed (most natural for animation) |
| Spline | Cardinal spline, sharper than Auto |
| Linear | Straight-line interpolation between keys |
| Stepped | Hold the value until the next key (constant) |
| Clamped | Auto, but flat near extremes |

Auto is the right default. Switch to Stepped during blocking to
preserve hard pose-to-pose timing; switch back to Auto for polish.

## Keying multiple channels

Multi-select placements and press `S`: the Designer keys every
keyable channel on every selected placement. Useful for keying a
whole rig's joints at once.

## What gets keyed

Only **keyable** channels (the filled-dot indicator in the
Channel Box). Non-keyable channels (path data, parent ids) cannot
be keyed; right-click and toggle keyable to opt them in.

## See also

- [Graph editor](graph-editor.md): edit the curves between keys.
- [Dope sheet](dope-sheet.md): edit timing across many channels.
- [Time slider](../interface/time-slider.md): the transport
  controls.
