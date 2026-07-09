# Maya → Elysium Migration Guide

This guide maps Maya 2027 concepts and hotkeys to their Elysium Designer
equivalents. Elysium Designer is **not** Maya: it's a borderless
3D-animated UI authoring tool: but it has been built so that a Maya
artist can drop in and feel at home immediately.

## Hotkeys

Every Maya tool-box hotkey works in Elysium with the same semantics.

| Maya hotkey | Maya action            | Elysium action            |
|-------------|------------------------|---------------------------|
| `Q`         | Select Tool            | Select Tool               |
| `Shift+Q`   | Lasso Select           | Lasso Select              |
| `W`         | Move Tool              | Move Tool                 |
| `E`         | Rotate Tool            | Rotate Tool               |
| `R`         | Scale Tool             | Scale Tool                |
| `B` (Maya) → `F12` (Elysium) | Soft Select toggle | Soft Select toggle. **Elysium rebinds this to F12** so hold-`B` can be used for the Brush Quick Wheel (Procreate-style radial brush picker). |
| `B` (hold)  | n/a                    | **Quick Wheel**: radial picker of your 8 favorite brushes, released-on-slice to switch. Only triggers while a brush tool (`Brush` or `Erase`) is active. |
| `Y`         | Last Tool (cycle)      | Last Tool (cycle)         |
| `T`         | Show / Hide Manipulator| Show / Hide Manipulator   |
| `F`         | Frame Selected         | Frame Selected            |
| `Home`      | Frame All              | Frame All                 |
| `4`         | Wireframe              | Wireframe view            |
| `5`         | Smooth Shaded          | Shaded view               |
| `6`         | Textured               | Textured view             |
| `7`         | Textured + Lit         | Lit view                  |
| `Alt+5`     | Wireframe on Shaded    | Wire-on-Shaded view       |
| `Alt+V`     | Play Forwards          | Play Forwards             |
| `S`         | Set Keyframe           | Set Keyframe (writes an AnimState at the playhead) |
| `Shift+S`   | Set Breakdown          | Set Breakdown             |
| `,`         | Step Back Key          | Step Back Key             |
| `.`         | Step Forward Key       | Step Forward Key          |
| `Alt+,`     | Step Back Frame        | Step Back Frame           |
| `Alt+.`     | Step Forward Frame     | Step Forward Frame        |

Maya marking menus (hold-and-drag radial menus) are reachable by
holding the corresponding tool hotkey for >180 ms. The wedges contain
the same options as Maya's defaults.

## Concept map

| Maya concept              | Elysium equivalent        | Notes |
|---------------------------|---------------------------|-------|
| Scene file (`.mb` / `.ma`)| `.esk` skin bundle        | Same role: a project file you New / Open / Save. |
| Transform node            | `Placement` dataclass     | Single record describing any element on canvas: Shape, Image, Mesh3D, NURBSCurve, Joint, HairStrand, etc. |
| Keyframe at frame N       | `AnimState` (named state) | Each placement has a list of states; the timeline scrubber tweens between them. |
| Outliner                  | Left-side accordion       | Same DAG view; toggles open/closed per section. |
| Channel Box               | Right-side panel          | Per-placement keyable attrs. |
| Attribute Editor          | Right-side panel          | Full dataclass-field editor. |
| Construction History DAG  | `Placement.history`       | Per-placement op log; visible in the Channel Box → History tab. |
| Mesh deformer node        | `Deformers` menu          | Bend / Twist / Sine non-destructively stack on the mesh and log to history. |
| Hypershade                | `Rendering ▸ Hypershade…` | Node-based material editor; 9 node kinds in v1 (File / Color / Ramp / Noise / Multiply / Add / Blend / Bump / Material). |
| Joint chain               | `Rigging ▸ Create Joint Chain` | `kind="Joint"` placements with `parent_name` defining the chain. Bone rest-lengths stored in `props["bone_length"]`. |
| Skin Bind                 | `Rigging ▸ Bind Skin to Selected Mesh` | Per-vertex top-2 inverse-distance weights stored in `props["skin_weights"]`. |
| 2-bone IK                 | `Rigging ▸ Solve 2-Bone IK on Selected Chain` | Analytical solver: drag the end joint, run the action, the mid joint repositions. |
| Constraints (Parent / Point / Orient / Aim / Scale) | `Rigging ▸ Constraints ▸ …` | Select constrained nodes + target (last picked), pick the constraint kind. Stored in `props["constraints"]`, applied per-frame after the AnimState tween. |
| nHair                     | `Simulation ▸ Create Hair Strand` | Verlet-integrated rope; anchor pinned to the placement's top-center, falls under gravity. |
| MASH Distribute           | `Procedural ▸ MASH ▸ Scatter…` | Duplicates the selected placement into a grid; jittered or aligned. |
| Render Settings           | `Rendering ▸ Render Quality ▸ …` | 4 presets (Draft / Preview / Production / Final) feed `samples` / `max_bounces` / `size` into the path tracer. |
| Batch Render              | `Rendering ▸ Batch Render ▸ …` | Renders a frame sequence at the active quality, writes PNG files to `<skin>/renders/<timestamp>/`. |
| Arnold (production renderer) | Elysium path tracer    | Same workflow: set quality, hit Render. `_render_final_selected` + `_batch_render` both call into `pbr.render_path_traced`. |

## Things Elysium has that Maya doesn't

These are not removals from Maya: they're additions Elysium gives you
on top. Don't expect them in Maya, and don't worry about losing them
when you migrate.

- **Borderless / shaped window primitive.** Every skin is a real
  NSWindow with an arbitrary path as its hit region. This is the entire
  point of Elysium.
- **`.esk` skin bundle.** A skin is a folder, not a binary file  
  contains the document, paired Python handlers, textures, and
  signature. Diff-able in `git`.
- **Code Link.** Double-click a placement's hook to jump to the
  paired Python handler. Maya has no analogue.
- **Hot reload.** The Designer can patch its own running code via
  `dev.reload_designer_module`: no restart, no scene loss.
- **AI Aether agent.** Aether is a headless agent — there is no
  menu item or window. It reads your scene, suggests changes, and
  calls any Designer tool (every menu action is exposed as an
  Aether tool), driven over the bridge API on `127.0.0.1:8183`.
  See [Aether](../aether/index.md). Maya has no analogue.
- **Magic Polish.** Single-shot AI pass that improves shading,
  lighting, and texture quality on the selected mesh.
- **Themes.** Light / Dark / OLED / Glass / Frost palettes; Customize
  to author your own and save as a user theme.

## Things to watch for

- **AnimState ≠ keyframe-per-attribute.** Maya stores one curve per
  attribute. Elysium stores one *named state* with `dx/dy/scale/opacity/
  rotation` per placement. Most workflows map cleanly, but if you need
  per-attribute curves the Graph Editor surfaces them visually.
- **Joints are 2D in v1.** Elysium's canvas is 2D; joint chains live
  in screen space. 3D meshes (Mesh3D) still render with full PBR, but
  joint-to-mesh skinning uses the 2D joint positions projected onto
  the mesh's XY frame.
- **Deformers stack via MESH_LIBRARY.** Each deformer registers a
  fresh mesh entry and re-points the placement at it. The original
  mesh is never modified: your `.3ds` / `.gltf` source files stay
  untouched.
