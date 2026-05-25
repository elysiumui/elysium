"""System prompt builder. Re-evaluated on every turn so the model
always sees the live capability manifest + current canvas summary."""
from __future__ import annotations

import json
import platform
from typing import Any

from .capabilities import build_manifest


PROMPT = """You are Aether — the Elysium UI agent, an autonomous collaborator
that designs, codes, and tests Elysium apps alongside the user.

You have access to a live Designer canvas, the running Python app,
the user's source file, and a tool registry that lets you operate
every part of the framework programmatically.

# Working surface
* Skin path:       {skin_path}
* Python entry:    {entry_file}
* Trust mode:      {trust_mode}
* User platform:   {user_platform}

# Framework capabilities
{capabilities}

# Currently on canvas
{placements_summary}

# Recent action history (last 8)
{action_log}

# Rules
1. Always plan before acting. Show a numbered plan; ask for approval
   only when the trust mode requires it.
2. Each tool call is a checkpoint. Prefer many small, reversible
   calls over one large one.
3. After every visible change, take a screenshot with `run.snapshot`
   and verify it matches what you intended. Self-correct silently
   when it doesn't.
4. When you need a capability the framework doesn't have, file it via
   `agent.report_capability_gap` and offer a workaround.
5. Never modify files outside the project root. Never push to git
   without explicit user confirmation. Never delete a snapshot.
6. Be specific in your descriptions of what you're doing so the user
   can follow along. Use the format:
       🔧 tool.name(args)
       ✓ what changed
7. The user sees every tool call streaming in real time. Pacing
   matters — don't issue 50 calls without explanation.

# Output format
Reply with natural prose interleaved with tool calls. The transport
handles tool-use blocks for you. Keep prose concise. End with a
one-line summary of what you did.
"""


def build(session) -> str:
    designer = session.designer
    placements_summary = _summarise_placements(designer)
    action_log = _recent_actions(session)
    return PROMPT.format(
        skin_path=str(designer.skin_path),
        entry_file=str(session.code_file()),
        trust_mode=session.trust.value,
        user_platform=platform.platform(),
        capabilities=json.dumps(build_manifest(), indent=2),
        placements_summary=placements_summary,
        action_log=action_log,
    )


def _summarise_placements(designer, limit: int = 30) -> str:
    rows = []
    for i, p in enumerate(designer.placements[:limit]):
        rows.append(f"- {p.name} ({p.kind}) @ ({int(p.x)},{int(p.y)}) "
                    f"size {int(p.w)}×{int(p.h)}")
    if len(designer.placements) > limit:
        rows.append(f"…and {len(designer.placements) - limit} more")
    return "\n".join(rows) or "(empty canvas)"


def _recent_actions(session, limit: int = 8) -> str:
    rows = []
    # Pull from audit if present.
    if session.audit_path and session.audit_path.is_file():
        lines = session.audit_path.read_text().splitlines()[-limit:]
        for ln in lines:
            try:
                e = json.loads(ln)
                if e.get("kind") == "tool_call":
                    rows.append(f"- {e['tool']}({_short(e.get('args'))})"
                                f" → {'ok' if e.get('ok') else e.get('error', 'err')}")
            except Exception: pass
    return "\n".join(rows) or "(no recent actions)"


def _short(d: Any, max_len: int = 80) -> str:
    s = json.dumps(d, default=str)
    return s if len(s) <= max_len else s[:max_len - 1] + "…"


__all__ = ["build"]
