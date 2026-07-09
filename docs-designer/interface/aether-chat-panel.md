# Aether agent (headless)

The Designer no longer has an in-app Aether chat panel. The former
chat panel and its floating action button were removed (2026-07).

Aether still exists — as a **headless backend agent**. It reads the
scene and runs the Designer's ~123 tools, but it is driven
programmatically over the AetherBridge HTTP API on
`127.0.0.1:8183` (by CLIs, the IDE plugin, and Claude Code
sessions), not from a window inside the app.

- [Aether](../aether/index.md) — what the agent is and how to reach
  it over the bridge.
- [Aether and bridge troubleshooting](../troubleshooting/aether-and-bridge.md)
  — provider and bridge fixes.
