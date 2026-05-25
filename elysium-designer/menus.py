"""Menu-bar definitions for the Elysium Designer.

Extracted from ``__main__.py`` so the Mesh / Surfaces / Rigging / FX /
Rendering shelves can grow into Maya parity without bloating the
already-large designer module. The format is:

    MENUS: list of (top_level_label, items)
    items: list of menu entries, where each entry is either:
        2-tuple `(label, action)` — visible in every menu set
        3-tuple `(label, action, menu_sets)` — visible only when
            `Designer.menu_set` is in the given frozenset
        `("---", "")` separator

`MENU_SETS` enumerates the recognised filter values (Maya F2–F6 modes).
"""

from __future__ import annotations


MENU_SETS: tuple[str, ...] = (
    "modeling", "animation", "rigging", "fx", "rendering",
)


MENUS: list[tuple[str, list[tuple]]] = [
    ("File", [
        ("New Skin",              "file.new"),
        ("Open Skin…",            "file.open"),
        ("Save",                  "file.save"),
        ("Save As…",              "file.save_as"),
        ("Close Skin",            "file.close_skin"),
        ("---",                   ""),
        ("Extract Texture from Image…", "texture.extract"),
        ("Apply Texture from Library…", "texture.apply"),
        ("AI Enhance Selection (×4)",   "texture.enhance"),
        ("🌌 Aether (chat with the agent)…", "ai.aether"),
        ("---", ""),
        ("Insert API Key › Anthropic (Claude)…",  "ai.set_key_anthropic"),
        ("Insert API Key › OpenAI (GPT)…",         "ai.set_key_openai"),
        ("Insert API Key › Google (Gemini)…",      "ai.set_key_gemini"),
        ("Insert API Key › DeepSeek…",              "ai.set_key_deepseek"),
        ("Remove all saved API Keys",               "ai.clear_keys"),
        ("---", ""),
        ("✨ Magic Polish (AI)…",         "ai.panel"),
        ("✨ Magic Polish (one-shot)",    "ai.magic_polish"),
        ("Generate Skin from prompt…",   "ai.generate_skin"),
        ("Import 3D Model…",      "import.mesh3d"),
        ("---",                   ""),
        ("Import › SVG…",         "import.svg"),
        ("Import › Figma URL…",   "import.figma"),
        ("Import › Lottie…",      "import.lottie"),
        ("Import › glTF / OBJ…",  "import.gltf"),
        ("Import › Canva…",       "import.canva"),
        ("Export › SVG…",         "export.svg"),
        ("Export › PNG…",         "export.png"),
        ("Export › .esk Bundle",  "export.esk"),
        ("---",                   ""),
        ("Exit Designer",         "file.close"),
    ]),
    ("Edit", [
        ("Undo",            "edit.undo"),
        ("Redo",            "edit.redo"),
        ("---",             ""),
        ("Duplicate",       "edit.duplicate"),
        ("Delete",          "edit.delete"),
        ("Select All",      "edit.select_all"),
        ("Deselect",        "edit.deselect"),
        ("---",             ""),
        # G4 Phase 7d — Maya-parity parenting actions.
        ("Parent",          "edit.parent"),       # selected → first-other-selection
        ("Unparent",        "edit.unparent"),     # selected → top-level
        ("Group Selected…", "edit.group"),        # wrap selection in a new parent
    ]),
    ("Window", [
        ("Set Shape: Rectangle",       "window.shape_rect"),
        ("Set Shape: Ellipse",         "window.shape_ellipse"),
        ("Set Shape From Selection",   "window.shape_from_selection"),
        ("---",                        ""),
        ("Toggle Transparency",        "window.transparent"),
        ("Toggle Title Bar",           "window.titlebar"),
        ("---",                        ""),
        ("Show Aether Agent",          "window.toggle_aether"),
        ("---",                        ""),
        ("Float Tool Properties",      "window.float_tool_dock"),
        ("Dock Tool Properties",       "window.dock_tool_dock"),
    ]),
    ("Arrange", [
        ("Align Left",            "arrange.align_left"),
        ("Align Center",          "arrange.align_center"),
        ("Align Right",           "arrange.align_right"),
        ("Align Top",             "arrange.align_top"),
        ("Align Middle",          "arrange.align_middle"),
        ("Align Bottom",          "arrange.align_bottom"),
        ("---",                   ""),
        ("Bring Forward",         "arrange.forward"),
        ("Send Backward",         "arrange.backward"),
    ]),
    ("Path", [
        ("Combine › Union",     "path.union"),
        ("Combine › Intersect", "path.intersect"),
        ("Combine › Subtract",  "path.subtract"),
        ("Combine › Exclude",   "path.exclude"),
    ]),
    ("View", [
        ("Zoom In",           "view.zoom_in"),
        ("Zoom Out",          "view.zoom_out"),
        ("Reset Zoom",        "view.zoom_reset"),
        ("---", ""),
        ("Frame Selected",    "view.frame_selected"),
        ("Frame All",         "view.frame_all"),
        ("Fit Canvas to App Window (auto on resize)", "view.fit_canvas"),
        ("---", ""),
        ("Toggle Grid",       "view.grid"),
        ("Snap to Grid",      "view.snap"),
        ("Toggle HUD",        "view.hud"),
        ("---", ""),
        ("Wireframe",          "view.mode_wireframe"),
        ("Smooth Shaded",      "view.mode_shaded"),
        ("Textured",           "view.mode_textured"),
        ("Textured + Lit",     "view.mode_lit"),
        ("Wireframe on Shaded","view.mode_wire_on_shaded"),
    ]),
    # Top-level Theme menu — Maya-style "switch palette from the menu
    # bar" rather than the five text-buttons that used to live in the
    # top toolbar. Each Built-In sets `Designer.theme_index`; Customise
    # opens the colour-picker dialog so the user can author + name +
    # save their own theme.
    ("Theme", [
        ("Light",             "theme.0"),
        ("Dark",              "theme.1"),
        ("OLED",              "theme.2"),
        ("Glass",             "theme.3"),
        ("Frost",             "theme.4"),
        ("---", ""),
        ("Customize…",        "theme.customize"),
        ("Save Current as User Theme…", "theme.save_user"),
        ("Manage User Themes…",         "theme.manage_user"),
    ]),
    # G5 Phase 11a — Maya parity Animate menu. Hosts the keyframe
    # actions that already exist on the timeline transport plus the
    # entry-points for the Graph Editor / Dope Sheet / Trax / Time
    # Editor / Motion Paths panels.
    ("Animate", [
        ("Set Key",                "animate.set_key"),
        ("Set Breakdown",          "animate.set_breakdown"),
        ("Toggle Auto Key",        "animate.auto_key"),
        ("---", ""),
        ("Graph Editor…",            "animate.graph_editor"),
        ("Dope Sheet…",              "animate.dope_sheet"),
        ("Trax Editor…",             "animate.trax"),
        ("Time Editor…",             "animate.time_editor"),
        ("Motion Paths…",            "animate.motion_paths"),
        ("---", ""),
        ("Go to Start",            "animate.go_start"),
        ("Go to End",              "animate.go_end"),
        ("Step Backward Frame",    "animate.step_back_frame"),
        ("Step Forward Frame",     "animate.step_fwd_frame"),
        ("Step Backward Key",      "animate.step_back_key"),
        ("Step Forward Key",       "animate.step_fwd_key"),
    ]),
    ("Run", [
        ("Preview Skin",     "run.preview"),
        ("Hot Reload",       "run.hot_reload"),
    ]),
    ("Code", [
        ("Open handler for selection",    "code.goto"),
        ("Scaffold missing handlers",     "code.scaffold_all"),
        ("---", ""),
        ("Pair Python file…",             "code.pair"),
        ("Reveal paired file",            "code.reveal"),
    ]),
    # G9 Phase 19 — Rigging menu. Joint creation ships in 19a; the
    # rest of the rigging stack lands in 19b-e.
    ("Rigging", [
        ("Create Joint Chain (3)",          "rig.create_joint_chain_3"),
        ("Create Joint Chain (5)",          "rig.create_joint_chain_5"),
        ("Insert Single Joint",             "rig.insert_joint"),
        ("---", ""),
        ("Bind Skin to Selected Mesh",      "rig.bind_skin"),
        ("Apply Skin Deform (from current joint pose)",  "rig.skin_deform"),
        ("---", ""),
        ("Solve 2-Bone IK on Selected Chain",  "rig.ik_2bone"),
        ("Paint Weights › Set Active Joint (from selection)",  "rig.paint_weights_set_joint"),
        ("Paint Weights › Paint at Cursor",                    "rig.paint_weights_at_cursor"),
        ("Paint Weights › Paint at Cursor (strong)",           "rig.paint_weights_at_cursor_strong"),
        ("Paint Weights › Reset to Uniform (0.5 / 0.5)",       "rig.paint_weights_reset"),
        ("Orient Joint to Child",           "rig.orient_joint"),
        ("Pole Vector Constraint on Joint", "rig.pole_vector"),
        ("---", ""),
        ("Skin Weights Editor",             "rig.skin_weights_editor"),
        ("Shape Editor (Blend Shapes)",     "rig.shape_editor"),
        ("Pose Editor",                     "rig.pose_editor"),
        ("HumanIK",                         "rig.humanik"),
        ("---", ""),
        ("Constraints › Parent",            "rig.constraint_parent"),
        ("Constraints › Point",             "rig.constraint_point"),
        ("Constraints › Orient",            "rig.constraint_orient"),
        ("Constraints › Aim",               "rig.constraint_aim"),
        ("Constraints › Scale",             "rig.constraint_scale"),
        ("Constraints › Clear (Selected)",  "rig.constraint_clear"),
    ]),
    # G10 — Simulation menu. HairStrand (Verlet rope/hair), nCloth,
    # Bullet rigidbodies, Cache, and Reset all ship in this phase.
    ("Simulation", [
        ("Create Hair Strand",              "sim.create_hair"),
        ("Create Long Hair Strand",         "sim.create_long_hair"),
        ("---", ""),
        ("Create nCloth Patch (8×10)",      "sim.ncloth"),
        ("Create nCloth Patch (12×14)",     "sim.ncloth_large"),
        ("---", ""),
        ("Bullet › Add Rigidbody (selected)",        "sim.bullet"),
        ("Bullet › Add Bouncy Rigidbody (selected)", "sim.bullet_bouncy"),
        ("Bullet › Pause / Resume All",              "sim.bullet_pause"),
        ("---", ""),
        ("Cache Simulation State",          "sim.cache"),
        ("Reset to Bind Pose",              "sim.reset"),
    ]),
    # G11 — MASH / Procedural distribution.
    ("Procedural", [
        ("MASH › Scatter Selection 3×5",        "mash.scatter_3x5"),
        ("MASH › Scatter Selection 5×5",        "mash.scatter_5x5"),
        ("MASH › Scatter Selection 3×5 (jittered)", "mash.scatter_3x5_jitter"),
        ("---", ""),
        ("XGen › Instanced Fur",                "mash.xgen"),
        ("Bifrost › Particles",                 "mash.bifrost"),
        ("Bifrost › Fluid Container",           "mash.bifrost_fluid"),
    ]),
    # G8 Phase 18 + G12 — Rendering menu. Hypershade, Render Quality,
    # Batch Render, Lights, Render Layers, Color Management, and AOVs
    # all ship in this phase.
    ("Rendering", [
        ("Hypershade…",                          "render.hypershade"),
        ("---", ""),
        ("Render Quality › Draft (4 spp)",       "render.quality_draft"),
        ("Render Quality › Preview (12 spp)",    "render.quality_preview"),
        ("Render Quality › Production (64 spp)", "render.quality_production"),
        ("Render Quality › Final (256 spp)",     "render.quality_final"),
        ("---", ""),
        ("Batch Render › 30 frames",             "render.batch_30"),
        ("Batch Render › 60 frames",             "render.batch_60"),
        ("---", ""),
        ("Light › Add Directional",              "render.light_add_directional"),
        ("Light › Add Point",                    "render.light_add_point"),
        ("Light › Toggle (enable/disable)",      "render.light_toggle"),
        ("---", ""),
        ("Render Layer › Assign Selected → 0",   "render.layer_assign_0"),
        ("Render Layer › Assign Selected → 1",   "render.layer_assign_1"),
        ("Render Layer › Assign Selected → 2",   "render.layer_assign_2"),
        ("Render Layer › Set Active → 0 (default)", "render.layer_active_0"),
        ("Render Layer › Set Active → 1",        "render.layer_active_1"),
        ("Render Layer › Set Active → 2",        "render.layer_active_2"),
        ("---", ""),
        ("Color Space › sRGB",                    "render.color_srgb"),
        ("Color Space › Linear",                  "render.color_linear"),
        ("Color Space › ACEScg",                  "render.color_acescg"),
        ("Color Space › Rec.709",                 "render.color_rec709"),
        ("---", ""),
        ("AOV › Toggle Beauty",                   "render.aov_beauty"),
        ("AOV › Toggle Diffuse",                  "render.aov_diffuse"),
        ("AOV › Toggle Specular",                 "render.aov_specular"),
        ("AOV › Toggle Normal",                   "render.aov_normal"),
        ("AOV › Toggle Depth",                    "render.aov_depth"),
    ]),
    # G8 Phase 17 — Deformers menu. Bend / Twist / Sine / Flare /
    # Squash / Wave (axis-bearing) plus Lattice / Cluster / Wire /
    # Wrap / Shrinkwrap / Jiggle / Soft Modification / Non-Linear /
    # Blend Shape (modal-editor) — all wired and applying live.
    ("Deformers", [
        ("Bend (Y axis)",          "deform.bend_y"),
        ("Bend (X axis)",          "deform.bend_x"),
        ("Bend (Z axis)",          "deform.bend_z"),
        ("---", ""),
        ("Twist (Y axis)",         "deform.twist_y"),
        ("Twist (X axis)",         "deform.twist_x"),
        ("Twist (Z axis)",         "deform.twist_z"),
        ("---", ""),
        ("Sine Wave (Y axis)",     "deform.sine_y"),
        ("Sine Wave (X axis)",     "deform.sine_x"),
        ("Sine Wave (Z axis)",     "deform.sine_z"),
        ("---", ""),
        ("Flare (Y axis)",         "deform.flare_y"),
        ("Flare (X axis)",         "deform.flare_x"),
        ("Flare (Z axis)",         "deform.flare_z"),
        ("---", ""),
        ("Squash (Y axis)",        "deform.squash_y"),
        ("Squash (X axis)",        "deform.squash_x"),
        ("Squash (Z axis)",        "deform.squash_z"),
        ("---", ""),
        ("Wave (Y axis)",          "deform.wave_y"),
        ("Wave (X axis)",          "deform.wave_x"),
        ("Wave (Z axis)",          "deform.wave_z"),
        ("---", ""),
        ("Lattice (3×3×3 swirl)",         "deform.lattice"),
        ("Cluster (Gaussian pull)",       "deform.cluster"),
        ("Wire (axial bend)",             "deform.wire"),
        ("Wrap (project to sphere)",      "deform.wrap"),
        ("Shrinkwrap",                    "deform.shrinkwrap"),
        ("Jiggle",                        "deform.jiggle"),
        ("Soft Modification",             "deform.softmod"),
        ("Non-Linear (bend + twist)",     "deform.nonlinear"),
        ("Blend Shape (toward sphere)",   "deform.blendshape"),
    ]),
    # G7 Phase 13 — Curves menu (NURBS).
    ("Curves", [
        ("Insert NURBS Curve",          "curves.insert"),
        ("Insert Closed NURBS Curve",   "curves.insert_closed"),
        ("---",                         ""),
        ("Loft Selected Curves → Mesh3D",  "curves.loft"),
        ("---",                         ""),
        ("Trim Curve (20%-80%)",        "curves.trim"),
        ("Blend Selected Curves",       "curves.blend"),
        ("Rebuild Curve  uniform 8 CPs", "curves.rebuild"),
    ]),
    ("Mesh", [
        # Lasso a region on the selected Mesh3D or its reference Image.
        # Action IDs stay wing-specific internally (the dispatcher still
        # wires them to the existing handlers); user-visible labels are
        # generic so the Designer reads as a generic 3D tool rather
        # than a butterfly demo.
        ("Lasso Top 1% of Selected Mesh Part (left side)",   "mesh.lasso_wing_left_1pct"),
        ("Lasso Top 1% of Selected Mesh Part (right side)",  "mesh.lasso_wing_right_1pct"),
        ("Lasso Top 5% of Selected Mesh Part (left side)",   "mesh.lasso_wing_left_5pct"),
        ("---", ""),
        ("Lasso Top 1% of Reference Image (left corner)",    "mesh.lasso_image_left_1pct"),
        ("Lasso Top 1% of Reference Image (right corner)",   "mesh.lasso_image_right_1pct"),
        ("---", ""),
        ("Lasso Both (Mesh part + Reference Image)",         "mesh.lasso_both_left_1pct"),
        ("---", ""),
        # Transfer Texture submenu — every method available on the
        # selected mesh part; recommended pipelines flagged with ⭐.
        ("Transfer Texture › ⭐ POLAR + Bake + Normal Map (PBR)",
                                                              "mesh.transfer_polar_normal"),
        ("Transfer Texture › ⭐ BBox-Warp then Landmark Gaps + Bake + Normal Map",
                                                              "mesh.bbox_then_landmark_gaps"),
        ("Transfer Texture › POLAR (left side)",              "mesh.transfer_wing_polar"),
        ("Transfer Texture › POLAR (right side)",             "mesh.transfer_wing_polar_right"),
        ("Transfer Texture › REGIONS (left side)",            "mesh.transfer_wing_regions"),
        ("Transfer Texture › REGIONS (right side)",           "mesh.transfer_wing_regions_right"),
        ("Transfer Texture › FLOW (left side)",               "mesh.transfer_wing_flow"),
        ("Transfer Texture › FLOW (right side)",              "mesh.transfer_wing_flow_right"),
        ("Transfer Texture › TPS (left side)",                "mesh.transfer_wing_tps"),
        ("Transfer Texture › TPS (right side)",               "mesh.transfer_wing_tps_right"),
        ("Transfer Texture › BBOX_WARP (safe baseline)",      "mesh.transfer_wing_100"),
        ("Transfer Texture › SWEEP (legacy row-by-row)",      "mesh.transfer_wing_100_sweep"),
        ("---", ""),
        # Landmark Transfer — uses point pairs placed via the Landmark
        # tool (Q's neighbour in the toolbox). Works on any imported
        # mesh + reference image pair.
        ("Apply Landmark Transfer (TPS, ≥6 pairs)",           "mesh.landmark_apply"),
        ("Apply Landmark Transfer + Bake + Normal Map",       "mesh.landmark_apply_full"),
        ("Landmarks › Save…",                                  "mesh.landmark_save"),
        ("Landmarks › Load…",                                  "mesh.landmark_load"),
        ("Landmarks › Clear",                                  "mesh.landmark_clear"),
        ("---", ""),
        # Inspect / utility commands.
        ("Inspect › Read Part Pixel Counts (Mesh3D + Image)", "mesh.read_wing_pixels"),
        ("Inspect › Match Reference Image Size to Selected Mesh",
                                                              "mesh.equalize_wings"),
        ("Inspect › Remove All Lasso Overlays",               "mesh.clear_lassos"),
        ("---", ""),
        ("Render Selected Part Mask → PNG (left side)",       "mesh.render_wing_left_mask"),
        ("Render Selected Part Mask → PNG (right side)",      "mesh.render_wing_right_mask"),
        ("Render Body Mask → PNG",                            "mesh.render_body_mask"),
    ]),
    ("Help", [
        ("Documentation",                "help.docs"),
        ("Keyboard Shortcuts",           "help.keys"),
        ("Maya → Elysium Migration Guide","help.maya_migration"),
        ("Brush System Guide",            "help.brush_system"),
        ("About Elysium",                "help.about"),
    ]),
]
