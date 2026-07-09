# Brush quick start

Three minutes from a fresh project to a confident first stroke.

## Activate the Brush

1. New project: `File > New Skin`, name "Brush Practice".
2. Drop a placement to paint on: `File > Import > Image` and pick any
   PNG, **or** drag a rectangle with the Rectangle tool (`M`) so
   there is a placement to paint on. The brush paints into the
   selected placement's mask layer.
3. Press `B` to activate Brush. The cursor changes to a circular
   nib showing the current size.

## Make a stroke

Drag across the canvas. With the default preset (Round Stamp,
20 px, full opacity, white), you should see a clean line follow the
cursor.

## Switch engines instantly

Hold `B` for ~0.4 seconds without releasing. The **Quick Wheel**
pops up around the cursor with six pie slices, one per engine.
Mouse to the slice you want and release.

| Slice (clockwise from 12) | Engine |
|---|---|
| Up | Round Stamp |
| Up-right | Airbrush |
| Down-right | Texture |
| Down | Pattern |
| Down-left | Bristle |
| Up-left | Wet Mix |

The Quick Wheel never blocks: keep dragging mid-stroke without it,
or hold `B` deliberately to invoke it.

## Common adjustments

The [Tool Properties dock](../interface/tool-properties-dock.md)
under the View Panel shows the brush's live options:

| Slider | Default | Hotkey |
|---|---|---|
| Size | 20 px | `[` smaller / `]` larger |
| Opacity | 1.0 | Shift+`[` / `]` |
| Hardness (Round Stamp only) | 0.8 | Ctrl+`[` / `]` |
| Spacing | 0.25 | (no hotkey, drag the slider) |
| Smoothing | 0.4 | (Properties dock) |

Hold Alt + click to **sample a color** from anywhere on the canvas;
the brush color updates. (The Eyedrop tool (`I`) is the full-power
version when you need swatch-tile or N×N samples.)

## Erase

Press `Shift+B` to swap to the Erase tool. Same controls as Brush,
just inverted: removes from the mask instead of adding to it.
`Shift+B` again toggles back.

## Pick a preset

The Quick Wheel switches **engine**. To switch the full **preset**
(engine + parameters + dynamics + texture), open
`Window > Brush Library`. Click any thumbnail to apply. Continue
painting with the new preset live.

The 30 built-in presets are grouped by family. The
[Library tour](library-tour.md) walks through them.

## The brush palette panel

The bottom of the toolbox column hosts a compact **brush palette**:
one strip of 12 generic slots. Each slot can hold a color, a texture,
or be empty.

```
Brush Palette
[active preview][Clear]
[■][▦][+][+]
[+][+][+][+]
[+][+][+][+]
```

The palette is **never** changed without your explicit confirmation.
Every click opens a menu. You always see what is going into each
square before it is saved.

### Click behavior

| Click | What happens |
|---|---|
| **Left-click** any slot | Opens the **Color menu** popover |
| **Right-click** any slot | Opens the **Texture menu** popover |

Both menus include:

- A way to pick a new value (color picker for the Color menu, tile
  picker for the Texture menu).
- **Apply to brush** when the slot already holds a value of that
  kind (uses the slot's content as the active brush).
- **Clear this square** when the slot holds anything (wipes the
  slot).
- **Cancel** (closes the menu without changes; Esc or outside-click
  also dismisses).

Nothing fills automatically. If you cancel a file dialog or close
the picker, the slot stays exactly as it was.

### Color menu

Left-click a slot to open it:

1. **Pick color…** opens the framework's color picker (wheel + hex
   + alpha). Confirming the picker writes the color to the slot
   **and** applies it as the active brush color.
2. **Apply to brush** (only when the slot already holds a color)
   sets the active brush color without re-opening the picker.
3. **Clear this square** wipes the slot.
4. **Cancel** closes the menu.

### Texture menu

Right-click a slot to open it. The headline action is **capture
from the canvas** the same gesture Maya's Artisan and Blender's
Texture Paint use for "I want this region as a brush stamp". The
menu is sectioned so the workflow is clear at a glance:

#### Primary actions (top of the menu)

1. **Capture from an Image placement…** switches to the Eyedrop
   tool with the slot armed. Drag a rectangle over an Image
   placement on the canvas; on release the slurped tile fills the
   slot AND becomes the active brush stamp. Press Esc to cancel.
2. **Import from file…** opens the OS file picker. If you confirm a
   file it is copied into the texture library, written to the slot,
   and applied. If you cancel, the slot is unchanged.

#### Saved tiles (secondary section)

When you have previously captured / imported / generated tiles, the
menu shows a labeled **"Saved tiles  ›  click to reuse"** grid of
thumbnails. Click any thumbnail to write that tile into the slot
and apply it. This section is hidden when there are no saved
tiles  the menu is never just a wall of unlabeled squares.

#### Footer actions

- **Apply to brush** (when the slot holds a texture).
- **Clear this square** (when the slot holds anything; tinted red).
- **Cancel** (or press Esc).

### Why this shape (no auto-fills)

The earlier design auto-filled an empty slot with the next unused
library entry if you cancelled a file dialog. That was wrong. Every
slot change now comes from an explicit user gesture. If a popover
is dismissed without a selection, the slot stays empty.

The single-strip model (no separate "colors strip" and "textures
strip") is closer to how Procreate, Krita, and Photoshop treat
swatches: a slot is a slot is a slot; what kind of value it holds
is a property of the slot, not a property of which row it lives in.

### Persistence

Palette slots persist between launches in your
[user preferences file](../reference/file-locations.md) under the
`brush_palette_slots` key. Slots from the previous dual-strip build
migrate automatically on first load.

If you want the full preset catalog (engine + dynamics + thumbnails
in addition to bare swatches), use `Window > Brush Library` instead.
The palette panel is for *fast access*; the Library is for *browse
and discover*.

## Save your tweaks as a preset

After dialing in a brush you like (engine + size + opacity +
dynamics), press `Save current as preset…` at the top of the Brush
Library panel. Name it; it appears in **My Presets**.

## Tablet and pen

If a tablet is connected the Designer auto-maps:

| Channel | Default mapping |
|---|---|
| Pressure | Size (0 → 0.1×, 1.0 → 1.0×) |
| Tilt | Rotation (Bristle, Pattern) |
| Velocity | Opacity attack |

The full mapping table is in [Touch and dynamics](touch-and-dynamics.md).

## What you painted into

The brush writes into the selected placement's mask layer (one mask
per placement). The mask is stored alongside the placement in the
`.esk` bundle's `textures/` folder when you export, so brushwork
travels with the skin.

## Next

- [Library tour](library-tour.md) for the 30 built-in presets.
- [Brush Studio](brush-studio.md) when you want to dial in dynamics
  curves or pick a custom texture.
- [Touch and dynamics](touch-and-dynamics.md) for tablet / pen.
