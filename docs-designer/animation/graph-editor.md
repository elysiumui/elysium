# Graph editor

The Graph Editor is the curve-level view of every animated channel.
Where keyframes are dots and breakdowns are little marks, here you
see the actual continuous functions and their tangent handles.

## Open

`Animate > Graph Editor` (or `G`). The Graph Editor opens as a
dockable panel; drag its title bar to dock to any edge.

## Layout

| Region | Purpose |
|---|---|
| Channel list (left) | Per-placement, per-channel selector with show/hide checkboxes |
| Curve view (right) | The actual interpolation curves |
| Toolbar (top) | Tangent type picker, snap toggles, framing |

By default the Graph Editor shows curves for whatever is selected.
Click any channel in the list to focus its curve in the view.

## Tangent types

Each key carries an **in-tangent** and an **out-tangent**. Common
options (with toolbar buttons):

| Type | Effect |
|---|---|
| Auto | Smoothed; the framework picks the slope |
| Spline | Cardinal spline; sharper |
| Linear | Straight slope, derived from neighbor positions |
| Stepped | Discontinuous; hold value until next key |
| Flat | Slope = 0; useful at the start/end of a hold |
| Free | User-controlled both directions independently |

Select keys (drag-box across them) and click a toolbar button to
apply.

## Manual tangent editing

Click any key to expose its tangent handles (two lines extending
out). Drag the handle endpoints to change slope. Shift-drag
constrains to horizontal (changes weight only); Alt-drag breaks
the symmetry between in- and out-tangents.

Most animators reach for the **Auto Tangent** button after
recording rough keys; it smooths the curve into a natural arc.

## Snap

Toolbar toggles:

- **Snap to integer frame**: keeps keys on whole frames during
  drag.
- **Snap to integer value**: useful for transform.scale or counter
  channels.

## Frame all / frame selected

`F` frames the visible curves to fit the view. `A` frames all
curves on every channel. Useful when zoomed in.

## Curve color

Each channel paints a distinctive color. Translate X is red,
translate Y is green, translate Z is blue (XYZ = RGB by
convention). Other channels are assigned colors automatically.

## Per-curve operations

Right-click a curve for:

- **Bake to Linear**: convert the curve to a series of per-frame
  Linear keys (destructive; useful for export to engines that do
  not understand Bezier tangents).
- **Simplify**: reduce key count by approximating; tolerance
  configurable.
- **Reverse**: flip the curve in time.
- **Scale Time** / **Scale Value**: numeric transforms.
- **Mirror Around Frame** / **Mirror Around Value**: useful for
  symmetric loops.

## Channel filters

The channel list's filter bar at the top:

- **Selected only** (default): show curves for the selected
  placements.
- **Visible only**: hide curves whose channel has the eye toggled
  off.
- **Animated only**: hide channels with no keys.

For very deep rigs, combine "Animated only" + "Selected only" to
focus on what is actually moving.

## See also

- [Keyframes](keyframes.md): set the keys that build these
  curves.
- [Dope sheet](dope-sheet.md): when you care about timing more
  than curve shape.
