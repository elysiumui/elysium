"""Shared world-space light/transform context for individual Layout previews."""
import json

import numpy as np

from . import pbr, scene, scene_lighting


def context(placement, window=None, placements=None):
    """Capture immutable job inputs before a render worker is started."""
    matrix = np.eye(4)
    if placements is not None:
        index = next((i for i, p in enumerate(placements) if p is placement), None)
        if index is not None:
            matrix = scene.world_matrices(placements)[index]
    return {
        'matrix': matrix.tolist(),
        'lighting': scene_lighting.settings(getattr(window, 'scene_lighting', None)),
        'studio': getattr(window, 'studio', None) or getattr(placement, '_studio_override', None) or 'Default Soft Studio',
    }


def key(values):
    return json.dumps(values, sort_keys=True, separators=(',', ':'))


def prepare(obj, values):
    """Bake the object's parent transform while keeping lighting in world space.

    Layout thumbnails render one object independently; other placements do
    not cast shadows into its thumbnail. Scene snapshots render the complete
    scene and include inter-object occlusion.
    """
    from .mesh_tangents import corner_tangents, transform
    matrix = np.asarray(values['matrix'], dtype=np.float64)
    local = pbr._euler_rot(*obj.rotation) @ np.diag(obj.scale)
    linear = matrix[:3, :3] @ local
    offset = matrix[:3, :3] @ np.asarray(obj.translation) + matrix[:3, 3]
    mesh = obj.mesh
    frames = None
    if any(mat.normal_map is not None for mat in obj.materials):
        frames = transform(corner_tangents(mesh), linear)
    reflected = np.linalg.det(linear) < 0
    result = pbr.Mesh(
        (mesh.verts @ linear.T + offset).astype(np.float32),
        mesh.faces[:, ::-1].copy() if reflected else mesh.faces.copy(),
        face_mats=mesh.face_mats,
        vert_normals=None if mesh.vert_normals is None else pbr._transform_normals(mesh.vert_normals, linear),
        vert_uvs=mesh.vert_uvs,
        corner_tangents=frames[:, ::-1] if reflected and frames is not None else frames,
    )
    return (pbr.MeshObject(result, obj.materials),
            scene_lighting.environment(values['lighting'], values['studio']),
            tuple(matrix[:3, 3]))
