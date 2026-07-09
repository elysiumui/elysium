# Aether

Aether is the Designer's **headless AI agent**. It can read the
current scene, run any of the **~123 tools across 15 modules** the
Designer exposes, and report what it did — all without a graphical
panel inside the app. There is no in-app chat window: Aether is
driven programmatically over a small local HTTP bridge.

That makes Aether a first-class automation surface. The same agent
is driven by command-line tools, the editor / IDE plugin, and
Claude Code sessions pointed at a running Designer.

!!! info "No in-app panel"
    The former in-app Aether chat panel and its floating action
    button were removed (2026-07). Aether now runs headless and is
    reached only through the bridge described below. See the
    [Aether agent (headless)](../interface/aether-chat-panel.md)
    note in the interface section.

## The AetherBridge

When the Designer launches it starts **AetherBridge**, a local
HTTP server bound to `127.0.0.1:8183`. Anything that can make an
HTTP request on localhost can drive the agent: read state, list
tools, call a tool directly, or hold a natural-language
conversation.

The bridge is **on by default**. It is controlled by one
environment variable:

| Variable | Default | Effect |
|---|---|---|
| `ELYSIUM_AETHER_BRIDGE` | `1` (on) | Set to `0` to disable the bridge entirely |
| `ELYSIUM_AETHER_BRIDGE_PORT` | `8183` | Override the port the bridge binds to |

```sh
# Disable the bridge for a session
ELYSIUM_AETHER_BRIDGE=0 elysium-designer

# Move it off the default port
ELYSIUM_AETHER_BRIDGE_PORT=51001 elysium-designer
```

See [Environment variables](../reference/environment-variables.md)
for the full list.

## Endpoints at a glance

All endpoints are served from `http://127.0.0.1:8183`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/state` | Current scene / session snapshot as JSON |
| `GET` | `/tools` | The full tool catalog (name, schema, side-effect flags) |
| `GET` | `/snapshot` | The current Designer render as an image |
| `GET` | `/logs` | Recent agent + tool-call log lines |
| `GET` | `/events` | Server-Sent Events stream of state / tool / log events |
| `POST` | `/tool` | Call one tool directly: `{ "name": …, "args": … }` |
| `POST` | `/chat` | Send a natural-language message: `{ "message": …, "provider"?: … }` |

## Quick smoke test

With a Designer running, confirm the bridge is up:

```sh
curl -s http://127.0.0.1:8183/state | head
```

A JSON document describing the active skin, selection, and menu
set means the agent is reachable. If the request is refused, the
bridge is disabled (`ELYSIUM_AETHER_BRIDGE=0`) or bound to a
different port (`ELYSIUM_AETHER_BRIDGE_PORT`).

## Two ways to drive it

- **Call tools directly** with `POST /tool` when you already know
  exactly which action you want (`mesh.set_channel`,
  `render.set_quality`, …). Deterministic, no model in the loop.
- **Chat** with `POST /chat` when you want the agent to plan a
  multi-step change from a natural-language description. The model
  chooses and sequences the tools for you.

See [Getting started with Aether](getting-started.md) for concrete
`curl` recipes for both.

## Where to next

- [Getting started](getting-started.md) — first requests, session
  and snapshot flow, provider selection.
- [Concepts](concepts.md) — tools, plans, approvals, transcripts.
- [Bridge and port](bridge-and-port.md) — bridge internals and the
  `:8183` contract.
- [Aether tool reference](../reference/aether-tool-reference.md) —
  the complete auto-generated tool catalog.
- [Safety and limits](safety-and-limits.md) — confirmation and
  scope rules.
- [Aether and bridge troubleshooting](../troubleshooting/aether-and-bridge.md)
  — provider and bridge fixes.
