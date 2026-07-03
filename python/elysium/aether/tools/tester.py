"""tester.*: autonomous probes the agent runs to verify its own work."""
from __future__ import annotations

import base64
import time

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="tester.probe",
    description="Run a bundle of autonomous test scenarios against the "
                "running app. Returns a list of findings the agent can "
                "act on. Scenarios: 'frame_budget', 'no_tracebacks', "
                "'every_hook_fires', 'screenshot_baseline', 'memory_stable'.",
    input_schema={"type": "object",
                   "properties": {"scenarios": {"type": "array"}},
                   "required": ["scenarios"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def tester_probe(session, scenarios: list[str]) -> dict:
    from .. import tester as tt
    findings = []
    for s in scenarios:
        try:
            findings.extend(tt.run_scenario(session, s))
        except Exception as e:
            findings.append({"scenario": s, "kind": "error",
                              "msg": str(e), "severity": "warn"})
    return {"findings": findings, "count": len(findings)}


@register_tool(
    name="tester.set_baseline",
    description="Lock in the current canvas snapshot as the visual "
                "baseline for `screenshot_baseline` probes.",
    input_schema={"type": "object", "properties": {}},
)
def tester_set_baseline(session) -> dict:
    from .. import tester as tt
    path = tt.capture_baseline(session)
    return {"baseline": str(path)}


@register_tool(
    name="tester.replay",
    description="Replay a recorded user-input session against the running "
                "app for regression / repro purposes.",
    input_schema={"type": "object",
                   "properties": {"session_file": {"type": "string"}},
                   "required": ["session_file"]},
)
def tester_replay(session, session_file: str) -> dict:
    import json
    from pathlib import Path
    events = json.loads(Path(session_file).read_text())
    # Send them through the simulate_input pipeline.
    session.simulated_events.extend(events)
    return {"replayed": len(events)}
