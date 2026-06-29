# AI workflows

`elysium.ai` is a thin async layer over Anthropic / OpenAI /
Ollama / a deterministic offline stub. Set
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` to use a real provider;
otherwise the stub returns a usable procedural skin so tests and
Designer offline mode still produce output.

## Generate a skin from a prompt

```python
import asyncio
from elysium import ai

skin = asyncio.run(ai.generate_skin(
    prompt="A glassmorphic music player with a circular play button.",
    hooks=["play.click", "track.title.text", "progress.value"],
    size=(960, 540),
))
skin.save("generated.esk/")
```

`hooks` is the contract: the model returns a skin that exposes
these hook names. Your Python code can then bind handlers without
knowing the visual structure.

## Modify an existing skin

```python
diff = asyncio.run(ai.modify_skin(
    "my.esk/",
    "Increase corner radius to 16, swap accent to teal, soften shadows.",
))
print(diff.preview())     # unified diff
diff.apply("my.esk/")     # commit if you like it
```

Returns a `SkinDiff` you can review before applying. The diff
operates on `document.json`, `manifest.json`, and embedded styles;
it never modifies your Python code.

## Magic Polish

A pre-prompted variant tuned for restrained taste-driven
improvements:

```python
diff = asyncio.run(ai.magic_polish("my.esk/", intensity="balanced"))
```

Intensities: `gentle` (1-3 changes), `balanced` (5-10), `bold`
(20+). Available from the Designer's `File > ✨ Magic Polish` menu;
the output lands at `<skin>.polished/` so you can A/B before
adopting.

## SkinDiff

The `SkinDiff` object returned by `modify_skin` / `magic_polish`:

```python
diff.summary()        # human-readable list of changes
diff.preview()        # unified diff against the original
diff.changes          # list of (placement_id, field, before, after)
diff.apply(path)      # write changes to disk
diff.apply(path, only=["btn_play", "btn_pause"])   # selective
```

## Providers

```python
ai.set_provider("anthropic")     # or "openai" / "ollama" / "stub"
```

Per-provider env vars:

| Provider | Env var |
|---|---|
| anthropic | `ANTHROPIC_API_KEY` |
| openai | `OPENAI_API_KEY` |
| ollama | `OLLAMA_HOST` (default `http://localhost:11434`) |
| stub | none |

`stub` is the offline deterministic provider used in CI and when
no API key is available. It produces a procedural skin shaped to
your hooks parameter; not creative but reliable.

## Aether vs ai

`elysium.ai` is a **batch** API: call once, get a result. The
[Aether](aether.md) agent is **interactive**: a chat session
where the model can call any of 123 Designer tools across multiple
turns.

Use `elysium.ai` for one-shot integrations ("generate a skin from
this prompt"); use Aether for "talk to the designer about my
project".

## Safety

- Generated skins are **opened**, never auto-saved over your
  source.
- Any bundled WGSL is sandboxed via `naga::front::wgsl::parse_str`
  before submission to wgpu.
- AI never reads your application code: only the manifest,
  document, and the user prompt.

## Determinism

```python no-check
result = await ai.generate_skin(prompt="...", seed=42)
```

A fixed seed pins the model's sampling. Useful for tests; not all
providers honor seeds rigidly, so treat as a hint.

## Caching

Identical prompts cache for 24 hours by default:

```python
ai.set_cache_ttl(seconds=3600)
```

Cache lives at `~/.elysium/ai_cache/`. Disable with `set_cache_ttl(0)`.

## See also

- [Aether](aether.md): interactive agent.
- [Skins](skins.md): what `generate_skin` produces.
- [Recipes: ask Aether to redesign at runtime](../recipes/25-aether-redesign-runtime.md)
