# How do I show a modal that returns a value?

Open a modal window, hold the "result" in a signal, and have the
caller wait on a callback.

```python
import elysium as ely
from elysium.reactive import signal

def confirm(parent, title: str, message: str, on_result):
    """Open a confirm dialog. on_result is called with True/False."""
    dialog = ely.current_app().window(
        transparent=True, title_bar=False, resizable=False,
        initial_size=(360, 160),
        parent=parent, modal=True,
    )
    dialog.load_skin("confirm.esk/")
    dialog.title_label.text = title
    dialog.message_label.text = message

    @dialog.on("yes.click")
    def yes(event):
        on_result(True)
        dialog.close()

    @dialog.on("no.click")
    def no(event):
        on_result(False)
        dialog.close()
```

Use it:

```python
@main.on("delete.click")
def maybe_delete(event):
    confirm(main, "Delete?", "This cannot be undone.",
            on_result=lambda yes: yes and do_delete())
```

The framework's modal mode blocks input to the parent until the
dialog closes. The callback gives you the return value when it's
ready: no `await` needed.

See [Windowing](../guides/windowing.md).
