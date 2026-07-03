"""Phase 2.1 animation engine — frame-evaluated tweens, timelines,
springs, and state machines.

Architecture:

    AnimationClock (one per app)
       └─ tick(dt)  → propagates dt to every active animation
              ├─ Tween:        interpolates one value, calls callback
              ├─ Timeline:     orchestrates many Tweens with offsets
              ├─ StateMachine: drives current_state → animations
              └─ Spring:       physics-based critically damped solver

User code:
    flap = ely.Tween(0.0, 1.0, duration=2.2, easing="ease-in-out-sine",
                     loop="ping_pong", on_update=lambda v: ...)
    flap.start(clock)            # registers with the global clock
    clock.tick(dt)               # call each render frame

For convenience, `ely.run_animation_thread(clock, fn)` spawns a 60 Hz
thread that ticks `clock` and calls `fn()` after each tick — the typical
pattern for a "publish a frame" loop.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Easings.
# ---------------------------------------------------------------------------

def _linear(t: float) -> float: return t
def _ease_in_quad(t: float) -> float: return t * t
def _ease_out_quad(t: float) -> float: return 1.0 - (1.0 - t) * (1.0 - t)
def _ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
def _ease_in_cubic(t: float) -> float: return t ** 3
def _ease_out_cubic(t: float) -> float: return 1 - (1 - t) ** 3
def _ease_in_out_cubic(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
def _ease_out_expo(t: float) -> float:
    return 1.0 if t == 1.0 else 1 - 2 ** (-10 * t)
def _ease_in_sine(t: float) -> float:
    return 1.0 - math.cos((t * math.pi) / 2.0)
def _ease_out_sine(t: float) -> float:
    return math.sin((t * math.pi) / 2.0)
def _ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1.0) / 2.0


_EASINGS: dict[str, Callable[[float], float]] = {
    "linear":             _linear,
    "ease-in-quad":       _ease_in_quad,
    "ease-out-quad":      _ease_out_quad,
    "ease-in-out-quad":   _ease_in_out_quad,
    "ease-in-cubic":      _ease_in_cubic,
    "ease-out-cubic":     _ease_out_cubic,
    "ease-in-out-cubic":  _ease_in_out_cubic,
    "ease-out-expo":      _ease_out_expo,
    "ease-in-sine":       _ease_in_sine,
    "ease-out-sine":      _ease_out_sine,
    "ease-in-out-sine":   _ease_in_out_sine,
}


def cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float) -> Callable[[float], float]:
    """Approximate a CSS-style cubic-bezier easing curve.

    Newton iteration on the X parameter; six iterations is enough to be
    visually indistinguishable for typical UI durations.
    """
    def evaluate(t: float) -> float:
        x = t
        for _ in range(6):
            cx = 3 * (1 - x) ** 2 * x * p1x + 3 * (1 - x) * x ** 2 * p2x + x ** 3
            dx = 3 * (1 - x) ** 2 * p1x + 6 * (1 - x) * x * (p2x - p1x) + 3 * x ** 2 * (1 - p2x)
            if abs(dx) < 1e-6: break
            x -= (cx - t) / dx
        return 3 * (1 - x) ** 2 * x * p1y + 3 * (1 - x) * x ** 2 * p2y + x ** 3
    return evaluate


def spring(stiffness: float, damping: float, mass: float = 1.0) -> Callable[[float], float]:
    """Closed-form damped harmonic oscillator easing — 0..1."""
    omega0 = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))

    def evaluate(t: float) -> float:
        if zeta < 1:
            omega_d = omega0 * math.sqrt(1 - zeta ** 2)
            return 1 - math.exp(-zeta * omega0 * t) * (
                math.cos(omega_d * t) + (zeta * omega0 / omega_d) * math.sin(omega_d * t)
            )
        return 1 - math.exp(-omega0 * t) * (1 + omega0 * t)
    return evaluate


def easing(name_or_fn: str | Callable[[float], float]) -> Callable[[float], float]:
    if callable(name_or_fn):
        return name_or_fn
    if name_or_fn in _EASINGS:
        return _EASINGS[name_or_fn]
    raise KeyError(f"unknown easing: {name_or_fn!r}")


# ---------------------------------------------------------------------------
# Animation primitives.
# ---------------------------------------------------------------------------

LoopMode = str  # "none" | "loop" | "ping_pong"


def _interp(a: Any, b: Any, t: float) -> Any:
    """Interpolate between scalars or same-shape tuples/lists."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * t
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b):
        return type(a)(_interp(ai, bi, t) for ai, bi in zip(a, b))
    raise TypeError(f"cannot interpolate {type(a).__name__} between {a!r} and {b!r}")


def _scale_duration(d: float) -> float:
    """Multiply the requested duration by the OS-reported reduce-motion
    factor. When the user has 'Reduce motion' on we collapse to ~5% of
    the requested time — enough to feel like an instantaneous swap but
    keeps the state-machine transition fire-and-forget contract intact."""
    try:
        from elysium.accessibility import current as _a11y_current
        prefs = _a11y_current()
        return d * (0.05 if prefs.reduce_motion else 1.0)
    except Exception:
        return d


class Animation:
    """Base class — subclasses override `_advance(dt)` and report aliveness."""

    def __init__(self) -> None:
        self.alive = True
        self.clock: "AnimationClock | None" = None

    def start(self, clock: "AnimationClock") -> "Animation":
        self.alive = True
        self.clock = clock
        clock._register(self)
        return self

    def stop(self) -> None:
        self.alive = False
        if self.clock is not None:
            self.clock._unregister(self)

    def _advance(self, dt: float) -> None:
        raise NotImplementedError


class Tween(Animation, Generic[T]):
    """Single-value interpolation.

    >>> v = [0.0]
    >>> def on_update(val): v[0] = val
    >>> t = Tween(0.0, 10.0, duration=1.0, on_update=on_update)
    >>> clock = AnimationClock()
    >>> t.start(clock)
    >>> clock.tick(0.5)
    >>> abs(v[0] - 5.0) < 1e-9
    True
    """

    def __init__(
        self,
        fr: T,
        to: T,
        *,
        duration: float,
        easing: str | Callable[[float], float] = "ease-out-cubic",
        on_update: Callable[[T], None] | None = None,
        on_complete: Callable[[], None] | None = None,
        loop: LoopMode = "none",
        delay: float = 0.0,
    ) -> None:
        super().__init__()
        self._from = fr
        self._to = to
        self._duration = max(_scale_duration(duration), 1e-9)
        self._ease = globals()["easing"](easing) if isinstance(easing, str) else easing
        self._on_update = on_update
        self._on_complete = on_complete
        self._loop = loop
        self._delay = delay
        self._elapsed = 0.0
        self._reverse = False

    def _advance(self, dt: float) -> None:
        if self._delay > 0:
            self._delay -= dt
            if self._delay > 0: return
            dt = -self._delay
            self._delay = 0.0
        self._elapsed += dt
        t = self._elapsed / self._duration
        if t >= 1.0:
            if self._loop == "loop":
                t = t % 1.0
                self._elapsed = t * self._duration
            elif self._loop == "ping_pong":
                cycles = int(self._elapsed / self._duration)
                t = (self._elapsed / self._duration) - cycles
                if cycles % 2 == 1:
                    t = 1.0 - t
                self._elapsed = self._elapsed % (2 * self._duration)
            else:
                t = 1.0
        # Apply easing + emit.
        eased_t = self._ease(t)
        value = _interp(self._from, self._to, eased_t)
        if self._on_update is not None:
            self._on_update(value)
        # Finalize?
        if self._loop == "none" and self._elapsed >= self._duration:
            if self._on_complete is not None:
                self._on_complete()
            self.stop()

    @property
    def value(self) -> T:
        """Current value without advancing — useful for polling display loops."""
        if self._delay > 0: return self._from
        t = min(self._elapsed / self._duration, 1.0)
        if self._loop == "ping_pong":
            cycles = int(self._elapsed / self._duration)
            t = (self._elapsed / self._duration) - cycles
            if cycles % 2 == 1:
                t = 1.0 - t
            t = max(0.0, min(1.0, t))
        return _interp(self._from, self._to, self._ease(t))


class Timeline(Animation):
    """Orchestrates many Tweens at relative offsets.

    >>> values = {}
    >>> tl = Timeline()
    >>> tl.add(Tween(0.0, 1.0, duration=1.0, on_update=lambda v: values.update(a=v)), at=0.0)
    >>> tl.add(Tween(0.0, 1.0, duration=0.5, on_update=lambda v: values.update(b=v)), at=0.5)
    >>> c = AnimationClock(); tl.start(c)
    >>> c.tick(0.25); abs(values['a'] - 0.5 ** 3) < 0.2  # ease-out-cubic at t=0.25
    True
    """

    def __init__(self, *, loop: LoopMode = "none") -> None:
        super().__init__()
        self._entries: list[tuple[float, Animation]] = []
        self._loop = loop
        self._elapsed = 0.0
        self._total_duration = 0.0

    def add(self, anim: Animation, *, at: float = 0.0) -> "Timeline":
        self._entries.append((at, anim))
        if isinstance(anim, Tween):
            anim._on_complete_chained = anim._on_complete  # type: ignore[attr-defined]
            end = at + anim._duration + anim._delay
        else:
            end = at + getattr(anim, "_total_duration", 1.0)
        self._total_duration = max(self._total_duration, end)
        return self

    def _advance(self, dt: float) -> None:
        self._elapsed += dt
        if self._loop == "loop" and self._elapsed > self._total_duration:
            self._elapsed = self._elapsed % self._total_duration
        elif self._loop == "ping_pong" and self._elapsed > self._total_duration:
            cycles = int(self._elapsed / self._total_duration)
            phase = self._elapsed - cycles * self._total_duration
            if cycles % 2 == 1:
                phase = self._total_duration - phase
            self._elapsed = phase
        for at, anim in self._entries:
            if self._elapsed < at:
                continue
            # Drive the child as if its clock started at `at`.
            local_elapsed = self._elapsed - at
            if isinstance(anim, Tween):
                anim._elapsed = local_elapsed
                eased = anim._ease(min(local_elapsed / anim._duration, 1.0))
                value = _interp(anim._from, anim._to, eased)
                if anim._on_update is not None:
                    anim._on_update(value)
        if self._loop == "none" and self._elapsed >= self._total_duration:
            self.stop()


@dataclass
class StateMachine:
    """State graph with named transitions, animated by `Tween`s authored
    per (from_state, to_state) pair.

    >>> sm = StateMachine("idle", {"idle": {}, "hover": {}})
    >>> sm.current == "idle"
    True
    >>> sm.transition_to("hover")
    >>> sm.current == "hover"
    True
    """
    initial: str
    states: dict[str, dict[str, Any]]
    transitions: list[dict[str, Any]] = field(default_factory=list)
    on_change: Callable[[str, str], None] | None = None
    current: str = field(init=False)

    def __post_init__(self) -> None:
        self.current = self.initial

    def transition_to(self, state: str) -> None:
        if state not in self.states:
            raise KeyError(f"unknown state: {state!r}")
        prev = self.current
        self.current = state
        if self.on_change is not None:
            self.on_change(prev, state)


@dataclass
class Spring:
    """Critically-damped harmonic oscillator. Use via `spring()` easing or
    `SpringValue` for time-uncoupled simulation."""
    stiffness: float = 220.0
    damping: float = 18.0
    mass: float = 1.0


class SpringValue(Animation):
    """Time-uncoupled spring — give it a moving target each frame, it
    chases naturally. Used for cursor-following, etc."""
    def __init__(self, initial: float, params: Spring = Spring()) -> None:
        super().__init__()
        self._value = initial
        self._velocity = 0.0
        self._target = initial
        self._p = params

    def target(self, t: float) -> None: self._target = t
    def value(self) -> float: return self._value

    def _advance(self, dt: float) -> None:
        # Reduce-motion: snap to target instead of simulating.
        try:
            from elysium.accessibility import current as _a11y_current
            if _a11y_current().reduce_motion:
                self._value = self._target
                self._velocity = 0.0
                return
        except Exception:
            pass
        # Symplectic Euler.
        f = -self._p.stiffness * (self._value - self._target) - self._p.damping * self._velocity
        a = f / self._p.mass
        self._velocity += a * dt
        self._value += self._velocity * dt


# ---------------------------------------------------------------------------
# Clock + helpers.
# ---------------------------------------------------------------------------

class AnimationClock:
    """Owns the set of live animations and ticks them in lockstep.

    `tick(dt)` is normally driven by the render loop; tests can call it
    with explicit dt values for deterministic stepping.
    """
    def __init__(self) -> None:
        self._anims: list[Animation] = []
        self._lock = threading.Lock()
        self._last_real_time: float | None = None

    def _register(self, a: Animation) -> None:
        with self._lock:
            if a not in self._anims:
                self._anims.append(a)

    def _unregister(self, a: Animation) -> None:
        with self._lock:
            if a in self._anims:
                self._anims.remove(a)

    def tick(self, dt: float) -> None:
        with self._lock:
            snapshot = list(self._anims)
        for a in snapshot:
            if a.alive:
                a._advance(dt)
        # GC dead anims.
        with self._lock:
            self._anims = [a for a in self._anims if a.alive]

    def tick_realtime(self) -> float:
        """Advance using wall-clock dt since the last call. Returns dt."""
        now = time.perf_counter()
        if self._last_real_time is None:
            self._last_real_time = now
            return 0.0
        dt = now - self._last_real_time
        self._last_real_time = now
        self.tick(dt)
        return dt

    def __len__(self) -> int:
        with self._lock:
            return len(self._anims)


def run_animation_thread(
    clock: AnimationClock,
    on_frame: Callable[[], None],
    *,
    target_hz: float = 60.0,
    idle_hz: float = 4.0,
    idle_after: float = 0.6,
    is_busy: Callable[[], bool] | None = None,
    running: Callable[[], bool] | None = None,
) -> threading.Thread:
    """Spawn a daemon thread that ticks `on_frame()` at `target_hz` while
    the UI is animating / hovered / pressed, and drops to `idle_hz` after
    `idle_after` seconds with no activity. Pass `is_busy=lambda: True` to
    disable idle decay entirely (legacy behaviour)."""
    stop_flag = [False]
    if running is None:
        running = lambda: not stop_flag[0]

    def loop() -> None:
        busy_period = 1.0 / target_hz
        idle_period = 1.0 / max(idle_hz, 0.1)
        last_busy = time.monotonic()
        while running():
            clock.tick_realtime()
            try:
                on_frame()
            except Exception:
                import traceback
                traceback.print_exc()
                break
            now = time.monotonic()
            if is_busy is None or is_busy():
                last_busy = now
                time.sleep(busy_period)
            elif now - last_busy < idle_after:
                time.sleep(busy_period)
            else:
                time.sleep(idle_period)

    t = threading.Thread(target=loop, daemon=True, name="elysium-anim")
    t.start()
    return t


__all__ = [
    "easing", "cubic_bezier", "spring",
    "Tween", "Timeline", "StateMachine", "Spring", "SpringValue",
    "Animation", "AnimationClock", "run_animation_thread",
]
