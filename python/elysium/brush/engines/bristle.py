"""Bristle — multi-strand simulation for ink, charcoal, dry media.

Each stamp draws N small radial dots offset by per-strand vectors; the
strands fan out perpendicular to the stroke direction so the brush
splays naturally on hard turns. Phase A: schema only."""
from __future__ import annotations

from ..engine import BrushEngine, ParamSpec, register_engine


class Bristle(BrushEngine):
    ID = "Bristle"
    LABEL = "Bristle"
    DESCRIPTION = "Multi-strand bristle brush — ink, charcoal, dry-media looks."
    PARAM_SCHEMA = (
        ParamSpec("size",        "Size",        "float", 20.0, min=0.5, max=400.0, step=0.5),
        ParamSpec("opacity",     "Opacity",     "float", 0.95, min=0.0, max=1.0,   step=0.01),
        ParamSpec("hardness",    "Hardness",    "float", 0.85, min=0.0, max=1.0,   step=0.01),
        ParamSpec("flow",        "Flow",        "float", 0.90, min=0.0, max=1.0,   step=0.01),
        ParamSpec("spacing",     "Spacing",     "float", 0.04, min=0.01, max=1.0,  step=0.01),
        ParamSpec("strands",     "Bristle Count", "int", 12,   min=2,    max=64,   step=1,
                   hint="Number of individual strands per stamp."),
        ParamSpec("scatter",     "Scatter",     "float", 0.25, min=0.0, max=1.0,   step=0.01,
                   hint="How far strands deviate from the stamp center."),
        ParamSpec("strand_size", "Strand Size", "float", 0.15, min=0.02, max=0.5,  step=0.01,
                   hint="Radius of each strand dot as a fraction of brush size."),
    )


register_engine(Bristle())
