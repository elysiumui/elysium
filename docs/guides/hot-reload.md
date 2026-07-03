# Hot reload

When you save a skin in the Designer (or edit the JSON by hand),
every running app that has called `enable_hot_reload()` receives
a `skin_changed` IPC message and re-loads the skin without
restarting. Runtime state is preserved: open windows stay open,
signals keep their values, animations keep ticking.

## App side

```python
window = app.window(...)
window.load_skin("my-skin.esk/")
window.enable_hot_reload()    # auto-starts an IPC server on ~/.elysium/sessions
app.run()
```

`enable_hot_reload` is idempotent. Calling it a second time
returns the same `IpcServer` instance.

## CLI watcher

```sh
elysium dev path/to/my-skin.esk/
```

Polls the skin path every 250 ms for file changes, posts a
`skin_changed` over the per-session UDS socket, and lets you
iterate on a skin without opening the Designer.

`elysium dev` also watches paired Python files (see
[Code Link](code-link.md)): edit a handler and the file change
triggers a process restart with the same window position.

## What hot-reloads vs what restarts

| Change | Reload type |
|---|---|
| `<skin>/document.json` | Skin reload (in-place) |
| `<skin>/manifest.json` | Skin reload |
| `<skin>/textures/*.png` | Skin reload |
| `<skin>/assets/*.png` | Skin reload |
| Your Python file | Process restart (via `elysium dev`) |
| `python/elysium/...` | Process restart (when running from source) |

The dividing line: anything in the static skin → in-place reload.
Anything in Python behavior → restart so the new code path runs
from initialization.

## Wire format

IPC is length-prefixed JSON with a session auth token. Message
types:

- `skin_changed { path, kind }`: the typical case.
- `node_patch { id, fields }`: surgical change for one node.
- `hook_renamed { from, to }`: preserves subscribers across
  renames.
- `python_module_reloaded { module }`: pairs with
  `importlib.reload` from advanced workflows.

Transports: Unix domain sockets on macOS / Linux, named pipes on
Windows.

## Custom socket path

By default the socket lives at `~/.elysium/sessions/elysium-default.sock`
(or the platform equivalent). Override:

```python
window.enable_hot_reload(socket_path="/tmp/my_app.sock")
```

Useful when running multiple Elysium apps that should not share a
socket.

## Listening for custom messages

`enable_hot_reload` returns the underlying `IpcServer`:

```python
ipc = window.enable_hot_reload()
ipc.on_message("my_event", lambda payload_json: print(payload_json))
```

Use this to wire bespoke developer tooling without rolling a
separate IPC stack.

## What survives a hot reload

After a skin reload:

- Window position, size, level: preserved.
- Open signals and their values: preserved.
- Effects, computed: still subscribed, re-run if their dependencies
  changed.
- Animations: keep playing.
- `@window.on(...)` handlers: still registered.
- Hook subscribers identified by id: still wired (the framework
  re-binds them to the new placement with the same id).

What does **not** survive:

- Placements that were renamed or removed (their hooks unbind;
  subscribers get an unbind callback if they registered one).
- Custom render-thread anim slots: numeric ids stay, but the
  placement at that slot may have been replaced.

## Disabling

```python
ipc.stop()
```

Stops the IPC server. Hot-reload requires the socket; without it,
the watcher's messages are dropped silently.

## Production builds

Packaged apps (`elysium pack`) ship with hot-reload disabled by
default. The IPC server is a development tool. Enable explicitly
if you want to ship a debug build that supports live reload from
a coworker's Designer.

## See also

- [Skins](skins.md): `.esk` anatomy.
- [Code Link](code-link.md): paired Python file workflow.
- [CLI](cli.md): `elysium dev` flags.
