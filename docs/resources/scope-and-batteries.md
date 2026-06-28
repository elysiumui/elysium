# Scope & batteries

Qt ships "batteries included" — `QtNetwork`, `QtMultimedia`, `QtSql`, printing,
and more — as part of the framework. **Elysium deliberately does not.** This
page states that scope decision explicitly so the difference is a considered
trade-off, not a surprise.

## What Elysium *is*

Elysium owns the **UI layer** and the things that are genuinely hard to do well
without deep framework support:

- A GPU-accelerated, **borderless and shaped**, optionally **3-D** rendering
  pipeline (wgpu + Skia).
- The Qt-parity UI surface from Tiers 1–2: text input + IME + clipboard,
  standard dialogs, Model/View tables/trees, data-entry widgets, scrolling +
  virtualization, dirty-rect compositing, threading→UI marshalling,
  multi-window depth, native OS integration, i18n/RTL/locale, settings, and a
  test harness.
- The Designer (a visual authoring tool) and the `.esk` skin pipeline.

## What Elysium intentionally leaves to the ecosystem

Python already has best-in-class libraries for these, and wrapping them would
add surface area we'd have to version and maintain for little gain:

| Qt module | Use instead |
| --- | --- |
| `QtNetwork` | `httpx` / `requests` / `aiohttp`, or stdlib `urllib`, `socket`, `asyncio` |
| `QtMultimedia` | `python-vlc`, `pyav`, `sounddevice`, `miniaudio`, or an embedded WebView |
| `QtSql` | stdlib `sqlite3`, `SQLAlchemy`, or any DB driver |
| Printing | `reportlab` / `weasyprint` → PDF, then the OS print dialog |
| Charts | `matplotlib` (render to an image), or draw with the `DisplayList` API |
| Image codecs beyond load | `Pillow` |

These compose cleanly because Elysium doesn't fight Python: background work runs
on ordinary threads / `asyncio` and marshals results back to the UI with
[`elysium.concurrency`](../api/concurrency.md); data loaded with any library
flows into an [`ItemModel`](../api/modelview.md) and renders in a table.

## Why this is the right call

- **Smaller, sharper surface.** Every public API we ship is one we commit to
  under [strict semver](../guides/api-stability.md). A thin, focused surface is
  one we can keep stable.
- **No lock-in on solved problems.** Networking, audio, and SQL are well-served
  by mature, independently-maintained Python packages. You pick the one that
  fits, and upgrade it on its own schedule.
- **Differentiation where it counts.** The effort goes into the GPU /
  borderless / 3-D capabilities that *don't* exist elsewhere, not into
  re-wrapping libraries that do.

If a batteries-included, single-vendor stack is a hard requirement, Qt/PySide6
remains the right tool. If you want a modern GPU UI that plays well with the
Python ecosystem, that's the trade Elysium makes on purpose.
