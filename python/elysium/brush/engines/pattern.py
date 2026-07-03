"""Pattern — tiles a sampled image stamp along the stroke.

The pattern source is a path to a PNG/PSD/JPG — referenced by
``params["pattern_path"]`` and resolved either against the user
brushes dir or the skin folder. Phase A: schema only."""
from __future__ import annotations

from ..engine import BrushEngine, ParamSpec, register_engine


class Pattern(BrushEngine):
    ID = "Pattern"
    LABEL = "Pattern"
    DESCRIPTION = "Stamps a sampled image along the stroke — chains, scales, leaves, custom shapes."
    PARAM_SCHEMA = (
        ParamSpec("size",         "Size",         "float", 40.0, min=2.0, max=400.0, step=1.0),
        ParamSpec("opacity",      "Opacity",      "float", 1.00, min=0.0, max=1.0,   step=0.01),
        ParamSpec("flow",         "Flow",         "float", 1.00, min=0.0, max=1.0,   step=0.01),
        ParamSpec("spacing",      "Spacing",      "float", 1.00, min=0.05, max=4.0,  step=0.05,
                   hint="Multiple of brush size between stamps — 1.0 = touching, 2.0 = doubled."),
        ParamSpec("rotation",     "Rotation",    "enum", "follow",
                   choices=("none", "follow", "random"),
                   hint="How each stamp's rotation is derived."),
        ParamSpec("scale_jitter", "Scale Jitter", "float", 0.10, min=0.0, max=1.0,   step=0.01,
                   hint="Per-stamp scale randomness (deterministic from stamp index)."),
        ParamSpec("hue_jitter",   "Hue Jitter",   "float", 0.0,  min=0.0, max=1.0,   step=0.01),
        ParamSpec("pattern_path", "Pattern Image", "path",  ""),
    )


register_engine(Pattern())
