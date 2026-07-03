# Elysium Designer

The cross-platform desktop authoring app for borderless, animated Python skins.

Elysium Designer is to the Elysium UI framework what Maya is to Arnold: an
authoring environment for the `.esk` skin bundles your Python app loads at
runtime. Author the look in the Designer, wire the behavior in your editor of
choice via Code Link, and ship a borderless animated app.

## Start with the butterfly

The fastest way to learn the Designer is the 45-minute Blue Morpho to Monarch
tutorial. You will:

- Import a Monarch butterfly 3D model.
- Bring in a Blue Morpho photo as the texture reference.
- Drop six landmarks pairing the photo to the model.
- Run the recommended texture transfer pipeline and bake a PBR normal map.
- Animate the wing flap.
- Export the result as a `.esk` skin that the Elysium UI framework loads as a
  borderless animated app, the official Elysium logo.

[Start the Blue Morpho to Monarch tutorial >>](getting-started/butterfly/index.md)

## What the Designer ships with

| Capability | Where to read |
|---|---|
| Texture transfer (9 methods, 2 recommended pipelines) | [Rendering > Texture transfer pipelines](rendering/texture-transfer-pipelines.md) |
| Brush system (6 engines, 30 builtin presets, .abr / .sut / .elybrush import) | [Brush system](brush/index.md) |
| Aether agent (123 in-app tools across 15 modules) | [Aether](aether/index.md) |
| Borderless and animated window authoring | [Borderless windows](borderless/index.md) |
| PBR rendering with 4 quality presets | [Rendering and lookdev](rendering/index.md) |
| Joint-based rigging + 2-bone IK + paint weights | [Rigging](rigging/index.md) |
| nCloth, hair, Bullet rigidbodies | [Simulation](simulation/index.md) |
| MASH procedural scatter | [Procedural](procedural/mash-scatter.md) |
| Hot reload (Run > Hot Reload) | [Hot reload](hot-reload/index.md) |
| Code Link to VS Code, PyCharm, Cursor | [Code Link](code-link/index.md) |
| Maya parity hotkeys + concepts | [Migration > From Maya](migration/from-maya.md) |

## Install

The Designer ships as a signed standalone executable per OS. Pick yours:

- [macOS .app](installation/macos.md) (Apple Silicon and Intel)
- [Windows .exe](installation/windows.md) (x64)
- [Linux AppImage](installation/linux.md) (x86_64 and aarch64)

Each release of the Designer is available on the
[GitHub Releases page](https://github.com/elysiumui/elysium/releases). The
[build-from-source guide](installation/build-from-source.md) explains how to
build your own `.app`, `.exe`, or AppImage with `pyinstaller scripts/build-designer.spec`.

## Tour the interface

When you launch the Designer for the first time, the layout is a familiar 3D
DCC arrangement. The [Interface tour](interface/index.md) walks every panel,
menu, and tool. If you would rather learn by doing, skip the tour and start
the butterfly tutorial above.

## A note on platforms

Elysium Designer runs on macOS 13 or newer, Windows 10 or newer, and any
reasonably current Linux desktop with X11 or Wayland plus OpenGL 4.1 or
better. The brush system's pressure-aware dynamics consume Windows touch and
pen input via WM_POINTER; on macOS the same dynamics curves stay inert
(touch pressure is reported by some trackpads but not exposed through the
standard event pipeline), and on Linux they activate when libinput reports
tablet pressure.

## The framework side

The Designer authors `.esk` bundles. The Elysium UI Python framework loads
them at runtime. The two are designed together; their docs sit at
[docs.elysiumui.com](https://docs.elysiumui.com/). After you finish the butterfly
tutorial here, the framework site's Butterfly Banner tutorial takes the `.esk`
you exported and wires it into a running borderless animated app.
