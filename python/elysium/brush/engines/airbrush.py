"""Airbrush — Gaussian-falloff dot, density modulated by flow.

Holding stationary causes the alpha to build up over time (real
airbrush behavior). Phase A: schema only."""
from __future__ import annotations

from ..engine import BrushEngine, ParamSpec, register_engine


class Airbrush(BrushEngine):
    ID = "Airbrush"
    LABEL = "Airbrush"
    DESCRIPTION = "Soft Gaussian-falloff brush; alpha builds up the longer you dwell."
    PARAM_SCHEMA = (
        ParamSpec("size",     "Size",     "float", 60.0, min=2.0, max=400.0, step=1.0),
        ParamSpec("opacity",  "Opacity",  "float", 1.00, min=0.0, max=1.0,   step=0.01),
        ParamSpec("hardness", "Hardness", "float", 0.05, min=0.0, max=1.0,   step=0.01,
                   hint="0 = pure Gaussian falloff; higher = sharper edge."),
        ParamSpec("flow",     "Flow",     "float", 0.15, min=0.01, max=1.0,  step=0.01,
                   hint="Per-frame alpha contribution when holding stationary."),
        ParamSpec("spacing",  "Spacing",  "float", 0.02, min=0.01, max=0.5,  step=0.01),
        ParamSpec("density",  "Density",  "float", 1.00, min=0.0, max=1.0,   step=0.01,
                   hint="Probability of a stamp landing per sample (lower = sparser spray)."),
    )


register_engine(Airbrush())
