# AI-assisted redesign

Time: 20 minutes. Difficulty: Intermediate.

Take the [Aurora Clock](../getting-started/aurora-clock-01-window.md)
you built in Getting Started and run `ai.modify_skin` on it with a
natural-language prompt. Watch the clock re-theme in real time.

## Prerequisites

- A finished `aurora_clock.esk/` from the lead Aurora Clock tutorial.
- An `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`, or local Ollama).

If you do not have a key, use the offline `stub` provider: it will
deterministically produce a procedural variant rather than a
creative one, but the workflow is the same.

## Add a "Redesign" button to the skin

Append to `aurora_clock.esk/document.json`:

```json
{
  "id": "redesign_btn",
  "kind": "button",
  "x": 144, "y": 248,
  "width": 72, "height": 24,
  "label": "Redesign",
  "font_size": 10,
  "fill": "#a78bfaff",
  "text_fill": "#0f0d1eff",
  "radius": 12
}
```

## Wire the button to `ai.modify_skin`

```python
import asyncio
from elysium import ai

@window.on("redesign_btn.click")
async def redesign(event):
    print("Redesigning…")
    diff = await ai.modify_skin(
        "aurora_clock.esk/",
        "Make it sunset themed: warm oranges, soft pinks, low "
        "contrast, more emphasis on the breathing glow.",
    )
    if not diff.changes:
        print("No changes suggested.")
        return
    print(diff.summary())
    diff.apply("aurora_clock.esk/")
    window.load_skin("aurora_clock.esk/")
```

`@window.on(...)` accepts async handlers; the framework awaits
them. `ai.modify_skin` returns a `SkinDiff`. `diff.apply(...)`
writes changes to the bundle; `window.load_skin(...)` hot-reloads
the live window.

## What gets changed

`SkinDiff.summary()` typically prints something like:

```
+ background.fill   #0f0d1eff -> #3a1f0eff
+ dial.stroke       #a78bfaff -> #f97316ff
+ glow.fill         #7c3aedff -> #f97316ff
+ sweep_arc.stroke  #f0abfcff -> #fde68aff
* time_label.fill   #ffffffff (kept)
```

Only declared color and shadow fields move; structure stays
intact. The model is deliberately conservative.

## Selective apply

To review before committing:

```python no-check
diff = await ai.modify_skin("aurora_clock.esk/", "...")
print(diff.preview())   # unified diff
diff.apply("aurora_clock.esk/", only=["background", "glow", "dial"])
```

## Iteration

Bind a series of prompts to different keys for fast iteration:

```python
PROMPTS = {
    "1": "Sunset themed: warm oranges, soft pinks.",
    "2": "Cyberpunk: high contrast neon teal and magenta.",
    "3": "Forest: cool greens, soft browns.",
    "4": "Original: revert to the default Midnight Glass theme.",
}

@window.on("window.key")
async def quick_redesign(event):
    if not event.pressed or event.code not in PROMPTS:
        return
    diff = await ai.modify_skin("aurora_clock.esk/", PROMPTS[event.code])
    diff.apply("aurora_clock.esk/")
    window.load_skin("aurora_clock.esk/")
```

Press 1 / 2 / 3 / 4 to audition four full re-themes.

## Aether vs ai.modify_skin

`ai.modify_skin` is one-shot. For multi-turn ("tighten the spacing,
then make the play button bigger"), open an Aether session:

```python
from elysium.aether import Daemon

daemon = Daemon(provider="anthropic")
session = daemon.new_session(scope=window)
session.send("Make it sunset themed.")
# wait for it…
session.send("Now make the glow more dramatic.")
```

See [Aether guide](../guides/aether.md).

## What you exercised

- `ai.modify_skin` async API.
- `SkinDiff.preview()` / `.summary()` / `.apply()`.
- Hot-reload via `window.load_skin` (preserves window state).
- Async event handlers.

## See also

- [AI workflows](../guides/ai.md)
- [Aether](../guides/aether.md)
- [Recipes: Aether redesign at runtime](../recipes/25-aether-redesign-runtime.md)
