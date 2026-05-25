# Aether Agent — Feature Specification

> Status: Phase 4 design. The runtime, Designer, LSP, and IDE plugin all
> exist; this spec describes the deep AI integration that fuses them
> into a single collaborative surface where a human and an LLM build
> apps together.

---

## 1. Vision

Today an Elysium developer's loop is: think → draw in Designer → wire
hooks in PyCharm → run → tweak. Each handoff costs context. Aether
collapses that loop into a single conversation. You describe what you
want; the agent picks up the pencil, the keyboard, and the run button
and works alongside you — visibly, in real time, in the actual
Designer canvas and the actual editor buffer.

It's not a code generator that drops a wall of JSON on you. It's an
autonomous *teammate* with the same affordances you have:

- It sees the canvas you see.
- It can use every tool you can — pen, shape, hook, timeline, brush,
  material studio, path-tracer, code-link, run button.
- It writes the Python handlers and runs the app.
- It watches the running app, notices what's broken, and fixes it.
- When it hits the framework's edges it tells the framework's
  maintainers what's missing.

The interaction is **always observable and always reversible**. Every
agent action is a checkpoint you can roll back to; every tool call is a
visible step in a transcript you can pause or branch from.

### Design tenets
1. **Glass-box, not black-box.** Every agent step is a tool call you
   can read. No hidden state, no opaque "AI did a thing."
2. **Human-grade affordances only.** The agent uses the same APIs the
   Designer's mouse and keyboard use. If the agent needs a capability
   the Designer doesn't have, the framework grows — never a backdoor.
3. **Live, not batch.** You watch the canvas update as the agent
   works. No "wait 30 seconds, then see the result."
4. **Reversible by default.** Snapshot before each step; one click to
   roll back any leg of the conversation.
5. **Local-first.** Works fully offline against a local model (Ollama
   / llama.cpp); remote providers (Anthropic, OpenAI, Google) are
   plug-replacements, not required.

---

## 2. User workflows

### 2.1 "Build me a photorealistic animated butterfly"
You open the Designer with a fresh `.esk`. In the Aether side panel:

> **You:** Build a photorealistic animated butterfly with no background
> or window border, floating gently with wing physics and landing on
> the middle of the screen, then show a banner that says "Elysium UI".

The agent streams:

```
🧠 Planning
   1. Make the window shaped + transparent (no chrome).
   2. Place a Mesh3D butterfly placement at the canvas centre.
   3. Pick a "Three-Point Hero" studio for warm-edge lighting.
   4. Apply iridescent wing material (metallic 0.8, clear-coat 0.9).
   5. Build a 3-state timeline: float-in → flap-loop → land.
   6. Add a banner placement that fades in after the landing.
   7. Scaffold the Python entry that runs it.
   8. Render Final to verify.

🔧 window.set_chrome(transparent=true, title_bar=false, shape="path")
   ✓ applied (snapshot #1)
🔧 placement.add(kind="Mesh3D", x=320, y=180, w=400, h=300,
                  name="Butterfly", props={"mesh": "Butterfly"})
   ✓ placement_id=p1 (snapshot #2)
🔧 window.set_studio("Three-Point Hero Studio")
   ✓ applied
🔧 placement.set_material(p1, preset="Metal — Iridescent Pearl",
                            clear_coat=0.9, anisotropy=0.7)
   ✓ canvas updated
🔧 animation.add_state(p1, name="float_in",
                         dx=0, dy=-40, scale=0.6, opacity=0.0,
                         duration=0.8, easing="ease_out")
   ✓
…
```

The canvas updates after each call. After 30 seconds you have a real
butterfly on transparent canvas. The agent then:

```
🔧 codelink.scaffold(hook="banner.fade_in")
   ✓ wrote on_banner_fade_in to app/main.py:24
🔧 run.start(entry="app/main.py")
   ✓ pid=58213
🔧 run.snapshot()
   📸 (image)
🤔 The wings clip the top of the screen at frame 8. Adjusting the
   pre-landing arc to keep the apex at y=120.
🔧 animation.modify_state(p1, "float_in", dy=-20)
   ✓ hot-reloaded
```

The whole thing — geometry, materials, lighting, animation, code,
verification — without you typing another character.

### 2.2 "Make the wings feel less stiff"
After the butterfly demo runs:

> **You:** The wings feel too stiff.

```
🔧 designer.read_animation(p1, "flap_loop")
   ↳ {keyframes: [{flap: 0.0, t: 0.0}, {flap: 1.0, t: 0.4}]}
🤔 Two keyframes with linear easing makes wing motion feel mechanical.
   Splitting into 4 keyframes with overshoot + adding a phase offset
   between forewing + hindwing.
🔧 animation.replace_keyframes(p1, "flap_loop", [
     {flap: 0.0, t: 0.0,  easing: "ease_in_out"},
     {flap: 1.1, t: 0.18, easing: "ease_out"},
     {flap: 0.95, t: 0.30, easing: "linear"},
     {flap: 0.0, t: 0.40, easing: "ease_in"}])
   ✓
🔧 placement.set_property(p1, "hindwing_phase_offset", 0.04)
   ✓
🔧 run.snapshot()
   📸 (compare)
🤔 Better. Wings now have soft-tissue swing. Want me to also adjust
   the body sway?
```

### 2.3 "What is this framework missing?"

> **You:** I want a particle system for the wing trail.

```
🔍 Searching capability registry…
   ❌ No particle component shipped in elysium.components.
   ❌ No DrawCommand::Particles in the render pipeline.

📝 Filed: framework_request:particle_system_v1 (severity: blocker)
   → opened draft GitHub issue elysium-ui/elysium#142
   → posted spec sketch (emitter, lifetime, sprite atlas, GPU evaluator)

⚙ Workaround: I can fake it with N small Mesh3D placements driven by
  a SpringValue per particle. Not as efficient but works for ≤200
  particles. Want me to proceed with the workaround?
```

The conversation is the substrate. When the framework can do what
you want, it does it. When it can't, the agent notices, files
properly-structured feedback, and offers a workaround.

---

## 3. Architecture

```
┌──────────────────────┐    ┌───────────────────────┐    ┌────────────────────┐
│   Elysium Designer   │    │      Aether Daemon    │    │   IDE Plugins      │
│  (Python, dogfooded) │◀──▶│   (Python, separate)  │◀──▶│  PyCharm / VS Code │
└──────────┬───────────┘    └───────────┬───────────┘    └────────────────────┘
           │                            │
           │   JSON-RPC over Unix       │   Provider-agnostic
           │   socket / Named Pipe      │   LLM transport
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌───────────────────────┐
│   Runtime Inspector  │    │      LLM Provider     │
│   (existing TCP)     │    │  Anthropic / OpenAI / │
└──────────────────────┘    │   Google / Ollama     │
                            └───────────────────────┘
```

### 3.1 Components

| Component | Lives in | Role |
|---|---|---|
| **Aether Daemon** | new — `python/elysium/aether/daemon.py` | Hosts the conversation, tool-call loop, snapshot store, LLM connection. One per developer session. |
| **Designer Adapter** | `elysium-designer/__main__.py` | Side panel + execution surface for tool calls. Streams canvas state. |
| **Runtime Adapter** | `python/elysium/aether/runtime_adapter.py` | Reuses the existing Inspector TCP channel; adds run/stop/snapshot. |
| **IDE Adapter** | `elysium-pycharm/`, `elysium-vscode/` | Side panel mirroring the Designer's; shares the same daemon. |
| **Tool Registry** | `python/elysium/aether/tools/` | Catalog of every operation the agent can perform. |
| **Snapshot Store** | `~/.elysium/aether/sessions/<id>/snapshots/` | Per-step `.esk` + Python source archives. |
| **Capability Registry** | `python/elysium/aether/capabilities.json` | Machine-readable manifest of what the framework can do — fed into the LLM's context. |

### 3.2 Process model

* **One daemon per developer.** Spawned by the Designer or the IDE
  plugin on first use, bound to `~/.elysium/aether/<user>.sock`.
* **Multiple clients per daemon.** Designer + PyCharm can both attach
  to the same conversation simultaneously; the transcript and snapshot
  store are shared.
* **Daemon dies cleanly.** Crash-only design; restart re-loads the
  active session from disk.

### 3.3 Transport: JSON-RPC over Unix sockets / named pipes

The same length-prefixed JSON framing the existing hot-reload IPC
uses, with two added message types:

```json
{"type": "tool_call",   "id": "01J0…", "name": "placement.add",
 "args": {"kind": "Mesh3D", "x": 320, "y": 180, "w": 400, "h": 300,
          "name": "Butterfly", "props": {"mesh": "Butterfly"}}}

{"type": "tool_result", "id": "01J0…", "ok": true,
 "value": {"placement_id": "p1"},
 "snapshot": "snap-2025-05-16-1437-007.tar"}
```

Streaming intermediate text from the LLM:

```json
{"type": "stream", "kind": "thinking",
 "text": "Wings need a 4-keyframe loop so the…"}
```

User-facing control:

```json
{"type": "control", "action": "pause" | "resume" | "undo" | "branch",
 "target_snapshot": "snap-…"}
```

### 3.4 Sequence: a single user turn

```
User              IDE/Designer       Daemon              LLM            Runtime
 │                    │                │                  │                │
 │── "build a btf" ──▶│                │                  │                │
 │                    │── chat.send ──▶│                  │                │
 │                    │                │── prompt+tools ─▶│                │
 │                    │                │◀─ tool_call ─────│                │
 │                    │◀── exec ───────│                  │                │
 │                    │── result ─────▶│                  │                │
 │                    │                │── observation ──▶│                │
 │                    │                │◀─ tool_call ─────│                │
 │                    │                │                  │                │
 │                    │                │   …N tool/obs cycles…             │
 │                    │                │                  │                │
 │                    │                │── run.start ────────────────────▶│
 │                    │                │── run.snapshot ─────────────────▶│
 │                    │                │◀── png + frame_stats ────────────│
 │                    │                │── observation ──▶│                │
 │                    │                │◀── final reply ──│                │
 │                    │◀── stream ─────│                  │                │
 │◀── transcript ─────│                │                  │                │
```

---

## 4. Designer Hooks API

The Hooks API is the agent's keyboard and mouse. Every Designer
operation maps to exactly one tool with a JSONSchema-typed signature.

### 4.1 Tool definition schema

```typescript
{
  name:        "namespace.action",         // dotted, stable across versions
  description: "One-sentence summary the LLM reads.",
  input_schema: { /* JSONSchema */ },
  output_schema: { /* JSONSchema */ },
  side_effect: "none" | "read" | "write" | "destructive",
  undoable:    boolean,
  requires_confirmation: "never" | "destructive" | "always",
  rate_limit:  { calls: int, window_ms: int },  // optional
}
```

`destructive` ops (delete a placement, drop a snapshot, push to git)
*always* prompt the user before executing, regardless of session-wide
auto-approve settings.

### 4.2 Tool catalog (selection — full list in Appendix A)

#### Scene / placement
* `placement.add(kind, x, y, w, h, name?, props?)`
* `placement.remove(id)` *(destructive)*
* `placement.move(id, x, y)`
* `placement.resize(id, w, h)`
* `placement.rename(id, name)`
* `placement.set_property(id, key, value)`
* `placement.duplicate(id, dx?, dy?)`
* `placement.bring_forward(id)` / `send_backward(id)`
* `placement.list(filter?)` → `[{id, kind, name, x, y, w, h, ...}]`

#### Window / canvas
* `window.set_chrome(transparent, title_bar, shape, path_d?)`
* `window.set_size(w, h)`
* `window.set_bg(color | gradient)`
* `window.set_studio(name)` — picks one of the lighting presets
* `window.set_theme(name)`

#### Shapes / paths
* `shape.draw_rect(x, y, w, h, radius?, fill?, stroke?)`
* `shape.draw_ellipse(cx, cy, rx, ry, fill?)`
* `shape.draw_path(d, fill?, stroke?)`  — SVG mini-language
* `shape.boolean_op(ids[], op="union"|"intersect"|"subtract"|"exclude")`
* `shape.simplify(id, tolerance)`

#### Materials / textures
* `material.set(placement_id, preset?, metallic?, roughness?, …)`
* `material.set_texture(placement_id, slot, path | bytes)`
* `texture.extract_from_image(src, name, seamless=true)`
* `texture.apply_layer(placement_id, layer)`
* `texture.list_library()` → `[{name, path, thumb}]`

#### Animation
* `animation.add_state(placement_id, name, dx, dy, scale, rotation,
                        opacity, duration, easing)`
* `animation.modify_state(...)`
* `animation.delete_state(...)`
* `animation.replace_keyframes(...)`
* `animation.play(placement_id?)`
* `animation.set_playhead(t)`

#### 3D / mesh
* `mesh.import(path)` → `placement_id`
* `mesh.set_camera(yaw, pitch, dist)`
* `mesh.toggle_wireframe(id)`
* `mesh.render_final(id, samples=12, max_bounces=3, denoise=true)`

#### Hooks / code-link
* `hook.declare(placement_id, name, kind, options?)`
* `hook.set_accessible(placement_id, role, label, description?)`
* `codelink.scaffold(hook_name, window_var="win")`
* `codelink.goto(hook_name)`           — opens editor at handler
* `codelink.read_handler(hook_name)`   → source

#### Code-behind (Python)
* `code.read_file(path)`
* `code.write_file(path, contents, mode="overwrite"|"append")`
                                          *(destructive on overwrite)*
* `code.patch(path, find, replace)`
* `code.run(entry, env?)` → `pid`
* `code.stop(pid)`

#### Runtime / inspector
* `run.start(entry?, env?)`
* `run.stop()`
* `run.snapshot()` → `{png_bytes, w, h}`
* `run.simulate_input(events)` — synthetic mouse / key
* `run.read_logs(since_ts?)` → `[{level, msg, ts, ...}]`
* `run.frame_stats()` → `{frame_ms[], paint_ms, composite_ms, swap_ms,
                           hooks_fired}`

#### History / safety
* `snapshot.list()` → `[{id, ts, action, parent}]`
* `snapshot.restore(id)`        *(destructive — wipes uncommitted work)*
* `snapshot.diff(a, b)` → unified diff
* `snapshot.branch(id, label)`

#### LLM meta
* `agent.search_docs(query)` → relevant doc snippets
* `agent.list_components()` → catalog
* `agent.list_studios()` / `list_presets()`
* `agent.report_capability_gap(name, summary, severity, sketch)`

Every tool returns `{ok, value | error, snapshot}`. `snapshot` is the
id of the auto-created checkpoint the user can revert to.

### 4.3 Capability manifest

`python/elysium/aether/capabilities.json` is a machine-readable summary
of every component, easing function, material preset, studio, draw
command, hook kind, and PBR feature the framework currently supports.
It's loaded into the LLM's system prompt verbatim so the model knows
exactly what's available and what isn't.

```json
{
  "components": ["Button","Card","Slider","Mesh3D","PBRSphere",…],
  "easings":    ["linear","ease_out","ease_in_out","spring",…],
  "studios":    ["Default Soft Studio","Three-Point Hero Studio",…],
  "material_presets": ["Metal — Gold","Paint — Candy Red",…],
  "draw_commands": ["FillPath","DrawText","DrawParagraph",…],
  "hook_kinds": ["event","text","image","value","state","slot","style"],
  "missing":    []           // populated by report_capability_gap
}
```

### 4.4 Side-effect taxonomy + safety

| Class | What it does | Default policy |
|---|---|---|
| `none` | Pure read of agent's own memory | Always allowed |
| `read` | Reads Designer / runtime state, file system | Always allowed |
| `write` | Modifies a placement, writes a file, runs the app | Snapshot, then run |
| `destructive` | Deletes data, overwrites without backup, pushes to git | Always prompt user |

The agent operates under a **trust budget** the user sets per session:

* **Cautious** — every `write` waits for user confirmation.
* **Collaborative** (default) — `write` auto-approves with snapshot;
  `destructive` always prompts.
* **Autonomous** — `destructive` auto-approves except git push.

---

## 5. LLM integration

### 5.1 Provider abstraction

```python
class Provider(Protocol):
    async def stream(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolDef],
    ) -> AsyncIterator[StreamEvent]: ...
```

`StreamEvent` is one of: `ThinkingDelta`, `ToolCall`,
`ToolResult` (ack-back), `MessageDelta`, `Done`.

Shipped providers:
* `Anthropic` — Claude Opus / Sonnet / Haiku via tool use.
* `OpenAI` — GPT-4o / o3 via function calling.
* `Google` — Gemini via function calling.
* `Ollama` — local llama.cpp models via the `/api/chat` tool-use endpoint.
* `Stub` — deterministic offline echo for tests.

### 5.2 System prompt template

```
You are Aether — the Elysium UI agent, an autonomous collaborator
that designs, codes, and tests Elysium apps alongside the user.

You have access to a live Designer canvas, the running Python app,
the user's source file, and a tool registry that lets you operate
every part of the framework programmatically.

# Working surface
* Skin path:       {skin_path}
* Python entry:    {entry_file}
* Trust mode:      {trust_mode}
* User platform:   {platform}

# Framework capabilities
{capabilities_manifest}    ← inlined capabilities.json

# Currently on canvas
{placements_summary}       ← top-N placements with kind/name/bounds

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
Reply with natural prose interleaved with tool calls. Wrap tool
calls in <tool>{...}</tool> blocks (your transport handles them).
Keep prose concise. End with a one-line summary of what you did.
```

The system prompt is regenerated on every turn so the model always
sees the *current* canvas + capability set.

### 5.3 Tool-use loop

```
def turn(user_message):
    messages = session.messages + [user_message]
    while True:
        events = provider.stream(system_prompt(), messages, tools)
        for event in events:
            yield event
            if event is ToolCall:
                result = registry.dispatch(event.name, event.args)
                messages.append(ToolResultMessage(event.id, result))
                yield ToolResult(event.id, result)
        if events.terminated_with_message:
            session.append(events.message)
            return
```

The daemon implements the loop server-side. Clients only see
streamed events — they never invoke the LLM directly.

### 5.4 Context management

* **Recent buffer:** Last K tool calls live verbatim.
* **Mid-window summary:** Older calls collapse into a one-line digest
  (`"Built 14 placements; applied 'Iridescent Pearl' to butterfly"`).
* **Snapshot anchors:** When the user branches from snapshot N, the
  context resets to the state captured at N + a re-summarised history.
* **Capability deltas:** When the user adds a new component / preset,
  the diff is injected at the next turn so the model picks it up.

Long sessions stay under 30k tokens for the daily-driver model.

### 5.5 Streaming protocol

Daemon → client is a continuous WebSocket of newline-delimited JSON
objects of the shapes in §3.3. Clients render each as it arrives —
"thinking" updates a spinner, "tool_call" appends a step row,
"tool_result" marks it ✓, "stream:message" appends user-facing text.

---

## 6. Real-time UX

### 6.1 Side panel layout (Designer + IDE)

```
┌─────────────────────────────────────┐
│  Aether Agent          [⏸] [⟲] [⤴]│   ← pause / undo / branch
├─────────────────────────────────────┤
│  Trust: Collaborative ▼             │
│  Model: Claude Opus 4.7 ▼           │
├─────────────────────────────────────┤
│  You: Build a butterfly…            │
│                                     │
│  🧠 Planning                         │
│   1. Transparent shaped window      │
│   2. Mesh3D butterfly at centre     │
│   …                                 │
│                                     │
│  🔧 window.set_chrome(transparent…) │
│   ✓ snapshot #1                     │
│  🔧 placement.add(Mesh3D, …)        │
│   ✓ p1 (snapshot #2)                │
│  🔧 material.set(p1, …)             │
│   ✓ snapshot #3   [revert]          │
│                                     │
│  📸 [thumbnail strip — last 6]      │
│                                     │
├─────────────────────────────────────┤
│  > _                                │   ← input
└─────────────────────────────────────┘
```

### 6.2 Live highlight overlay

While the agent's `placement.*` tool is in flight, the affected
placement glows accent-purple on the canvas. While `animation.play`
runs, the timeline scrubber rides the playhead. Visual reinforcement
that the agent's words mean real action.

### 6.3 Step-by-step transcript

Every tool call renders as a collapsible row:

```
▾ 🔧 placement.add(Mesh3D, x=320, y=180, w=400, h=300, name="Butterfly")
    args  → {"kind":"Mesh3D","x":320,"y":180,...}
    result→ {"ok":true,"value":{"placement_id":"p1"}}
    snap  → snap-2025-05-16-1437-002.tar  [restore here]
```

The chevron expands to show the JSON. Each row has a `[restore]`
button that rolls the session back to before that call.

### 6.4 Controls

| Button | Effect |
|---|---|
| ⏸ Pause | Halts before the next tool call. Inflight call completes. |
| ▶ Resume | Continues from the paused point. |
| ⟲ Undo | Rolls back to the previous snapshot. |
| ⤴ Branch | Forks the conversation from a chosen snapshot. |
| 🔁 Retry | Re-asks the LLM for the most recent step with a new seed. |
| ✋ Approve | Required for `destructive` calls under Cautious trust. |

### 6.5 Status indicators

* **Spinner colors** — yellow=thinking, blue=tool exec, green=ok,
  red=error, grey=paused.
* **Token meter** — input/output token usage for the current turn +
  cumulative session cost (or "local" when no remote provider).
* **Latency badge** — round-trip per tool call (helps spot a slow
  `render_final` vs a fast `placement.move`).

---

## 7. Autonomous testing

### 7.1 Test orchestrator

A module `python/elysium/aether/tester.py` that the agent can call:

```
tester.probe(app_pid, scenarios=[
  "every hook fires without traceback",
  "no frame > 33ms over a 5s window",
  "memory stable over 30s",
  "screenshot diff vs baseline < 2% pixels",
])
→ {findings: [Finding, ...], suggestions: [...]}
```

Each scenario is a built-in probe with a clear pass/fail criterion.
The agent strings them together; results stream back as observations.

### 7.2 Screenshot diff

`run.snapshot()` returns the current canvas as PNG; the tester stores
a per-state baseline under `~/.elysium/aether/sessions/<id>/baselines/`.
On the next run a pixel-difference threshold flags drift; the
threshold is per-region (the agent can mark "this circle moves, ignore
it; this banner shouldn't change").

### 7.3 Synthetic event probe

`run.simulate_input([{ev: "click", x: 200, y: 240}, …])` posts events
through the same channel real users do. The agent uses it to:
* Cycle every interactive hook to verify each one fires its handler.
* Stress-test edge zones (corners, sub-pixel coordinates, rapid
  double-clicks).
* Replay a recorded user session to reproduce a reported bug.

### 7.4 Findings log

```jsonl
{"ts": ..., "kind": "perf",   "scenario": "frame budget",
 "msg": "p99 frame 41.2ms", "placement_id": "p1",
 "fix_suggestion": "drop sample count on the path-traced backdrop"}
{"ts": ..., "kind": "visual", "scenario": "screenshot diff",
 "diff_pct": 14.2,
 "region": [320,180,400,300],
 "fix_suggestion": "Mesh3D drift — likely an unconverged path tracer"}
```

Logs live under `~/.elysium/aether/sessions/<id>/findings.jsonl` and
are echoed into the transcript with severity icons.

### 7.5 Self-fix loop

After running the probes the agent decides what to do with each
finding:

```
for f in findings:
    plan = think_about(f, history)
    if plan.confidence > 0.7:
        await apply(plan.tool_calls)
        new = await tester.reverify(f.scenario)
        if not new.passed:
            log("auto-fix didn't take; surfacing to user")
            stream_to_user(f, plan)
```

When confidence is low the agent surfaces the finding plus a proposed
fix and waits for approval.

---

## 8. Feedback → framework evolution loop

When the agent hits a wall ("I need a `Particles` component", "I need
a `motion_blur` effect on `Mesh3D`"), it calls:

```python
agent.report_capability_gap(
    name="particles_component",
    summary="A GPU-evaluated particle emitter with sprite atlas + spring "
            "physics; needed for trail effects on Mesh3D placements.",
    severity="enhancement" | "blocker",
    sketch={
        "api": "ely.components.Particles(emitter, lifetime, count, ...)",
        "draw_command": "DrawCommand::Particles { vbo, sprite, count }",
        "minimum_viable": "static count, atlas-cell sprite, CPU update",
    },
    seen_in_session="snap-2025-05-16-1437-…",
)
```

### 8.1 Where requests go

* **Local digest:** `~/.elysium/feedback/<date>.jsonl` — one entry per
  request. The Designer's status bar shows pending requests when the
  user opens it.
* **GitHub draft issue:** with explicit user opt-in (`elysium feedback
  share`), the daemon opens a draft issue on the framework repo using
  the GitHub CLI / API. Issue body includes the sketch, the session
  snapshot link, and a redacted excerpt of the conversation.
* **Quarterly digest:** the framework maintainers see an
  aggregate-and-rank view: which gaps were reported most often, what
  severity, what workarounds users adopted.

### 8.2 Closing the loop

When a gap ships as a real feature, the framework's release notes
mark the original request id (e.g. `closes elysium-ui/elysium#142`).
The agent reads the release notes on update and notifies users whose
sessions had that gap:

> 🎉 Your "particle system" request from May 16th is now in 0.7.0 —
> want me to retrofit the butterfly trail with the new API?

---

## 9. Safety + trust

### 9.1 Snapshots

* Every `write`/`destructive` tool call snapshots *before* executing.
* Snapshot = compressed tarball of the `.esk` directory + the paired
  Python file + the agent message history up to that point.
* Storage cap: 200 snapshots per session, rolling.
* `snapshot.restore(id)` rolls back deterministically; the
  pre-restore state itself becomes snapshot N+1 so you can re-restore
  if you change your mind.

### 9.2 Confirmation tiers

(See §4.4.) The trust mode is a session-level preference; the user
can change it any time without restarting the session.

### 9.3 Sandboxing

* The daemon refuses any file operation outside the project root.
* `code.run` runs the user's app in a subprocess with its own
  working directory and env; `code.stop` SIGTERMs.
* Network egress from the daemon is allow-listed: LLM provider URL,
  GitHub API (only when `feedback share` is invoked), the
  marketplace registry.
* Local LLM mode (Ollama) leaves the egress allow-list at "GitHub
  only when feedback share invoked" — everything else stays on disk.

### 9.4 Audit log

`~/.elysium/aether/sessions/<id>/audit.jsonl` records every tool
call, its args, its result, the user-facing prose, the model id,
and the token counts. The user can `elysium aether export <session>`
to share a redacted replay for reproduction or bug reports.

---

## 10. Performance + cost

| Surface | Target |
|---|---|
| First user-visible canvas update | < 2 s from the user pressing return |
| Tool-call dispatch latency | < 50 ms (excluding the LLM round-trip) |
| Snapshot create | < 100 ms for a typical project |
| Streamed prose latency | matches the provider's stream cadence |
| Idle agent CPU | < 0.1% (only the daemon's WebSocket reader runs) |
| Cost per typical "polish this" turn | < $0.05 on Claude Sonnet; $0 on local |

### 10.1 Cost controls

* **Model tiering:** plan with Opus, execute with Haiku, screenshot
  with vision-only call. Cuts daily-driver cost by 5–8×.
* **Context trimming:** see §5.4.
* **Local-mode toggle:** Ollama-only is free; the side panel exposes
  one-click switch.
* **Batch tool calls:** when the agent stages many independent
  `placement.set_property` calls, the daemon coalesces them into a
  single transaction so the canvas re-paints once.

---

## 11. Challenges + solutions

| Challenge | Solution |
|---|---|
| LLMs hallucinate tool names | Tools enumerated in system prompt + JSONSchema-validated; unknown names get a `tool_not_found` observation the LLM corrects from. |
| LLMs lose track of canvas state | After every `write` call, the daemon re-summarises the placement list and injects it as the tool result, so the model can't drift. |
| Long agent sessions blow context | §5.4 mid-window summarisation; per-snapshot context resets. |
| User wants to undo mid-stream | ⏸ then ⟲ — the inflight call completes (already-scheduled tool runs to avoid corrupting the canvas), then the restore lands; daemon flushes pending calls. |
| Agent breaks the project | Always restore-able via any snapshot row in the transcript. Snapshots are immutable on disk. |
| Local LLM is too small to plan | Smaller models do well at execution. The daemon supports "split provider": planning model and execution model can be different. |
| Visual realism (e.g. photoreal butterfly) | Reuse existing PBR + path tracer + studio presets; the agent picks the right `studio` + `material` + `render_final` combination. |
| Concurrent edits (user + agent at once) | Optimistic locking on placement state — the daemon detects a user-side change since the snapshot the LLM was reasoning over and re-prompts with the conflict diff before applying. |
| Cost runaway on a long session | Per-session token budget; hard-stop at the limit with a "raise budget" prompt. |
| Safety of running user code | `code.run` is a separate subprocess with rlimits; crashes don't take the daemon down. |

---

## 12. Worked example: photorealistic butterfly from scratch

**User:** "Build a photorealistic animated butterfly with no
background or window border, floating gently with wing physics and
landing on the middle of the screen, then show a banner that says
'Elysium UI'."

The streamed transcript, edited for length:

```
🧠 Plan
  1. Shaped + transparent window — no chrome.
  2. Place a Mesh3D butterfly placement; use the built-in butterfly mesh
     so we get a real triangle mesh, not just a sprite.
  3. Pick "Three-Point Hero Studio" — warm key light + cool fill +
     rim — sells the photoreal feel.
  4. Iridescent metallic material with high clear-coat so wings catch
     specular highlights as they flap.
  5. 3 animation states: float_in (descend + scale up + fade in),
     flap_loop (cyclic wing flap with phase-offset hindwing),
     land (deceleration to centre with overshoot spring).
  6. Banner placement that fades in 200ms after landing completes.
  7. Python entry: trigger float_in → flap_loop on launch, fire land
     after 4s, fire banner.fade_in on land complete.
  8. Run + screenshot, then path-trace one Render Final pass for the
     final hero frame.

🔧 window.set_chrome(transparent=true, title_bar=false, shape="path",
                      path_d="M 0 0 L 960 0 L 960 540 L 0 540 Z")
   ✓ snapshot #1

🔧 window.set_bg(color="#00000000")
   ✓ snapshot #2

🔧 placement.add(kind="Mesh3D", x=280, y=170, w=400, h=300,
                  name="Butterfly", props={"mesh":"Butterfly","flap":0})
   ✓ placement_id=p1, snapshot #3

🔧 window.set_studio("Three-Point Hero Studio")
   ✓ snapshot #4

🔧 material.set(p1, preset="Metal — Iridescent Pearl",
                 metallic=0.85, roughness=0.18,
                 clear_coat=0.9, clear_coat_roughness=0.06,
                 anisotropy=0.7)
   ✓ snapshot #5

🔧 animation.add_state(p1, name="float_in",
                        dx=0, dy=80, scale=0.7, opacity=0.0,
                        duration=0.0)
   ✓ (this is the start pose)

🔧 animation.add_state(p1, name="float_target",
                        dx=0, dy=0, scale=1.0, opacity=1.0,
                        duration=0.8, easing="ease_out")
   ✓

🔧 animation.add_state(p1, name="flap_loop", loop=true,
                        keyframes=[
                          {"flap":0.0, "t":0.0,  "easing":"ease_in_out"},
                          {"flap":1.1, "t":0.18, "easing":"ease_out"},
                          {"flap":0.95,"t":0.30, "easing":"linear"},
                          {"flap":0.0, "t":0.40, "easing":"ease_in"}])
   ✓

🔧 animation.add_state(p1, name="land",
                        dx=0, dy=-20, scale=1.05,
                        duration=0.45,
                        easing="spring", spring_k=180, spring_d=22)
   ✓ snapshot #9

🔧 placement.add(kind="Label", x=320, y=440, w=320, h=48,
                  name="Banner",
                  props={"label":"Elysium UI","font_size":36,
                         "font_family":"Inter","weight":700})
   ✓ placement_id=p2

🔧 animation.add_state(p2, name="rest", opacity=0.0, duration=0)
🔧 animation.add_state(p2, name="fade_in", opacity=1.0,
                        duration=0.6, easing="ease_out")
   ✓ snapshot #12

🔧 hook.declare(p1, name="butterfly", kind="state",
                 states=["float_in","flap_loop","land"])
🔧 hook.declare(p2, name="banner",    kind="state",
                 states=["rest","fade_in"])
   ✓

🔧 codelink.scaffold(hook="boot")
   ✓ wrote on_boot to app/main.py:18

🔧 code.patch(path="app/main.py",
              find='def on_boot():\n    # TODO',
              replace="""def on_boot():
    win["butterfly"].state = "float_in"
    asyncio.create_task(_butterfly_lifecycle())

async def _butterfly_lifecycle():
    await asyncio.sleep(0.8)
    win["butterfly"].state = "flap_loop"
    await asyncio.sleep(4.0)
    win["butterfly"].state = "land"
    await asyncio.sleep(0.5)
    win["banner"].state = "fade_in"
""")
   ✓ snapshot #14

🔧 code.run(entry="app/main.py")
   ✓ pid=58213

🔧 run.snapshot()
   📸 [butterfly at floating position, no chrome, transparent canvas]

🤔 The butterfly is floating but the wings clip the top of the canvas
   at the apex of the float_in animation. Tightening the dy from 80
   to 40 fixes it without changing the perceived motion much.

🔧 animation.modify_state(p1, "float_in", dy=40)
   ✓ hot-reloaded (snapshot #15)

🔧 run.snapshot()
   📸 [no clipping, looks great]

🔧 mesh.render_final(p1, samples=24, max_bounces=4, denoise=true)
   ✓ saved to .elysium/renders/hero-frame-2025-05-16.png

✅ Done. The butterfly fades in from below, flaps for ~4s, lands at
   the centre with a spring, then the "Elysium UI" banner fades in.
   File-paired Python at app/main.py, snapshot history at #14 (use
   "restore" if you want to roll back). One thing I noticed: the
   wing iridescence reads metallic on light backgrounds and dull on
   dark — if you want to make this work on any wallpaper, swap the
   material to "Metal — Iridescent Pearl Adaptive" once you ship
   that preset. I filed a capability gap for it.

📝 Filed: framework_request:material_adaptive_iridescence
   → opened draft elysium-ui/elysium#143
```

Total wall time: ~45 seconds (Claude Opus, no human input after the
initial prompt). The user watched every step land in the canvas.

---

## 13. Phased rollout

### Phase 4.1 — Foundations (Month 0–2)
* Daemon + JSON-RPC transport.
* Tool registry + first 20 tools (placement, window, shape, hook).
* Snapshot store + restore.
* Side panel in Designer (chat + transcript + thumbnail strip).
* Anthropic + Ollama providers.

### Phase 4.2 — Code-link + run loop (Month 2–4)
* `codelink.*`, `code.*`, `run.*` tools.
* Live preview + screenshot diff in transcript.
* Trust modes + per-call confirmation.
* PyCharm + VS Code panels mirroring the Designer.

### Phase 4.3 — Autonomy (Month 4–7)
* `tester.*` probes + self-fix loop.
* Capability-gap reporter + GitHub integration.
* Branching + alternate-future support in transcript.
* Local-only mode parity (no remote-provider dependency).

### Phase 4.4 — Polish + launch (Month 7–9)
* Cost dashboard.
* Multi-client (Designer + IDE share a session).
* Recorded-session export + replay (for bug reports + tutorials).
* Featured demos: photorealistic butterfly, Spotify clone, glass
  weather widget — each built start-to-finish in a single prompt.

### Exit criteria
* "Build me a photoreal butterfly" works end-to-end on Claude Opus
  in under 60 s with no human intervention.
* The same prompt works on a 13B local model in under 5 minutes
  with degraded but recognisable output.
* Snapshot revert is 100% deterministic across 1000 random
  conversations.
* Zero data leaves the machine in local-only mode.
* 90th-percentile token cost per "polish this" turn < $0.05.

---

## Appendix A — Full tool catalog (v1)

(Excerpt; the canonical machine-readable list lives in
`python/elysium/aether/tools/manifest.json`.)

```
placement.add          placement.remove        placement.move
placement.resize       placement.rename        placement.set_property
placement.duplicate    placement.bring_forward placement.send_backward
placement.list         placement.read

window.set_chrome      window.set_size         window.set_bg
window.set_studio      window.set_theme        window.read

shape.draw_rect        shape.draw_ellipse      shape.draw_path
shape.boolean_op       shape.simplify          shape.bezier_smooth

material.set           material.set_texture    material.read
texture.extract_from_image
texture.apply_layer    texture.list_library    texture.paint_mask

animation.add_state    animation.modify_state  animation.delete_state
animation.replace_keyframes
animation.play         animation.set_playhead  animation.read

mesh.import            mesh.set_camera         mesh.toggle_wireframe
mesh.render_final      mesh.read

hook.declare           hook.set_accessible     hook.read
codelink.scaffold      codelink.goto           codelink.read_handler

code.read_file         code.write_file         code.patch
code.run               code.stop

run.start              run.stop                run.snapshot
run.simulate_input     run.read_logs           run.frame_stats

snapshot.list          snapshot.restore        snapshot.diff
snapshot.branch        snapshot.export

agent.search_docs      agent.list_components   agent.list_studios
agent.list_presets     agent.report_capability_gap

tester.probe           tester.replay           tester.set_baseline
```

72 tools across 12 namespaces in v1.

---

## Appendix B — Example LLM exchange (raw)

A single tool round-trip on the Anthropic API, abbreviated:

```jsonc
// Request
{
  "model": "claude-opus-4-7",
  "system": "...full system prompt from §5.2...",
  "messages": [
    {"role": "user", "content": "Build me a butterfly."},
    {"role": "assistant", "content": [
       {"type":"text","text":"Planning..."},
       {"type":"tool_use","id":"01","name":"window.set_chrome",
        "input":{"transparent":true,"title_bar":false,"shape":"path",
                 "path_d":"M 0 0 L 960 0 L 960 540 L 0 540 Z"}}
    ]},
    {"role": "user", "content": [
       {"type":"tool_result","tool_use_id":"01",
        "content":"{\"ok\":true,\"snapshot\":\"snap-..1.tar\"}"}
    ]}
  ],
  "tools": [...72 tool defs from manifest.json...]
}

// Response (streamed)
event: content_block_delta
data: {"delta":{"type":"text_delta","text":"Adding the butterfly mesh now."}}

event: content_block_start
data: {"content_block":{"type":"tool_use","id":"02","name":"placement.add"}}

event: input_json_delta
data: {"partial_json":"{\"kind\":\"Mesh3D\","}
...
event: message_stop
```

The daemon decodes the stream, dispatches each `tool_use` against
the registry, sends back the `tool_result`, and continues. Clients
see a clean `tool_call` → `tool_result` → `stream:text` sequence
matching the side-panel UX.

---

## Appendix C — How the agent feels to use

It feels like watching a designer who's also a software engineer
work alongside you with infinite patience. You can stop them mid-stride,
say "no, redder", and they pick up where they left off with the change
applied. You can ask "why did you do it that way?" and get a real
answer because every action is in the transcript and the model knows
its own history.

When it works, it's not "AI generated this app." It's "we built this
app together." That's the deliverable.
