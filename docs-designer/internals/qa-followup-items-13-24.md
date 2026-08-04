# QA follow-up — priority report items 13–24

Items 1–12 of the QA priority report were reproduced and fixed in **elysium-ui
1.2.0**. Items 13–24 came from hands-on use of the running Designer with no
reproduction steps, so this page records what was determined by code inspection,
what each item now needs, and what is already believed fixed.

**Correction to the report's stated hypothesis.** The report concludes that a
device-pixel-ratio mismatch explains items 14, 15, 17 and 19 together, on the
grounds that a search for `scale_factor` / `device_pixel` / `dpi` / `hidpi` /
`retina` returns no matches. That search covered only the **Python** package. The
native layer *does* convert physical→logical consistently — `WindowEvent::Resized`
(`event_loop.rs:527`), `CursorMoved` (`:584`), `Moved` (`:575`) and the wheel
pixel-delta path (`:565`) all divide by the live `scale_factor()`. There is no
single blind DPI fix to make.

---

## Status

| # | Item | Status |
|---|---|---|
| 13 | Laggy / slow response | **Largely fixed** — main-loop busy-spin + frame pacing; idle CPU 150% -> 11% |
| 14 | Window doesn't adapt to screen size | **Fixed** — monitor query added; windows now size to the display |
| 15 | Cursor doesn't match interaction point | Needs the discrimination test below |
| 16 | Strokes render over other applications | Narrowed — two candidates remain, see below |
| 17 | Top menu bar clipped | **Partly fixed** (MenuBar metrics). Geometry half needs the display config |
| 18 | Drag-and-drop doesn't work | **Re-test** — a crash cause was fixed; expect it to survive |
| 19 | Multiple clicks to select a sidebar tool | Duplicate of 15 |
| 20 | Workspace/canvas size can't be adjusted | **Re-test** — `fit()` no-op fixed |
| 21 | Progress not saved / work lost | **Likely fixed** — two causes fixed, see below |
| 22 | Layers feature doesn't work | **Likely fixed** — z-tie hit-testing, see below |
| 23 | Sidebar tools unresponsive/laggy | Duplicate of 13 |
| 24 | Overall slow/unreliable | Umbrella — close in favour of 13 |

## Already addressed in 1.2.0 — please re-test these first

- **13 (lag).** Charting small-magnitude data (probabilities, error rates,
  microsecond latencies) hit an unbounded gridline loop: at 1e-9 it emitted 2,009
  draw calls per frame instead of 9, and near 1e-15 it never returned — a frozen
  UI with no traceback. If a chart was on screen when the lag was observed, this
  was very likely the cause.
- **22 (layers).** Hit-testing returned the item *underneath* the one painted on
  top whenever two items shared a z value — and `z` defaults to 0, so this
  affected every object created without an explicit layer. In a layers UI this
  presents exactly as "selection picks the wrong layer".
- **21 (lost work).** Two independent causes fixed: `UndoStack.is_clean()`
  reported "no unsaved changes" for a document that had genuinely diverged (so
  the app closed without prompting), and an unclosed `begin_macro()` made every
  later edit invisible to the undo stack. **When re-testing, check autosave
  specifically** — if autosave is keyed off the dirty flag, the second bug
  disabled it entirely.
- **20 (canvas size).** `fit()` was a silent no-op on an empty scene, so "fit" or
  "reset view" on a fresh canvas did nothing; `GraphicsView(zoom=0)` raised
  `ZeroDivisionError` on every pointer event.
- **18 (drag).** A stale-index crash on dock-tab release was fixed — but this
  explains a *crash on release*, not "does not function", so expect the report to
  survive. If it does, treat it as item 13 (see the frame-loop note below).
- **17 (menu bar).** Menu titles were sized by a character-count estimate that
  over-counted by ~81 px across a ten-menu bar, and nothing clamps the layout
  against the bar width — enough to push the rightmost menus off a narrow window.
  Titles are now measured. The other half (a window taller than the work area,
  with no title bar to drag by) needs the display config below.

## What we need from the tester

**Mandatory — four items cannot be progressed without this:**

1. OS and version.
2. **Exact display resolution and scaling setting** (macOS: Displays → which
   "Looks like" resolution; Windows: Settings → Display → Scale %). This alone
   decides whether the fixed 1200×800 window exceeded the work area — items 14
   and half of 17 are undecidable without it.
3. **How many displays, and did the window ever move between them?** This decides
   whether the stale-scale defect (N1) could have fired at all. Single monitor
   with unchanged scaling refutes it for that session.
4. Whether display scaling changed, or a monitor was connected/disconnected, or
   the lid was opened/closed, while the app was running.
5. Mac model / GPU, or whether it was a VM.

**Per item — the questions that actually discriminate:**

- **15 (cursor offset)** — was the offset **constant everywhere**, or **larger
  toward the bottom-right**? Was it worse when **moving the mouse quickly** versus
  clicking with a stationary pointer? Was it worse **after the app sat idle for a
  few seconds**? Each answer points at a different mechanism (window-chrome
  origin / display scale / frame-loop sampling latency).
- **16 (strokes escaping)** — *highest priority:* a **full-desktop screen
  recording** (not a window capture). Did the stray strokes appear only outside
  the window's rectangle, or at its transparent/rounded edges? Did clicks on them
  pass through to the app underneath? Did they persist after switching apps?
- **17 (menu bar)** — cut off at the **top** (window positioned too high) or are
  the **rightmost menus missing** (overflow)? Different bugs, different fixes.
- **18 (drag)** — which drag: an object on the canvas, rubber-band selection, a
  dock panel/tab, a splitter, or a file dropped onto the window? Did the item
  follow the cursor, or did nothing happen at all?
- **20** — does "workspace size" mean the document/artboard dimensions, the zoom
  level, or a panel size? Where was it changed from?
- **21** — explicit Save or autosave? Did it prompt on close? Does a file exist on
  disk and is it stale? **Please keep the file rather than deleting it.**
- **22** — when clicking an object, did it select a *different* object than the
  one visibly on top? (A yes confirms the fix above lands.)
- **13/23** — which view, was a chart on screen, constant or triggered, and did it
  worsen the longer the session ran or the more strokes were drawn?

## Open native work items (located, not yet applied)

These were found by reading the native layer during this investigation. None is
confirmed as the cause of a reported symptom; all are real.

- **N1 — stale render scale.** `SurfaceRenderer.scale_factor` is captured once at
  construction (`ely-render/src/surface.rs:176`) and `resize()` (`:193`) never
  re-reads `target.scale_factor()`. Paint therefore uses a stale scale while input
  reads the live one. Fix: re-read it in `resize()`.
- ~~**N2 — `ScaleFactorChanged` is not handled.**~~ **Fixed** — the arm now
  publishes the new scale, so moving a window between displays with different
  scaling no longer leaves Python reporting the old value.
- ~~**N3 — no monitor query anywhere.**~~ **Fixed.** The window is now sized
  against the display it opens on: `initial_size` is clamped to the usable area
  and the window centred there, so it never opens larger than the screen. The
  PyO3 `Window` gained `monitor` and `scale_factor`, so an app can also place
  itself. Note the docs had described an `ely.platform.screens()` API that never
  existed — that is likely why this looked like a pure app bug.
- ~~**N4 — main-thread busy-spin.**~~ **Fixed.** `new_events` re-asserted
  `ControlFlow::Poll` every iteration (to notice the quit flag promptly), which
  ran the loop continuously. Now `WaitUntil` on an 8 ms tick. Measured on the
  Designer with an empty canvas: **~150% -> ~11% idle CPU**.
- **Clip asymmetry.** The partial-repaint path clips to the damage rect
  (`render_thread.rs:162`); the full-repaint path (`:203`) has no clip at all, so
  nothing constrains drawing to the surface bounds. Adding a symmetric
  `clip_rect` would contain escaping content regardless of its cause — the
  cheapest defensive fix for item 16.
- ~~**Frame loop.**~~ **Fixed.** Two parts: it slept a fixed period rather
  than to a deadline (so the achieved rate was 1/(work+period) and `target_hz`
  was an unreachable ceiling), and it had no wake-on-input path, so at 4 Hz idle
  a click waited up to 250 ms and a press+release inside one tick produced zero
  drag events. Now deadline-paced, and the native layer signals the loop on
  input (`wake_on=window`). **Apps must opt in** by passing `wake_on` — the
  Designer does not yet, which is a one-line change at
  `elysium-designer/__main__.py:21859`.

## Checks already run (so they aren't repeated)

- **Clip/transform balance audit** across thirteen framework widgets (DataGrid,
  GraphicsView, DockManager, Splitter, MenuBar, GroupBox, StatusBar, TabWidget,
  ToolBar, LineChart, Label, Button, ScrollView): **every stream returns to depth
  zero and never goes negative.** So item 16 is *not* an unbalanced clip stack in
  the framework — it narrows to the Designer's own drawing layer missing a clip,
  or to N1.
- **MenuBar hit accuracy**: sampling across every painted glyph run produced
  **zero** mis-hits, so the metrics estimate was never a click-targeting bug.
- **Designer source is not in this repository** (see `OPERATIONS.md`), so items
  16, 18, 19, 20 and 22 cannot be traced past the framework boundary here.
