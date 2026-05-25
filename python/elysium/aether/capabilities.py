"""Machine-readable capability manifest fed verbatim into the LLM's
system prompt so the model knows what's available."""
from __future__ import annotations

import json
from pathlib import Path


def build_manifest() -> dict:
    out: dict = {
        "components": [], "easings": [], "studios": [],
        "material_presets": [], "draw_commands": [],
        "hook_kinds": ["event","text","image","value","state","slot","style"],
        "missing": [],
    }
    try:
        from elysium import components
        out["components"] = sorted([n for n in dir(components)
                                      if n[0].isupper()
                                      and not n.startswith("_")])
    except Exception: pass
    try:
        from elysium.anim import EASINGS
        out["easings"] = sorted(EASINGS.keys())
    except Exception:
        out["easings"] = ["linear","ease_in","ease_out","ease_in_out",
                          "spring","ease-in-sine","ease-out-cubic"]
    try:
        from elysium.render import pbr
        out["studios"] = list(pbr.STUDIOS.keys())
        out["material_presets"] = list(pbr.PRESETS.keys())
        out["mesh_library"] = list(pbr.MESH_LIBRARY.keys())
    except Exception: pass
    out["draw_commands"] = [
        "FillPath","FillPathLinearGradient","FillPathRadialGradient",
        "StrokePath","DrawText","DrawParagraph","DrawImageFile",
        "DrawImageBytes","DrawImageFileTransformed","DrawImageFileRegion",
        "FilledCircle","GradientCard","PushTransform","PopTransform",
        "SkslEffect",
    ]
    # Read existing capability gaps from the local feedback digest so
    # the agent doesn't re-file the same request.
    digest = Path.home() / ".elysium" / "feedback"
    if digest.is_dir():
        for f in digest.glob("*.jsonl"):
            for line in f.read_text().splitlines():
                try:
                    out["missing"].append(json.loads(line).get("name"))
                except Exception: pass
    return out


__all__ = ["build_manifest"]
