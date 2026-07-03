# Render part mask

A render part mask isolates a sub-region of a Mesh3D (or a group of
placements) so subsequent operations affect only that region.
Useful for retouching one wing without disturbing the other, baking
texture data into just the body, or painting in masked-only mode.

## Two kinds of mask

| Kind | Stored on | Reach via |
|---|---|---|
| Vertex mask | Mesh3D placement | `Mesh > Render Part Mask > From Vertex Selection` |
| Placement mask | Placement group | `Mesh > Render Part Mask > From Selected Placements` |

Both live in the placement's metadata; both export with the `.esk`.

## Create a vertex mask

1. Select the Mesh3D placement.
2. Switch to **vertex mode** by entering the lasso (`Shift+Q`) or
   by pressing `V` to drop into vertex mode directly.
3. Lasso (or click) the vertices you want masked.
4. `Mesh > Render Part Mask > From Vertex Selection`.

The selected vertices are written to the placement's
`render_part_mask` channel. The View Panel shows the masked region
in a soft orange tint when the placement is selected.

## Use a vertex mask

Many menu actions honor the mask. The mask narrows their effect to
the selected vertices only. Examples:

- `Mesh > Transfer Texture > …`: bakes only inside the mask.
- `Animate > Set Key`: keys the selected vertex positions but
  leaves the rest of the mesh untouched.
- Brush / Erase: paint operations skip pixels outside the mask's
  projected UV region.
- Deformers: applied inside the mask only.

To clear: `Mesh > Render Part Mask > Clear`.

## Create a placement mask

When the granularity you want is whole placements (not vertices)
the workflow is simpler:

1. Select the placements you want masked (Shift-click or lasso).
2. `Mesh > Render Part Mask > From Selected Placements`.

The selection becomes a named "render set" (visible under the
[Sets tab in Project Explorer](../interface/project-explorer.md#sets-tab))
and operations that read the render-set filter respect it.

## Toggle visibility of masked vs unmasked

A small "Mask Visibility" dropdown in the View Panel's top toolbar:

- **All** (default): show everything; masked region tints orange.
- **Masked only**: hide unmasked geometry / placements.
- **Unmasked only**: hide the masked region.

The toggle is purely visual; it does not change the mask itself.

## Mask export

Export the mask as a PNG matte:

`File > Export > Render Part Mask as PNG`

This writes a black-and-white PNG with the masked region in white,
sized to your selected resolution. Useful for handing off to
external comp tools (Nuke, After Effects, Photoshop) or for
verifying coverage by eye.

## Multiple masks per placement

A placement holds one mask channel by default. Need more? Right-
click the placement in the Project Explorer > **Add Named Mask…**
and provide a name. The placement gains a second mask channel
selectable in the same View Panel toolbar.

Up to 8 named masks per placement. The
[`.esk` bundle format reference](../reference/esk-bundle-format.md)
documents how multiple masks serialize.

## See also

- [Lasso selection](lasso-selection.md): how to select the
  vertices in the first place.
- [Texture transfer pipelines](../rendering/texture-transfer-pipelines.md)
 : masked bakes.
