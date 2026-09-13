# Bridge and port

The :8183 bridge and how the agent talks to Designer.

Start Designer with `ELYSIUM_AETHER_BRIDGE=1` and it listens on
`http://127.0.0.1:8183` (loopback only, no authentication — every process
on your loopback is yours). `elysium aether …` is the client; any HTTP
client works.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/state` | placements, window doc, selection, `revision` |
| `GET` | `/tools` | tool catalog with `side_effect` / `undoable` / `requires_confirmation` |
| `GET` | `/snapshot` | current canvas as PNG |
| `GET` | `/logs?n=200` | recent audit entries |
| `GET` | `/events` | server-sent events: `tool_call`, `tool_result` (when the command settles — also after a 202, and for cancellations), `feedback_observed`, `user_feedback`, `control` |
| `GET` | `/status` | paused / stopped / busy (queued + running > 0), `pace_ms`, last call, operation queue depth |
| `GET` | `/operations/<id>` | receipt of a command — readable even while paused or stopped |
| `POST` | `/tool` | `{id?, name, args, confirm?, wait?}` → receipt |
| `POST` | `/operations/<id>/cancel` | cancel a command that has not started yet |
| `POST` | `/pause` · `/resume` · `/stop` · `/pace` · `/feedback` | user control |
| `POST` | `/chat` | run an Aether turn |

## Every call is a receipt

Commands are queued and run one at a time on Designer's frame thread, so
they never race your mouse. The reply to `POST /tool` is the receipt:

```json
{"id": "cli-…", "name": "placement.move", "status": "committed", "ok": true,
 "value": {"x": 40, "y": 12}, "revision": 17, "attempts": 1,
 "snapshot": "snap-…", "warnings": []}
```

* `status`: `queued` → `running` → `committed` | `failed` | `cancelled`.
* `revision`: the document revision after the command (unchanged when it
  failed). `/state` shows the same number, so you can tell whether the
  canvas already reflects a call.
* `id`: pick it yourself. Sending the same id again returns the same
  receipt (`attempts` goes up) — the command **never runs twice**, so a
  timed-out client just asks again. Reusing an id for a different command
  is a 400.
* `wait`: seconds to block for the receipt (default 25, max 120). When it
  runs out you get **202** and the receipt so far; poll
  `GET /operations/<id>`.

| HTTP | Meaning |
|---|---|
| 200 | committed |
| 202 | still pending after `wait` — poll, don't resubmit |
| 400 | failed (bad arguments, handler error, checkpoint or save failure) or a malformed request |
| 409 | confirmation required — resend with `"confirm": true` and a new id; or you cancelled it |
| 423 | you paused or stopped the agent (`aether_paused` / `aether_stopped`, with a `hint`) |
| 503 | the journal is full — start a new bridge session |

`POST /stop` cancels everything still queued (reason `aether_stopped`);
`/resume` hands control back. `/pace {"ms": 300}` slows the *replies* so
you can watch each step land; execution itself is never delayed.

## CLI

```sh
elysium aether state
elysium aether call -m placement.add --args '{"kind":"Card","x":40,"y":40,"w":200,"h":120}'
elysium aether call -m snapshot.restore --args '{"id":"snap-…"}' --confirm
elysium aether call -m mesh.import_3d --args '{…}' --id import-1 --wait 90
elysium aether op --id import-1          # read the receipt
elysium aether cancel --id import-1      # only while still queued
elysium aether watch                     # follow the event stream
```

`call` exits 0 when committed, 2 when failed or cancelled, 3 when still
pending after `--wait`, 1 when the bridge is unreachable.
