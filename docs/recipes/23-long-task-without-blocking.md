# How do I run a long task without blocking the render thread?

Submit to `elysium.workers.submit(fn, *args)`. The function runs
on a background thread; the framework marshals the result back
to the Python main thread.

```python
from elysium import workers
from elysium.reactive import signal

progress = signal(0.0)
result = signal(None)


def expensive_job():
    for i in range(100):
        # simulate work …
        progress.set((i + 1) / 100)
    return "done"


@window.on("start.click")
def start(event):
    future = workers.submit(expensive_job)
    future.on_done(lambda value: result.set(value))
```

`progress.set` is safe to call from the worker thread; the signal
queues the effect re-runs for the next frame on the main thread.

For UI-blocking tasks (parsing a huge file, running an export),
this is the way. For tasks that should appear and disappear
within a single frame (like a small computation), just run them
on the main thread.

Workers use a thread pool sized at `os.cpu_count()` by default;
configure with `workers.configure(max_workers=N)`.

See [Reactive](../guides/reactive.md) and
[Architecture](../guides/architecture.md).
