# Particle confetti celebration

Time: 30 minutes. Difficulty: Intermediate.

A one-shot confetti burst skin. Triggered by a `fire.click` hook;
200 colored rectangles fly across the canvas with gravity. Ships
as a ready-to-fire effect for any "thanks for signing up" or
"order placed" moment.

## Prerequisites

- Designer installed.
- Familiarity with [MASH scatter](../procedural/mash-scatter.md).

## Author the source particle

1. `File > New Skin`, 640 x 480.
2. Drop a small rectangle (`M`) at (320, 240), width 8, height 4,
   fill `#ec4899ff` (pink). Name it `confetti_source`.

## Scatter

1. `Procedural > MASH > Create Scatter…`.
2. Source: `confetti_source`.
3. Count: 200.
4. Generator: Random.
5. Region: full canvas + 200 px overshoot.
6. Click Create.

200 pink rectangles appear at random positions.

## Variation

In the MASH set's Properties pane > **Variation**:

- Rotation jitter: 180 degrees.
- Scale jitter: 0.3 (each piece ±30%).
- Color jitter: HSV deltas (`H: 60`, `S: 0`, `V: 0`) so colors
  span hot pink to gold.

Now the scatter reads as confetti, not "200 identical rectangles".

## Animate the burst

The confetti should fall with gravity and slight horizontal drift.

1. F4 (Animation set).
2. With the MASH set selected, in the Properties pane >
   **Variation > Per-instance time offset**: enable. Each
   instance's animation samples at a seeded offset so they spread.
3. Animate each instance's `translateY` from initial to +600 over
   60 frames with linear easing.
4. Animate `rotateZ` from 0 to 360 per second with random offset.

`Animate > Toggle Auto Key`, drag a keyframe at frame 1 and frame
60, the framework records.

## Burst trigger

`Animate > Playback > Loop Mode = Once`. The animation plays
exactly once on triggered start.

The Designer exposes a `fire.click` hook that resets and plays the
animation:

```python
@window.on("fire.click")
def fire(event):
    window.skin.animations["confetti"].restart()
```

## Test

`Run > Preview Skin`. Click anywhere; the confetti bursts. After
~1 second, all pieces have fallen off the canvas.

## Export

`File > Export > .esk Bundle`. Ship the bundle; layer it on top
of any window with `level=3` for a celebration overlay.

## What you exercised

- MASH scatter with Random generator.
- Per-instance variation (rotation / scale / color).
- Per-instance time offset.
- Animation with `loop: once` for one-shot triggers.

## See also

- [MASH scatter](../procedural/mash-scatter.md)
- [Animation index](../animation/index.md)
