# `elysium.ai`

Batch one-shot AI calls: generate a skin from a prompt, modify an
existing skin, polish a skin.

## Functions (async)

| Function | Purpose |
|---|---|
| `generate_skin(prompt, hooks=[], size=(960, 540), seed=None)` | Produce a fresh skin |
| `modify_skin(path, prompt, seed=None)` | Return a SkinDiff |
| `magic_polish(path, intensity='balanced')` | Return a curated SkinDiff |

## Classes

| Class | Purpose |
|---|---|
| `GeneratedSkin` | Result of `generate_skin`; has `.save(path)` |
| `SkinDiff` | Result of `modify_skin` / `magic_polish` |

## Provider control

| Function | Purpose |
|---|---|
| `set_provider(name)` | `"anthropic"` / `"openai"` / `"ollama"` / `"stub"` |
| `current_provider()` | Name of the active provider |
| `set_cache_ttl(seconds)` | Cache identical prompts |

## SkinDiff

```python
diff.summary()           # human-readable changes
diff.preview()           # unified diff
diff.changes             # list of (placement_id, field, before, after)
diff.apply(path)         # write changes
diff.apply(path, only=[...])    # selective
```

## Auto-rendered details

::: elysium.ai

## See also

- [AI workflows](../guides/ai.md)
- [Aether](../guides/aether.md): interactive (vs batch) alternative.
