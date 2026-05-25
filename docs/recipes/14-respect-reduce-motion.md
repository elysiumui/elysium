# How do I respect reduce-motion preferences?

Read `accessibility.current().reduce_motion` and shorten or skip
non-essential animations.

```python
from elysium import accessibility

prefs = accessibility.current()
descent_duration = 0.4 if prefs.reduce_motion else 2.4
descent = Tween(target=..., start=..., end=..., duration=descent_duration)

# Disable a glow ping-pong entirely:
if not prefs.reduce_motion:
    clock.add(glow_pingpong)
```

Subscribe to changes mid-session:

```python
accessibility.subscribe(lambda prefs: print("reduce_motion:", prefs.reduce_motion))
```

What "essential" means is up to your app. Loading spinners and
press feedback usually stay; idle decorative loops should go away
under reduce-motion.

See [Accessibility](../guides/accessibility.md).
