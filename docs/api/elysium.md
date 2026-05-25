# `elysium`

The top-level package. Re-exports the most-used classes from the
native extension.

## Classes

| Class | Purpose |
|---|---|
| `App` | The application object. One per process. |
| `Window` | An OS window with optional borderless / shaped properties. |
| `HookProxy` | Python-side dotted accessor for skin placements. |
| `Canvas` | A GPU surface inside a placement. |
| `Path` | Vector path builder (move_to / line_to / curve_to / etc.). |
| `DisplayList` | Immutable list of draw commands. |
| `SkiaLayer` | A placement kind owning its own internal DisplayList. |
| `Skin` | A loaded `.esk` bundle. |
| `Image` | Raster image, loaded from disk or bytes. |
| `IpcServer` | Local IPC server used for hot reload + Code Link. |

## Functions

| Function | Purpose |
|---|---|
| `load_skin(path, surface_size=None)` | Load a `.esk` folder into a window. |
| `current_app()` | Return the currently-running App. |

## Exceptions

| Exception | When |
|---|---|
| `ElysiumError` | Base of every framework exception. |
| `SkinError` | Skin manifest / document errors. |
| `HookNotFound` | A `@window.on(...)` named a hook that does not exist. |
| `ShaderValidationError` | A WGSL shader failed validation. |
| `CanvasExpired` | DisplayList submitted to a Canvas that has been replaced. |

## Constants

`__version__`: package version string.

## Auto-rendered details

::: elysium
    options:
      members:
        - App
        - Window
        - Skin
        - load_skin
        - __version__

## See also

- [Architecture](../guides/architecture.md)
- [Skins](../guides/skins.md)
- [Borderless and shaped](../guides/borderless-and-shaped.md)
