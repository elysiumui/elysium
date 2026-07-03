"""RoundStamp — the baseline brush engine.

Each sample stamps a single radial dot via PaintMask. This is the exact
algorithm the existing Designer uses today; porting it here is what
makes the Phase A pixel-parity gate trivially passable. The default
``stamp`` / ``stroke`` in the base class already calls PaintMask the
same way `_brush_apply` does, so the only customisation here is the
parameter schema + the engine ID."""
from __future__ import annotations

from ..engine import BrushEngine, ParamSpec, register_engine


class RoundStamp(BrushEngine):
    ID = "RoundStamp"
    LABEL = "Round Stamp"
    DESCRIPTION = "Single radial dab per sample — the baseline ink / pencil / pen engine."
    PARAM_SCHEMA = (
        ParamSpec("size",     "Size",     "float", 12.0,  min=0.5,  max=400.0, step=0.5,
                   hint="Brush radius in pixels."),
        ParamSpec("opacity",  "Opacity",  "float",  1.0,  min=0.0,  max=1.0,   step=0.01,
                   hint="Stroke alpha — 0 = invisible, 1 = solid."),
        ParamSpec("hardness", "Hardness", "float",  0.6,  min=0.0,  max=1.0,   step=0.01,
                   hint="Edge softness — 0 = soft falloff, 1 = hard edge."),
        ParamSpec("flow",     "Flow",     "float",  1.0,  min=0.0,  max=1.0,   step=0.01,
                   hint="Per-stamp alpha contribution; lower = build-up over many stamps."),
        ParamSpec("spacing",  "Spacing",  "float",  0.10, min=0.01, max=2.0,   step=0.01,
                   hint="Distance between stamps as a fraction of brush size."),
        ParamSpec("jitter",   "Jitter",   "float",  0.0,  min=0.0,  max=1.0,   step=0.01,
                   hint="Per-stamp position randomness (deterministic from sample index)."),
    )


register_engine(RoundStamp())
