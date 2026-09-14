# Native transform animation curves

`props.keys3d` is an ascending list of unique integer frames in 0–360000. A key has a complete local transform, optional explicit `channels`, optional per-channel `interpolation` and optional per-channel `handles`. Missing channels retain the legacy complete-transform meaning; missing interpolation means Linear. Native authoring, Aether operations, preview, render jobs and scene export use this same document and evaluator.

## Interpolation and handle storage

Linear joins channel values directly. Constant holds the preceding key until the next key. Bezier applies a cubic to the outgoing segment of the key. Outside the channel's key range, evaluation holds its first/last value. Values use meters for location/pivot, degrees for Euler rotation and dimensionless factors for scale. Interpolation occurs before parenting.

A `handles` entry maps a keyed channel to `{"left": [dt, dv], "right": [dt, dv]}`. Offsets are relative to that key's frame/value, stored as entered finite numbers. Left time offsets must be nonpositive; right offsets nonnegative. Free handles are independent. Missing handles default to horizontal tangents with one third of the adjacent channel interval; the first/last unused side mirrors the available interval, and an isolated key uses one frame. These are explicit horizontal defaults, not a claim to implement all Blender automatic-handle modes.

The four segment controls are the first key, its outgoing handle, the next key's incoming handle and the next key. For evaluation only, a handle reaching past the other key is shortened horizontally to the segment duration, proportionally shortening its value offset to preserve slope. Stored offsets remain unchanged. This agrees with the bounded horizontal-reach behavior in [Blender's F-curve implementation](https://github.com/blender/blender/blob/main/source/blender/blenkernel/intern/fcurve.cc). The monotonic cubic time coordinate is inverted with 52 bisection steps; value is evaluated with De Casteljau interpolation using Python floating-point precision. Designer retains its precision rather than reproducing Blender's float storage/evaluation rounding.

Nonfinite controls and Bezier scale curves crossing the nonzero-scale domain are rejected before committing. Scale validation checks cubic extrema, not just integer-frame samples.

## Editing and persistence

Native Animation → Keys provides Values, Channels, Key list, Curve and Handles sections. Select an exact key, open Handles, enter offsets and use Set handles; this also enables Bezier on that outgoing segment. Curve displays the actual channel evaluator and selected free handles. The exact key list provides keyboard access when plot points overlap or handles lie outside the plot. The graph currently supports key picking and numeric handle editing; direct handle dragging, automatic/aligned/vector handle modes and named actions remain separate work.

`scene.key_handles_set` accepts an object ID, frame, channel and left/right pairs. Existing `scene.key_set`, `scene.key_edit` and `scene.keys_edit` accept `BEZIER` interpolation. `scene.keys_get` returns authored handles unchanged. Single/batch key moves and copies retain offsets with their source key; deletes remove only the chosen channel's handles. Editing a keyed value translates its relative handles with it. Native changes commit one Undo step; invalid drafts never partially mutate the document.

Saved authoring and portable scene exports retain the same keys and handles. Exported frame images evaluate the authored curve at each declared `source_frame`. The packaged player presents those exported images; curve evaluation is performed during export, so no external Blender runtime is required.
