# Architecture

The framework has six top-level concepts. Knowing how they
relate makes every other guide read faster.

## The six concepts

| Concept | Role |
|---|---|
| **App** | The process. One per program. Owns the event loop and the GPU device. |
| **Window** | An OS window. One App can host many. Borderless and shaped by default. |
| **Skin** | A folder (`.esk`) describing visual layout. Loaded into a window. |
| **Canvas** | A GPU surface inside a window or skin. Receives DisplayLists. |
| **DisplayList** | An immutable list of draw commands. Published to a Canvas each frame. |
| **HookProxy** | Python-side dotted accessor onto a skin placement (`window.cover.text = "..."`). |

## The threading model

Elysium runs three threads of interest:

| Thread | What runs on it | When you touch it |
|---|---|---|
| Python (main) | `app.run()`'s event loop, all reactive effects, all event handlers | Always when you read Python code |
| Render | wgpu compositor; reads a queue of published DisplayLists | Never directly |
| Worker pool | Animation thread, hot-reload watcher, background tasks | Indirectly via `run_animation_thread`, `enable_hot_reload` |

The OS input events arrive on the Python thread via the native
event loop. From there:

1. The framework dispatches events to handlers you registered with
   `@window.on(...)`.
2. Handlers mutate Python state (signals).
3. Effects re-run to translate state changes into Skin mutations.
4. The render thread sees the mutations on the next frame and
   composites.

You never directly publish to the render thread; the framework
batches mutations for you.

## The data flow

```
OS input
  ↓
Native event loop  (Python thread)
  ↓
window.fire("hook.click", event)
  ↓
your @window.on("hook.click") handler
  ↓
signal.set(new_value)
  ↓
@effect runs (Python thread)
  ↓
window.placement.attribute = new_value   (dotted hook → HookProxy)
  ↓
native side queues a Skin mutation
  ↓
Render thread picks up the mutation
  ↓
wgpu compositor produces pixels
  ↓
OS swap-chain presents them
```

The whole loop runs in well under 16 ms at 60 fps under normal
load.

## `.esk` skin

A skin is a folder with a manifest, a document, and any textures
or assets. The framework loads the manifest and the document on
`window.load_skin(path)`. After that, every placement in the
document is addressable from Python via dotted access:

```python
window.background.fill = "#0f0d1eff"
window.time_label.text = "12:34:56"
```

The skin folder is the source of truth for visual layout; your
Python file wires interaction.

The Designer authors `.esk` folders directly; in tutorials we
edit JSON by hand for full understanding.

## App lifecycle

```python
import elysium as ely

app = ely.App(title="My App", identifier="com.example.app")   # construct
window = app.window(transparent=True)   # create window
window.load_skin("path/")                  # load skin
# (register handlers, signals, effects here)
app.run()                                  # event loop blocks here
# app.quit() can be called from any thread to break out
```

`app.run()` blocks on the main thread until `app.quit()` is
called. A graceful quit drains the render queue and closes the
GPU device before returning.

## Multiple windows

A single App can host multiple windows. Each `app.window(...)`
call returns a new window. Common patterns:

- Primary + tool windows (Tutorials > Aurora Clock Pro).
- Main app + popovers / dropdowns.
- Multi-monitor authoring tools.

Each window has its own Canvas, its own Skin (or none), and its
own hook proxy. Signals can be shared across windows; effects
running on one window can mutate placements in another.

## Performance budget

Targets the framework holds:

- Cold start to first frame: ~150 ms on M2, ~250 ms on baseline
  Intel.
- Frame time: < 16 ms (60 fps) at 1080p with a moderate skin.
- Memory: ~30 MB resident + ~10 MB per loaded skin.

These are floors; production apps measure ~2-4 ms per frame on
discrete GPUs.

## See also

- [Borderless and shaped](borderless-and-shaped.md): Window
  shape and hit testing.
- [Skins](skins.md): `.esk` bundle anatomy.
- [Reactive](reactive.md): signals + effects in depth.
- [Rendering](rendering.md): DisplayLists and the compositor.
