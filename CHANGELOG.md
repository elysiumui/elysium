# Changelog

All notable changes to Elysium are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and from 1.0.0 the
project adheres to [Semantic Versioning](https://semver.org) — see
[API stability](docs/guides/api-stability.md).

## [Unreleased]

## [1.1.1] - 2026-06-29

### Fixed

- **Designer release build** now succeeds on all platforms (the published distro
  had been stale ~a month). `scripts/build-designer.spec` anchored its
  PyInstaller `datas` source paths to `REPO_ROOT` (they were resolved against
  the spec dir and failed); dropped stale hidden imports (`aether.tools.render`,
  the removed `elysium.ai.*` providers → `elysium.ai.enhance`); and added the
  missing `scripts/windows-installer.iss` (+ a robust iscc invocation with a
  portable-zip fallback) so the Windows installer step stops failing.

### Documentation

- Added `examples/butterfly/BLUE_MORPHO_INTRO_SPEC.md` — a 3D model + animation
  spec for the Blue Morpho logo-intro asset, written against the Designer's
  Mesh3D pipeline.

## [1.1.0] - 2026-06-29

### Documentation

- New API reference pages for every public module added since 1.0 (`shell`,
  `graphics`, `charts`, `commands`, `styling`, `dnd`, `text.richtext`,
  `components.completer` / `.daterange` / `.dashboard`, `modelview.grid`).
- New guides: charts & dashboards, the data grid, wizards & flows, commands &
  undo, rich text, drag-and-drop, completer, and a developer-handoff index.
- An end-to-end tutorial ("Build a Shopify-style desktop app"), a component
  gallery, an expanded Qt porting map, and a green `--strict` Designer site.

### Added

- **DataGrid sorting & filtering** (both optional + configurable): click a
  header to sort a column (asc → desc → unsorted, honouring `Column.sortable`
  and the grid `sortable` flag), and opt into a per-column **filter row** with
  `DataGrid(filterable=True)` — a live search box per `Column.filterable`
  column, with a pluggable `filter_match`. Both delegate to `ItemModel`
  (`toggle_sort` / `filter`), so virtualization and identity-keyed cell state
  keep working.

- **Tabular numerals** — `DisplayList.draw_paragraph(..., tabular=True)` now
  enables the OpenType `tnum`+`lnum` features (equal-width lining figures) so
  monetary / metric columns reconcile to the digit. Opt in per widget via
  `Label(tabular=True)` and `MetricCard(tabular=True)`. (Rust: threaded through
  `ely-render`'s Skia paragraph layer via `TextStyle::add_font_feature`.)
- **Reference apps** under `examples/`: `storeprofitlens-dashboard/` (KPI cards,
  net-profit area chart, cost donut + legend, profit table, alert inbox) and
  `variantproof-grid/` (Excel-grade `DataGrid` with frozen columns, pending
  edits, validation badges, saved-views rail, pending-changes tray) — each with
  a headless `build_*()`/`paint_*()` split and a smoke test.

- **DataGrid** (`elysium.modelview.grid`, Tier 8 — Excel-grade editable grid over
  `ItemModel`): **frozen/pinned leading columns**, column **resize / reorder /
  show-hide**, **rectangular range selection**, **copy / paste TSV** (paste an
  Excel block into a cell range), **fill-down**, **per-cell validation badges**
  and **pending-edit highlighting** — with virtualized row painting (100k rows)
  and cell state keyed by row identity (survives sort/filter). Complements the
  existing read-oriented `TableView`. Closes the bulk-editor grid gap.

- **Dashboard & flow widgets** (Tier 8): `components.dashboard.MetricCard` (KPI
  tile — eyebrow + big value + direction-aware delta badge + inline sparkline),
  `Alert` + `NotificationInbox` (a persistent "needs attention" panel, distinct
  from transient Toast/Snackbar); `components.daterange.SegmentedControl` +
  `DateRangePicker` (preset Today/Yesterday/7d/30d/Custom bar with range math);
  and `shell.Drawer` (slide-out content panel), `shell.Stepper` / `shell.Wizard`
  (numbered multi-step flow with Back/Next). For dashboards + import wizards.

- **Charts** (`elysium.charts`, Tier 8 — Qt QtCharts class): immediate-mode,
  theme-recolouring chart widgets built purely on the existing `DisplayList`
  (polylines + SVG-arc donut wedges, no native dependency) — `LineChart` /
  `AreaChart` (incl. stacked), `BarChart` (stacked/grouped), `DonutChart` /
  `PieChart`, `Sparkline`, and a `Legend`, with `Series` data, a categorical
  `chart_palette`, `nice_ticks` axis helper, and `format_money` / `format_pct` /
  `format_compact` number formatters. Closes the dashboard-charting gap for
  data/finance apps.

- **Styling & accessibility** (Tier 7 — Qt QSS / `QCompleter` / `QAccessible`):
  - `elysium.styling.StyleSheet` — a QSS-like selector→property resolver
    (type / `#id` / `.class` / `:state`, CSS specificity, `resolve` + `apply`).
  - `elysium.components.completer.Completer` — autocomplete popup (prefix →
    contains → fuzzy, history-first, keyboard nav, prefix highlight).
  - `elysium.accessibility` gained a semantic layer: `Role` constants,
    `AccessibleNode` (→ accesskit-bridge `to_dict`, incl. table row/col/header),
    a live-region `Announcer` + `announce()`, and `paint_focus_ring` (scales
    with high-contrast prefs).
  - Per-widget fonts: `Label(font_family=…, weight=…)` (opt-in; the default path
    is unchanged so goldens don't move).
- **Documents & editing** (Tier 6 — Qt `QUndoStack` / `QTextDocument` / `QDrag`):
  - `elysium.commands` — `Command` (+ `FunctionCommand` / `MacroCommand`) and an
    `UndoStack` (undo/redo, merge/coalesce by `merge_id`, macros, history limit,
    clean-state index, `on_change`); `Action`, one shared trigger for a menu
    item + toolbar button + shortcut (`to_menu_item()` / `to_tool_button()`).
  - `elysium.text.richtext` — `RichDocument` of styled `Run`s + inline `Image`s
    + paragraph `Break`s, word-wrapped + baseline-aligned via `measure_text_run`;
    `RichTextView` renders through the Skia paragraph path (real bold weight +
    italic slant axis) with hyperlink hit-testing.
  - `elysium.dnd` — `MimeData` / `DropZone` / `DragController` for in-app
    widget-to-widget drag-and-drop (press→threshold→drag, accepting-zone
    highlight, drag ghost, delivered drop). `examples/notes-demo/` ties all
    three together (rich-text notes, undoable drag-reorder).
- **Interactive 2D canvas** (`elysium.graphics`, Tier 5 — Qt `QGraphicsScene` /
  `QGraphicsView` / `QGraphicsItem` parity):
  - `Scene` owning a z-ordered list of `Item`s with scene-space bounds,
    shape-accurate hit-testing, and a `paint(dl)` in scene coordinates. Built-in
    items `RectItem` / `EllipseItem` / `LineItem` (distance hit-test) /
    `PathItem` / `TextItem`. Scene queries: `items_at` (topmost-first),
    `items_in_rect` (intersect or contained — the rubber-band query),
    `bounding_rect`, z-order raise/lower, selection helpers.
  - `GraphicsView` — a pan/zoom viewport with `to_view`/`to_scene` mapping,
    cursor-anchored `zoom_at`, `fit()`, and off-screen culling.
  - `SceneController` — select / Shift-multi-select / rubber-band / move (grid
    `snap`) / 8 screen-space resize handles for a single selection.
  - `examples/graphics-demo/` flowchart editor + `docs/guides/graphics.md`.
- **App-shell widgets** (`elysium.shell`, Tier 4 — Qt `QMainWindow` parity).
  Immediate-mode Components that recolour with the theme:
  - `GroupBox` (titled bordered container with a content rect), `StatusBar`
    (transient message + right-aligned permanent sections), `Splitter`
    (draggable two-pane divider, H/V, min-size clamped), `MenuBar` (persistent
    in-window menu bar over the existing `Menu`/`MenuItem`).
  - `ToolButton`/`ToolBar` (icon/text tool strips with separators + a flexible
    spacer; pluggable icon painter; checked/disabled states), `TabWidget`
    (content-width closable tabs + content routing).
  - `DockWidget`/`DockManager` (`QDockWidget` parity): left/right/bottom/centre
    dock areas, per-area tabbing, splitter resize between areas, drag-a-tab to
    re-dock with drop-zone overlays, and layout save/restore via `serialize()` /
    `restore()` (wire to `elysium.settings`).
- **Studio theme + design tokens** (Designer redesign, part A1): new
  `elysium.theme.studio_dark()` / `studio_light()` built-ins (the clean
  professional "Studio" direction), plus new `Theme` tokens — a spacing scale
  (`space_xs..xl`), state opacities (`opacity_disabled/hover/focus`), and
  `font_family`. Exported the previously-internal `oled()` theme.
- **App-wide UI font:** `elysium.theme.set_ui_font(family_or_path)` and native
  `set_ui_font` / `register_ui_font` — set a preferred UI font family or
  register a bundled `.ttf`/`.otf`. `set_theme` now applies the theme's
  `font_family`. The no-preference default is unchanged (opt-in).

## [1.0.0]

First stable release. Elysium commits to a stable public API under strict
semver. This release consolidates the Qt-parity work (Tiers 1–3) into a
production baseline.

### Added

**Tier 1 — Qt day-one parity**
- Robust text editing: `elysium.text.EditableText`, `TextField`, multi-line
  `TextArea`, caret/selection/undo-redo/word-jump, validators
  (`IntValidator`, `DoubleValidator`, `RegexValidator`) and input `Mask`s.
- IME composition (CJK) and system clipboard integration, routed centrally by
  `elysium.input.InputRouter` + `FocusManager`.
- Standard dialogs: native file pickers (`open_file`/`save_file`/`pick_folder`)
  plus Elysium-rendered `MessageDialog`/`InputDialog`/`ProgressDialog`/
  `ColorDialog`/`FontDialog` via `DialogHost`.
- Model/View: `ItemModel` (+ `QtItemModelAdapter`), virtualized `TableView`/
  `ListView`/`TreeView`, and delegates incl. a GPU `Mesh3DDelegate`.
- Data-entry widgets: `SpinBox`, `DoubleSpinBox`, `DateEdit`, `TimeEdit`,
  `CalendarWidget`, `EditableComboBox`.

**Tier 2 — scale & services**
- True dirty-rect compositing in the render thread (partial repaint +
  skip-when-clean) and reusable virtualization (`VirtualList`, `VirtualForm`).
- Scroll system: `ScrollView`, `ScrollBar`, mouse-wheel routing, `PushClip`.
- Threading → UI marshalling: `elysium.concurrency` (`UiDispatcher`,
  `call_on_ui_thread`, `post`, `@ui_thread`, `run_async`, `FrameLoop`).
- Multi-window depth: `elysium.windowing.WindowManager` (owned/modal windows,
  inter-window messaging).
- Native OS integration: `elysium.native` (single-instance, notifications,
  system tray, global hotkeys) — GTK-free on Linux, capability-gated.
- i18n / RTL / locale: `elysium.i18n` (gettext `tr`/`tr_n`, RTL layout) and
  `elysium.locale` (Babel-backed formatting); paragraph base-direction.
- Settings: `elysium.settings.Settings` (QSettings-equivalent, atomic writes).
- UI test automation: `elysium.testing.UiHarness` (QTest-equivalent).

**Tier 3 — maturity**
- This `CHANGELOG.md`, the [API stability policy](docs/guides/api-stability.md),
  a public-API surface-lock test, and the `elysium.deprecated` /
  `deprecated_alias` deprecation mechanism.
- Pattern guides (CRUD, forms, tables, dialogs), API-reference pages for the
  Tier-1/2 modules, and an explicit [scope/batteries statement](docs/resources/scope-and-batteries.md).
- Broadened end-to-end, scale, and error-path test coverage; `pytest-cov`
  reporting in CI.

### Changed

- **Version → 1.0.0**; package status is now Production/Stable.
- CI (`build.yml`) is green and the test suite (`cargo test` + `pytest`, three
  platforms) now gates merges — the workspace `cargo fmt`/`clippy` debt that
  previously blocked it has been cleared.

### Deprecated

- _Nothing yet — the deprecation path is in place for future changes._

[Unreleased]: https://github.com/elysiumui/elysium/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/elysiumui/elysium/releases/tag/v1.0.0
