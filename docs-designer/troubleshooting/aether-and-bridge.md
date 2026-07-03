# Aether and bridge troubleshooting

The Aether agent runs locally and talks to the framework over a
small IPC bridge. Most problems are either provider-side (API
key, rate limit) or bridge-side (socket, port).

## "No AI provider configured"

Set one:

```sh
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
# or run Ollama locally; defaults to http://localhost:11434
```

Then restart the Designer. Provider can also be picked at runtime
in `Preferences > AI > Provider`.

## Aether chat unresponsive

| Try | Why |
|---|---|
| Refresh the chat panel (`Cmd/Ctrl+R`) | Reconnects to the bridge socket |
| Check the bridge socket exists at `~/.elysium/sessions/elysium-default.sock` | The IPC server may have stopped |
| Switch provider | Provider may be rate-limited |
| Open the dev console (`Help > Open Aether Log`) | See stack traces |

## Tool call rejected

The agent calls a tool; the Designer rejects it.

| Reason | Fix |
|---|---|
| Confirmation required | Click "Allow" in the confirmation dialog; or auto-confirm the tool in `Preferences > AI > Safety` |
| Scope blocked | The active session's scope does not include the target placement. Open a new session with broader scope. |
| Schema mismatch | The model produced invalid args. Retry; if persistent, file a bug with the tool call payload. |

## Bridge port collision

The Aether bridge binds to `localhost:<random-high-port>` by
default. To pin:

```sh
export ELYSIUM_BRIDGE_PORT=51001
```

Useful when running multiple Designers, or when corporate firewalls
require a specific port.

## Tools list looks short

The agent sees only tools relevant to the current session scope.
If you scoped to a single placement, only that placement's tools
appear. Open a new session with `scope=window` (or no scope at
all) to see the full 123-tool catalog.

## High latency

| Cause | Fix |
|---|---|
| Anthropic provider with large input | Truncate the conversation history (`Session > New`) |
| OpenAI provider rate-limited | Wait, or switch to Anthropic |
| Ollama on CPU | Use a discrete GPU, or switch to a cloud provider |
| Network proxy | Ensure HTTPS proxy is reachable from the Designer |

## Privacy

Aether reads:

- The active skin's manifest and document.
- The session scope (the placement / window you pointed it at).
- The conversation history.

It does **not** read:

- Your application Python code.
- Files outside the active project folder.
- System credentials beyond the AI provider key (which lives in
  the OS keychain).

## Logs

| Where | What |
|---|---|
| `Help > Open Aether Log` | Per-session log: model calls, tool calls, errors |
| `~/Library/Logs/Elysium Designer/aether.log` (macOS) | Persisted log; same for Windows / Linux per platform conventions |
| `Preferences > AI > Log Level` | `debug` / `info` / `warn` / `error` |

`debug` shows every model request and response in full; useful
when filing bugs.

## See also

- [Aether](../aether/index.md)
- [Safety and limits](../aether/safety-and-limits.md)
- [Bridge and port](../aether/bridge-and-port.md)
