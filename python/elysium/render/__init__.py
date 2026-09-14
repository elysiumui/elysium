"""GPU/CPU rendering helpers for Elysium — currently PBR sphere shading."""
from elysium.render import pbr  # noqa: F401

import importlib as _importlib

# Public submodules, imported lazily (PEP 562) so that `elysium.render.scene`
# resolves as an attribute without paying for every renderer at import time.
# Listed in __all__ so the API-surface lock (tests/test_public_api.py) covers
# the render package.
__all__ = ['animation_curve', 'collections', 'component_transform', 'compute', 'designer_preview', 'layout_lighting', 'material_graph', 'material_image', 'mesh_document', 'mesh_edge_split', 'mesh_edit', 'mesh_materials', 'mesh_modifiers', 'mesh_normals', 'mesh_subdivision', 'mesh_tangents', 'mesh_uv', 'mesh_uv_diagnostics', 'mesh_uv_islands', 'mesh_uv_stitch', 'mesh_uv_unwrap', 'pbr', 'preview', 'primitives', 'scene', 'scene_actions', 'scene_animation', 'scene_export', 'scene_lighting', 'scene_render_job', 'scene_views', 'texture', 'topology']


def __getattr__(name):
    if name in __all__:
        return _importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
