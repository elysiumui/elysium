# Properties pane

The Properties pane sits at the bottom of the right column. Where
the [Channel Box](channel-box.md) gives you the fast-edit numeric
surface, the Properties pane is the **full** property editor: every
field on the selected placement, grouped by category, with rich
editors per type.

![Properties pane expanded showing material, transform, mask, and animation sections for a Mesh3D selection](../assets/interface-properties-pane.png)

## Sections

The pane groups properties into collapsible sections. The exact
sections depend on the placement kind, but the common ones are:

| Section | Contents |
|---|---|
| Identity | id, name, kind, tags |
| Transform | translate, rotate, scale, pivot (also editable in Channel Box) |
| Geometry | kind-specific: vertices for curves, mesh_dist + UV layout for Mesh3D, image_path for Image |
| Material | albedo color, texture maps, roughness, metalness, IBL contribution |
| Mask | render_mask, locked, visibility |
| Animation | per-channel keyability, expressions, driver bindings |
| Code Link | paired Python handler file, scaffold status |
| Notes | free-form text; rendered into the bundle's `manifest.json` |

Click any section header to expand or collapse. State persists
between selections so you keep "Material" open while clicking
through placements.

## Field editors

The Properties pane uses richer editors than the Channel Box:

| Type | Editor |
|---|---|
| Color | Color picker (HSV / RGB / OKLCH) with eyedropper |
| Path | File chooser button + drop target |
| Enum | Dropdown |
| Bool | Toggle |
| Float / Int | Slider + numeric field |
| Vector2 / Vector3 / Vector4 | Field per component |
| Texture | Thumbnail + path + reimport button |
| Expression | Multi-line formula editor |

## Multi-select editing

When multiple placements are selected, fields shared across them
show as editable. Fields that differ between selected placements
show a "mixed" placeholder; setting a value applies it to all.

## Locked properties

Lock icons next to each field freeze the value. A locked field
ignores tool drags, signals, and animation keys. Useful for
"the reference image is at exactly these coordinates, do not let
me bump it": exactly the workflow used in chapter 3 of the Blue
Morpho tutorial.

## Search

A search field at the top of the pane filters visible properties by
name. Helpful when looking for a field you remember by name but not
by section ("uv_offset", "stroke_cap", etc.).

## Compared to the Channel Box

- Use the **Channel Box** for fast numeric tweaks and keyframing on
  transform-like properties.
- Use the **Properties pane** for everything else: colors, paths,
  enums, expressions, code-link wiring, notes.

Both edit the same underlying placement, so changes in either pane
update the other immediately.
