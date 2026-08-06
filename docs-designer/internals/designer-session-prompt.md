# Prompt — Elysium Designer session

Paste everything below the line into a fresh session started in `~/elysium-designer`.

---

I'm working on **Elysium Designer** (commercial app by Lamaute Labs LLC, built on
the Elysium UI framework). This session is exclusively for the Designer.

## Setup

- **Designer source:** private repo `klamaute/elysium-designer`, already cloned at
  `~/elysium-designer` (clean tree). Entrypoint is `elysium-designer/__main__.py`
  — a single ~22k-line file.
- **Framework:** the repos are split. The Designer's dependency is the **public**
  framework — `elysiumui/elysium`, published to PyPI as **`elysium-ui`**. The old
  private monorepo (`klamaute/Elysium`, checked out at `~/ElysiumUI`) is *not*
  the Designer's source of truth; treat it as upstream-internal only. The stale
  `~/ElysiumUI/elysium-designer/` directory is leftover `__pycache__`, ignore it.
- **Launch detached** (`nohup … &` + `disown`) or the app dies when the tool
  call's shell exits.
- **Introspection:** the Aether bridge serves `127.0.0.1:8183` — `GET /state`,
  `/tools`, `/snapshot` (PNG, no `.png` suffix), `/logs`, `POST /tool`. Use it to
  read placements and drive the app instead of guessing from screenshots.

## Framework dependency — read this first

`release-designer.yml:81` pins **`pip install "elysium-ui==1.1.7"`** from PyPI.
That pin is the Designer's real framework dependency.

**1.2.0 is not available yet.** It is merged to the private monorepo's `main`,
but the public repo `elysiumui/elysium` is still at 1.1.7 and PyPI still serves
1.1.7. The chain that has to complete before the Designer can consume it:

```
private main (has 1.2.0)
  → mirror framework files to public elysiumui/elysium
  → merge there → tag v1.2.0 there
  → release-library.yml publishes elysium-ui 1.2.0 to PyPI
  → bump the ==1.1.7 pin in release-designer.yml to ==1.2.0
```

Until that lands, to test against 1.2.0 **locally only**, run against the
monorepo checkout — a temporary dev workaround, not the shipping configuration:

```bash
cd ~/elysium-designer
PYTHONPATH=~/ElysiumUI/python ~/ElysiumUI/.venv/bin/python elysium-designer/__main__.py
```

(If framework Rust changes, rebuild first or you won't see it:
`cd ~/ElysiumUI && .venv/bin/python -m maturin develop --release`.)

Never `pip install elysium` — that name is squatted on PyPI by an unrelated
abandoned package. The distribution is `elysium-ui`; only the *import* name is
`elysium`. A stale line doing exactly this had silently broken the framework's
own test CI for a month.

**Also stale:** `README.md:17-20` still says CI checks out the *private*
framework repo and needs a `FRAMEWORK_REPO_TOKEN` PAT. That contradicts
`release-designer.yml:17-18` ("the framework is public … no token required") and
should be corrected.

## Task 1 — the one change the Designer must make itself

Wake-on-input is opt-in and the Designer doesn't use it yet. At
`elysium-designer/__main__.py:21859`, `run_animation_thread(...)` needs
`wake_on=self.win` added.

Without it the frame loop polls at 4 Hz when idle, so a click waits up to 250 ms
to be noticed and a press-and-release inside one tick is never seen as a drag at
all. I verified this change locally: idle CPU 11% → 9%, bridge round-trip 7.4 ms,
then reverted it. This is the fix for QA items 15/18/19.

## Task 2 — re-test what 1.2.0 already fixes (rebuild only, no Designer change)

A QA tester filed 24 defects. Items 1–12 were framework bugs, all fixed. Several
runtime complaints should now be gone — please confirm each:

| QA item | Was | Should now be |
|---|---|---|
| 13 lag | ~150% CPU on an **empty idle canvas** | ~11% (busy-spin + frame pacing fixed) |
| 22 layers | clicking selected the object *underneath* the visible one (z-tie) | correct object |
| 21 lost work | `is_clean()` claimed "saved" for a diverged doc; unclosed macro made edits un-undoable | prompts correctly — **specifically check autosave**, which was dead if keyed off the dirty flag |
| 20 canvas | `fit()` was a silent no-op on an empty scene | resets the view |
| 14 window | fixed 1200×800 regardless of display | sized to the display |
| 17 menu bar | titles overflowed a narrow window | measured properly (geometry half may remain) |

## Task 3 — still open, likely Designer-side

- **Item 16 — "drawn strokes render over other applications."** Most alarming and
  least explained. I audited 13 framework widgets: every one balances its
  clip/transform stack, so this is **not** a framework stack bug. Two candidates
  remain: (a) the Designer's own brush/canvas layer painting without a
  `push_clip`, or (b) a stale render scale (framework defect **N1**, unfixed:
  `ely-render/src/surface.rs:176` captures `scale_factor` once and `resize()` at
  `:193` never re-reads it). Note the window is `transparent: true,
  title_bar: false` by default, so anything painted outside the drawn chrome
  lands on see-through pixels and reads as "over the desktop" — no overlay
  window needed to explain it. **Cheapest decisive test: run with
  `transparent=False`.** If strokes still escape, there's a second OS window and
  this analysis is wrong; if they instead appear as garbage inside an opaque
  window, it's unclipped paint.
- **Item 18 drag** — re-test after Task 1; a stale-index crash was fixed but that
  explained a crash on release, not "doesn't function".

Full triage, including the exact questions still needed from the tester, is in
`~/ElysiumUI/docs-designer/internals/qa-followup-items-13-24.md`.

## Gotchas that cost me time

- `/snapshot` calls `designer.save_layout()` as a side effect — browsing state
  persists to `~/.elysium/untitled.esk`.
- `CaptureDL.calls` is the draw-call tally; `.len` is swallowed by its recording
  `__getattr__` and returns a function.
- To prove a render change is safe, hash `SkiaLayer.encode_png()` before/after
  via `git stash push <file>` rather than trusting the test suite — snapshot
  coverage is thin.
- Don't write timing tests that assert achieved frame rate; they pass locally and
  fail on loaded machines. Drive a fake `time.monotonic`/`time.sleep` and assert
  the pacing decision.

## Ground rules

- **Don't change framework code from this session.** The repos are split: fixes
  to `elysium-ui` belong upstream in the framework repo and reach the Designer
  only via a PyPI release. If you find a framework bug, report it and note the
  version it needs, rather than patching `~/ElysiumUI` from here.
- Don't cut a release tag or publish anything without asking.
- Verify claims by running the app and reading `/state`, not by assuming.
