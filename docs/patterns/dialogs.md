# Dialogs

Elysium has two dialog families: **native file dialogs** (the real OS picker)
and **Elysium-rendered modals** (borderless, themed, GPU-drawn) managed by a
[`DialogHost`](../api/dialogs.md). The rendered dialogs are *non-blocking* — they
fit the immediate-mode loop instead of spinning a nested event loop like Qt's
`exec()`.

## Native file dialogs

```python
from elysium import dialogs as D

path   = D.open_file(title="Open", filter_label="Images", filter_patterns=["*.png", "*.jpg"])
out    = D.save_file(default_name="export.png")
folder = D.pick_folder()
```

## The DialogHost

Install one `DialogHost` per window. Each frame: `update(dt)`, `paint(dl)`, and
forward mouse/key. Dialogs resolve through an `on_result` callback and expose a
pollable `.result` / `.done`.

```python
from elysium import dialogs as D

host = D.DialogHost(win)

# In your frame loop:
#   host.update(dt)
#   host.paint(dl)
#   if host.is_modal:
#       host.on_mouse_press(*cursor)   # on click
#       host.on_key(code, mods)        # on key
```

## Message & input dialogs

```python
dlg = host.message("Delete file?", "This can't be undone.",
                   buttons=["Cancel", "Delete"])
dlg.on_result = lambda label: do_delete() if label == "Delete" else None

name = host.input("Rename", "New name:", default="untitled")
name.on_result = lambda value: rename(value) if value is not None else None
```

`Enter` triggers the primary (last) button; `Escape` triggers the first
(Cancel) button.

## Progress, color & font

```python
prog = host.progress("Exporting…", cancelable=True)
prog.set_progress(0.5)            # 0..1; or leave indeterminate
prog.close()

host.color(initial=(122, 88, 244, 255))   # resolves to (r, g, b, a)
host.font()                                # resolves to (family, size)
```

## Modal stacking & non-blocking results

`DialogHost` keeps a stack — opening a second dialog over the first makes only
the topmost one take input, and closing it returns focus to the one beneath.
Because results arrive via callbacks (not a blocking return), your frame loop
keeps running and rendering underneath the scrim.

## OS-modal child windows

For a dialog that should be a *real* OS window (its own taskbar entry, movable
off the parent), open an owned modal window with the
[`WindowManager`](../api/windowing.md) instead — it blocks the owner's input
until closed:

```python
from elysium.windowing import WindowManager

wm = WindowManager(app)
main = wm.open(initial_size=(900, 600))
dlg = wm.open(owner=main, modal=True, initial_size=(360, 220))   # blocks `main`
# ... when done:
wm.close(dlg)                                                    # focus returns to main
```
