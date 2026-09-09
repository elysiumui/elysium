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

# Spring integration safety valves — see SpringValue._advance.
_MAX_SUBSTEPS = 64
# Wall-clock dt ceiling for tick_realtime(). A frame longer than this is a
# stall (window drag, breakpoint, GC pause, laptop resume), never intent.
_MAX_REALTIME_DT = 0.25

# Set by App; explicit tick(dt) remains deterministic for offline evaluation.
_app_time: Callable[[], float] | None = None

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
        # `max(nan, 1e-9)` is nan — max keeps its first argument when the
        # comparison is False — which would poison every `elapsed/duration`.
        _d = _scale_duration(duration)
        self._duration = _d if (math.isfinite(_d) and _d > 1e-9) else 1e-9
        self._ease = globals()["easing"](easing) if isinstance(easing, str) else easing
        self._on_update = on_update
        self._on_complete = on_complete
        self._loop = loop
        self._delay = delay
        self._elapsed = 0.0
        self._reverse = False

    def _advance(self, dt: float) -> None:
        if not math.isfinite(dt):
            return
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
        if not math.isfinite(dt):
            return
        self._elapsed += dt
        if self._total_duration <= 0.0:
            # An empty timeline has nothing to drive, and the loop branches
            # below would divide by zero.
            return
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
    def __init__(self, initial: float, params: Spring | None = None) -> None:
        super().__init__()
        self._value = initial
        self._velocity = 0.0
        self._target = initial
        # NB: a `params: Spring = Spring()` default would be evaluated once at
        # class-definition time, so every default-constructed SpringValue in
        # the process would share — and be able to retune — one Spring.
        self._p = params if params is not None else Spring()

    def target(self, t: float) -> None: self._target = t
    def value(self) -> float: return self._value

    def _snap(self) -> None:
        self._value = self._target
        self._velocity = 0.0

    def _advance(self, dt: float) -> None:
        # Reduce-motion: snap to target instead of simulating.
        try:
            from elysium.accessibility import current as _a11y_current
            if _a11y_current().reduce_motion:
                self._snap()
                return
        except Exception:
            pass
        if not math.isfinite(dt) or dt <= 0.0:
            return
        k, c, m = self._p.stiffness, self._p.damping, self._p.mass
        if not (math.isfinite(k) and math.isfinite(c) and math.isfinite(m)) or m <= 0.0:
            self._snap()
            return

        # Symplectic Euler is only *conditionally* stable: it needs roughly
        # dt < 2/sqrt(k/m) from the spring term and dt < 2m/c from the
        # damping term. With the defaults (k=220, c=18, m=1) that ceiling is
        # ~0.13 s, so a single slow frame — a GC pause, a breakpoint, a laptop
        # waking from sleep — used to diverge geometrically: 40 frames of
        # 0.5 s drove the value to -4.7e73, which then landed straight in a
        # widget's position.
        #
        # Sub-stepping keeps the integrator itself untouched and simply runs
        # it at a stable step size. For every normal frame n == 1, so the
        # arithmetic is bit-identical to before.
        dt_max = math.inf           # unconstrained until a term says otherwise
        if k > 0.0:
            dt_max = min(dt_max, 1.0 / math.sqrt(k / m))
        if c > 0.0:
            dt_max = min(dt_max, m / c)
        n = 1 if dt <= dt_max else int(math.ceil(dt / dt_max))
        if n > _MAX_SUBSTEPS:
            # Faster than the frame can resolve (e.g. mass=1e-9 would need
            # ~3e8 steps). A spring this stiff settles within the frame
            # anyway, so snapping is both correct and cheap.
            self._snap()
            return
        h = dt / n
        for _ in range(n):
            f = -k * (self._value - self._target) - c * self._velocity
            a = f / m
            self._velocity += a * h
            self._value += self._velocity * h


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
        """Advance using wall-clock dt since the last call. Returns the dt
        actually applied.

        The measured interval is capped at `_MAX_REALTIME_DT`: a frame longer
        than that is a stall artifact — a dragged window, a breakpoint, a GC
        pause, a laptop waking from sleep — and feeding it in verbatim makes
        animations jump (and previously made springs diverge outright).
        `tick(dt)` is deliberately *not* clamped: it is the deterministic
        stepping API that tests and fixed-timestep callers rely on.
        """
        now = _app_time() if _app_time is not None else time.perf_counter()
        if self._last_real_time is None:
            self._last_real_time = now
            return 0.0
        dt = now - self._last_real_time
        self._last_real_time = now
        if not math.isfinite(dt) or dt < 0.0:
            return 0.0
        dt = min(dt, _MAX_REALTIME_DT)
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
    wake_on: Any = None,
) -> threading.Thread:
    """Spawn a daemon thread that ticks `on_frame()` at `target_hz` while
    the UI is animating / hovered / pressed, and drops to `idle_hz` after
    `idle_after` seconds with no activity. Pass `is_busy=lambda: True` to
    disable idle decay entirely (legacy behaviour).

    Pass ``wake_on=window`` to make idling *event-driven*. Without it the loop
    only looks at input when its timer next fires, so at ``idle_hz=4`` a click
    can wait 250 ms to be noticed and a press+release inside one tick is never
    seen as a drag at all. With it, input wakes the loop immediately and the
    next frame runs on the busy cadence — so idle stays cheap without the UI
    going deaf between ticks.

    ``wake_on`` is anything exposing ``input_seq`` and
    ``wait_for_input(timeout, since)`` — in practice the native window.
    """
    stop_flag = [False]
    if running is None:
        running = lambda: not stop_flag[0]

    def _waker_failed(waker: Any, what: str) -> None:
        import traceback
        print(f"[elysium] wake_on.{what} raised; falling back to timed "
              f"polling for the rest of this run. Pass a window from a build "
              f"that supports wake-on-input, or omit wake_on. Got: {waker!r}",
              flush=True)
        traceback.print_exc()

    def loop() -> None:
        busy_period = 1.0 / target_hz
        idle_period = 1.0 / max(idle_hz, 0.1)
        last_busy = time.monotonic()
        next_at = time.monotonic()
        # Local, so a `wake_on` that doesn't honour the protocol can be
        # disabled mid-run. These two calls sit outside the try that guards
        # on_frame, so an unguarded raise here killed the daemon thread and
        # left the window alive but frozen — no repaint, and nothing in the
        # log connecting the freeze to wake_on.
        waker = wake_on
        while running():
            frame_start = time.monotonic()
            # Sample the input counter *before* the frame: anything arriving
            # while on_frame runs must still count as "there is work to do",
            # or it would be swallowed and the UI would sit on stale input.
            seq = 0
            if waker is not None:
                try:
                    seq = waker.input_seq
                except Exception:
                    _waker_failed(waker, "input_seq")
                    waker = None
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
                period = busy_period
            elif now - last_busy < idle_after:
                period = busy_period
            else:
                period = idle_period
            # Sleep to a deadline, not for a fixed duration. Sleeping
            # `period` *after* the work means the real rate is
            # 1/(work + period) — so `target_hz` was an unreachable ceiling
            # that sagged as the scene grew: at 60 Hz with a 10 ms frame the
            # loop actually ran at 37 Hz.
            next_at += period
            delay = next_at - time.monotonic()
            if delay <= 0:
                # Overran the budget. Drop the missed frames rather than
                # running a burst to catch up — a burst just steals time from
                # the frame that is already late.
                next_at = time.monotonic()
            elif waker is None:
                time.sleep(delay)
            else:
                try:
                    woke = waker.wait_for_input(delay, seq)
                except Exception:
                    _waker_failed(waker, "wait_for_input")
                    waker = None
                    woke = False
                    # Still owe the caller this frame's delay, or the loop
                    # would spin at full tilt for the rest of the run.
                    time.sleep(max(0.0, next_at - time.monotonic()))
                if woke:
                    # Input landed. Re-aim at the busy cadence — but do NOT run
                    # a frame straight away: pointer events arrive far faster
                    # than the frame rate, and honouring each one would drive
                    # the loop at event rate. Pulling the deadline forward makes
                    # the app responsive without letting input dictate the
                    # frame rate.
                    next_at = min(next_at, frame_start + busy_period)
                    rest = next_at - time.monotonic()
                    if rest > 0:
                        # No point waiting on further input here — we are
                        # already committed to the responsive cadence.
                        time.sleep(rest)

    t = threading.Thread(target=loop, daemon=True, name="elysium-anim")
    t.start()
    return t


__all__ = [
    "easing", "cubic_bezier", "spring",
    "Tween", "Timeline", "StateMachine", "Spring", "SpringValue",
    "Animation", "AnimationClock", "run_animation_thread",
]
