# Command palette launcher

Time: 25 minutes. Difficulty: Intermediate.

A Cmd+K / Ctrl+K global hotkey that summons a borderless rounded
launcher with a fuzzy-search command list. Picks a command, runs
it, dismisses on Esc or outside-click. The pattern behind Raycast,
Alfred, and the VS Code command palette.

## Prerequisites

- Walked through [Pomodoro](../getting-started/pomodoro-01-shape-and-modes.md).
- `pip install elysium-ui`.

## Register the global hotkey

```python
from elysium import platform
import elysium as ely
from elysium.components import CommandPalette

app = ely.App(title="Launcher", identifier="dev.example.launcher")
launcher = None


def open_launcher():
    global launcher
    if launcher is not None:
        launcher.focus()
        return

    launcher = app.window(
        transparent=True, title_bar=False, resizable=False,
        initial_size=(560, 360),
        level=3,
    )
    ROUNDED = (
        "M 24,0 L 536,0 A 24,24 0 0 1 560,24 "
        "L 560,336 A 24,24 0 0 1 536,360 "
        "L 24,360 A 24,24 0 0 1 0,336 "
        "L 0,24 A 24,24 0 0 1 24,0 Z"
    )
    launcher.set_hit_test_path(ROUNDED)
    launcher.load_skin("launcher.esk/")
    center_on_active_screen(launcher)
    launcher.focus()


def center_on_active_screen(win):
    screens = platform.screens()
    s = screens.primary
    x = s.x + (s.width - win.width) // 2
    y = s.y + (s.height - win.height) // 3   # upper-third placement
    win.set_outer_position(x, y)


platform.register_hotkey("Cmd+K", open_launcher)    # macOS
platform.register_hotkey("Ctrl+K", open_launcher)   # Win / Linux
```

## Skin

`launcher.esk/document.json`:

```json
{
  "placements": [
    { "id": "panel", "kind": "rounded_rect",
      "x": 0, "y": 0, "width": 560, "height": 360,
      "radius": 24, "fill": "#1e1b4be0",
      "shadow": { "color": "#000000aa", "blur": 40, "y": 8 } },
    { "id": "search_input", "kind": "text_input",
      "x": 24, "y": 16, "width": 512, "height": 56,
      "placeholder": "Type a command…", "font_size": 18 },
    { "id": "results", "kind": "canvas",
      "x": 24, "y": 80, "width": 512, "height": 264 }
  ]
}
```

## Command list

```python
COMMANDS = [
    {"id": "new_project", "label": "New project",       "subtitle": "Open the project wizard"},
    {"id": "open_file",   "label": "Open file…",        "subtitle": "Browse for a file"},
    {"id": "settings",    "label": "Open settings",     "subtitle": ""},
    {"id": "quit",        "label": "Quit",              "subtitle": "Cmd+Q"},
    {"id": "toggle_theme","label": "Toggle theme",      "subtitle": "Light ↔ Dark"},
]
```

## Filter and render results

```python
from elysium.reactive import signal, effect, computed
from elysium.components import CommandPalette

query = signal("")
highlight = signal(0)


@computed
def filtered():
    q = query().lower()
    if not q:
        return COMMANDS
    return [c for c in COMMANDS if q in c["label"].lower()]


@effect
def push_results():
    # Use CommandPalette's auto-render
    launcher.results.publish_display_list(
        CommandPalette.render(filtered(), highlight=highlight()))
```

`CommandPalette.render(items, highlight)` returns a DisplayList
with the standard launcher look (selection highlight bar, label,
subtitle, shortcut hint).

## Wire keys

```python
@launcher.on("search_input.change")
def on_query(event):
    query.set(event.value)
    highlight.set(0)


@launcher.on("window.key")
def on_key(event):
    global launcher
    if not event.pressed:
        return
    if event.code == "ArrowDown":
        highlight.set(min(highlight() + 1, len(filtered()) - 1))
    elif event.code == "ArrowUp":
        highlight.set(max(highlight() - 1, 0))
    elif event.code == "Enter":
        run(filtered()[highlight()])
    elif event.code == "Escape":
        launcher.close()
        launcher = None


def run(command: dict):
    print("running:", command["id"])
    launcher.close()
```

## Outside-click closes

```python
@launcher.on("window.focus.lost")
def lost(event):
    global launcher
    launcher.close()
    launcher = None
```

## Run

```python
app.run()
```

The app sits in the background. Press Cmd+K from any other app:
the launcher appears, you type, you pick a command, it dismisses.

## Ship

```sh
elysium pack launcher.py --name "Launcher" \
  --identifier dev.example.launcher --include launcher.esk
```

For ship-day polish, mark the app as a background-only agent so
it does not show in the Dock (macOS: `Info.plist` LSUIElement=1;
`elysium pack` supports `--background-only`).

## See also

- [Recipes: global hotkey + CommandPalette](../recipes/19-global-hotkey-command-palette.md)
- [Components overview](../guides/components-overview.md)
