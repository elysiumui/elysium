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

Destructive tools (deletion, overwriting bakes, exports) require
**confirmation**: the agent asks before running. Configure the
confirmation policy:

```python
daemon.set_safety_policy(
    auto_confirm=["theme.*", "view.*"],     # auto-confirm UI-only tools
    require_confirm=["file.*", "mesh.*"],   # always ask for these
)
```

See [Designer > Aether > Safety and limits](https://designer.elysiumui.com/aether/safety-and-limits/).

## Providers

```python
daemon = Daemon(provider="anthropic")    # or "openai", "ollama"
```

The same providers as `elysium.ai`; same env vars. Switching
provider mid-session restarts the agent's working context.

## Bridge

Aether and the Designer talk over a local IPC socket
(`elysium-aether.sock`). Apps that want to drive the Designer from
the outside (or vice versa) hook in via:

```python
from elysium.aether import bridge
client = bridge.connect()
client.send("aether.user_message", {"text": "make the wings warmer"})
```

The Designer's chat panel and any embedded Aether sessions
multiplex over this bridge. See [Bridge and port](https://designer.elysiumui.com/aether/bridge-and-port/).

## Performance

Each tool call adds ~50-200 ms latency (model + tool execution).
Streamed responses arrive token-by-token so the user sees activity
immediately. The agent is deliberately patient: it never makes
many tool calls without explanation.

## See also

- [AI workflows](ai.md): batch one-shot AI.
- [Recipes: expose a custom tool](../recipes/24-custom-aether-tool.md)
- [Designer > Aether](https://designer.elysiumui.com/aether/)
