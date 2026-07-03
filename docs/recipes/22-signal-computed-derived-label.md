# How do I use signal/computed for a derived label?

`computed` derives one value from one or more signals; an effect
pushes the derived value to a label.

```python
from elysium.reactive import signal, computed, effect

first = signal("Ada")
last = signal("Lovelace")

full = computed(lambda: f"{first()} {last()}")


@effect
def update_label():
    window.greeting.text = full()
```

When either `first` or `last` changes, `full()` recomputes (lazily,
only when read), the effect re-runs, and the label updates.

Computed values memoize: calling `full()` twice in a row without
a signal change returns the cached result without re-evaluating
the lambda.

For values that mix signals and constants, prefer `computed` over
plain functions: it tracks the dependencies for you and re-runs
effects only when something it depends on actually changes.

See [Reactive](../guides/reactive.md).
