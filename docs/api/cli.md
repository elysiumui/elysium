# `elysium.cli`

Console entry points. The `elysium` script lives here.

## Subcommands

| Command | Function | Purpose |
|---|---|---|
| `elysium dev` | `dev_command` | Hot-reload file watcher |
| `elysium doctor` | `doctor_command` | Diagnose installation |
| `elysium aether` | `aether_command` | Interactive Aether REPL |
| `elysium pack` | `pack_command` | Build a signed bundle |
| `elysium new` | `new_command` | Scaffold a project |
| `elysium skins` | `skins_command` | Marketplace subcommands |

## Programmatic dispatch

```python
from elysium.cli import dispatch
dispatch(["dev", "myapp.py"])     # equivalent to `elysium dev myapp.py`
```

Useful for testing or embedding the CLI in larger tooling.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Generic error |
| 2 | Bad usage |
| 3 | Native lib missing |
| 4 | AI provider error |
| 5 | Build / packaging error |

## Auto-rendered details

::: elysium.cli

## See also

- [CLI](../guides/cli.md)
