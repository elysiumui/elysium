# How do I expose a custom tool to Aether?

Subclass `aether.Tool` and decorate with `@register_tool`.

```python
from elysium.aether import register_tool, Tool

@register_tool("myapp.set_pomodoro_minutes")
class SetPomodoroMinutes(Tool):
    description = "Set the Pomodoro focus duration in minutes."
    args_schema = {
        "minutes": {"type": "integer", "minimum": 10, "maximum": 60},
    }
    confirmation_required = False

    def call(self, args, context):
        focus_minutes.set(args["minutes"])
        return {"ok": True, "new_value": args["minutes"]}
```

Once registered, Aether sees the tool in its catalog. When the
user says "Set focus to 40 minutes", the agent calls the tool with
`{"minutes": 40}` and your handler runs.

The `context` arg carries the active session, scope, and any
attached snapshots; use to read state without re-querying.

`confirmation_required = True` for destructive tools so the agent
prompts the user before calling.

See [Aether](../guides/aether.md).
