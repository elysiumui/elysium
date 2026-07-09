# Menu reference

Every Designer menu entry with its action id. Use the action id to
bind shortcuts, drive Aether tool calls, or script the Designer
externally.

## File

| Label | Action id |
|---|---|
| New Skin | `file.new` |
| Open Skin… | `file.open` |
| Save | `file.save` |
| Save As… | `file.save_as` |
| Extract Texture from Image… | `texture.extract` |
| Apply Texture from Library… | `texture.apply` |
| AI Enhance Selection (×4) | `texture.enhance` |
| ✨ Magic Polish (AI)… | `ai.panel` |
| ✨ Magic Polish (one-shot) | `ai.magic_polish` |
| Generate Skin from prompt… | `ai.generate_skin` |
| Import 3D Model… | `import.mesh3d` |
| Import > SVG… | `import.svg` |
| Import > Figma URL… | `import.figma` |
| Import > Lottie… | `import.lottie` |
| Import > glTF / OBJ… | `import.gltf` |
| Import > Canva… | `import.canva` |
| Export > SVG… | `export.svg` |
| Export > PNG… | `export.png` |
| Export > .esk Bundle | `export.esk` |
| Close Window | `file.close` |

## Edit

| Label | Action id |
|---|---|
| Undo | `edit.undo` |
| Redo | `edit.redo` |
| Duplicate | `edit.duplicate` |
| Delete | `edit.delete` |
| Select All | `edit.select_all` |
| Deselect | `edit.deselect` |
| Parent | `edit.parent` |
| Unparent | `edit.unparent` |
| Group Selected… | `edit.group` |

## Window

| Label | Action id |
|---|---|
| Set Shape: Rectangle | `window.shape_rect` |
| Set Shape: Ellipse | `window.shape_ellipse` |
| Set Shape From Selection | `window.shape_from_selection` |
| Toggle Transparency | `window.transparent` |
| Toggle Title Bar | `window.titlebar` |

## Arrange

| Label | Action id |
|---|---|
| Align Left / Center / Right | `arrange.align_left` / `_center` / `_right` |
| Align Top / Middle / Bottom | `arrange.align_top` / `_middle` / `_bottom` |
| Bring Forward / Send Backward | `arrange.forward` / `.backward` |

## Path

| Label | Action id |
|---|---|
| Combine > Union / Intersect / Subtract / Exclude | `path.union` / `.intersect` / `.subtract` / `.exclude` |

## View

| Label | Action id |
|---|---|
| Zoom In / Out / Reset | `view.zoom_in` / `.zoom_out` / `.zoom_reset` |
| Frame Selected / All | `view.frame_selected` / `.frame_all` |
| Toggle Grid / Snap / HUD | `view.grid` / `.snap` / `.hud` |
| Wireframe / Smooth / Textured / Lit / Wire-on-Shaded | `view.mode_wireframe` / `.mode_shaded` / `.mode_textured` / `.mode_lit` / `.mode_wire_on_shaded` |

## Theme

| Label | Action id |
|---|---|
| Light / Dark / OLED / Glass / Frost | `theme.0` / `.1` / `.2` / `.3` / `.4` |
| Customize… | `theme.customize` |
| Save Current as User Theme… | `theme.save_user` |
| Manage User Themes… | `theme.manage_user` |

## Animate

| Label | Action id |
|---|---|
| Set Key / Breakdown / Toggle Auto Key | `animate.set_key` / `.set_breakdown` / `.auto_key` |
| Graph Editor / Dope Sheet / Trax / Time Editor / Motion Paths | `animate.graph_editor` / `.dope_sheet` / `.trax` / `.time_editor` / `.motion_paths` |
| Go to Start / End | `animate.go_start` / `.go_end` |
| Step Backward / Forward Frame | `animate.step_back_frame` / `.step_fwd_frame` |
| Step Backward / Forward Key | `animate.step_back_key` / `.step_fwd_key` |

## Run

| Label | Action id |
|---|---|
| Preview Skin | `run.preview` |
| Hot Reload | `run.hot_reload` |

## Code

| Label | Action id |
|---|---|
| Open handler for selection | `code.goto` |
| Scaffold missing handlers | `code.scaffold_all` |
| Pair Python file… | `code.pair` |
| Reveal paired file | `code.reveal` |

## Rigging

| Label | Action id |
|---|---|
| Create Joint Chain (3 / 5) | `rig.create_joint_chain_3` / `_5` |
| Insert Single Joint | `rig.insert_joint` |
| Bind Skin to Selected Mesh | `rig.bind_skin` |
| Apply Skin Deform | `rig.skin_deform` |
| Solve 2-Bone IK on Selected Chain | `rig.ik_2bone` |
| Paint Weights > Set Active Joint / Paint / Paint Strong / Reset | `rig.paint_weights_set_joint` / `.paint_weights_at_cursor` / `_strong` / `.paint_weights_reset` |
| Constraints > Parent / Point / Orient / Aim / Scale / Clear | `rig.constraint_parent` / `.constraint_point` / `.constraint_orient` / `.constraint_aim` / `.constraint_scale` / `.constraint_clear` |

## Simulation

| Label | Action id |
|---|---|
| Create Hair Strand / Long | `sim.create_hair` / `.create_long_hair` |
| Create nCloth Patch (8×10 / 12×14) | `sim.ncloth` / `.ncloth_large` |
| Bullet > Add Rigidbody / Bouncy | `sim.bullet` / `.bullet_bouncy` |

## Rendering

| Label | Action id |
|---|---|
| Light > Add Directional / Point / Spot | `render.light_directional` / `.light_point` / `.light_spot` |
| Render Quality > Draft / Preview / Production / Final | `render.quality_draft` / `_preview` / `_production` / `_final` |
| Render Selected | `render.selected` |
| Color Space > sRGB / Linear / ACEScg / Rec.709 | `render.cs_srgb` / `.cs_linear` / `.cs_aces` / `.cs_rec709` |
| AOV > Beauty / Diffuse / Specular / Normal / Depth | `render.aov_beauty` / `.aov_diffuse` / `.aov_specular` / `.aov_normal` / `.aov_depth` |

## See also

- [Keyboard shortcuts](keyboard-shortcuts.md)
- [Aether tool reference](aether-tool-reference.md)
