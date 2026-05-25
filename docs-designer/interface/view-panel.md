# View Panel

The View Panel is the big region in the middle of the window. Every
placement on the canvas renders there in real time, and every
authoring tool draws into it. It is the GPU-composited heart of the
Designer.

![View Panel showing a Mesh3D placement with Textured + Lit shading and the orbit gizmo](../assets/interface-view-panel.png)

## Navigation

| Action | Mouse | Keyboard alternative |
|---|---|---|
| Pan | Middle-click drag (or hold Space + drag) | Arrow keys (with Hand tool active) |
| Zoom | Mouse wheel | `+` / `-` |
| Orbit (3D scenes) | Alt + middle-click drag | Numpad 4 / 6 / 8 / 2 |
| Frame Selected | Click to select, then `F` | `View > Frame Selected` |
| Frame All | `A` | `View > Frame All` |
| Reset zoom | `1` | `View > Reset Zoom` |

The orbit gizmo lives in the upper-right corner; clicking any face
of the cube snaps the camera to that view (Top / Front / Right /
Back / Left / Bottom). Hold Alt while clicking a face to flip 180°.

## Shading modes

Press a digit key or use `View > …`:

| Key | Mode | What it shows |
|---|---|---|
| 4 | Wireframe | Edges only |
| 5 | Smooth Shaded | Lit with a default headlight, no textures |
| 6 | Textured | Albedo only, no lighting |
| 7 | Textured + Lit | Full PBR with directional lights, normal maps, shadows |
| 8 | Wireframe on Shaded | Combination for topology review |

For 2D-only skins the mode is "Textured + Lit" by default (still
makes sense for shadowed UI panels) and you can ignore the orbit
gizmo.

## HUD

Press `0` (zero) or `View > Toggle HUD` to show the on-canvas heads-
up display: frame number, FPS, current tool, current snap state.
Toggle off for screenshots.

## Grid

`View > Toggle Grid` shows a 10-pixel grid overlay. Holding Ctrl
while dragging snaps movement to the grid; you can change snap
size in `File > Preferences > Snapping`.

## Multiple views

Drag the small **+** in the View Panel's top-right corner to open a
second viewport split. Up to four splits supported; useful for
seeing Top + Side + Perspective + Front while modeling. Right-click
a split's title bar to set its camera (Persp, Top, etc.).

## Recording from the View Panel

`File > Export > PNG` captures the current frame at the project's
render resolution. `Run > Preview Skin` renders to a separate
borderless window so the chrome of the Designer is excluded from
the capture.

For full animations the framework's `elysium.render.Recorder` (used
in the Butterfly Banner tutorial) captures any window output to mp4
or gif.

## DPI

The View Panel honors your monitor's DPI. On a 2x Retina display
the rendered placements look as crisp as the underlying mesh
allows; on a 1x display the framework's wgpu compositor uses sub-
pixel rasterization to soften aliasing. Multi-monitor moves
recompute the surface automatically.
