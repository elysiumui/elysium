"""run.*: launch the user app, screenshot it, drive synthetic input,
read frame stats from the existing Inspector channel."""
from __future__ import annotations

import base64
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import register_tool
from ..types import SideEffect


def _safe_entry(session, path: str | None) -> Path:
    p = Path(path) if path else session.code_file()
    p = p.resolve()
    root = session.project_root.resolve()
    if root not in p.parents and p != root:
        raise PermissionError(f"refusing entry outside project root: {p}")
    return p


@register_tool(
    name="run.start",
    description="Spawn the user app as a subprocess with ELYSIUM_INSPECTOR=1.",
    input_schema={"type": "object",
                   "properties": {"entry": {"type": "string"},
                                   "env":   {"type": "object"}}},
)
def run_start(session, entry: str | None = None,
              env: dict | None = None) -> dict:
    e = _safe_entry(session, entry)
    env_full = os.environ.copy()
    env_full["ELYSIUM_INSPECTOR"] = "1"
    env_full["ELYSIUM_HOT_RELOAD"] = "1"
    if env: env_full.update({str(k): str(v) for k, v in env.items()})
    proc = subprocess.Popen(
        [sys.executable, str(e)],
        env=env_full,
        cwd=str(session.project_root),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    session.run_pid = proc.pid
    session._run_proc = proc
    return {"pid": proc.pid, "entry": str(e)}


@register_tool(
    name="run.stop",
    description="Stop the running app (SIGTERM).",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.DESTRUCTIVE,
    requires_confirmation="never",
)
def run_stop(session) -> dict:
    proc = getattr(session, "_run_proc", None)
    if not proc: return {"stopped": False, "reason": "no app running"}
    try: proc.send_signal(signal.SIGTERM)
    except Exception: pass
    proc.wait(timeout=2)
    session.run_pid = None
    session._run_proc = None
    return {"stopped": True}


@register_tool(
    name="run.snapshot",
    description="Capture the current Designer scene or Layout as PNG, including authored materials and lights. This is a Designer preview, not a capture of an independently running app. Does not save or mutate the project.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def run_snapshot(session) -> dict:
    from elysium.render.designer_preview import paint_designer_png
    png = paint_designer_png(session.designer)
    return {"png_b64": base64.b64encode(png).decode(), "bytes": len(png),
            "source": "designer", "view": "scene" if getattr(session.designer.window_doc, "scene_view", False) else "layout"}



@register_tool(
    name="run.simulate_input",
    description="Post synthetic mouse / keyboard events into the running "
                "app via the Designer's existing input plumbing. Events: "
                "{ev: 'click'|'move'|'key', x, y, code?}.",
    input_schema={"type": "object",
                   "properties": {"events": {"type": "array"}},
                   "required": ["events"]},
)
def run_simulate_input(session, events: list) -> dict:
    # v1 surface: records the events; the runtime-side consumer
    # ships in Phase 4.2 alongside the daemon. For now, append to
    # the per-session journal so the agent can reason about them.
    session.simulated_events.extend(events)
    return {"queued": len(events)}


@register_tool(
    name="run.read_logs",
    description="Drain stdout / stderr from the running app.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def run_read_logs(session) -> dict:
    proc = getattr(session, "_run_proc", None)
    if not proc: return {"lines": []}
    out, err = [], []
    # Non-blocking peek (proc.stdout might be None).
    for stream, sink in ((proc.stdout, out), (proc.stderr, err)):
        if not stream: continue
        import select
        while True:
            rl, _, _ = select.select([stream], [], [], 0)
            if not rl: break
            line = stream.readline()
            if not line: break
            sink.append(line.decode(errors="replace").rstrip())
    return {"stdout": out, "stderr": err}


@register_tool(
    name="run.frame_stats",
    description="Pull the latest frame timing + hook traffic from the "
                "Inspector TCP endpoint of the running app.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def run_frame_stats(session) -> dict:
    port = int(os.environ.get("ELYSIUM_INSPECTOR_PORT", "11434"))
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.sendall(b"get_stats\n")
        line = b""
        while not line.endswith(b"\n"):
            chunk = s.recv(8192)
            if not chunk: break
            line += chunk
        s.close()
        import json
        return json.loads(line)
    except Exception as e:
        return {"error": str(e)}
