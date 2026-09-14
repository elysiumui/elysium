# Safety and limits

Confirmation prompts, sandbox, rate limits.

## What a tool may touch

Every tool declares its `side_effect` (shown in `elysium aether tools` and
`GET /tools`):

| Class | Meaning | Checkpoint / undo |
|---|---|---|
| `read` | Looks, never touches. | none |
| `none` | Changes only transient state — selection, playhead, zoom, caches, files outside the project (texture library tiles, landmark presets), the running app. | none |
| `write` | Changes the document or the paired code file. | checkpoint, one undo entry, revision +1 |
| `destructive` | Cannot be undone from the document alone: deleting or overwriting files, stopping the app, `dev.eval`, hot reloads, `snapshot.restore`. | checkpoint + confirmation per policy |

## Confirmation

| `requires_confirmation` | cautious trust | collaborative (default) | autonomous |
|---|---|---|---|
| `never` | every write | no | no |
| `destructive` | every write | destructive tools | destructive tools |
| `always` | yes | yes | yes |

Over the bridge a refused call answers **409** `confirmation_required`;
resend with `"confirm": true` (`--confirm` in the CLI) and a new id. In the
chat daemon the approval callback is asked. `dev.eval` always asks.

## Every write is a transaction

1. A checkpoint (skin folder, code file, chat history, external-asset hash
   manifest) is written **before** the handler runs. If that fails the
   command is refused: `Cannot checkpoint command`.
2. The handler runs with its arguments validated against the tool schema.
3. Headless sessions save the layout before acknowledging: a failed save
   fails the command.
4. Success publishes exactly one undo step — including owned mesh
   geometry — and bumps the revision. Failure rolls the document and the
   undo/redo history back to what they were, together, so the two never
   disagree. If the Designer supplies no `_aether_dispatcher`, a command
   runs on the bridge's own thread and a user undo/redo performed while it
   runs is discarded and reported as a `history` warning on the receipt;
   with a dispatcher the race cannot happen.

Library textures are not copied into checkpoints; `snapshot.restore`
reports which referenced files have gone missing or changed since the
checkpoint (`missing_assets`, `changed_assets`). Material slot images are
embedded in the document and always come back.

## Limits

* The bridge binds to loopback only and has no authentication; do not
  expose it.
* Request ids live for the bridge session (up to 10 000); when the journal
  is full you get **503** and must restart the bridge.
* A single `/tool` request waits at most 120 s; longer commands return
  **202** and are polled.
* `run.start` / `code.*` tools refuse paths outside the project root.
