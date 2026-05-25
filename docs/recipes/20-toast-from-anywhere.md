# How do I show a Toast from anywhere in the app?

Create one `Toast` on the main window and expose a helper.

```python
from elysium.components import Toast

toast = Toast(window=main_window, duration_ms=3000)

def show_toast(title: str, body: str = ""):
    toast.show(title=title, body=body)
```

Then anywhere:

```python
show_toast("Saved", "your.esk written.")
show_toast("Error", "Bake failed.", kind="error")
```

The `Toast.show(...)` is thread-safe; callable from any worker.
Subsequent calls while one toast is visible queue behind it.

For app-wide use, put `show_toast` in a module that everything
else imports:

```python
# notifications.py
from elysium.components import Toast
_toast = Toast(window=None, duration_ms=3000)

def attach(window):
    _toast.window = window

def show(title, body=""):
    _toast.show(title=title, body=body)
```

In your main file:

```python
import notifications
notifications.attach(main_window)
notifications.show("Hi")
```

See [Components overview](../guides/components-overview.md).
