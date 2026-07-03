"""Texture — applies a grain mask over a base stamp.

Pencil-on-paper, charcoal-on-canvas, etc. The grain image multiplies
the base stamp's alpha so the stroke picks up the underlying texture.
Phase A: schema only."""
from __future__ import annotations

from ..engine import BrushEngine, ParamSpec, register_engine


class Texture(BrushEngine):
    ID = "Texture"
    LABEL = "Textured"
    DESCRIPTION = "Base stamp masked by a grain image — pencil, charcoal, dry-brush textures."
    PARAM_SCHEMA = (
        ParamSpec("size",          "Size",         "float", 18.0, min=0.5, max=400.0, step=0.5),
        ParamSpec("opacity",       "Opacity",      "float", 1.00, min=0.0, max=1.0,   step=0.01),
        ParamSpec("hardness",      "Hardness",     "float", 0.55, min=0.0, max=1.0,   step=0.01),
        ParamSpec("flow",          "Flow",         "float", 0.85, min=0.0, max=1.0,   step=0.01),
        ParamSpec("spacing",       "Spacing",      "float", 0.07, min=0.01, max=1.0,  step=0.01),
        ParamSpec("grain_path",    "Grain Image",  "path", ""),
        ParamSpec("grain_scale",   "Grain Scale",  "float", 1.00, min=0.1, max=8.0,   step=0.05),
        ParamSpec("grain_rotation", "Grain Rotation", "float", 0.0, min=0.0, max=360.0, step=1.0),
        ParamSpec("grain_blend",   "Grain Blend",  "enum", "multiply",
                   choices=("multiply", "overlay", "screen"),
                   hint="How the grain combines with the base stamp's alpha."),
        ParamSpec("grain_depth",   "Grain Depth",  "float", 0.50, min=0.0, max=1.0,   step=0.01,
                   hint="0 = grain ignored, 1 = grain dominates."),
    )


register_engine(Texture())
