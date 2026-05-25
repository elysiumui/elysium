"""LLM provider abstraction. All providers stream `StreamEvent` objects
to the daemon's tool-use loop."""
from .base      import Provider
from .anthropic import AnthropicProvider
from .ollama    import OllamaProvider
from .stub      import StubProvider
from .gemini    import GeminiProvider
from .deepseek  import DeepSeekProvider


# OpenAI shares the chat-completions wire format with DeepSeek, so we
# re-use the same streaming code (in DeepSeekProvider.stream) and just
# change the env var / host. No `openai` package dependency.
from .deepseek import _OpenAIChatCompletionsProvider


class OpenAIProvider(_OpenAIChatCompletionsProvider):
    name = "openai"
    _env_var = "OPENAI_API_KEY"
    _default_host = "https://api.openai.com"
    _default_model = "gpt-4o"

    # Borrow DeepSeekProvider's streaming impl unchanged.
    stream = DeepSeekProvider.stream


# Provider auto-detection order — picked when `make_provider(None)` is
# called. Anthropic-first because the Designer's system prompts + tool
# schemas are tuned for Claude; others are accepted as alternatives.
_AUTO_ORDER: list[tuple[str, str]] = [
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("openai",    "OPENAI_API_KEY"),
    ("gemini",    "GEMINI_API_KEY"),
    ("deepseek",  "DEEPSEEK_API_KEY"),
]


def make_provider(spec: str | Provider | None) -> Provider:
    """`anthropic[:model]`, `openai[:model]`, `gemini[:model]`,
    `deepseek[:model]`, `ollama[:model]`, `stub`, or a live Provider.

    When `spec` is None or "auto", picks the first provider whose env
    var is set, falling back to the stub when none are configured.
    """
    import os
    if isinstance(spec, Provider):
        return spec
    if spec in (None, "auto"):
        for name, env in _AUTO_ORDER:
            if os.environ.get(env):
                return _spawn(name, model=None)
        return StubProvider()
    if isinstance(spec, str):
        kind, _, model = spec.partition(":")
        try:
            return _spawn(kind, model=model or None)
        except KeyError:
            pass
    raise ValueError(f"unknown provider spec: {spec!r}")


def _spawn(kind: str, *, model: str | None) -> Provider:
    if kind == "anthropic":
        return AnthropicProvider(model=model or "claude-opus-4-7")
    if kind == "openai":
        return OpenAIProvider(model=model or "gpt-4o")
    if kind == "gemini":
        return GeminiProvider(model=model or "gemini-1.5-flash")
    if kind == "deepseek":
        return DeepSeekProvider(model=model or "deepseek-chat")
    if kind == "ollama":
        return OllamaProvider(model=model or "llama3.1")
    if kind == "stub":
        return StubProvider()
    raise KeyError(kind)


__all__ = [
    "Provider",
    "AnthropicProvider", "OpenAIProvider",
    "GeminiProvider", "DeepSeekProvider",
    "OllamaProvider", "StubProvider",
    "make_provider",
]
