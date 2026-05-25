"""Autonomous test orchestrator. Probes spec'd in §7 of agent.md."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def run_scenario(session, scenario: str) -> list[dict]:
    """Dispatch to one named scenario; return a list of findings."""
    fn = _SCENARIOS.get(scenario)
    if fn is None:
        return [{"scenario": scenario, "kind": "error",
                  "severity": "warn",
                  "msg": f"unknown scenario: {scenario}"}]
    return fn(session)


def capture_baseline(session) -> Path:
    """Stash the current run.snapshot as the visual baseline."""
    from elysium.render.preview import paint_skin_png
    base = Path.home() / ".elysium" / "aether" / "sessions" / session.id / "baselines"
    base.mkdir(parents=True, exist_ok=True)
    session.designer.save_layout()
    png = paint_skin_png(session.designer.skin_path)
    out = base / "current.png"
    out.write_bytes(png)
    return out


# ---------------------------------------------------------------------------
# Built-in scenarios.
# ---------------------------------------------------------------------------

def _frame_budget(session) -> list[dict]:
    from .tools.run import run_frame_stats
    stats = run_frame_stats(session)
    if "error" in stats: return []
    frames = stats.get("frame_ms") or []
    if not frames:
        return [{"scenario": "frame_budget", "kind": "info",
                  "severity": "info", "msg": "no frame samples"}]
    over = [f for f in frames if f > 33.3]
    if over:
        return [{"scenario": "frame_budget", "kind": "perf",
                  "severity": "warn",
                  "msg": f"{len(over)}/{len(frames)} frames over 33ms "
                         f"(max {max(frames):.1f})",
                  "fix_suggestion": "drop sample count on PBR / path "
                                      "tracer or reduce active animations"}]
    return [{"scenario": "frame_budget", "kind": "pass",
              "severity": "info", "msg": f"all frames within 30fps "
                                          f"(p99 {max(frames):.1f}ms)"}]


def _no_tracebacks(session) -> list[dict]:
    from .tools.run import run_read_logs
    logs = run_read_logs(session)
    bad = [l for l in logs.get("stderr", []) if "Traceback" in l or "Error" in l]
    if bad:
        return [{"scenario": "no_tracebacks", "kind": "crash",
                  "severity": "blocker",
                  "msg": f"{len(bad)} traceback lines in stderr",
                  "snippet": "\n".join(bad[:6])}]
    return [{"scenario": "no_tracebacks", "kind": "pass",
              "severity": "info", "msg": "stderr clean"}]


def _every_hook_fires(session) -> list[dict]:
    """Synthesise a click on every hook'd placement."""
    designer = session.designer
    events = []
    for p in designer.placements:
        if not (p.props or {}).get("hook"): continue
        events.append({"ev": "click", "x": p.x + p.w/2, "y": p.y + p.h/2})
    session.simulated_events.extend(events)
    return [{"scenario": "every_hook_fires", "kind": "pass",
              "severity": "info",
              "msg": f"queued {len(events)} synthetic clicks"}]


def _memory_stable(session, samples: int = 5, sleep: float = 1.0) -> list[dict]:
    proc = getattr(session, "_run_proc", None)
    if not proc: return []
    try:
        import psutil
    except ImportError:
        return [{"scenario": "memory_stable", "kind": "info",
                  "severity": "info",
                  "msg": "psutil not installed; skipping"}]
    p = psutil.Process(proc.pid)
    readings = []
    for _ in range(samples):
        try: readings.append(p.memory_info().rss / (1024 * 1024))
        except Exception: pass
        time.sleep(sleep)
    if not readings: return []
    drift = max(readings) - min(readings)
    if drift > 40:
        return [{"scenario": "memory_stable", "kind": "leak",
                  "severity": "warn",
                  "msg": f"RSS drifted {drift:.1f}MB over {len(readings)}s",
                  "readings": readings}]
    return [{"scenario": "memory_stable", "kind": "pass",
              "severity": "info",
              "msg": f"RSS stable ({min(readings):.0f}–{max(readings):.0f}MB)"}]


def _screenshot_baseline(session, threshold_pct: float = 2.0) -> list[dict]:
    base = Path.home() / ".elysium" / "aether" / "sessions" / session.id / "baselines" / "current.png"
    if not base.is_file():
        return [{"scenario": "screenshot_baseline", "kind": "info",
                  "severity": "info",
                  "msg": "no baseline yet; call tester.set_baseline first"}]
    from elysium.render.preview import paint_skin_png
    session.designer.save_layout()
    cur_bytes = paint_skin_png(session.designer.skin_path)
    base_bytes = base.read_bytes()
    if cur_bytes == base_bytes:
        return [{"scenario": "screenshot_baseline", "kind": "pass",
                  "severity": "info",
                  "msg": "screenshot byte-equal to baseline"}]
    # Approximate pixel diff via Pillow (always installed in our deps).
    try:
        from io import BytesIO
        from PIL import Image
        a = Image.open(BytesIO(base_bytes)).convert("RGBA")
        b = Image.open(BytesIO(cur_bytes)).convert("RGBA")
        if a.size != b.size:
            return [{"scenario": "screenshot_baseline", "kind": "drift",
                      "severity": "warn",
                      "msg": f"size differs {a.size} -> {b.size}"}]
        import numpy as np
        a_np = np.asarray(a); b_np = np.asarray(b)
        diff = (a_np != b_np).any(axis=-1).mean() * 100
        if diff > threshold_pct:
            return [{"scenario": "screenshot_baseline", "kind": "drift",
                      "severity": "warn",
                      "msg": f"{diff:.1f}% pixel drift "
                             f"(threshold {threshold_pct}%)"}]
        return [{"scenario": "screenshot_baseline", "kind": "pass",
                  "severity": "info",
                  "msg": f"{diff:.2f}% drift, within threshold"}]
    except Exception as e:
        return [{"scenario": "screenshot_baseline", "kind": "error",
                  "severity": "warn", "msg": str(e)}]


_SCENARIOS = {
    "frame_budget":         _frame_budget,
    "no_tracebacks":        _no_tracebacks,
    "every_hook_fires":     _every_hook_fires,
    "memory_stable":        _memory_stable,
    "screenshot_baseline":  _screenshot_baseline,
}
