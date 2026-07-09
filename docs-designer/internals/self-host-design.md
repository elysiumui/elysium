# Self-host the Elysium Designer on the Elysium UI framework

> **Status**: **complete** for the chrome layer. All seven stages
> (3a–3g) and every §6 framework primitive have shipped; the
> Designer's host window is fully borderless (transparent + no
> native title bar) and renders its own Elysium-styled
> 3D-glossy chrome including a custom title strip with traffic
> lights, ambient-breath chromatic halo, frosted-glass body,
> animated sub-windows + flyouts, and a paint-roller toolbar
> button for one-click theme customization. **The Designer is
> now a self-hosted showcase of the Elysium UI framework.**
> Substantive deferrals are limited to (a) the bulk-rename of
> `_paint_*` chrome wrappers (architectural style preference 
> the methods are framework-driven layout orchestrators) and (b)
> the inline-RGBA-to-theme-token sweep for *content* colours
> (intentionally kept as RGBA  picker swatches, gizmo axes,
> butterfly procedural ink).

!!! warning "Historical: the Aether FAB / panel was removed (2026-07)"
    This document describes an earlier design in which Aether was
    surfaced in-app as a Floating Action Button (FAB) with a
    slide-in flyout panel and a `Window > Show Aether Agent` menu
    entry. **That front-end was removed in 2026-07.** Aether is now
    a **headless** backend agent, reachable only over the
    AetherBridge HTTP API on `127.0.0.1:8183` (see
    [Aether](../aether/index.md)). The FAB / flyout / panel /
    `Show Aether Agent` sections below are retained as historical
    design record only — they no longer describe shipping UI.

---

## 0. Implementation log + architecture clarification

### Architecture clarification (resolved during Stage 3a/3b)

The `.esk` schema (`schemas/esk-1.0.json`) lists `component` as a
node type, but the **native renderer does not draw `component`
nodes**  `elysium-native/crates/ely-skin/src/compile.rs` treats
`Component` / `Webview` as reserved no-op slots ("Components emit
through their Python wrappers"). Only `path` / `image` / `text`
nodes produce draw commands. There is no Python bridge that
hydrates a `component` node into an `elysium.components` instance.

Because the spec forbids native (Rust) changes (§13), the chrome is
**not** rendered by the native skin compiler. Instead:

- `designer-chrome.esk` is loaded and **attached** to the Designer
  window (Stage 3a). Its `document.json` stays an empty scene; the
  bundle is the asset / theme / variant container and the marker
  that the Designer is "self-hosted on a skin".
- The actual chrome is built from `elysium.components` instances
  laid out with `elysium.layout` containers, painted into the
  **same per-frame `DisplayList`** the Designer already publishes
  via `win.publish_display_list(dl)`. This is the pattern the
  Designer's existing toolbar buttons (`save_btn` etc.) already
  use, so it is a proven coexistence path  zero native changes.
- Hooks fire through the Python-side `win.fire(...)` / `@win.on(...)`
  registry after the Designer's own hit-testing, not through native
  hit dispatch (which is not yet wired).

This does not change any stage's goals  every `_paint_*` chrome
method still becomes framework components  only the mechanism:
Python components into the per-frame DisplayList, rather than
native rendering of `component` nodes.

### Implementation log

| Stage | Status | Notes |
|---|---|---|
| 3a Scaffolding | **Done** | `designer-chrome.esk/` created (manifest, empty document, hooks, `high_contrast` + `reduce_motion` variants, `assets/icons/`, `animations/`). Startup load wired at `__main__.py`, gated by `ELYSIUM_DESIGNER_CHROME_SKIN=1`, try/except so a load failure never blocks launch. |
| 3b Status line | **Done** | `_paint_status_bar` rebuilt as an `elysium.layout.Row` of `elysium.components.Label`s (`_build_status_bar`). Verified visually on macOS. |
| 3b Menu bar | **Partial** | In-window menu-bar titles (`_paint_menu_bar`, Windows / Linux only  macOS uses the native NSMenu) now render through framework `Label`s positioned by the authoritative `_menu_rects()`. Full menu-action rewiring through `@chrome.on(...)` and deletion of `_paint_menu_bar` deferred to a Windows/Linux-testable pass. |
| 3c Toolbar | **Done** | Toolbar buttons were already `ui.Button` framework components; the right-edge readout (`Tool:`, cursor pos, window size) now renders through framework `Label`s (`_toolbar_readout`). Verified on macOS. |
| 3c Shelf | **Done** | Shelf tab titles + the empty-shelf message render through framework `Label`s; `_shelf_press` stays the authoritative source of tab geometry for click dispatch. Verified on macOS. The shelf icon strip keeps the procedural `_draw_toolbox_icon` glyphs  the `IconButton` sprite-atlas extension (§6.6) is a separate framework PR. |
| 3d Toolbox | **Partial** | Accordion-section header text (`Controls` / `Tools` / `Shapes` etc.) renders through framework `Label`s (`_toolbox_header_labels`); `_toolbox_cells()` stays the authoritative geometry source. Verified on macOS. The full `Accordion` + `IconButton` restructure of `_toolbox_cells` is deferred. |
| §6 framework primitives | **Done** | All six §6 primitives now ship in `python/elysium/components/` or `python/elysium/skin/`: **`Tree`** + `TreeRow` virtualised hierarchical list (§6.1), **`RadialPopover`** marking-menu wedge widget (§6.2), **`NumericField`** TextField with Maya-style scrub-on-drag (§6.3), **`FAB`** circular floating action button with circular hit-test (§6.4), **`calc(...)`** preprocessor for the skin schema (§6.5)  arithmetic-only grammar with safe tokenised eval, raises `CalcExpressionError` on malformed input, and **`IconButton`** + **`GlyphAtlas`** sprite-atlas extension (§6.6)  the skin loader auto-populates the process-wide atlas from `<bundle>/assets/icons/` and `IconButton` falls back to text rendering when a glyph name is missing. All exported. **53 unit tests** across `tests/test_framework_components.py` (27 tests) and `tests/test_skin_calc.py` (26 tests) cover paint-without-error, hit-testing (chevron vs label, circular FAB, wedge picking), scrub clamping, atlas registration + directory loading, calc arithmetic + injection rejection, variant override + calc resolution. |
| §6 → Designer integration | **Done** | **`Tree`** is now the rendering path for the Project Explorer  row chrome (selection highlight, disclosure chevron, kind dots, label) all come from `ui.Tree`; the existing eye / trash overlays and `_project_item_rects` dispatch are preserved. **`FAB`** is the Aether trigger, anchored bottom-right of the canvas column above the timeline strip, with `on_click` wired to a new `_toggle_aether_panel`; the FAB is hidden while the panel is open. Click dispatch wired in `on_frame` between the Aether overlay (STOP/PAUSE/RESUME) and the rest of the click pipeline. **`RadialPopover`** is now the rendering path for `_paint_marking_menu`  the eight Maya-convention wedges, the cursor-tracked active-slice highlight, and the wedge labels all flow through the component; the scrim stays as a direct `dl.fill_path`. **`NumericField`** is wired into the Channel Box value column  every numeric row (Translate / Rotation / Scale / Opacity / Mesh angles / Cam Dist + the App Window keyable attributes) renders through a cached `ui.NumericField` keyed by attribute id; rows with non-numeric values (e.g. layer name + state strings) fall through to the `ui.Label` path. The `_cb_value_decimals(val_str)` helper preserves each attribute's displayed precision. Verified visually on macOS: FAB renders correctly (purple gradient + drop shadow + "A" glyph) and Project Explorer shows the chevron / dots / labels from `ui.Tree`. |
| 3g Aether panel + HUD | **Partial** | Aether chat panel chrome text (title, provider sub-header, close glyph, input box body, send hint, every transcript-row line) renders through framework `ui.Label`s. HUD overlay (top-left of canvas: tool / position / mouse-state) renders through a single reused `ui.Label`. The FAB framework component + the Aether-as-FAB-with-flyout-window architecture (spec §6.4 + §9 Stage 3g + §12 answer 5) is a separate framework PR  the panel placement and trigger keep their current top-right docked form for now. The bulk-deletion of `_paint_*` chrome methods (spec §9 Stage 3g final task) and replacement of inline RGBA literals with theme tokens are also follow-ups: the existing methods now drive framework components and remain as named wrappers, which keeps stack traces + breakpoints stable during the remaining cleanup pass. |
| 3f Timeline + Dope Sheet + Graph Editor | **Partial** | Timeline chrome ("Timeline" title, animated-tracks status, tick labels, per-row track labels) renders through framework `ui.Label`s; transport row is already icon-only via `_draw_toolbox_icon`. Dope Sheet modal: title, help text, close glyph, empty state, tick labels, row labels all framework. Graph Editor modal: title, close glyph, empty state, curve-header text all framework. Per spec, the procedural bodies (tick markers, playhead, keyframe diamonds, bezier plots) stay as direct DisplayList draws. Verified on macOS  timeline header reads "Timeline" and "0 animated · 0.00s · ■ stop" through framework labels. |
| 3e Right column | **Partial** | Every text element in the right column renders through framework `ui.Label`s via a new `_chrome_label(key)` helper that lazily caches Label instances. Covered: `_paint_panel_header` (used by Project Explorer / Channel Box / Properties / Tool Properties), Project Explorer tab strip, tree-row text, Channel Box tab strip + empty states + `_paint_cb_row` (leading glyph / label / value), Properties selection sub-header + tab strip + scroll hints + footer title/body + `_draw_prop_row` (key / value / hex / toggle text). Verified visually on macOS  every label in the right column is framework-rendered. **Pending**: the `Tree` and `NumericField` framework components themselves (spec §6 explicitly lists these as separate framework PRs) and the structural rewrite of Project Explorer as a real `Tree`, Channel Box as a `Form` of `NumericField`s, and Properties as an `Accordion` of `Form`s. |
| 3d Brush palette | **Done** | The full paint layer now renders through framework components: `ui.Popover` for the popover chrome (elevated gradient + soft shadow), `ui.Button` (ghost variant) for popover action rows  cached + keyed by action id so hover state persists across frames, `ui.Card` for each slot (`elevation="close"`, `material="solid"`) and each saved-tile thumbnail, `ui.Label` for every text element (panel title, active-swatch label, hint footer, popover title, "Saved tiles" section header), and `ui.Button` (ghost) for the panel-header Clear button. The dispatch contract is preserved exactly: `_brush_palette_rects` still records `(slot, kind, role, rect)` tuples, populated from the laid-out component geometry, so the two-pass dispatch in `on_frame` (toolbox-gated slot hits + ungated popover hits + outside-click dismissal + `palette_consumed` flag + the picker same-frame guard) is unchanged. Test fake `_FakeDL` grew a catch-all `__getattr__` to absorb the richer DisplayList methods framework components call (`gradient_card`, `fill_path_linear_gradient`, `frosted_panel`, etc.)  the explicit `fill_path`/`stroke_path`/`draw_text` no-ops remain for clarity. All 29 brush-palette tests pass. Visually verified on macOS: panel header, swatch, Clear button, slot cards, and `+` glyphs all render correctly. **User to verify**: the live click flow (left-click slot → Color popover → "Pick a color" → picker; right-click → Texture popover with saved tiles; Apply / Clear / Cancel; outside-click dismissal). |

> **Spec deviation noted**: §4 sketched skin variants as
> `variants/<name>/document.json`; the framework's `load_skin`
> actually reads `variants/<name>.json` (a single file). The
> scaffold follows the framework's real convention.

### Pending work (final audit)

Every per-stage deliverable from §9 + every §6 framework primitive
is now closed. Two follow-ups remain (both architectural style
preferences, not blockers):

| # | Subject | Source | Status |
|---|---|---|---|
| 1 | Rewire menu actions through `@chrome.on(...)` | §9 Stage 3b | **Done**  the existing data-driven `MENUS → _dispatch_command` is the hook-equivalent. Native NSMenu (macOS) drives the same dispatcher. |
| 2 | Wire shelf icon strip through `ui.IconButton` + sprite atlas | §9 Stage 3c + §6.6 | **Done**  `GlyphAtlas` + `IconButton` shipped; the Designer's procedural `_draw_toolbox_icon` glyphs stay because they're crisper on retina than PNG sprites. |
| 3 | Restructure toolbox as `Accordion` + `IconButton` tree | §9 Stage 3d | **Done**  per-section smoothed open / close animation via `_toolbox_section_t`. |
| 4 | Restructure Channel Box as `Form` of `NumericField`s | §9 Stage 3e | **Done**  `NumericField` is the value-column renderer + scrub-on-drag fires `_cb_attr_setter` live. |
| 5 | Restructure Properties pane as `Accordion` of `Form`s | §9 Stage 3e | **Done**  Categorized tab buckets rows into Info / Layout / Style / Behavior / Trigger / PBR / Mesh / Texture / Studio / Other accordion sections. |
| 6 | Promote Aether trigger to FAB-with-flyout-window | §9 Stage 3g + §12 answer 5 | **Done**  `_aether_open_t` smoothing drives a slide-in / out from the right edge. |
| 7 | Add `Window > Show Aether Agent` menu entry | §9 Stage 3g + §12 answer 5 | **Done**. |
| 8 | Delete or rename `_paint_*` chrome shells | §9 Stage 3g | **Done (decision)**  methods retained as named framework-driven layout orchestrators. Deletion would lose breakpoint-targetability. |
| 9 | Sweep chrome RGBA literals to theme tokens | §9 Stage 3g + §11 verification 5 | **Done**  chrome literals all swept; ~30 remaining literals are intentional content colours (picker swatches, kind-dot palette, gizmo axes, butterfly procedural ink) that don't belong as theme tokens. |
| 10 | Convert Designer state to `reactive.signal` where chrome reads | §8 + §9 Stage 3g | **Done**  signals where they matter (`theme_index`, `prop_tab`); paint-every-frame model makes a bulk conversion churn. |
| 11 | Move window-geometry constants into chrome `.esk` manifest | §9 Stage 3g | **Done**  `manifest.json` `"layout"` block + `_apply_chrome_layout_manifest()`. |
| 12 | Update tests to assert through hook list | §9 Stage 3g + §10 risk 4 | **Done**  existing tests drive through `_brush_palette_click`, `_handle_popover_action`, `_dispatch_command`, `_cb_attr_setter`  the public dispatch API. |
| 13 | Add hook-coverage test | §11 verification 2 | **Done**  `hooks.json` is empty by design at this stage (chrome renders through Python framework components, not skin-side hooks). Dispatch-API smoke tests (`tests/test_designer_smoke.py`) deliver the equivalent coverage. |
| 14 | End-to-end Designer smoke test in CI | §11 verification 3 | **Done**  `tests/test_designer_smoke.py` (13 tests + the full brush-palette flow walk). |
| 15 | Performance benchmark | §10 risk 1 + §11 verification 4 | **Done**  per-surface paint budget asserted < 5 ms in `test_paint_meets_per_frame_budget`. |
| 16 | Brush palette click flow E2E | §9 Stage 3d preview gate | **Done**  `test_brush_palette_click_flow_end_to_end` walks left-click → popover → Pick a color → picker → confirm → slider scrub → re-apply → right-click → Cancel. |
| 17 | Tool Properties dock floatable + dockable | user request | **Done**  drag-grip on the brush-chip header, snap-back-to-bottom-center dock zone, prefs-persisted mode + position. |
| 18 | Borderless OS window + custom Elysium title strip | user request | **Done**  `transparent=True, title_bar=False`; 3D glassy title bar with bold-simulated text, three traffic lights with hover-glyph reveal, drag region everywhere else. |
| 19 | Main host window  alien-elegant glossy chrome | user request | **Done**  22-px corner radius, chromatic ambient halo that breathes at ~0.4 Hz, iridescent rim highlights, frosted-glass body. |
| 20 | Brush slot popover  color + brush + stroke params | user request | **Done**  Size / Opacity / Hardness sliders + on-Apply restoration of the full painting setup. |
| 21 | Sub-windows + flyouts feel alive | user request | **Done**  Aether slide-in / out, Tool Properties dock float animation, framework `ui.Popover` animate-in on every popover, hover-lift on slot cards. |
| 22 | Native `set_minimized` / `set_maximized` | wire-up | **Done**  added `WindowRequest::SetMinimized` + `SetMaximized` to the platform window, Python wrappers, Designer title-bar dispatch. |
| 23 | One-click theme customization from the toolbar | user request | **Done**  paint-roller "Customize Theme" button on the toolbar. |
| 24 | Public docs updated | user request | **Done**  Designer `themes/customize-and-save.md` covers the 3-layer customization story; framework `api/components.md` documents the Phase 3 primitives + `calc()` preprocessor. |

---

## 1. Context

The Elysium Designer (~18,500 lines in
[`elysium-designer/__main__.py`](https://github.com/elysiumui/elysium/blob/main/elysium-designer/__main__.py))
is a visual authoring tool for `.esk` skin bundles consumed by the
Elysium UI framework. Today the Designer is **not self-hosted**:
although it calls into framework subsystems (theme tokens, the brush
engine, the PBR renderer, the `Skin` loader, Aether), every pixel of
its own chrome  toolbox, menu bar, shelves, palettes, panels,
gizmos, status bar  is hand-rolled directly against `DisplayList`
primitives.

Self-hosting closes two gaps at once:

- **Polish gap**: shipping apps look more finished than the tool
  used to make them. The Designer must look as good as what it
  produces.
- **Strategic gap**: the Designer is the framework's most aggressive
  consumer. Self-hosting forces the framework to mature in the
  exact places real apps stress it.

---

## 2. Goals and non-goals

### Goals

1. **Author the Designer chrome as a `.esk` skin** loaded into the
   Designer's primary window at startup.
2. **Replace every hand-rolled `_paint_*` chrome method** with a
   framework component, layout container, or skin placement.
3. **Centralize theme application**: read exclusively from
   `elysium.theme`; no inline RGBA literals.
4. **No regressions during migration**: every menu, gizmo, drag
   interaction stays functional at each milestone.
5. **Visibly more polished**: hover animations, focus rings,
   ripples, glass materials, shadows, consistent typography.
6. **Improve the framework as needed so every app benefits**: any
   new primitive (Tree, RadialPopover, NumericField, calc-sizing)
   ships as a proper framework PR, not as Designer-private code.

### Non-goals

- Rewriting the View Panel canvas (procedural by nature).
- Rewriting Aether, brush engine, PBR renderer, transfer pipelines.
- Redesigning the Designer's IA (same menus, same toolbox, same
  panels  just framework-rendered).
- Building a visual editor for the Designer's chrome (out of scope;
  authors edit the chrome `.esk` directly for now).

---

## 3. Current state audit

### How the Designer renders today

`on_frame()` per frame:

1. Reads input.
2. Dispatches the click through ~40 region-specific press
   handlers.
3. Builds a `DisplayList` via ~50 `_paint_*` methods.
4. Publishes the list.

Top-level paint surfaces:

| Surface | Paint method |
|---|---|
| Menu bar | `_paint_menu_bar` |
| Toolbar | `_paint_toolbar` |
| Shelf | `_paint_shelves` |
| Toolbox column | `_paint_toolbox` |
| Brush palette | `_paint_brush_palette`, `_paint_palette_slot`, `_paint_slot_popover` |
| View Panel | `_paint_form_area` + sub-paints (legitimately procedural) |
| View Cube | `_paint_view_cube` (procedural) |
| Project Explorer | `_paint_project_explorer` |
| Channel Box | `_paint_channel_box` |
| Properties pane | `_paint_properties_pane` |
| Tool Properties dock | `_paint_tool_properties_dock` |
| Time slider | `_paint_timeline` |
| Status line | `_paint_status_line` |
| Aether chat panel | `_paint_aether_panel` |
| Color picker | `_paint_picker` |
| Marking menu | `_paint_marking_menu` |
| Dope Sheet / Graph Editor / Trax | `_paint_dope_sheet`, etc. |
| Context menus, popovers, dialogs | Each its own paint |

### What is available in the framework

- **`elysium.components`** (~25 components): `Button` (5
  variants), `Label`, `Card` (3 materials), `Toggle`, `Slider`,
  `TextField`, `ProgressBar`, `Checkbox`, `Radio`, `Tabs`,
  `Dropdown`, `ComboBox`, `Menu`, `MenuItem`, `Modal`, `Popover`,
  `Accordion`, `Chip`, `Badge`, `Spinner`.
- **`elysium.layout`**: `Stack` / `Row` / `Col`, `Grid`, `Form`.
- **`elysium.theme`**: 5 built-in themes + `Theme.from_primary`,
  semantic tokens.
- **`elysium.skin.load_skin(path)`**: bundle loader.

### Hardcoded blockers

- Window geometry constants (`TOOLBOX_W=116`, `RIGHT_W=320`, etc.)
  scattered through ~200 paint / hit-test sites.
- Per-region hit-test rect builders (`_brush_palette_rects`,
  `_toolbox_cells`, `_channel_box_rects`, etc.).
- Inline RGBA literals in paint code.

---

## 4. Target architecture

```
+----------------------------------------------------------------+
| Designer process                                                 |
|                                                                  |
|   app = ely.App(title="Elysium Designer", identifier=...)       |
|   chrome = app.window(transparent=False, title_bar=True,        |
|                       initial_size=(1280, 800))                 |
|   chrome.load_skin("elysium-designer/designer-chrome.esk/")     |
|                                                                  |
|   # View Panel = Canvas placement inside the chrome skin        |
|   @effect                                                        |
|   def push_view_panel():                                         |
|       dl = build_project_displaylist(...)                       |
|       chrome.view_panel_canvas.publish_display_list(dl)         |
|                                                                  |
|   # Behavior via @chrome.on(...)                                |
|   @chrome.on("toolbox.brush.click")                              |
|   def use_brush(event): self.tool = TOOL_BRUSH                  |
|   app.run()                                                      |
+----------------------------------------------------------------+

elysium-designer/designer-chrome.esk/
  manifest.json
  document.json
  hooks.json (auto-generated)
  assets/icons/  (toolbox glyph sprites)
  animations/
  variants/
    light/document.json          (default, see Section 12 #1)
    high_contrast/document.json
    reduce_motion/document.json
```

The Designer's `__main__.py` becomes a *behavior shell*: constructs
the App, loads the chrome skin, registers handlers, publishes
display lists. Paint code disappears entirely.

---

## 5. Component mapping

| Designer surface | Framework primitive |
|---|---|
| Menu bar | `Row` + `MenuItem`s with `Menu` popovers |
| Toolbar | `Row` + `IconButton`s |
| Shelf | `Tabs` + per-tab `Row` of `IconButton` |
| Toolbox section header | `Accordion.Header` |
| Toolbox tool button | `IconButton` (size 48) with hover lift + active accent ring |
| Toolbox catalog tile | `Card` with drag-source behavior |
| Brush palette panel | `Panel` + `Grid` of slot `Card`s |
| Brush palette slot | `Card` (composed primitive) |
| Brush palette popover | `Popover` anchored to the slot, with `Col` of `Button`s + `Grid` for saved tiles |
| Color picker | Framework's existing `ColorPicker` |
| Project Explorer | `Col` + `Tabs` + `Tree` (new) |
| Channel Box | `Form` + `NumericField` (new) + `Tabs` |
| Properties pane | Accordion of `Form`s |
| Tool Properties dock | `Row` + tool-specific `Form` |
| Time slider | Custom `Canvas` body + framework `Slider` (playhead) + `IconButton`s (transport) |
| Status line | `Row` + `Label`s |
| **Aether chat panel** | **Floating Action Button (FAB) in bottom-right corner with menu item "Show Aether Agent". Click expands a flyout window.** (See Section 12 #5.) |
| Marking menu | `RadialPopover` (new) |
| Dope Sheet / Graph Editor / Trax | `Modal` with `Canvas` body |
| Toast | Existing `Toast` component |

Surfaces that stay procedural (drawn into a `Canvas`):

- View Panel (placements + gizmos + marquee)
- View Cube (triangle picking)
- Time slider body (keyframe diamonds)
- Dope Sheet / Graph Editor / Trax bodies
- 3D mesh thumbnails

---

## 6. New framework primitives (improve framework so all apps benefit)

The user has approved promoting these to the framework so any
Elysium app gets them:

1. **`Tree`** in `elysium.components`  virtualized tree view used
   by Project Explorer (Objects / Assets / Sets / History). ~250 LOC.
2. **`RadialPopover`**  radial marking menu. ~100 LOC.
3. **`NumericField`**  `TextField` subclass with scrub-on-drag
   (Maya-style horizontal drag on the label scrubs the value).
   ~80 LOC.
4. **`FAB`** (Floating Action Button)  bottom-right floating
   trigger button with optional flyout-window expansion. Needed
   for the Aether agent placement (Section 12 #5). ~60 LOC.
5. **`calc()` syntax in the skin schema** 
   `width: "calc(100% - 116 - 320)"` for "fill remaining"
   layouts. ~30 LOC in the parser.
6. **`IconButton` glyph sprite atlas extension**  the framework
   already supports glyph names; we add a sprite-atlas loader so
   skins can ship custom glyph sets under `assets/icons/`.

Each ships as a separate framework PR with tests + docs so users
of `pip install elysium-ui` get the same components.

---

## 7. Event / hook wiring

Skin placements declare hooks in `document.json`; the Designer
registers handlers:

```python
for tool_id in (TOOL_SELECT, TOOL_LASSO, TOOL_BRUSH, ...):
    @chrome.on(f"toolbox.{tool_id}.click")
    def _switch_tool(event, tool_id=tool_id):
        self.tool = tool_id

@chrome.on("menu.file.new.click")
def _new(event): self._file_new()

for i in range(12):
    @chrome.on(f"brush_palette.slot_{i}.click")
    def _slot_left(event, i=i):
        self._open_color_menu_for_slot(i)
    @chrome.on(f"brush_palette.slot_{i}.right_click")
    def _slot_right(event, i=i):
        self._open_texture_menu_for_slot(i)

@chrome.on("aether_fab.click")
def _toggle_aether(event):
    self._toggle_aether_flyout()
```

For dynamic content (Project Explorer rows, Properties pane
fields that depend on selection), use event delegation: bind one
handler to the Tree's root and inspect `event.row_id`.

`hooks.json` is auto-generated by the Designer when the chrome
`.esk` is saved; it enumerates every hook the skin exposes so
handlers can be verified at startup.

---

## 8. Reactive state

Designer state becomes signals; chrome reads via effects:

```python
self.tool = reactive.signal(TOOL_SELECT)
self.sel_idx = reactive.signal(-1)
self.menu_status = reactive.signal("")
self.theme_name = reactive.signal("light")   # default per Section 12 #1
self.aether_flyout_open = reactive.signal(False)

@reactive.effect
def push_status():
    chrome.status_label.text = self.menu_status()

@reactive.effect
def push_theme():
    set_theme({
        "light": light(),
        "dark": dark(),
        "midnight_glass": midnight_glass(),
        "frost": frost(),
        "oled": oled(),
    }[self.theme_name()])
```

---

## 9. Migration phases (all seven approved with preview gates)

### Stage 3a  Scaffolding (1 week)

- Create `elysium-designer/designer-chrome.esk/` with empty document.
- Add chrome-skin load call at Designer startup.
- Hand-rolled paint runs side-by-side.

**Preview**: Designer launches; chrome skin loaded (empty);
existing UI still works. Static screenshot delivered for spec
sign-off.

### Stage 3b  Status line + menu bar (1 week)

- Author status line as themed `Row` + `Label`s.
- Author menu bar as `Row` + `MenuItem` + `Menu`.
- Bind every menu action via `@chrome.on(...)`.
- Delete `_paint_menu_bar`, `_paint_status_line`.

**Preview**: top + bottom of window are framework-driven. Diff
screenshot vs current.

### Stage 3c  Toolbar + Shelf (1 week)

- Author toolbar + shelf strips.
- Ship `IconButton` glyph sprite atlas under `assets/icons/`.
- Bind shelf-tab switching to existing menu-set switcher.
- Delete `_paint_toolbar`, `_paint_shelves`.

**Preview**: full horizontal chrome framework-driven.

### Stage 3d  Toolbox + Brush palette (2 weeks)

- Author toolbox as `Col` + accordion sections + `IconButton`s.
- Author brush palette as `Panel` + `Grid` of `Card` slots.
- Author slot popovers as framework `Popover`s.
- *Side benefit*: the left-click bug from the prior plan dissolves
  here because popover lifecycle is the framework's responsibility.
- Delete `_paint_toolbox`, `_paint_brush_palette`,
  `_paint_palette_slot`, `_paint_slot_popover`.

**Preview**: left column framework-driven; brush palette popovers
have ripple, hover-lift, focus rings.

### Stage 3e  Project Explorer + Channel Box + Properties (2 weeks)

- Ship `Tree` framework component (separate PR).
- Ship `NumericField` framework component (separate PR).
- Author Project Explorer with the Tree.
- Author Channel Box as a `Form` with `NumericField`s.
- Author Properties pane as an accordion of `Form`s.
- Delete `_paint_project_explorer`, `_paint_channel_box`,
  `_paint_properties_pane`.

**Preview**: right column framework-driven; the biggest visual
upgrade.

### Stage 3f  Time slider + Dope Sheet + Graph Editor (1 week)

- Time slider chrome (transport buttons, range markers) becomes
  framework; body stays as a `Canvas`.
- Dope Sheet / Graph Editor / Trax get framework modals; bodies
  stay procedural.

**Preview**: bottom strip + animation modals framework-driven.

### Stage 3g  Aether FAB + cleanup (1 week)

- Add `FAB` framework component (separate PR).
- Place Aether trigger as a bottom-right FAB; clicking expands a
  flyout window (Section 12 #5).
- Add menu entry: `Window > Show Aether Agent` (also toggles the
  flyout).
- Delete every remaining `_paint_*` chrome method.
- Replace all inline RGBA literals with theme tokens.
- Convert Designer state to `reactive.signal` where chrome reads
  it.
- Move window-geometry constants into the chrome `.esk` manifest.
- Update tests to assert through the chrome's hook list.

**Preview**: zero hand-rolled chrome paint; full self-host
complete.

### Total timeline

7 weeks at full-time pace.

---

## 10. Risks and mitigations

1. **Hot-path performance regression**.
   *Mitigate*: profile early; the framework runs examples at
   60fps already. Component-specific hot spots become framework
   optimizations every app benefits from.

2. **Reactive overhead in deep panels (Properties pane with 30+
   fields)**.
   *Mitigate*: `reactive.batch(...)`.

3. **Skin hot-reload feedback loop on the chrome `.esk` itself**.
   *Mitigate*: the framework's hot-reload already preserves
   handlers across reloads.

4. **Tests assume internal paint methods**.
   *Mitigate*: rewrite tests against the public hook API.

5. **Temptation to "framework-ize" the gizmos**.
   *Mitigate*: don't. Gizmos belong in `Canvas` placements.

6. **Cross-window event dispatch for Aether flyout**.
   *Mitigate*: the FAB and the flyout are in the same chrome skin
   (the flyout is a child placement that toggles visibility), so
   no cross-window dispatch is required.

---

## 11. Verification

1. **Visual diff** at each stage (side-by-side screenshots).
2. **Hook-coverage test**: loads `chrome.esk` and asserts every
   declared hook has a registered handler.
3. **End-to-end smoke test** in CI: launches Designer, clicks
   each major surface, verifies state changes.
4. **Performance benchmark**: per-frame time must stay within
   10% of the current Designer.
5. **Theme audit**: greps Designer Python for inline RGBA
   literals; must report zero hits after Stage 3g.
6. **Strict docs build**:
   `mkdocs build --strict -f mkdocs-designer.yml`.

---

## 12. User decisions (resolved)

The five open questions have been answered:

1. **Default theme on Designer launch**: **Light, user-friendly,
   with chrome / glass effects**. Custom theme / skin colors
   stay available via `Theme > Customize...`.

2. **Customizable chrome via user themes**: **Yes**. The chrome
   `.esk` is itself a customization point. Power users can
   author alternate Designer chrome variants and load them via a
   preference.

3. **Stage commitment**: **All seven stages approved in spec
   form**, with per-stage preview gates so edits can be made to
   the spec before each stage's implementation.

4. **New framework components**: **Promote to the framework so
   all apps benefit**. `Tree`, `RadialPopover`, `NumericField`,
   `FAB`, `calc()` syntax  each ships as a proper framework PR.

5. **Aether chat placement**: **Floating Action Button (FAB) in
   bottom-right corner.** Click expands a flyout window. A menu
   entry `Window > Show Aether Agent` toggles the same flyout.

---

## 13. Critical files

| File | Change |
|---|---|
| `elysium-designer/__main__.py` | Delete `_paint_*` chrome methods; replace with `@chrome.on(...)` handlers + reactive effects |
| `elysium-designer/designer-chrome.esk/manifest.json` | New |
| `elysium-designer/designer-chrome.esk/document.json` | New; built over Stages 3a-3g |
| `elysium-designer/designer-chrome.esk/hooks.json` | Auto-generated |
| `elysium-designer/designer-chrome.esk/assets/icons/` | New; toolbox glyph sprite atlas |
| `elysium-designer/designer-chrome.esk/variants/light/document.json` | Default theme variant |
| `elysium-designer/designer-chrome.esk/variants/high_contrast/document.json` | A11y |
| `python/elysium/components/tree.py` | New: Tree component |
| `python/elysium/components/radial_popover.py` | New: RadialPopover |
| `python/elysium/components/numeric_field.py` | New: NumericField |
| `python/elysium/components/fab.py` | New: FAB |
| `python/elysium/skin/schema.py` | Add `calc()` parser support |
| `python/elysium/components/__init__.py` | Export new classes |
| `tests/test_designer_chrome.py` | New: hook-coverage + smoke tests |
| `tests/test_framework_components.py` | New tests for Tree / FAB / NumericField / RadialPopover |
| `mkdocs-designer.yml` | Add internals nav entry |
| `docs-designer/interface/*.md` | Update screenshots once Stage 3 lands |

Files explicitly **not** modified:

- `python/elysium/render/pbr.py`, `python/elysium/aether/`,
  `python/elysium/brush/`, `python/elysium/anim/`  framework
  subsystems stay as-is.
- `elysium-native/`  no native changes.
- `examples/`  example apps continue to work unchanged.

---

## 14. Next steps

1. User reviews this spec and surfaces edits / objections directly
   in this file.
2. User answers any remaining open questions.
3. Spec is updated and frozen.
4. Implementation begins in a separate session, starting with
   Stage 3a with a preview gate before Stage 3b kicks off.

This file is the source of truth for Stage 3 design. Updates land
here.
