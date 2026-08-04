# `elysium.core`

Small numeric primitives shared across the framework — currently `clamp`, a
NaN-safe replacement for the `min(max(v, lo), hi)` idiom.

That idiom looks correct but returns `nan` unchanged for a `nan` input, because
every comparison against NaN is false and both `min` and `max` fall through. A
NaN that survives a clamp goes on to poison whatever consumes it — a zoom
factor, a scroll offset, a device coordinate — and usually only surfaces a frame
later, far from the code that produced it.

```python
from elysium.core import clamp

clamp(5.0, 0.0, 1.0)            # 1.0
clamp(float("nan"), 0.0, 1.0)   # 0.0  — not nan
```

## Auto-rendered details

::: elysium.core
