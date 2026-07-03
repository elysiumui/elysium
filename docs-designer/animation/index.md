# Animation

The Designer's animation system records keyframes on placement
channels and plays them back at runtime via the framework's
`AnimationClock`. This section covers the authoring surfaces.

## Six surfaces, one model

Animation in the Designer happens across six panels:

| Surface | Role |
|---|---|
| [Time slider](../interface/time-slider.md) | Scrub frames, transport controls |
| [Keyframes](keyframes.md) | Set / edit / delete keys |
| [Graph Editor](graph-editor.md) | Edit per-channel curves and tangents |
| [Dope Sheet](dope-sheet.md) | Edit timing in a roll-up view |
| [Trax + Time Editor](trax-and-time-editor.md) | Clip-level layout |
| [Motion paths](motion-paths.md) | Visualize and edit translate keys in canvas |
| [Playback controls](playback-controls.md) | Speed, loop, range |

Underneath, every animatable channel is a **curve**: an ordered
list of (frame, value, tangent_in, tangent_out) records.

## What is animatable

Most placement channels are animatable: translate, rotate, scale,
opacity, fill, stroke, every numeric Properties pane field, every
brush parameter (size, opacity, etc), every deformer parameter,
every constraint weight. The Channel Box's small dot to the left of
each row marks keyable channels.

Non-animatable: paths (vertex lists), shader programs, file
references.

## Workflow

The conventional flow is:

1. **Block in**: rough key poses at sparse frames (block-in).
2. **Spacing**: refine the timing in the dope sheet.
3. **Polish**: refine the curves in the graph editor.

This top-down approach matches Maya / Blender conventions and
keeps you out of the curve weeds until the timing reads.

## Auto Key

`Animate > Toggle Auto Key` (red dot on the time slider) records a
key whenever you change a value. Convenient for blocking; turn off
for polish so a stray nudge does not commit.

## Animation playback at runtime

When you export the `.esk` bundle, every keyed channel becomes
part of `document.json`. The framework's runtime reads these tracks
into `Tween`s registered with an `AnimationClock`, then plays them
at the rate you set in `playback-controls`.

The Aurora Clock and Butterfly Banner tutorials show the runtime
side: signals + effects + Tweens are the framework primitives that
the Designer's authored tracks ride on.

## Layered animation

The Designer supports layered animation: stack multiple tracks per
channel with blend weights. Useful for procedural overlays (a
flap-base loop + a hand-keyed acceleration on top), or for non-
destructive iteration ("save the v3 timing as a layer, audition
v4 on top, blend").

Manage layers in the Properties pane's **Animation** section.

## See also

- Each panel's dedicated page (linked above).
- [Animate menu](../interface/menu-bar.md#animation-set-additions)
 : quick reference for the top-level menu's contents.
