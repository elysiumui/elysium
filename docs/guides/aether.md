# Aether

Aether is the framework's in-app agent: a chat session backed by
a model (Anthropic / OpenAI / Ollama) with access to 123 tools
across 15 modules (mesh, theme, render, anim, rig, sim, brush,
path, curves, window, view, arrange, file, code, help).

The agent reads your scene, calls tools, and explains its
reasoning. Use it from the Designer's chat panel, from a CLI, or
embed it in your own app.

## CLI

```sh
elysium aether
```

Opens an interactive REPL. Connects to the currently-running
Designer or app if one has Aether enabled; otherwise runs in
"design from scratch" mode.

## Enable in your app

```python
from elysium.aether import Daemon, Session

daemon = Daemon(provider="anthropic")
session = daemon.new_session(scope=window)
```

The Daemon owns the model connection; sessions are per-conversation.
`scope=window` gives the agent access to the window's skin,
signals, and registered tools.

## What a tool call looks like

```
User: Rotate the left wing 10 degrees and key it at frame 12.
Agent: I'll set rotateZ on left_wing to 10 and key it at frame 12.
       [tool: mesh.set_channel { id: "left_wing", channel: "rotateZ", value: 10 }]
       [tool: anim.set_key { id: "left_wing", channel: "rotateZ", frame: 12 }]
       Done. The wing now rotates 10° at frame 12.
```

Each tool call shows in the chat panel as a collapsible card with
the exact arguments and the result. Audit and reproducibility are
first-class.

## Tools

The full catalog (123 tools, 15 modules) is auto-generated from
the shipping code and lives at:

- Framework: [API > Aether](../api/aether.md)
- Designer: [Aether tool reference](https://designer.elysiumui.com/reference/aether-tool-reference/)

Each tool has a docstring, an argument schema, and a "confirmation
required" flag. The agent reads these to decide which tool to
call.

## Register a custom tool

```python
from elysium.aether import register_tool, Tool

@register_tool("myapp.greet")
class Greet(Tool):
    description = "Print a greeting in the app."
    args_schema = {"name": {"type": "string"}}

    def call(self, args, context):
        print(f"Hello, {args['name']}!")
        return {"ok": True}
```

The tool appears in the agent's tool list with id `myapp.greet`.
Aether can now call it when the user's intent matches.

See [Recipes: expose a custom tool to Aether](../recipes/24-custom-aether-tool.md).

## Snapshots

Snapshots are named restore points of the scene:

```python
snap = session.take_snapshot("before-bake")
# ... do destructive things ...
session.restore_snapshot("before-bake")
```

Aether can take and restore snapshots automatically. Common
pattern: "Try X. If it doesn't look right, undo."

## Safety and limits

Every tool declares three contract fields, validated when it is
registered (a bad `input_schema` fails `import elysium.aether` loudly):

| Field | Values | Meaning |
|---|---|---|
| `side_effect` | `READ` | No mutation anywhere. |
| | `NONE` | No *document* mutation; may touch transient view/playback state, session journals, out-of-project caches or logs. No checkpoint, no undo entry, no revision bump. |
| | `WRITE` | Mutates the document (placements/window/mesh/material/animation) or the paired code file. Checkpoint + one undo entry + revision bump. |
| | `DESTRUCTIVE` | Irrecoverable outside the document checkpoint (file delete/overwrite, process kill, arbitrary code, module reload). Checkpoint + confirmation per policy. |
| `undoable` | bool | Whether undo can reverse it. Under a transaction every `WRITE`/`DESTRUCTIVE` call publishes the pre-call document as one undo entry; `undoable=False` marks tools whose *external* effect (a written file, a killed process) is not reversed by that entry. |
| `requires_confirmation` | `never` / `destructive` / `always` | See the matrix below. |

### Confirmation policy

One helper, `elysium.aether.execution.confirmation_required(tool, trust, confirmed)`,
is the only place the policy lives; the bridge, the headless CLI path and
the daemon all call it. Confirmation is required when:

| `requires_confirmation` | `TrustMode.CAUTIOUS` | `COLLABORATIVE` | `AUTONOMOUS` |
|---|---|---|---|
| `never` | every `WRITE`/`DESTRUCTIVE` | no | no |
| `destructive` | every `WRITE`/`DESTRUCTIVE` | `DESTRUCTIVE` tools | `DESTRUCTIVE` tools |
| `always` | yes | yes | yes |

Over the bridge a call that needs confirmation fails with **409** and
`confirmation_required`; resubmit with `"confirm": true` and a *new* id
(`elysium aether call --confirm`). The daemon asks its `approve_callback`
(the CLI REPL auto-approves). `dev.eval` is `DESTRUCTIVE` + `always`;
`dev.reload_module`, `dev.reload_designer_module`, `texture.delete_from_library`,
`code.write_file`, `placement.remove` and `snapshot.restore` are
`DESTRUCTIVE` + `destructive`.

### Checkpoints, rollback and undo

Every `WRITE`/`DESTRUCTIVE` call runs inside `execution.run_transaction`:

1. **Checkpoint first.** `session.snapshots.capture()` writes a tarball
   (skin directory, paired code file, message history, asset manifest).
   If the checkpoint fails the handler never runs and the result is
   `Cannot checkpoint command: ...`.
2. **Dispatch** with schema validation (`invalid arguments for <tool>: ...`).
3. **Persist** (headless CLI/daemon only): `save_layout()`; a failed save
   fails the command (`Cannot persist command: ...`).
4. **Commit**: exactly one undo entry (the pre-call document, mesh assets
   included) replaces whatever the handler pushed, the redo stack clears,
   `_document_revision` increments.
5. **Rollback** on any failure: `_restore(before)` and both history stacks
   go back to what they were; a rollback failure is retained in
   `rollback_error`.

The document and its history are written together, so they never
disagree: a rollback that takes the document back to where the command
began takes both stacks with it.

That is exact when the transaction runs on the Designer's frame thread —
the thread that owns the document — which is what `_aether_dispatcher`
buys you: a user edit cannot interleave with a command at all. Without a
dispatcher the bridge runs inline on its HTTP thread (the daemon likewise
on its own), and a user pressing undo or redo mid-command races it. The
transaction cannot serialize against a thread it has no handle on, so it
still writes history wholesale — anything else leaves states unreachable,
a redo that does nothing, or undo steps out of order — and **reports** the
race as a `history` warning on the receipt instead of discarding it
silently:

```json
{"status": "committed", "revision": 42,
 "warnings": [{"path": "history",
               "message": "an undo or redo performed while this command ran was discarded: ..."}]}
```

Supply `_aether_dispatcher` and the warning can never occur.

A handler fails when it raises, raises `ToolError(code, message, details=...)`
(the structured form: the result value is `{"error": {"code", "message",
"details"}}`), returns a top-level `{"error": ...}` or `{"ok": false}`.
`error` keys *nested* deeper (per-item reports such as
`textures[3].error` or a render job's `job.error`) are collected as
`warnings` and never fail the call.

### External assets

Checkpoints do **not** embed library textures (`~/.elysium/textures`,
shared and large). Instead `assets.json` records every external reference
(`image_path`, `texture_path`, PBR maps, texture layers, per-part
textures, `file:` mesh imports) as `{path, exists, size, sha256}`.
`snapshot.restore` reports `missing_assets` and `changed_assets` by
re-hashing the files on disk; material slot images are embedded in the
document and always round-trip.

See [Designer > Aether > Safety and limits](https://designer.elysiumui.com/aether/safety-and-limits/).

## Providers

```python
daemon = Daemon(provider="anthropic")    # or "openai", "ollama"
```

The same providers as `elysium.ai`; same env vars. Switching
provider mid-session restarts the agent's working context.

## Bridge

The Designer opens a loopback HTTP server (port 8183, `ELYSIUM_AETHER_BRIDGE=1`)
so a CLI, an IDE plugin or a shell session can drive the live canvas
without a model in the loop. `elysium.aether.bridge.AetherBridge(designer, port)`
serves it; `elysium aether ...` is the client.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/state` | placements, window doc, selection, `revision` |
| `GET` | `/tools` | registry catalog with `side_effect`/`undoable`/`requires_confirmation` |
| `GET` | `/snapshot` | current canvas as PNG |
| `GET` | `/logs?n=200` | recent audit entries |
| `GET` | `/events` | SSE: `tool_call`, `tool_result` (pushed when the command settles — also after a 202, and for cancellations), `feedback_observed`, `user_feedback`, `control` |
| `GET` | `/status` | `paused`/`stopped`/`busy` (queued + running > 0), `pace_ms`, `last_call`, `operations` queue depth |
| `GET` | `/operations/<id>` | receipt of a command (never gated) |
| `POST` | `/tool` | `{id?, name, args, confirm?, wait?}` → receipt |
| `POST` | `/operations/<id>/cancel` | cancel a still-queued command (never gated) |
| `POST` | `/pause` `/resume` `/stop` `/pace` `/feedback` | user control |
| `POST` | `/chat` | run an Aether turn in the Designer's daemon |

### Acknowledged commands

`POST /tool` is an **acknowledged, idempotent operation**. Commands are
journalled by `elysium.aether.execution.Operations` and executed one at a
time on the Designer's frame thread (or inline, serialized against each
other, when the Designer supplies no dispatcher — the undo history is then
shared with the frame thread, see above). The reply is the receipt:

```json
{"id": "cli-3f2…", "name": "placement.move", "status": "committed",
 "ok": true, "value": {"x": 40, "y": 12}, "revision": 17, "attempts": 1,
 "snapshot": "snap-20260913-101500-a1b2c3", "warnings": [],
 "feedback_observed": [], "_bridge": {"paused": false, "stopped": false}}
```

* `status` is `queued` → `running` → `committed` | `failed` | `cancelled`.
* `revision` is the document revision after the command in *both*
  terminal states (unchanged on failure). `/state` reports the same counter.
* `id` is chosen by the client. Resubmitting the same id with the same
  `name`/`args`/`confirm` returns the same receipt with `attempts`
  incremented — the command **never executes twice**. A different payload
  under a used id is a 400. Ids are never evicted during a session.
* `wait` (0–120 s, default 25 s) is how long the request blocks for the
  receipt; it is transport-only and not part of the idempotency signature.

| HTTP | When |
|---|---|
| 200 | `committed` |
| 202 | still `queued`/`running` after `wait` — poll `GET /operations/<id>`, do not resubmit with a new id |
| 400 | `failed` (schema, handler, checkpoint, persist), or a malformed request |
| 409 | `confirmation_required` (resubmit with `confirm: true` and a new id), or a client cancel |
| 423 | paused or stopped (`{"error": "aether_paused", "hint", "since_last_call_s"}` / `{"error": "aether_stopped", "hint"}`); also a queued command cancelled by `/stop` |
| 503 | the journal cannot accept the request (`retry_after_s`) |

`POST /stop` cancels every queued command with `reason: "aether_stopped"`;
`/operations/<id>` and `/operations/<id>/cancel` stay reachable while
paused or stopped so a client can always learn its command's fate.
`/tool`, `/state` and `/snapshot` stay hands-off until `/resume`.
`pace_ms` delays the *reply* after the commit (on the HTTP thread), never
execution. `/status.busy` is derived from the journal in the same reply as
`operations` (queued + running > 0), so the two never disagree. A tool that
raises `SystemExit`/`KeyboardInterrupt` (`exit()` inside `dev.eval`) is a
failed, rolled-back command like any other — it never ends the frame loop.

```sh
elysium aether call -m placement.move --args '{"id":"entity:…","x":40,"y":12}'
elysium aether call -m dev.eval --args '{"code":"len(designer.placements)"}' --confirm
elysium aether call -m mesh.import_3d --args '{…}' --id job-42 --wait 90   # retry-safe
elysium aether op --id job-42
elysium aether cancel --id job-42
```

`call` always sends an id; on a 202 or a transport timeout it polls the
receipt for the rest of `--wait` and never resubmits (exit 0 committed,
2 failed/cancelled, 3 still pending, 1 transport error).

See [Bridge and port](https://designer.elysiumui.com/aether/bridge-and-port/).

## Performance

Each tool call adds ~50-200 ms latency (model + tool execution).
Streamed responses arrive token-by-token so the user sees activity
immediately. The agent is deliberately patient: it never makes
many tool calls without explanation.

## See also

- [AI workflows](ai.md): batch one-shot AI.
- [Recipes: expose a custom tool](../recipes/24-custom-aether-tool.md)
- [Designer > Aether](https://designer.elysiumui.com/aether/)
