# From Blender

Concept and hotkey mapping from Blender to Elysium Designer.

Blender is a full-featured DCC: polygon modeling, sculpting, UV
unwrapping, rendering, video editing. Elysium Designer is a much
narrower tool: it authors `.esk` skins, not films or 3D assets. The
overlap is in modeling primitives, brush systems, and animation.

## Use Blender for; use the Designer for

| Use Blender for | Use the Designer for |
|---|---|
| Polygon modeling, retopo, UV unwrap | Authoring skins consumed by Elysium |
| Sculpting (multires) | Per-skin texture painting |
| Cycles / EEVEE rendering | PBR previews for skins |
| Compositor / video editor | (no equivalent) |

For the usual workflow: model in Blender → export `.gltf` or
`.3ds` → import into the Designer → texture / animate / package.

## Hotkey map (selected)

Blender's selection-first hotkey model is similar to the
Designer's. Most letters land in the same place.

| Blender | Action | Designer |
|---|---|---|
| `Tab` | Object / Edit mode toggle | `V` (vertex mode on Mesh3D) |
| `G` | Grab (move) | `W` (Move) |
| `R` | Rotate | `E` |
| `S` | Scale | `R` |
| `Numpad .` | Frame selected | `F` |
| `Numpad ,` | Frame all | `A` |
| `Numpad 1 / 3 / 7` | Front / Side / Top view | Orbit gizmo (top-right) |
| `Alt + middle drag` | Orbit | `Alt + middle drag` (same) |
| `Z` | Toggle wireframe | `4` (wireframe mode) |
| `Shift+A` | Add menu | Toolbox shape tools (`M`, `F`, `Shift+M`) |
| `X` / `Delete` | Delete | `Delete` |
| `Cmd/Ctrl + Z` | Undo | `Cmd/Ctrl + Z` (same) |
| `B` | Box select | `Q` (Select) with drag |
| `Ctrl + Tab` | Mode pie menu | F2-F6 (menu sets) |

## Concept map

| Blender concept | Designer equivalent |
|---|---|
| Object | Placement |
| Mesh | Mesh3D placement |
| Empty | Group placement |
| Camera | Camera placement |
| Light | Light placement |
| Material | Material (Hypershade) |
| Texture image | Image placement / texture map on a material |
| Modifier stack | [Deformer stack](../deformers/index.md) |
| Armature / Bones | [Joint chain](../rigging/joint-chains.md) |
| Vertex group | Render part mask |
| Shape keys | Blend shapes (rig.shape_editor) |
| Action | Animation clip (Trax) |
| NLA Editor | Trax + Time Editor |
| Driver | Constraint with expression |
| Geometry Nodes | (no v1 equivalent) |
| Compositor | (no v1 equivalent) |

## Import workflow

`File > Import > glTF / OBJ…` (Blender exports both natively).
Blender's UV unwrapping carries through; Designer reads UVs but
does not re-author them.

For `.fbx` import, install the optional `blender2fbx` companion
extension or re-export from Blender as `.gltf`.

## Brush workflow

Blender's texture-painting and sculpting brushes are conceptually
similar to the Designer's [brush system](../brush/index.md). The
six Designer engines (round_stamp, airbrush, bristle, texture,
pattern, wet_mix) cover the most common Blender brush kinds.

Blender's `.abr` import is third-party; the Designer reads `.abr`
and `.sut` natively.

## Coordinate system

Both apps use a right-handed coordinate system with Z up by
default. Models exported from Blender import without axis
remapping.

## When Blender still wins

- Anything beyond UI skin authoring: feature animation, VFX,
  cinematic rendering, modeling complex meshes, sculpting,
  retopo.
- Geometry Nodes / procedural modeling.
- Compositor / video editing.

## See also

- [From Maya](from-maya.md): sister DCC migration.
- [Importing 3D models](../importing/3d-models.md): the bridge
  for both.
