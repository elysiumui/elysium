# Code Link

Two-way wiring between the Designer and your Python source: the same one-click feel Interface Builder gives you in Xcode, or the Forms designer in Visual Studio.

## In the Designer

- **Pair a Python file once.** `Code › Pair Python file…` (or accept the default `<skin>.py` sibling). Stored as `code_file` on the skin.
- **Double-click any placement.** The Designer derives the hook name (e.g. a button named `play` → `play.click`), finds or scaffolds the handler in your paired file, and opens your editor at the right line.
- **Visual badge.** Every placement whose hook has a handler shows a small ↗ in the top-right. Refreshes every ~2s: appears the moment you save.
- **`Code › Scaffold missing handlers`** sweeps every placement and writes a stub for any hook that's not yet wired.

## In your editor

When the LSP is running (VS Code, PyCharm, Neovim, Helix, Zed), a **code lens appears above every `@win.on("hook")` decorator**:

```python
@win.on("play.click")     # → Open 'play.click' in Designer
def on_play_click():
    ...
```

Click the lens and the Designer launches (or refocuses) with that placement pre-selected.

## Handler conventions

The framework recognises two styles. Both round-trip through Code Link.

```python
# 1. Decorator form (preferred: explicit and refactor-safe).
@win.on("play.click")
def on_play_click():
    ...

# 2. Naming-convention form: `on_<hook_with_dots_to_underscores>`.
def on_play_click():
    ...
```

The decorator form is what `scaffold_handler` writes for you.

## Editor auto-detection

The launcher walks `$ELYSIUM_EDITOR` → `$VISUAL` → `$EDITOR`, then probes PATH for VS Code, Cursor, Windsurf, Zed, Sublime, Helix, PyCharm, IntelliJ, Neovim, Vim, Emacs, and Xed in that order. Override per-project with:

```bash
export ELYSIUM_EDITOR=code      # VS Code
export ELYSIUM_EDITOR=cursor    # Cursor
export ELYSIUM_EDITOR=pycharm   # PyCharm
```

## Programmatic API

```python
from elysium.codelink import index_handlers, scaffold_handler, goto_handler

# Discover everything wired in a file.
idx = index_handlers("app.py", known_hooks=["play.click", "pause.click"])
# {"play.click": HandlerLocation(line=12, function="on_play_click", ...)}

# Add a stub if missing.
scaffold_handler("app.py", "stop.click", window_var="win")

# Open the user's editor at the handler, scaffold if needed.
goto_handler("app.py", "track.next.click",
              known_hooks=["track.next.click"], window_var="win")
```

## File watcher integration

When `elysium dev` is watching, edits to the paired Python file
trigger a process restart (preserving window position). Code Link's
"scaffold + open" flow plays nicely with this: scaffolding writes
a stub, the watcher restarts, your handler is now wired live.

## Multi-window apps

Pair one Python file with multiple skins. Each `@window.on(...)`
decoration carries the window variable name; Code Link uses that
to disambiguate.

```python
@main_window.on("save.click")
def save(event): ...

@settings_window.on("save.click")    # different scope
def save_settings(event): ...
```

The Designer routes "open handler" to the right window based on
which Designer panel issued the request.

## Limits

- Code Link only inspects the paired file. Handlers in other
  modules are not auto-discovered.
- The "scaffold missing handlers" sweep writes to the bottom of the
  file in order of `document.json` placement order.
- The framework does not refactor in-file (a renamed hook does not
  rename the handler); use the IDE's rename for that.

## See also

- [Hot reload](hot-reload.md): what plays alongside Code Link.
- [Events](events.md): handler signature details.
- [Designer > Code Link](https://designer.elysiumui.com/code-link/)
 : Designer-side workflow.
