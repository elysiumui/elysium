# Dope sheet

The Dope Sheet shows every keyframe across every channel as a
single grid. Each row is one channel; each column is one frame.
The view is purpose-built for changing **timing** without
disturbing curve shape.

## Open

`Animate > Dope Sheet` opens the panel. It is a separate surface
from the Graph Editor (and complementary): use the Dope Sheet for
"when does this happen", use the Graph Editor for "how does this
look between keys".

## Layout

- **Channel list (left)**: same channel selector as Graph Editor.
- **Grid (right)**: each row is a channel, each column a frame.
  Keys are dots; breakdowns are small marks; gaps are silence.
- **Toolbar (top)**: time scale, snap, frame number visibility.

## Move keys around

- Click a key to select; Shift-click to extend.
- Drag selected keys horizontally to shift them in time.
- Drag-box to grab every key inside a rectangle.

Holding Shift during a drag constrains to whole-frame steps;
holding Ctrl snaps to the nearest existing key on any channel.

## Scale time

Select multiple keys, then drag the **scale handle** at either end
of the selection (a small triangle marker). The selection
compresses or expands proportionally:

- Drag the right handle right: stretches the selection longer.
- Drag the left handle left: stretches earlier in time.

Use this to slow down or speed up an animation without re-keying.

## Hold keys

To extend a key as a "hold" without adding another:

1. Right-click the key > **Convert to Held**.
2. The key turns into a flat segment until the next key.

Equivalent to setting the out-tangent to Flat / Stepped, but
faster to author when many channels share a hold.

## Mute / Solo

The channel list's two icons per row:

- **Mute**: ignore this channel during scrub / playback. Useful
  for auditioning.
- **Solo**: hide every other channel from playback. Useful for
  isolating a sub-rig (only the wings, not the body).

Multiple channels can be soloed at once.

## Filters

- **Show empty channels**: include channels with zero keys (off by
  default).
- **Show child placements**: flatten the rig hierarchy so all
  joint channels appear at the same indent level.

## Snap to step

For block-in passes the Dope Sheet supports stepping at fixed
intervals (every 2 frames, every 4 frames, every 8 frames). The
toolbar's **Snap to step** dropdown enforces that all moved keys
land on the chosen step.

## See also

- [Keyframes](keyframes.md): adding and removing keys.
- [Graph editor](graph-editor.md): curve shape and tangents.
- [Trax and Time Editor](trax-and-time-editor.md): clip-level
  layout instead of key-level.
