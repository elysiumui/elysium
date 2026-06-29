# Developer handoff

You are building a production app on Elysium. This page is the map: where to
start, what's available, and how the framework and the Designer IDE fit together.

## Start here

1. **[Install](../getting-started/install.md)** the framework, then run
   **[Hello World](../getting-started/hello-world.md)** to confirm your toolchain.
2. Read **[Architecture](architecture.md)** for the immediate-mode mental model
   (build a `DisplayList` each frame; widgets paint themselves and read the theme
   at paint time).
3. Work through **[Build a Shopify-style desktop app](../tutorials/shopify-style-desktop-app.md)**
   — it builds a dashboard and a bulk editor end to end, the two screens most
   data apps need.

## What's available

- **[Component gallery](../resources/component-gallery.md)** — every widget,
  categorized, with links to its guide and API.
- **[API reference](../api/index.md)** — auto-generated from the source for every
  public module. Each page lists exact signatures and docstrings.
- **[Scope and batteries](../resources/scope-and-batteries.md)** — what is in and
  out of scope, so you know what to build yourself.
- **[Porting from Qt](porting-from-qt.md)** — a class-by-class map if you are
  coming from PySide6 / PyQt.

## Building the UI

| Need | Guide |
| --- | --- |
| Windows, shape, transparency | [Windowing](windowing.md), [Borderless and shaped](borderless-and-shaped.md) |
| The app frame (toolbars, docks, tabs, status bar) | [App shell](app-shell.md) |
| Charts, KPI cards, alerts, date bar | [Charts and dashboards](charts-and-dashboards.md) |
| An editable data grid | [The data grid](data-grid.md) |
| Multi-step flows + slide-out panels | [Wizards and flows](wizards-and-flows.md) |
| Undo/redo + actions | [Commands and undo](commands-and-undo.md) |
| An interactive canvas | [Interactive 2D canvas](graphics.md) |
| Rich text, drag-and-drop, autocomplete | [Rich text](rich-text.md), [Drag and drop](drag-and-drop.md), [Completer](completer.md) |
| Theme, fonts, tabular numerals | [Theming](theming.md) |
| Styling + accessibility | [Styling and accessibility](styling-and-a11y.md), [Accessibility](accessibility.md) |
| Layout, animation, reactive state | [Layout](layout.md), [Animation](animation.md), [Reactive bindings](reactive.md) |
| Threading / background work | [Threading and services](threading-and-services.md) |
| Package + auto-update | [Packaging](packaging.md), [Auto-update](auto-update.md) |

## Designing in the Designer IDE

The **Designer** is the visual companion to the framework — author themes, skins,
icons and shaped windows, preview them live, and sync back to code.

- Designer docs: see the **Elysium Designer** documentation site (built from
  `mkdocs-designer.yml`).
- The handoff loop is covered in **[Designer → code → ship](designer-to-code.md)**
  and **[Code Link](code-link.md)** (pair the Designer with your editor, scaffold
  event handlers, hot-reload skins into the running app).
- Theme tokens authored in the Designer map directly onto the
  [Theming](theming.md) API your code reads at paint time.

## Stability

Public APIs follow [semantic versioning](api-stability.md); the surface is
snapshot-locked in CI, so a minor upgrade will not break your imports. The
[changelog](../resources/changelog.md) records every addition.

## See also

- [Getting started overview](../getting-started/index.md)
- [Component gallery](../resources/component-gallery.md)
- [API reference](../api/index.md)
