"""WetMix — Procreate's signature engine.

Samples blend with the underlying mask via alpha-weighted averaging
rather than alpha-over composition. Wetness decays along the stroke so
the brush "dries out" — color pulled into the brush head at the
beginning of a stroke gets deposited along the trail.

Phase A: schema only. The actual sample-blending implementation lands
when this engine ships in Phase B (existing strokes route through
``RoundStamp`` for now, so WetMix has no callers yet)."""
from __future__ import annotations

from ..engine import BrushEngine, ParamSpec, register_engine


class WetMix(BrushEngine):
    ID = "WetMix"
    LABEL = "Wet Mix"
    DESCRIPTION = "Watercolor / oil engine — samples blend with the canvas instead of stamping over it."
    PARAM_SCHEMA = (
        ParamSpec("size",        "Size",       "float", 24.0, min=0.5, max=400.0, step=0.5),
        ParamSpec("opacity",     "Opacity",    "float", 0.85, min=0.0, max=1.0,   step=0.01),
        ParamSpec("hardness",    "Hardness",   "float", 0.30, min=0.0, max=1.0,   step=0.01),
        ParamSpec("flow",        "Flow",       "float", 0.70, min=0.0, max=1.0,   step=0.01),
        ParamSpec("spacing",     "Spacing",    "float", 0.05, min=0.01, max=1.0,  step=0.01),
        ParamSpec("wetness",     "Wetness",    "float", 0.70, min=0.0, max=1.0,   step=0.01,
                   hint="How much canvas color the brush picks up per stamp."),
        ParamSpec("dilution",    "Dilution",   "float", 0.30, min=0.0, max=1.0,   step=0.01,
                   hint="How quickly the picked-up color dilutes the brush color."),
        ParamSpec("dry_rate",    "Dry Rate",   "float", 0.10, min=0.0, max=1.0,   step=0.01,
                   hint="How fast wetness decays along the stroke."),
    )


register_engine(WetMix())
