# API Reference

Auto-generated class reference for every public symbol in
`elysium`. Each subpackage's index lists its classes and points
into mkdocstrings-rendered pages for the full surface (signatures,
parameter tables, examples).

## Subpackages

| Package | Purpose |
|---|---|
| [elysium](elysium.md) | App, Window, Canvas, DisplayList, Path, Skin, load_skin |
| [components](components.md) | The 30 built-in components |
| [layout](layout.md) | Stack, Row, Col, Grid, Form |
| [theme](theme.md) | Color math, Theme, Shadow, MotionPreset, built-ins |
| [anim](anim.md) | Tween, Timeline, StateMachine, Spring, AnimationClock |
| [reactive](reactive.md) | signal, computed, effect, Signal |
| [render](render.md) | pbr, texture, compute, preview |
| [brush](brush.md) | BrushEngine, Preset, Library, importers |
| [aether](aether.md) | Daemon, Session, Provider, register_tool, Tool |
| [ai](ai.md) | generate_skin, modify_skin, magic_polish, SkinDiff |
| [codelink](codelink.md) | index_handlers, scaffold_handler, goto_handler |
| [accessibility](accessibility.md) | A11yPrefs, current, subscribe |
| [events](events.md) | ClickEvent, stop_propagation, prevent_default |
| [focus](focus.md) | FocusNode, next_focus |
| [pack](pack.md) | Build a signed standalone bundle |
| [updater](updater.md) | Sparkle / appcast / channels |
| [webview](webview.md) | Embed a native browser engine |
| [cli](cli.md) | elysium dev / doctor / aether / pack / new |

## Alphabetical class index (selected)

| Class | Lives in |
|---|---|
| `A11yPrefs` | [accessibility](accessibility.md) |
| `AnimationClock` | [anim](anim.md) |
| `App` | [elysium](elysium.md) |
| `BrushEngine` | [brush](brush.md) |
| `Button` | [components](components.md) |
| `Canvas` | [elysium](elysium.md) |
| `ChatPanel` | [aether](aether.md) |
| `ClickEvent` | [events](events.md) |
| `Color` | [theme](theme.md) |
| `CommandPalette` | [components](components.md) |
| `Component` | [components](components.md) |
| `Daemon` | [aether](aether.md) |
| `DisplayList` | [elysium](elysium.md) |
| `FocusNode` | [focus](focus.md) |
| `Grid` | [layout](layout.md) |
| `HookProxy` | [elysium](elysium.md) |
| `Image` | [elysium](elysium.md) |
| `IpcServer` | [elysium](elysium.md) |
| `Library` | [brush](brush.md) |
| `Material` | [render](render.md) |
| `Path` | [elysium](elysium.md) |
| `PaintMask` | [render](render.md) |
| `Popover` | [components](components.md) |
| `Preset` | [brush](brush.md) |
| `ProgressBar` | [components](components.md) |
| `Session` | [aether](aether.md) |
| `Shadow` | [theme](theme.md) |
| `Signal` | [reactive](reactive.md) |
| `SkiaLayer` | [elysium](elysium.md) |
| `Skin` | [elysium](elysium.md) |
| `SkinDiff` | [ai](ai.md) |
| `Slider` | [components](components.md) |
| `Spring` | [anim](anim.md) |
| `Stack` | [layout](layout.md) |
| `StateMachine` | [anim](anim.md) |
| `TextInput` | [components](components.md) |
| `Theme` | [theme](theme.md) |
| `Timeline` | [anim](anim.md) |
| `Toast` | [components](components.md) |
| `Toggle` | [components](components.md) |
| `Tool` | [aether](aether.md) |
| `Tween` | [anim](anim.md) |
| `WebView` | [webview](webview.md) |
| `Window` | [elysium](elysium.md) |

## Reading the pages

Each per-class page follows a consistent shape:

1. Synopsis.
2. Status (stable / experimental / internal).
3. Quick example (10-20 lines that produce a screenshot).
4. Constructors with parameter tables.
5. Properties (reactive ones tagged).
6. Methods grouped (lifecycle / layout / rendering / events / util).
7. Events / hooks emitted.
8. Recipes that use this class.
9. Source link on GitHub.

The auto-generator behind these pages is mkdocstrings; docstring
edits in the source code flow directly to the published docs.

## See also

- [Guides](../guides/index.md): topic-shaped deep dives that
  weave classes together.
- [Recipes](../recipes/index.md): "how do I X?" cookbook.
