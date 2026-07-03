# The Interface

The Designer window is divided into seven main regions. Knowing
where each region lives saves time in every tutorial that follows.

![Designer interface overview annotated with the seven main regions](../assets/interface-overview.png)

| Region | Position | What it does |
|---|---|---|
| [Menu bar](menu-bar.md) | Top edge | 19 top-level menus: File, Edit, Mesh, Animate, Window, Theme, etc. |
| [Shelf](shelf.md) | Below the menu bar | Quick-access toolbar with the menu set switcher and the most-used commands |
| [Toolbox](toolbox.md) | Left edge | 17 selection / authoring / paint tools |
| [View Panel](view-panel.md) | Center | The 3D viewport / 2D canvas; where you actually edit |
| [Project Explorer](project-explorer.md) | Right edge, top | Tabs for Objects, Assets, History, Sets |
| [Channel Box](channel-box.md) | Right edge, middle | Numeric properties for the current selection |
| [Properties pane](properties-pane.md) | Right edge, bottom | Full property editor for the active placement |
| [Tool Properties dock](tool-properties-dock.md) | Bottom, expandable | Options for the currently-active toolbox tool |
| [Time Slider](time-slider.md) | Bottom edge | Frame, timeline, playback transport |
| [Status line](status-line.md) | Very bottom | Cursor coords, current mode, transient toasts |
| [Aether chat panel](aether-chat-panel.md) | Floating / docked | Chat with the in-app AI agent |

## The five menu sets

The Designer's menu bar reorganizes itself by **menu set**: the
same pattern as Maya's F2-F6 modes. Switching set shows a different
subset of top-level menus. Use the shelf's dropdown or the keyboard
shortcuts:

| Menu set | Shortcut | Adds menus |
|---|---|---|
| Modeling | F2 | Mesh, Surfaces, Path |
| Rigging | F3 | Skeleton, Skin, Constraints |
| Animation | F4 | Animate, Trax, Time Editor |
| FX (Simulation) | F5 | Simulation, Procedural |
| Rendering | F6 | Rendering, Lookdev, Hypershade |

Menus common to every set (File, Edit, Window, Arrange, View, Run,
Code, Theme, Help) stay visible regardless. Press F2-F6 to switch
instantly.

## Default layout

Out of the box the Designer ships in the **Modeling** set with the
Project Explorer's **Objects** tab active, the Channel Box visible,
and the Properties pane collapsed. The first time you launch, you
walked through the [first-run wizard](../installation/first-run.md)
which set your theme and tablet permissions.

## Workspaces

Window > Workspaces lets you save and recall full layout snapshots:
panel positions, dock states, toolbox order, and visible tools.
Three ship by default:

- **Authoring** (default): everything visible, balanced for skin work.
- **Painting**: extra-wide canvas, big brush panel, compact channel box.
- **Animation**: tall time slider, graph editor docked at the bottom.

Switch with the shelf workspace dropdown, or pin one with
`File > Preferences > Workspaces > Default`.

## Theme

The whole UI honors the theme you chose at first launch. Switch any
time from `Theme > Light/Dark/OLED/Glass/Frost`, or author your own
under `Theme > Customize…`. The active theme persists between
launches.

## Where to next

- [Menu bar](menu-bar.md) for the full menu catalog.
- [Toolbox](toolbox.md) for the left-edge tools.
- [Project Explorer](project-explorer.md) for how placements are
  organized.
