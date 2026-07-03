# How do I ask Aether to redesign my skin at runtime?

For a one-shot batch request, use `elysium.ai.modify_skin`. For
an interactive multi-turn redesign, open an Aether session.

## One-shot

```python
import asyncio
from elysium import ai

diff = asyncio.run(ai.modify_skin(
    "my.esk/",
    "Make it sunset themed: warm oranges, soft pinks, low contrast.",
))

if diff.changes:
    diff.apply("my.esk/")
    window.load_skin("my.esk/")     # hot-reload picks it up automatically
```

`modify_skin` returns a `SkinDiff`. Inspect with `.summary()` or
`.preview()`, apply with `.apply(path)`. Selective apply via
`diff.apply(path, only=[...])`.

## Multi-turn

```python
from elysium.aether import Daemon

daemon = Daemon(provider="anthropic")
session = daemon.new_session(scope=window)

session.send("Tighten the spacing in the toolbar.")
# Aether responds, possibly calling arrange.align_* and adjusting padding.

session.send("Now make the play button bigger.")
# Aether continues from the previous state.
```

Each `session.send(...)` runs the agent's turn. Tool calls log to
the session's history; access via `session.history` for an audit
trail.

For UI integration (a chat bubble panel inside your app), embed
the Aether component:

```python
from elysium.aether import ChatPanel
window.add(ChatPanel(id="aether_chat", session=session))
```

See [Aether](../guides/aether.md) and [AI](../guides/ai.md).
