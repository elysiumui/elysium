"""LLM-backed skin generation, modification, and polish.

Providers are pluggable via the `Provider` protocol. The Anthropic
provider is the default; OpenAI and a deterministic local "stub"
provider are also shipped.

    from elysium import ai
    skin = await ai.generate_skin(
        prompt="A glassmorphic music player with a circular play button.",
        hooks=["play.click", "track.title.text", "progress.value"],
        size=(960, 540),
    )
    skin.save("skins/generated.esk/")

If no API key is set, the stub provider returns a deterministic procedural
skin so tests and the Designer can run offline.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Provider protocol + built-in implementations.
# ---------------------------------------------------------------------------

@runtime_checkable
class Provider(Protocol):
    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str: ...


class AnthropicProvider:
    """Calls the Anthropic Messages API. Requires ANTHROPIC_API_KEY in env.
    Imports the SDK lazily so the dep is optional."""
    def __init__(self, model: str = "claude-opus-4-7", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("AnthropicProvider: ANTHROPIC_API_KEY not set")

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "AnthropicProvider needs `pip install anthropic`."
            ) from e
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        msg = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if hasattr(block, "text"))


class OpenAIProvider:
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OpenAIProvider: OPENAI_API_KEY not set")

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("OpenAIProvider needs `pip install openai`.") from e
        client = openai.AsyncOpenAI(api_key=self.api_key)
        resp = await client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


class StubProvider:
    """Offline provider that returns a deterministic procedural skin
    based on the prompt + requested hooks. Used in tests, in the
    Designer's offline mode, and as a fallback when no API key is set."""
    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        # Extract the requested hooks from the user message (we know the
        # format because `_user_prompt_for_skin` is the only caller).
        try:
            body = json.loads(user)
        except json.JSONDecodeError:
            return json.dumps(_fallback_skin(["greeting.click", "message.text"], 480, 320))
        return json.dumps(_fallback_skin(
            body.get("hooks", ["greeting.click", "message.text"]),
            body.get("size", (480, 320))[0],
            body.get("size", (480, 320))[1],
        ))


# ---------------------------------------------------------------------------
# Provider resolution.
# ---------------------------------------------------------------------------

def _make_provider(spec: str | Provider | None) -> Provider:
    if isinstance(spec, Provider):  # type: ignore[arg-type]
        return spec
    if spec is None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicProvider()
        if os.environ.get("OPENAI_API_KEY"):
            return OpenAIProvider()
        return StubProvider()
    if isinstance(spec, str):
        if ":" in spec:
            kind, model = spec.split(":", 1)
        else:
            kind, model = spec, None
        if kind == "anthropic":
            return AnthropicProvider(model=model or "claude-opus-4-7")
        if kind == "openai":
            return OpenAIProvider(model=model or "gpt-4o")
        if kind == "stub":
            return StubProvider()
    raise ValueError(f"unknown provider spec: {spec!r}")


# ---------------------------------------------------------------------------
# Prompt construction.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_FOR_SKIN = """You are a UI designer for Elysium UI, a Python desktop framework.
You produce `.esk` skin documents — JSON describing a scene-tree of vector paths,
gradients, shadows, and hooks for behavior wiring.

When given a brief, output ONLY a JSON object matching this exact shape:

{
  "manifest": {
    "schema_version": "1.0",
    "id": "dev.elysium.generated",
    "name": "<short title>",
    "version": "0.1.0",
    "color_space": "srgb"
  },
  "document": {
    "root": {
      "type": "scene",
      "size": {"w": <int>, "h": <int>},
      "background": {"type": "color", "value": "#RRGGBB"},
      "children": [
        {"type": "path", "id": "...", "d": "M ... Z",
         "fill": {"type": "linear_gradient", "stops": [[0.0, "#HEX"], [1.0, "#HEX"]], "angle": 135},
         "effects": [{"type": "outer_shadow", "offset": [0,12], "blur": 40, "color": "#0000007F"}],
         "hooks": [{"name": "...", "type": "event", "events": ["click"]}]
        },
        ...
      ]
    }
  }
}

Rules:
- All numeric path data uses SVG path mini-language (M, L, H, V, Q, C, S, T, Z; no A).
- Every hook listed in the brief MUST appear in the document.
- Choose tasteful, accessible colours; respect requested theme cues.
- Output ONLY the JSON object. No markdown, no commentary."""


def _user_prompt_for_skin(prompt: str, hooks: list[str], size: tuple[int, int]) -> str:
    return json.dumps({
        "prompt": prompt,
        "hooks": hooks,
        "size": list(size),
    })


def _fallback_skin(hooks: list[str], w: int, h: int) -> dict:
    """Deterministic procedural skin used when no LLM is available."""
    pad = min(w, h) * 0.08
    cw = w - 2 * pad
    ch = h - 2 * pad
    rect_d = (
        f"M {pad + 24} {pad} L {pad + cw - 24} {pad} "
        f"Q {pad + cw} {pad} {pad + cw} {pad + 24} "
        f"L {pad + cw} {pad + ch - 24} Q {pad + cw} {pad + ch} {pad + cw - 24} {pad + ch} "
        f"L {pad + 24} {pad + ch} Q {pad} {pad + ch} {pad} {pad + ch - 24} "
        f"L {pad} {pad + 24} Q {pad} {pad} {pad + 24} {pad} Z"
    )
    children: list[dict] = [
        {
            "type": "path",
            "id": "card",
            "d": rect_d,
            "fill": {"type": "linear_gradient",
                     "stops": [[0.0, "#5B3FF5"], [1.0, "#FF5C8A"]], "angle": 135},
            "effects": [{"type": "outer_shadow", "offset": [0, 12], "blur": 40,
                         "color": "#0000007F"}],
            "hooks": [{"name": h, "type": _hook_type_from_name(h)} for h in hooks],
        }
    ]
    return {
        "manifest": {
            "schema_version": "1.0",
            "id": "dev.elysium.generated",
            "name": "Generated Skin",
            "version": "0.1.0",
            "color_space": "srgb",
        },
        "document": {
            "root": {
                "type": "scene",
                "size": {"w": w, "h": h},
                "background": {"type": "color", "value": "#0E0B1A"},
                "children": children,
            }
        },
    }


def _hook_type_from_name(name: str) -> str:
    if name.endswith(".click") or name.endswith(".hover"): return "event"
    if name.endswith(".text"):  return "text"
    if name.endswith(".image"): return "image"
    if name.endswith(".value"): return "value"
    if name.endswith(".state"): return "state"
    return "event"


# ---------------------------------------------------------------------------
# Generated skin output type.
# ---------------------------------------------------------------------------

@dataclass
class GeneratedSkin:
    manifest: dict
    document: dict

    def save(self, path: str | os.PathLike) -> Path:
        """Write the skin as an unzipped `.esk` directory."""
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(self.manifest, indent=2))
        (out / "document.json").write_text(json.dumps(self.document, indent=2))
        return out


@dataclass
class SkinDiff:
    before: dict
    after: dict
    notes: str = ""

    def preview(self) -> str:
        """Return a unified-diff string of the JSON serializations."""
        import difflib
        a = json.dumps(self.before, indent=2, sort_keys=True).splitlines()
        b = json.dumps(self.after,  indent=2, sort_keys=True).splitlines()
        return "\n".join(difflib.unified_diff(a, b, lineterm="", n=2,
                                              fromfile="before", tofile="after"))

    def apply(self, to: str | os.PathLike) -> Path:
        out = Path(to)
        out.mkdir(parents=True, exist_ok=True)
        if "manifest" in self.after:
            (out / "manifest.json").write_text(json.dumps(self.after["manifest"], indent=2))
        if "document" in self.after:
            (out / "document.json").write_text(json.dumps(self.after["document"], indent=2))
        return out

    def discard(self) -> None: ...


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------

async def generate_skin(
    prompt: str,
    hooks: list[str],
    size: tuple[int, int] = (960, 540),
    provider: str | Provider | None = None,
) -> GeneratedSkin:
    """Generate a `.esk` skin from a natural-language prompt.

    The provider returns a JSON document that we validate + load into
    a `GeneratedSkin` ready to `.save(...)`.
    """
    prov = _make_provider(provider)
    raw = await prov.complete(
        _SYSTEM_PROMPT_FOR_SKIN,
        _user_prompt_for_skin(prompt, hooks, size),
        max_tokens=4096,
    )
    # LLMs occasionally wrap JSON in ```json fences; strip if present.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json\n"): cleaned = cleaned[5:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        body = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Fall back to the stub so the call still produces a usable skin.
        body = _fallback_skin(hooks, size[0], size[1])
        body["manifest"]["description"] = f"LLM produced invalid JSON: {e}; fell back."
    return GeneratedSkin(
        manifest=body.get("manifest", {}),
        document=body.get("document", {}),
    )


async def modify_skin(
    skin: dict | str | os.PathLike,
    prompt: str,
    provider: str | Provider | None = None,
) -> SkinDiff:
    """Take an existing skin and apply a natural-language modification.
    Returns a `SkinDiff` you can preview / apply / discard."""
    if not isinstance(skin, dict):
        path = Path(skin)
        manifest = json.loads((path / "manifest.json").read_text())
        document = json.loads((path / "document.json").read_text())
        before = {"manifest": manifest, "document": document}
    else:
        before = skin

    prov = _make_provider(provider)
    system = _SYSTEM_PROMPT_FOR_SKIN + (
        "\n\nThe user will provide the CURRENT skin JSON and a MODIFICATION request. "
        "Return the FULL updated skin JSON. Preserve every hook and id unless the "
        "request explicitly removes one."
    )
    user_body = json.dumps({
        "current": before,
        "modification": prompt,
    })
    raw = await prov.complete(system, user_body, max_tokens=8192)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json\n"): cleaned = cleaned[5:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        after = json.loads(cleaned)
    except json.JSONDecodeError:
        after = before  # no-op if the LLM mangled JSON
    return SkinDiff(before=before, after=after, notes=prompt)


async def magic_polish(
    skin: dict | str | os.PathLike,
    *,
    provider: str | Provider | None = None,
    intensity: str = "balanced",   # "subtle" | "balanced" | "bold"
) -> SkinDiff:
    """Run the AI 'Magic Polish' pass over a skin — picks restrained tweaks
    that improve gradient quality, shadow softness, spacing, and animation
    cues. Returns a SkinDiff."""
    intensities = {
        "subtle":   "Make conservative, taste-driven improvements.",
        "balanced": "Make moderate improvements — refine gradients, deepen "
                    "shadows slightly, tighten spacing, add subtle animation cues.",
        "bold":     "Make pronounced improvements — premium gradients, layered "
                    "shadows, generous radii, opinionated motion curves.",
    }
    direction = intensities.get(intensity, intensities["balanced"])
    return await modify_skin(skin, f"Apply Magic Polish. {direction}", provider=provider)


__all__ = [
    "Provider", "AnthropicProvider", "OpenAIProvider", "StubProvider",
    "generate_skin", "modify_skin", "magic_polish",
    "GeneratedSkin", "SkinDiff",
]
