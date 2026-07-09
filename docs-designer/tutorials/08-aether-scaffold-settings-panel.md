# Aether scaffolds a settings panel

Time: 30 minutes. Difficulty: Intermediate.

Use the Aether agent to scaffold a complete settings panel for an
existing skin. The agent picks the right components, lays them
out, and binds them to signals: your job is to describe what the
settings should be.

## Prerequisites

- A running Designer with the AetherBridge enabled (the default;
  disabled only when `ELYSIUM_AETHER_BRIDGE=0`).
- An AI provider configured (`Preferences > AI`, or via
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`).
- An existing skin with a hook for opening settings (any of the
  earlier tutorials' outputs works).

## Reach the agent

Aether is headless — you drive it over the bridge on
`127.0.0.1:8183`. Every instruction below is a `POST /chat`
request. Confirm the bridge is up first:

```sh
curl -s http://127.0.0.1:8183/state | head
```

## Describe the panel

A good prompt names the toggles, sliders, and selects you want.
Send it as the `message` of a `POST /chat` request. For example,
with this prompt:

> "Add a settings panel to this skin. It should have:
>
> - A theme dropdown (Midnight Glass / Frost / OLED).
> - A toggle for 'Reduce motion' (default off).
> - A slider 'Window opacity' (0.4 to 1.0, default 1.0).
> - A toggle 'Always on top' (default on).
> - A 'Close' button at the bottom right.
>
> Lay it out as a Form. The window should be 380 x 320,
> borderless rounded-rect, glass-dark material."

post it to the bridge:

```sh
curl -s http://127.0.0.1:8183/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Add a settings panel to this skin with a theme dropdown (Midnight Glass / Frost / OLED), a Reduce motion toggle (default off), a Window opacity slider (0.4 to 1.0, default 1.0), an Always on top toggle (default on), and a Close button at the bottom right. Lay it out as a Form. The window should be 380 x 320, borderless rounded-rect, glass-dark material."}'
```

Aether responds by:

1. Adding a Settings sub-window placement (or a new `.esk`).
2. Calling `arrange.align_*` to lay out the form.
3. Calling `aether.bind_signal` per control to wire the reactive
   state.
4. Reporting what it did in the response transcript.

## Review the result

Run > Preview Skin (or open the settings hook on the existing
skin). The panel appears.

If something looks off, send another `POST /chat` message:

> "Make the slider track narrower and add more vertical spacing
> between controls."

The agent iterates.

## Lock in the layout

Once you are happy, `File > Save`. The settings layout is now
part of your `document.json`.

## Wire the signals

Aether exposes hook names like `settings.theme.change`,
`settings.reduce_motion.change`, etc. Your runtime code binds
them:

```python
@window.on("settings.theme.change")
def on_theme(event):
    set_theme(THEMES[event.value])
```

The Aether session log shows the exact hook names it created —
read it over the bridge with `GET /logs`.

## Tips

- Run the agent against a blank skin first to author the panel,
  then `Edit > Copy Placement Group` and paste into your real
  skin.
- For consistency across panels, prefix every settings hook with
  `settings.` so they're easy to search and bind.
- Take a snapshot before you start so you can revert if the agent
  goes off course.

## What you exercised

- The AetherBridge `POST /chat` endpoint.
- Multi-step tool calls.
- The arrange.* and aether.bind_signal tools.
- Iterative refinement via follow-up prompts.

## See also

- [Aether index](../aether/index.md)
- [Aether cookbook](../aether/cookbook.md)
- [Code Link](../code-link/index.md)
