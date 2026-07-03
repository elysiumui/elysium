# `elysium.aether`

The in-app agent: a chat session backed by a model with access to
123 tools across 15 modules.

## Core classes

| Class | Purpose |
|---|---|
| `Daemon` | Owns the model connection; spawns sessions |
| `Session` | One conversation thread |
| `Snapshot` | A named restore point of scene state |
| `Provider` | Base for model providers |
| `AnthropicProvider` / `OpenAIProvider` / `OllamaProvider` | Concrete providers |
| `Tool` | Base for agent-callable tools |
| `Registry` | Catalog of registered tools |
| `ChatPanel` | Embeddable UI component for in-app chat |

## Functions

| Function | Purpose |
|---|---|
| `register_tool(id)` | Decorator to register a `Tool` subclass |

## Bridge

| Symbol | Purpose |
|---|---|
| `bridge.connect()` | Connect to a running Designer's Aether socket |

## Tool catalog

The full catalog is auto-generated from shipping code. View it at
[aether-tools.partial.md](aether-tools.partial.md) (also included
in the Designer reference).

## Auto-rendered details

::: elysium.aether

## See also

- [Aether](../guides/aether.md)
- [Recipes: custom tool](../recipes/24-custom-aether-tool.md)
- [Designer > Aether](https://designer.elysiumui.com/aether/)
