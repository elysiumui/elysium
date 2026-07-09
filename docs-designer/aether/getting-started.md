# Getting started with Aether

This page walks an agent or developer through driving the Designer
programmatically over the [AetherBridge](index.md): checking the
bridge is up, listing tools, calling one directly, and holding a
natural-language conversation. Everything happens over HTTP on
`127.0.0.1:8183` — there is no in-app panel to open.

## Prerequisites

- A running Designer. The bridge starts automatically unless
  `ELYSIUM_AETHER_BRIDGE=0`.
- For `POST /chat`, an AI provider key in the environment (or set
  in `Preferences > AI`):

  ```sh
  export ANTHROPIC_API_KEY=sk-ant-...
  # or
  export OPENAI_API_KEY=sk-...
  # or run Ollama locally (defaults to http://localhost:11434)
  ```

  Direct tool calls (`POST /tool`) need **no** provider — they run
  without a model in the loop.

## 1. Confirm the bridge is reachable

```sh
curl -s http://127.0.0.1:8183/state
```

`GET /state` returns a JSON snapshot of the current session: the
active skin, the current selection, the active menu set, and any
open snapshots. This is the first call an agent should make to
orient itself.

If the connection is refused, see
[Aether and bridge troubleshooting](../troubleshooting/aether-and-bridge.md).

## 2. Discover the tools

```sh
curl -s http://127.0.0.1:8183/tools
```

`GET /tools` returns the full catalog — every tool's `name`,
argument schema, whether it has a side effect, and whether it is
undoable. The ~123 tools span 15 modules: `mesh`, `theme`,
`render`, `anim`, `rig`, `sim`, `procedural`, `brush`, `path`,
`curves`, `window`, `view`, `arrange`, `file`, `code`.

The same catalog, rendered for humans with one-line purposes, is
the [Aether tool reference](../reference/aether-tool-reference.md).

## 3. Call a tool directly

When you know exactly which action you want, `POST /tool` runs it
deterministically — no model involved:

```sh
# Read the current render quality
curl -s http://127.0.0.1:8183/tool \
  -H 'content-type: application/json' \
  -d '{"name": "render.get_quality", "args": {}}'

# Rotate the selected wing 10 degrees around its hinge
curl -s http://127.0.0.1:8183/tool \
  -H 'content-type: application/json' \
  -d '{"name": "mesh.set_channel", "args": {"channel": "rotate_z", "value": 10}}'
```

The response contains the tool result (and, for side-effecting
tools, whether the change is undoable). Destructive tools may
require confirmation — see [Safety and limits](safety-and-limits.md).

## 4. Chat with the agent

When you want the agent to plan a multi-step change from a
description, `POST /chat` puts a model in the loop to choose and
sequence tools for you:

```sh
curl -s http://127.0.0.1:8183/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Make the butterfly'\''s iridescence warmer."}'
```

The agent replies with a transcript that includes the natural
language answer and the tool calls it made (e.g. `theme.set_palette`,
`render.adjust_material`). Because the response streams tool calls
as it works, you can also watch progress live on `GET /events`
(Server-Sent Events).

### Selecting a provider

`POST /chat` uses the default provider unless you override it
per-request:

```sh
curl -s http://127.0.0.1:8183/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Scaffold a settings panel.", "provider": "anthropic"}'
```

| `provider` | Notes |
|---|---|
| `anthropic` | Default. Strongest at multi-step tool use. |
| `openai` | Strong general assistant. |
| `ollama` | Local / offline; slower, smaller models. |

The default and API keys are configured in `Preferences > AI` or
via the provider environment variables above.

## Sessions and snapshots over the bridge

State returned by `GET /state` is the agent's session context: the
Designer snapshot at the start of the conversation (which
placements existed, the current selection, the active menu set) so
follow-up messages can reference "the wing" or "the brush we just
authored".

`GET /snapshot` returns the current Designer render as an image —
useful for an agent that wants to *see* the result of a change
before deciding the next step. Named restore points created by the
`file`/session tools let the agent roll back without manual undo.

## Watching activity live

`GET /events` is a Server-Sent Events stream. Subscribe to it to
receive state changes, tool calls, and log lines as they happen —
the programmatic equivalent of watching the agent work:

```sh
curl -N http://127.0.0.1:8183/events
```

`GET /logs` returns the recent log buffer as a one-shot request if
you only need a tail rather than a live stream.

## Where to next

- [Concepts](concepts.md) — tools, plans, approvals, transcripts.
- [Cookbook](cookbook.md) — task-oriented recipes.
- [Bridge and port](bridge-and-port.md) — the `:8183` contract.
- [Aether tool reference](../reference/aether-tool-reference.md) —
  the full catalog.
- [Tutorial: Aether scaffolds a settings panel](../tutorials/08-aether-scaffold-settings-panel.md)
  — an end-to-end `POST /chat` walkthrough.
