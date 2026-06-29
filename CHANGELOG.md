# Changelog

All notable changes to Elysium are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and from 1.0.0 the
project adheres to [Semantic Versioning](https://semver.org) — see
[API stability](docs/guides/api-stability.md).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/klamaute/Elysium/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/klamaute/Elysium/releases/tag/v1.0.0
