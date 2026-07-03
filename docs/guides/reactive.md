# Reactive

`elysium.reactive` is a fine-grained reactive layer modeled on
Solid.js. No virtual DOM, no diffing: dependencies are tracked
synchronously when you call a signal, and any effect that read
the signal re-runs automatically when it changes.

## Three primitives

| Primitive | What it is |
|---|---|
| `signal(value)` | Mutable cell. Read with `s()`; write with `s.set(v)` |
| `computed(fn)` | Derived read; re-evaluates lazily on signal change |
| `effect(fn)` | Side-effecting callable; re-runs on signal change |

```python
from elysium import reactive

count = reactive.signal(0)
doubled = reactive.computed(lambda: count() * 2)

@reactive.effect
def log():
    print("count =", count(), "doubled =", doubled())

count.set(5)        # prints "count = 5 doubled = 10"
```

## Dependency tracking

When an effect (or computed) runs, every signal it **reads** is
recorded as a dependency. On the next signal change, the effect
re-runs.

```python
toggle = reactive.signal(True)
a = reactive.signal(0)
b = reactive.signal(0)

@reactive.effect
def watch_one():
    if toggle():
        print("a =", a())
    else:
        print("b =", b())
```

If `toggle` is True, the effect depends on `toggle` and `a`. When
you change `toggle` to False, the effect re-runs, this time
recording dependencies on `toggle` and `b`. It will no longer
re-run if `a` changes.

Dependency tracking is **synchronous**: never `await` inside an
effect; the dependency graph would be lost.

## Writing into the skin

The Skin's HookProxy bridges signals → placement attributes:

```python
@reactive.effect
def push_title():
    window.title_label.text = "Score: " + str(score())
```

The effect runs once at registration to record the dependency on
`score`, then again whenever `score.set(...)` is called. The
attribute setter writes through to the native side.

## Higher-level bindings

```python
window.bind("count.text", count)         # one-way: signal → hook attribute
window.bind_two_way("name_input.value", name_signal)   # two-way for inputs
window.bind_list("rows", todos,
                 item=render_todo,
                 key=lambda t: t.id)      # bind a signal-of-list
```

`bind_list` reuses identity-keyed children across updates so
animations on persistent rows survive insertions and deletions.

## Batching

Multiple `set` calls inside a single function call automatically
batch:

```python
def update_user(name, email):
    user_name.set(name)
    user_email.set(email)
    # effects run once at the end of update_user, not twice
```

Use `reactive.batch(fn)` for explicit batching across function
boundaries.

## Untracked reads

To read a signal without registering a dependency:

```python
last_count = reactive.untrack(lambda: count())
```

Useful inside effects when you want to read a signal "as of now"
but not re-run when it changes.

## Cleanup

Effects can register cleanup callbacks that run before the next
re-run (or when the effect is disposed):

```python
@reactive.effect
def timer():
    counter = count()
    handle = schedule(lambda: print(counter))
    reactive.on_cleanup(lambda: handle.cancel())
```

Useful for subscriptions, intervals, and any resource the effect
acquires.

## Disposal

Effects keep running until disposed. To dispose:

```python
dispose = reactive.effect(my_fn)
# later …
dispose()
```

For effects scoped to a window's lifetime, the framework auto-
disposes them when the window closes. For app-lifetime effects,
no manual disposal is needed.

## Threading

`signal.set(...)` is thread-safe. Effects always run on the
thread that owns the dependency tracker (typically the Python
main thread). Setting a signal from a worker thread queues the
effect re-run for the next frame.

## See also

- [Animation](animation.md): drive Tweens off signals.
- [Components overview](components-overview.md): components
  accept signals for props.
- [Recipes: signal + computed for a derived label](../recipes/22-signal-computed-derived-label.md)
