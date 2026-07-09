# Environment variables

Every env var the Designer honors. Set in your shell, your CI
job, or the OS user environment.

## General

| Var | Effect |
|---|---|
| `ELYSIUM_LOG` | Log level: `debug` / `info` / `warn` / `error`. Default `info`. |
| `ELYSIUM_TELEMETRY` | `0` disables anonymous telemetry |
| `ELYSIUM_EDITOR` | Editor command for "Open paired Python file" |
| `VISUAL` / `EDITOR` | Fallback editor (if `ELYSIUM_EDITOR` not set) |

## AI providers

| Var | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Claude provider |
| `OPENAI_API_KEY` | OpenAI provider |
| `OLLAMA_HOST` | Ollama endpoint (default `http://localhost:11434`) |
| `ELYSIUM_AI_PROVIDER` | Override the default provider |

## Packaging / signing

| Var | Effect |
|---|---|
| `ELYSIUM_SIGNING_IDENTITY` | macOS Developer ID |
| `ELYSIUM_NOTARY_PROFILE` | macOS notarytool profile |
| `ELYSIUM_WINDOWS_CERT` | Path to a Windows PFX |
| `ELYSIUM_WINDOWS_CERT_PASSWORD` | Password for the above |
| `ELYSIUM_SIGN_KEY` | Hex-encoded 32-byte seed for marketplace signing |

## Renderer

| Var | Effect |
|---|---|
| `ELYSIUM_GPU_BACKEND` | Force a backend: `metal` / `dx12` / `vulkan` / `gl` / `cpu` |
| `ELYSIUM_TEXTURE_BUDGET_MB` | Override runtime texture budget |
| `ELYSIUM_RENDER_THREADS` | Number of CPU render threads |

## Hot reload

| Var | Effect |
|---|---|
| `ELYSIUM_IPC_SOCKET` | Override the IPC socket path |
| `ELYSIUM_NO_HOT_RELOAD` | `1` disables hot reload entirely |

## Designer-specific

| Var | Effect |
|---|---|
| `ELYSIUM_DESIGNER_HOME` | Override the per-user state directory |
| `ELYSIUM_DESIGNER_PLUGINS` | Path to extra plugins folder |
| `ELYSIUM_AETHER_BRIDGE_PORT` | Override the Aether bridge port |

## CLI

The `elysium` CLI inherits all of the above plus standard PATH /
PYTHONPATH conventions.

## See also

- [CLI](https://docs.elysiumui.com/guides/cli/) (framework)
- [File locations](file-locations.md)
- [Hot reload internals](hot-reload-internals.md)
