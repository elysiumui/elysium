"""Aether API-key store.

Reads / writes ``~/.elysium/credentials.json`` with mode 0o600 (owner
read/write only) so saved keys aren't world-readable.

Layout:

    {
      "anthropic": "sk-ant-...",
      "openai":    "sk-...",
      "gemini":    "AIza...",
      "deepseek":  "sk-..."
    }

`load_into_env()` runs at Designer startup and copies each stored key
into `os.environ[<PROVIDER>_API_KEY]` so the providers' lazy `os.environ
.get(...)` lookups succeed without the user having to set shell env
vars. `pick_provider()` returns the highest-priority provider that has
a key (used to switch `aether_provider` away from the stub on startup).

Important: the file lives in the user's home dir, not in the .esk
bundle, so saved keys never leak into the skin distribution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


# Mapping between the short provider name we use everywhere and the
# environment-variable convention each SDK reads. Keep these in sync
# with `providers/__init__.py::_AUTO_ORDER`.
PROVIDERS: list[tuple[str, str]] = [
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("openai",    "OPENAI_API_KEY"),
    ("gemini",    "GEMINI_API_KEY"),
    ("deepseek",  "DEEPSEEK_API_KEY"),
]

# Display labels (Title Case) used in menu entries + dialogs.
DISPLAY_LABELS: dict[str, str] = {
    "anthropic": "Anthropic (Claude)",
    "openai":    "OpenAI (GPT)",
    "gemini":    "Google (Gemini)",
    "deepseek":  "DeepSeek",
}


def _store_path() -> Path:
    home = Path(os.environ.get("HOME") or os.path.expanduser("~"))
    return home / ".elysium" / "credentials.json"


def load() -> dict[str, str]:
    """Read the saved credentials. Returns an empty dict if the file
    is missing or corrupt — never raises."""
    p = _store_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def save(provider: str, api_key: str) -> Path:
    """Write `api_key` for `provider` to the store, creating the dir
    + setting mode 0o600 on first write. Returns the store path."""
    if not api_key:
        raise ValueError("api_key must be non-empty")
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    current = load()
    current[provider] = api_key
    p.write_text(json.dumps(current, indent=2))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def remove(provider: str) -> bool:
    p = _store_path()
    if not p.is_file():
        return False
    current = load()
    if provider not in current:
        return False
    current.pop(provider, None)
    p.write_text(json.dumps(current, indent=2))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return True


def load_into_env() -> list[str]:
    """Copy every saved key into `os.environ`. Returns the list of
    provider names that were loaded (so callers can prefer them when
    auto-selecting an active provider)."""
    loaded: list[str] = []
    creds = load()
    by_env = dict(PROVIDERS)
    for provider, key in creds.items():
        env = by_env.get(provider)
        if env and key:
            os.environ.setdefault(env, key)
            loaded.append(provider)
    return loaded


def pick_provider(prefer: Iterable[str] = ()) -> str:
    """Pick the highest-priority provider that has a key set (either in
    the store or in the environment). `prefer` is an explicit override
    order; otherwise we use PROVIDERS' canonical priority."""
    creds = load()
    order = list(prefer) + [name for name, _ in PROVIDERS
                              if name not in prefer]
    by_env = dict(PROVIDERS)
    for name in order:
        if creds.get(name):
            return name
        env = by_env.get(name)
        if env and os.environ.get(env):
            return name
    return "stub"
