# Hot reload internals

How live skin patching works under the hood. For the user-level
view, see [Hot reload](../hot-reload/index.md).

## Trigger flow

1. The user saves a change in the Designer (or edits a `.esk` JSON
   directly).
2. The Designer's file watcher detects the change.
3. The Designer sends an IPC message describing the change.
4. The framework's `IpcServer` receives the message.
5. The framework patches the running skin in place.
6. Subscribers (effects, components) see the new state on the next
   frame.

## Transport

Unix domain sockets on macOS / Linux; named pipes on Windows.
Default socket: `~/.elysium/sessions/elysium-default.sock`.

## Wire format

Length-prefixed JSON with a session auth token:

```
4 bytes: payload length (big-endian uint32)
N bytes: { "type": "<message>", "payload": { ... }, "auth": "<token>" }
```

## Message types

| Type | Purpose | Payload |
|---|---|---|
| `skin_changed` | Whole-skin reload | `{ "path": "/abs/path/to.esk", "kind": "full" }` |
| `node_patch` | Surgical change to one placement | `{ "id": "btn_play", "fields": { "fill": "#abcdef" } }` |
| `hook_renamed` | Preserve subscribers across renames | `{ "from": "old.click", "to": "new.click" }` |
| `python_module_reloaded` | Pairs with `importlib.reload` | `{ "module": "myapp" }` |
| `texture_changed` | Reload one texture | `{ "path": "textures/wing.png" }` |

## What survives a `skin_changed`

- Window position, size, level.
- Signal values and computed memoizations.
- Active effect subscriptions (re-bound to identically-named
  placements).
- Animations on `AnimationClock`.
- `@window.on(...)` handlers.

## What does not survive

- Placements that were renamed or removed (subscribers see an
  unbind callback).
- Render-thread anim slots referring to vanished placements.

## Auth

The session token is generated at `enable_hot_reload(...)` time
and stored in the socket's metadata. Messages without a matching
token are dropped. Prevents accidental cross-app patching when
multiple apps run on the same machine.

## Failure modes

- **Socket missing**: the framework warns once and continues; the
  IpcServer stays running and accepts late connections.
- **Bad JSON**: skipped silently, with a debug-level log.
- **Schema mismatch**: the patch is rejected; the user sees a
  toast in the Designer and the live state is unchanged.

## Disabling hot reload

`window.enable_hot_reload(...)` returns the `IpcServer`. Call
`.stop()` to shut it down. Packaged apps (`elysium pack`) ship
with hot reload disabled by default.

## See also

- [Hot reload](../hot-reload/index.md)
- [Code Link](../code-link/index.md)
