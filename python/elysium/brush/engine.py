"""Brush engine base class — defines how a stroke (a sequence of
samples) becomes pixels on a PaintMask. Engines are *immutable in a
session*: users pick one and parameterise it via a Preset; they don't
edit the engine itself.

Per the Phase A plan: an Engine declares its `PARAM_SCHEMA` (list of
parameter spec dicts), and the Designer's Brush Studio UI auto-generates
sliders from that schema. Adding a 7th engine = one new file in
`engines/`, no other code change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


# Parameter type → widget hint for the auto-generated UI.
# (Phase E's Brush Studio reads this; Phase A just records it.)
ParamType = str  # "float" | "int" | "color" | "path" | "enum" | "bool"


@dataclass(frozen=True)
class ParamSpec:
    """One row in an engine's parameter schema."""
    name:    str                   # machine name, used as preset["params"] key
    label:   str                   # human-readable; shown next to sliders
    type:    ParamType             # "float" / "int" / "color" / "path" / "enum" / "bool"
    default: Any                   # falls back here when a preset omits the field
    min:     float | None = None   # numeric range; ignored for non-numeric types
    max:     float | None = None
    step:    float | None = None
    # For "enum" type, the list of allowed values shown in a dropdown.
    choices: tuple[str, ...] = ()
    # Short tooltip text — surfaced in Tool Properties Dock + Brush Studio.
    hint:    str = ""


class BrushEngine:
    """Subclass once per engine. A subclass must:

      * Set ``ID`` to a stable string used as the preset["engine"] field.
        e.g. "RoundStamp" / "WetMix" / "Bristle".
      * Declare ``PARAM_SCHEMA`` — the list of every tunable parameter.
        Each entry is a ParamSpec.
      * Implement ``stamp(mask, x, y, params, erase)`` and
        ``stroke(mask, x0, y0, x1, y1, params, erase)``. Both write
        pixels into the PaintMask using whatever algorithm the engine
        owns. The base class provides defaults that call straight into
        ``PaintMask.stamp`` / ``stroke`` — sufficient for the
        baseline RoundStamp behavior.

    Engines must be deterministic given the same (samples, params)
    inputs so per-stroke undo can replay them without surprises. Any
    pseudo-randomness (jitter, hue drift) must be seeded by the
    sample's `stamp_index` so two identical strokes produce identical
    pixel output.
    """

    ID: ClassVar[str] = ""
    LABEL: ClassVar[str] = ""             # Display name in Brush Studio + Library.
    DESCRIPTION: ClassVar[str] = ""        # One-line hover hint.
    PARAM_SCHEMA: ClassVar[tuple[ParamSpec, ...]] = ()

    def __init__(self) -> None:
        if not self.ID:
            raise TypeError(
                f"{type(self).__name__} must define ID class attr")

    # ---- parameter helpers --------------------------------------------------

    def defaults(self) -> dict:
        """Return the default param dict — every spec's default value
        keyed by its name. Presets only need to override the params
        they care about; missing keys fall through to these."""
        return {s.name: s.default for s in self.PARAM_SCHEMA}

    def resolve(self, preset_params: dict | None) -> dict:
        """Merge a preset's `params` dict on top of the defaults so the
        engine never sees a missing key. Returns a fresh dict (no
        mutation of inputs)."""
        out = self.defaults()
        if preset_params:
            for k, v in preset_params.items():
                if k in out:
                    out[k] = v
        return out

    # ---- stroke API ---------------------------------------------------------

    def stamp(self, mask, x: float, y: float, params: dict,
                erase: bool = False) -> None:
        """Apply a single dab at (x, y) in mask-local coordinates.
        Subclasses override to add jitter, multi-strand bristles, wet
        blending, etc. Base implementation = the default PaintMask
        stamp call, exactly matching the pre-engine behavior.
        """
        radius = float(params.get("size", 12.0))
        color = tuple(params.get("color", (0, 0, 0, 255)))
        opacity = float(params.get("opacity", 1.0))
        hardness = float(params.get("hardness", 0.6))
        mask.stamp(x, y, radius, color,
                   opacity=opacity, hardness=hardness, erase=erase)

    def stroke(self, mask, x0: float, y0: float, x1: float, y1: float,
                 params: dict, erase: bool = False) -> None:
        """Apply a continuous stroke segment from (x0, y0) to (x1, y1).
        Base implementation calls PaintMask's segment rasteriser so
        the default behavior is pixel-identical to the pre-engine
        brush code path."""
        radius = float(params.get("size", 12.0))
        color = tuple(params.get("color", (0, 0, 0, 255)))
        opacity = float(params.get("opacity", 1.0))
        hardness = float(params.get("hardness", 0.6))
        mask.stroke(x0, y0, x1, y1, radius, color,
                    opacity=opacity, hardness=hardness, erase=erase)


# ---- input-driven dynamics --------------------------------------------------

def _lerp_curve(curve: list, x: float) -> float:
    """Sample a polyline curve (list of (x, y) pairs sorted by x) at
    `x`. Assumes the curve covers [0, 1] in x — extrapolates by
    clamping to the endpoints. Returns the y value (intended as a
    multiplier on a base param; typical y range = [0, 2]).
    """
    if not curve:
        return 1.0
    if x <= curve[0][0]:
        return float(curve[0][1])
    if x >= curve[-1][0]:
        return float(curve[-1][1])
    for i in range(len(curve) - 1):
        x0, y0 = curve[i]
        x1, y1 = curve[i + 1]
        if x0 <= x <= x1:
            if x1 - x0 < 1e-6:
                return float(y0)
            f = (x - x0) / (x1 - x0)
            return float(y0 + (y1 - y0) * f)
    return 1.0


def apply_dynamics(params: dict, dynamics: dict | None,
                    pressure: float = 1.0,
                    velocity: float = 0.0) -> dict:
    """Multiply per-input curves onto the base params.

    Returns a NEW dict (no mutation of the caller's params). The
    inputs map to standard Designer touch input:

      * ``pressure`` — 0..1, sampled from WM_POINTER per stamp (1.0
        when the native layer hasn't reported pressure yet so the
        renderer falls back to "full press" semantics).
      * ``velocity`` — 0..1, normalised stroke speed; 0 = stationary,
        1 = max-speed drag.

    Curve keys recognised by name: ``pressure_<target>``,
    ``velocity_<target>`` where ``<target>`` is ``size``, ``opacity``,
    or ``spacing``. Tilt is intentionally absent — Windows touch
    screens don't report tilt, and surfacing a dial that does nothing
    would mislead the user.

    Missing curves and flat curves (all y == 1) are no-ops so this
    function is safe to call unconditionally — the per-stamp cost is
    a single ``next()`` over the dynamics dict.
    """
    if not dynamics:
        return params
    out = dict(params)
    inputs = {"pressure": float(pressure), "velocity": float(velocity)}
    for key, curve in dynamics.items():
        if not curve: continue
        try:
            inp, target = key.split("_", 1)
        except ValueError:
            continue
        if inp not in inputs:
            continue
        # Tilt curves silently ignored on touch hardware. The Studio
        # tab strip already drops them; this is the renderer-side
        # twin so loading an older preset with a stale tilt curve
        # doesn't crash the stroke.
        if inp == "tilt":
            continue
        if target not in ("size", "opacity", "spacing", "flow"):
            continue
        multiplier = _lerp_curve(curve, inputs[inp])
        base = float(out.get(target, 1.0))
        out[target] = base * multiplier
    return out


# ---- engine registry --------------------------------------------------------

_REGISTRY: dict[str, BrushEngine] = {}


def register_engine(engine: BrushEngine) -> None:
    """Add an engine instance to the global registry. Called by each
    `engines/<name>.py` module at import time. Duplicate IDs overwrite
    silently so hot-reload of an engine module replaces the live
    instance."""
    _REGISTRY[engine.ID] = engine


def get_engine(engine_id: str) -> BrushEngine | None:
    return _REGISTRY.get(engine_id)


def list_engines() -> list[BrushEngine]:
    """Snapshot of every registered engine — order is insertion order
    (stable, so the UI lists them consistently across reloads)."""
    return list(_REGISTRY.values())
