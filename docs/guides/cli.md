# CLI

`elysium` is the framework's command-line tool. It ships with the
PyPI install (`pip install elysium-ui`) and exposes the same surface
across macOS, Windows, and Linux.

```sh
elysium --help
```

## Subcommands

| Command | Purpose |
|---|---|
| `elysium dev <path>` | Watch a `.esk` skin and / or a `.py` file; hot-reload on change |
| `elysium doctor` | Diagnose installation issues |
| `elysium aether` | Interactive REPL with the Aether agent |
| `elysium pack <entry.py>` | Package the app as a signed standalone bundle per OS |
| `elysium new <name>` | Scaffold a new project |

## `elysium dev`

```sh
elysium dev myapp.py
elysium dev myapp.esk/
elysium dev .          # watch the current directory
```

Polls the path every 250 ms for changes. Skin edits hot-reload
in-place; Python edits restart the process while preserving window
position.

Flags:

- `--no-restart`: skin reloads only; ignore Python file edits.
- `--ipc-socket=PATH`: override the IPC socket path.
- `--log=LEVEL`: `debug` / `info` / `warn` / `error`.
- `--port=N`: expose the dev server on a TCP port (for remote
  pairing with the Designer).

## `elysium doctor`

```sh
elysium doctor
```

Checks the installation:

```
Elysium 0.1.0
Python 3.12.2 (cpython)
Platform: macOS 14.4 arm64

[ ok ] elysium._native loaded (wgpu, Skia, Bullet)
[ ok ] GPU: Apple M2 (Metal)
[ ok ] Wheels: arm64-darwin
[warn] ANTHROPIC_API_KEY not set; AI features will use the stub provider
[ ok ] No PYTHONPATH conflicts
```

Anything that errors or warns links to a troubleshooting page.

## `elysium aether`

```sh
elysium aether
```

Opens an interactive REPL with the agent. Connects to a running
Designer or app if one is broadcasting, otherwise runs in
standalone mode.

Flags:

- `--provider=NAME`: `anthropic` (default), `openai`, `ollama`,
  `stub`.
- `--snapshot=PATH`: load a saved scene snapshot before starting.
- `--scope=PATH`: restrict tool access to a specific skin folder.

## `elysium pack`

```sh
elysium pack myapp.py \
  --name "My App" \
  --identifier dev.example.app \
  --icon ./icon.png \
  --include myapp.esk
```

Wraps PyInstaller with sane defaults plus per-OS code signing.
Produces a `.app` on macOS, `.exe` + installer on Windows, and an
AppImage on Linux.

See [Packaging](packaging.md) for the full flag reference and
signing env vars.

## `elysium new`

```sh
elysium new my-clock --template aurora-clock
```

Scaffolds a new project:

- `my-clock/`
  - `aurora_clock.py`
  - `aurora_clock.esk/manifest.json`
  - `aurora_clock.esk/document.json`
  - `README.md`
  - `pyproject.toml`

Templates: `aurora-clock`, `pomodoro`, `stylized-music`,
`butterfly-banner`, `blank`. Each maps to a finished Getting
Started tutorial.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Generic error |
| 2 | Missing argument or invalid usage |
| 3 | Native library missing or failed to load |
| 4 | AI provider error |
| 5 | Build / packaging error |

`elysium doctor` always exits 0 unless the framework itself is
broken; warnings do not change the exit code.

## Environment variables

| Var | Effect |
|---|---|
| `ELYSIUM_LOG` | Default log level for the framework (`debug`, `info`, etc.) |
| `ELYSIUM_EDITOR` | Editor command for Code Link "open handler" |
| `ELYSIUM_AI_PROVIDER` | Default AI provider for `elysium.ai` |
| `ELYSIUM_SIGNING_IDENTITY` | macOS Developer ID for `elysium pack` |
| `ELYSIUM_NOTARY_PROFILE` | macOS notarytool profile name |
| `ELYSIUM_WINDOWS_CERT` | Path to a Windows PFX cert |
| `ELYSIUM_WINDOWS_CERT_PASSWORD` | Password for the above |
| `ELYSIUM_TELEMETRY` | Set to `0` to disable anonymous telemetry |

## See also

- [Hot reload](hot-reload.md): `elysium dev` internals.
- [Packaging](packaging.md): `elysium pack` details.
- [Code Link](code-link.md): editor integration.
