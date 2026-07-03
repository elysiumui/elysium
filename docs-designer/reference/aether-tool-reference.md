# Aether tool reference

Complete auto-generated catalog of every Aether-callable tool.
The Designer ships with **123 tools across 15 modules**.

The catalog is regenerated from shipping code on every doc build
via `scripts/gen_aether_tool_reference.py`, so this page never
drifts.

## What you see below

Each module has a table listing:

- **Tool**: id used by the agent and by scripting.
- **Side effect**: yes / no (read-only tools never modify state).
- **Undoable**: whether undo restores the prior state.
- **One-line purpose**: short docstring summary.

## The two starred mesh pipelines

These three tools power the [Blue Morpho tutorial's](../getting-started/butterfly/index.md)
texture transfer workflow:

- `mesh.transfer_polar_normal`: Polar warp + bake + normal map.
- `mesh.bbox_then_landmark_gaps`: BBox-warp + landmark gaps + bake
  + normal map.
- `mesh.landmark_apply_full`: TPS + per-region weighting in one
  shot.

See [Texture transfer pipelines](../rendering/texture-transfer-pipelines.md)
for the full math.

## Catalog

{!reference/aether-tool-reference.partial.md!}

## Calling tools

From inside Aether the agent calls these by name. To call one
directly from Python or from a custom Aether tool:

```python
from elysium.aether import call_tool
result = call_tool("mesh.transfer_polar_normal", {
    "mesh_id": "butterfly",
    "image_id": "BlueMorphoSrc",
})
```

## See also

- [Aether](../aether/index.md)
- [Aether > Tool reference](../aether/tool-reference.md): same
  content reached from the Aether section.
- Framework: [aether-tools.partial.md](https://docs.elysiumui.com/api/aether-tools.partial.md)
