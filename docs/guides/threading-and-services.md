# Threading, multi-window, native integration, i18n, settings & testing

The Tier-2 application services. Each maps to a familiar Qt facility.

## Threading → UI marshalling

Elysium's UI runs on one thread. Marshal worker results back with
`elysium.concurrency`:

```python
from elysium.concurrency import call_on_ui_thread, post, ui_thread, run_async, FrameLoop

post(lambda: status.set_text("done"))        # fire-and-forget, runs next tick
fut = call_on_ui_thread(recompute)           # returns a Future

@ui_thread
def on_result(data): table.set_rows(data)    # auto-marshals if off-thread

run_async(fetch())                           # asyncio on a background loop
```

`FrameLoop(window, on_frame)` drains the dispatcher then calls `on_frame(dt)`
each tick — call `window.post(fn)` from any thread.

## Multi-window depth

```python
from elysium.windowing import WindowManager

wm = WindowManager(app)
main = wm.open(initial_size=(900, 600))
dlg = wm.open(owner=main, modal=True, initial_size=(360, 220))   # blocks `main`
# ... when done:
wm.close(dlg)                                # input returns to `main`
wm.send(main, {"saved": True})               # inter-window message
```

Modal children block their owner's input and center over it; closing an owner
cascades to its children.

## Native OS integration

```python
import elysium.native as native

if not native.single_instance("dev.example.app"):
    sys.exit("already running")
native.notify("Build finished", "All tests passed")

tray = native.Tray("MyApp", [("open", "Open"), ("quit", "Quit")])
tray.on("quit", app.quit); tray.create()     # main thread; tray.poll() each frame

keys = native.HotKeys()
keys.register(native.CTRL | native.SHIFT, "KeyR", reload)   # keys.poll() each frame
```

`native.capabilities()` reports per-platform support. Tray + global hotkeys are
macOS/Windows (Linux is GTK-free by design); notifications work everywhere
(native on macOS/Windows, `notify-send` on Linux); power/sleep events arrive via
`window.poll_lifecycle_event()`.

## i18n / RTL / locale

```python
from elysium.i18n import tr, tr_n, install, is_rtl, flip_align
from elysium import locale as L

install("fr", localedir="locale")            # gettext .mo catalogs
label = tr("Save")                           # → "Enregistrer"
count = tr_n("{n} file", "{n} files", n)
amount = L.format_currency(9.9, "EUR", locale="fr")
```

For right-to-left locales, `is_rtl()` / `flip_align()` / `mirror_x()` mirror
layout; paragraphs render with the correct base direction via
`dl.draw_paragraph(..., rtl=True)` (Skia shapes Arabic/Hebrew).

## Settings

```python
from elysium.settings import Settings
s = Settings("myapp", autosave=True)         # platform config dir
s.set("window.size", [900, 600])
w, h = s.get("window.size", [800, 600])
```

Dotted keys form groups; writes are atomic.

## UI test automation

```python
from elysium.testing import UiHarness
h = UiHarness([name_field, save_button])
h.focus("name").type("Ada")
assert h.find("name").value == "Ada"
h.click_widget("save")
```

`UiHarness` drives the real `InputRouter` headlessly — `type`/`key`/`click`/
`scroll`/`find`/`texts` — the QTest equivalent.
