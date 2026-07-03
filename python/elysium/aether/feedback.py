"""Capability-gap reporter — writes feature requests the agent files
when it hits a framework wall."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any


def report_capability_gap(*, name: str, summary: str, severity: str,
                            sketch: dict | None = None,
                            session_id: str | None = None) -> Path:
    base = Path.home() / ".elysium" / "feedback"
    base.mkdir(parents=True, exist_ok=True)
    day = _dt.datetime.now().strftime("%Y-%m-%d")
    out = base / f"{day}.jsonl"
    entry = {
        "ts": _dt.datetime.now().isoformat(),
        "name": name,
        "summary": summary,
        "severity": severity,
        "sketch": sketch or {},
        "session_id": session_id,
    }
    with out.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return out


def list_pending() -> list[dict]:
    """Drain everything in the local feedback digest."""
    base = Path.home() / ".elysium" / "feedback"
    if not base.is_dir(): return []
    out = []
    for f in sorted(base.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            try: out.append(json.loads(line))
            except Exception: pass
    return out


def share_via_github(repo: str, *, dry_run: bool = True) -> int:
    """Open one GitHub draft issue per pending request via `gh`.
    Returns the count of issues created (or that would be created in
    dry-run mode). Requires the user to have opted in by calling this
    explicitly — never automatic."""
    import shutil, subprocess
    if shutil.which("gh") is None:
        raise RuntimeError("gh CLI not on PATH")
    items = list_pending()
    count = 0
    for it in items:
        body = json.dumps(it, indent=2)
        title = f"[Aether] {it['name']} ({it.get('severity', 'enhancement')})"
        if dry_run:
            print(f"[dry-run] would file: {title}")
        else:
            subprocess.run(["gh", "issue", "create",
                            "--repo", repo, "--title", title,
                            "--body", body, "--label", "aether-request"],
                            check=False)
        count += 1
    return count


__all__ = ["report_capability_gap", "list_pending", "share_via_github"]
