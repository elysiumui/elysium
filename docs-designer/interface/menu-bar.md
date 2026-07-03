# Menu bar

The menu bar sits at the very top of the window and hosts every
discoverable command in the Designer. Its content shifts with the
active [menu set](index.md#the-five-menu-sets).

## Always-visible menus

These nine top-level menus appear in every set:

| Menu | Purpose |
|---|---|
| File | New, Open, Save, Import, Export, .esk Bundle, AI workflows |
| Edit | Undo, Redo, Duplicate, Delete, Parent, Group |
| Window | Set Shape (Rect / Ellipse / From Selection), toggles for Transparency and Title Bar |
| Arrange | Align (six directions), Bring Forward / Send Backward |
| Path | Boolean combine: Union, Intersect, Subtract, Exclude |
| View | Zoom, Frame All / Selected, Grid, HUD, render mode (Wireframe / Shaded / Textured / Lit / Wire-on-Shaded) |
| Theme | Light, Dark, OLED, Glass, Frost, Customize, Save User Theme |
| Run | Preview Skin, Hot Reload |
| Code | Open paired Python handler, Scaffold missing handlers, Pair / Reveal |

## Modeling-set additions

| Menu | Purpose |
|---|---|
| Mesh | Inspect, render-part mask, Transfer Texture (8 transfer algorithms + 2 starred recommended pipelines), Landmarks (Save / Load / Clear) |
| Surfaces | NURBS, Loft to Mesh |

## Animation-set additions

| Menu | Purpose |
|---|---|
| Animate | Set Key, Set Breakdown, Toggle Auto Key, Graph Editor, Dope Sheet, Trax, Time Editor, Motion Paths, frame / key step |

## Rigging-set additions

| Menu | Purpose |
|---|---|
| Rigging | Create Joint Chain (3 / 5), Bind Skin, IK 2-bone solver, Paint Weights, Constraints (Parent / Point / Orient / Aim / Scale) |

## FX-set additions

| Menu | Purpose |
|---|---|
| Simulation | Hair (short / long), nCloth (small / large), Bullet rigidbody (default / bouncy) |
| Procedural | MASH-style scatter |

## Rendering-set additions

| Menu | Purpose |
|---|---|
| Rendering | Light (Directional / Point / Spot), Render Quality (Draft / Preview / Production / Final), Render Selected, Color Space (sRGB / Linear / ACEScg / Rec.709), AOV (Beauty / Diffuse / Specular / Normal / Depth) |
| Hypershade | Material editor |

## Reading the menu reference

Each menu entry maps to an action ID like `mesh.transfer_polar_normal`.
The [Aether tool reference](../reference/aether-tool-reference.md)
documents every action ID and what it does, both for human reference
and for the in-app agent.

## Tear-off menus

Hold Shift and click a menu's top label to **tear it off** into a
floating panel. Tear-offs persist across menu-set switches, so you
can keep, for example, the Mesh > Transfer Texture submenu open
while you experiment.

Close a tear-off by clicking its X, or `Window > Close All Tear-offs`.

## Recent commands

`Edit > Recent Commands` shows the last 20 actions you ran. Useful
for re-running a transfer-texture preset or a deformer chain without
hunting through deep submenus again.

## Customize the menu bar

`File > Preferences > Menu Bar` lets you hide menu entries you never
use, add separators, and reorder top-level menus. Customizations
save into your preferences and follow your account.
