# Step 8. Animate the wings and ship the skin

Time: 8 minutes.

## What we are adding

The static bake from chapter 5 (or 6) looks great, but the butterfly
that ships as the Elysium logo flies. In this chapter we give the
wings a gentle flap, shape the window to the butterfly's silhouette,
preview the skin live, and export the final `.esk`.

## Turn on Auto Key

Auto Key records keyframes automatically whenever you change a
property on the timeline. Choose `Animate > Toggle Auto Key`. A small
red dot appears on the Time Slider to confirm Auto Key is on.

Set the timeline range to 24 frames by editing the **End** field on
the right edge of the Time Slider. At the default 24 fps this gives
us a one-second loop, which is the cadence the Framework's Butterfly
Banner tutorial expects.

## Keyframe the wing flap

We will set three poses: a neutral spread, a downstroke, and the
return to neutral.

Select the `butterfly` Mesh3D placement. In the Channel Box, find the
two child transforms named `left_wing` and `right_wing` (the `.3ds`
file's hierarchy gives us these for free).

### Frame 1: neutral

- Move the Time Slider to frame 1.
- Set `left_wing.rotateZ` to `0` and `right_wing.rotateZ` to `0`.

Auto Key records a keyframe on each channel. A small diamond appears
on the Time Slider track for each one.

### Frame 12: downstroke

- Scrub to frame 12.
- Set `left_wing.rotateZ` to `-30` (tip down 30 degrees).
- Set `right_wing.rotateZ` to `30` (mirror).

The model in the canvas folds its wings down. New diamonds appear at
frame 12.

### Frame 24: back to neutral

- Scrub to frame 24.
- Set both rotateZ values back to `0`.

Press the Play button in the playback controls (or press `Space`).
The wings flap once per second. Press `Space` again to stop.

## Clean up the curves

Press `G` or choose `Animate > Graph Editor`. The Graph Editor opens
showing two yellow curves (one per wing). The default tangents are
spline, which gives a slightly mechanical feel.

Select all four keys on each curve (drag a box across them) and click
the **Auto Tangent** button in the Graph Editor toolbar. The curves
soften into a smoother sine-like shape and the wings start to feel
alive.

Close the Graph Editor. Play once more to confirm. If the flap looks
twitchy, reopen the Graph Editor and nudge the middle key's tangent
handles symmetrically.

## Shape the window to the butterfly

The skin will run in a borderless transparent window in the
Framework. We want the window's hit region to match the butterfly's
outline, not a bounding rectangle.

With the `butterfly` placement selected, choose
`Window > Set Shape > From Selection`. The Designer:

1. Computes the model's silhouette by projecting the visible mesh
   into screen space.
2. Writes the resulting SVG path into the `manifest.json`'s
   `window.shape.path_d` field.
3. Records `window.shape.kind = "path"` so the Framework knows to
   honor it.

The canvas updates with a faint dashed outline showing the new hit
region.

## Preview the skin live

Choose `Run > Preview Skin`. The Designer launches a separate
borderless transparent window that loads the current `.esk` exactly
the way the Framework will. The wings flap; the window is
butterfly-shaped; drag it around your desktop by clicking anywhere on
the wings or body.

The preview window also reloads automatically if you keep editing in
the Designer. Try nudging a keyframe in the Graph Editor with the
preview open: the flap timing updates within a second.

When you are satisfied, close the preview window.

## Final export

Choose `File > Export > .esk Bundle` one more time. The Designer
overwrites the bundle with the animation data and the new shape:

```
butterfly.esk/
  manifest.json         (now records the path-shape window + 24-frame timeline)
  document.json         (now includes the wing rotation animation track)
  textures/
    butterfly_albedo.png
    butterfly_normal.png
```

The status bar confirms with "Exported butterfly.esk".

## You shipped a skin

This `.esk` is a complete Elysium skin. It contains:

- A 3D model with PBR textures (chapters 2 and 5).
- A hand-tuned animation (this chapter).
- A non-rectangular window shape (this chapter).
- Everything the Framework needs to render and animate it in a real
  Python app.

## Next: take it into the Framework

The [Framework's Butterfly Banner tutorial](https://docs.elysiumui.com/getting-started/butterfly-banner-01-load-the-skin/)
picks up exactly where this leaves off. In three chapters it walks
through:

1. Loading this `.esk` in a borderless transparent window.
2. Sequencing a descent from the top of the screen with a
   cubic-bezier easing.
3. Unfurling the Elysium wordmark behind the butterfly and exporting
   the result as the official logo gif and mp4.

The two tutorials together form the official end-to-end story for
authoring an Elysium skin and shipping it as a runtime app.

## Checkpoint

You should have:

- A 24-frame wing flap that plays cleanly in the canvas.
- A butterfly-shaped window outline visible in the canvas.
- A `butterfly.esk` on disk containing model, textures, animation,
  and shape data.
- (Optional) A preview window that ran the skin live.

Congratulations. You are done with the Blue Morpho to Monarch
tutorial.

[Back to the tutorial index](index.md) · [Continue into the Framework >>](https://docs.elysiumui.com/getting-started/butterfly-banner-01-load-the-skin/)
