# Aether chat panel

Aether is the Designer's in-app AI agent. It can read your scene,
run any of the 123 tools the Designer exposes, and explain what it
did. The chat panel is how you talk to it.

![Aether chat panel docked to the right of the View Panel mid-conversation](../assets/interface-aether-chat.png)

## Opening

| Path | Where |
|---|---|
| `File > 🌌 Aether (chat with the agent)…` | Menu bar |
| `Cmd+/` (macOS) or `Ctrl+/` (other) | Keyboard |
| The 🌌 button on the shelf | Quick-access |

The panel opens floating by default. Drag its title bar to dock it
to any edge of the window; the layout persists.

## Anatomy

- **Conversation log**: top region. Aether's messages are rendered
  with markdown, code blocks, and "tool call" cards.
- **Tool call cards**: collapsible panels showing exactly which
  tool Aether invoked, the arguments, and the result. Useful for
  audit and reproducibility.
- **Input field**: bottom, two-line by default; press Shift+Enter
  to add a newline, Enter to send.
- **Session controls**: top-right: new session, history, snapshot,
  settings.

## Sessions

Each conversation lives in a session. Sessions remember the
Designer's snapshot at the start (which placements existed, the
current selection, the active menu set) so future questions can
reference "the wing" or "the brush we just authored".

`Session > New` starts fresh; `Session > History` lists previous
sessions (searchable by content).

## Providers

The active provider is set in `Preferences > AI`. Aether supports:

| Provider | Latency | Best for |
|---|---|---|
| Anthropic Claude | Low | Default. Best at multi-step tool use. |
| OpenAI GPT-4 | Low | Strong general assistant. |
| Ollama (local) | Higher | Free, offline. Slower; smaller models. |

Switching provider mid-session restarts the agent's context. The
panel shows which provider is active in the bottom-left.

## What Aether can do

The 123 tools span 15 modules: `mesh`, `theme`, `render`, `anim`,
`rig`, `sim`, `procedural`, `brush`, `path`, `curves`, `window`,
`view`, `arrange`, `file`, `code`. Examples:

- "Make the butterfly's iridescence warmer." → `theme.set_palette`,
  `render.adjust_material`.
- "Rotate this wing 10 degrees around its hinge." →
  `mesh.set_channel`, `anim.set_key`.
- "Scaffold a Python handler for the play button." →
  `code.scaffold_handlers`.
- "Show me the current Render Quality." → `render.get_quality`.

The full catalog with example prompts is in the
[Aether tool reference](../reference/aether-tool-reference.md)
(auto-generated from the shipping code).

## Safety

Aether asks for confirmation before destructive actions: deleting
placements, overwriting baked textures, exporting to disk. The
confirm dialog shows the exact tool call so you know what is about
to run. Configure auto-confirm thresholds in
[Safety and limits](../aether/safety-and-limits.md).

## Snapshots

`Session > Snapshot` saves the current scene state as a named
restore point. Aether sees snapshots and can "go back to the
snapshot before we tried the BBox pipeline" without you using
undo manually.

## Code surface

Everything Aether can do is also reachable from the menu bar and
the toolbox. The chat panel is a convenience surface, not a
necessity. The same actions are scriptable from a paired Python
handler via the [Code Link](../code-link/index.md) bridge.
