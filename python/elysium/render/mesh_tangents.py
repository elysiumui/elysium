"""Derived MikkTSpace corner frames; authored geometry is never modified."""
from collections import OrderedDict
import hashlib
import json

import numpy as np

_CACHE = OrderedDict()


def corner_tangents(mesh):
    """Return (triangle, corner, tangent XYZ/sign), retaining source quads.

    Cache keys include array contents and polygon source, so in-place UV,
    normal and geometry edits cannot reuse stale derived frames.
    """
    if mesh.corner_tangents is not None:
        return mesh.corner_tangents
    if mesh.vert_uvs is None or not len(mesh.faces):
        return np.zeros((len(mesh.faces), 3, 4), np.float32)
    digest = hashlib.sha256()
    for a in (mesh.verts, mesh.faces, mesh.vert_normals, mesh.vert_uvs):
        if a is None:
            digest.update(b'none')
        else:
            digest.update(str((a.shape, a.dtype)).encode())
            digest.update(a.tobytes())
    digest.update(json.dumps(mesh.topology, sort_keys=True, separators=(',', ':')).encode())
    key = digest.digest()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    from elysium import _native
    counts, positions, normals, uvs, output_indices = [], [], [], [], []
    if mesh.topology is not None:
        from . import topology
        from .mesh_normals import corner_normals
        doc = mesh.topology
        vertices = {v['id']: v['position'] for v in doc['vertices']}
        generated = corner_normals(doc) if 'shading' in doc else None
        for face in doc['faces']:
            corners = face['corners']
            start = min(range(len(corners)), key=lambda i: int(corners[i]['id'][1:]))
            corners = corners[start:] + corners[:start]
            points = [vertices[c['vertex']] for c in corners]
            fallback = topology.normal(points).tolist()
            ns = [generated[c['id']] if generated is not None else c.get('normal') or fallback for c in corners]
            tex = [c.get('uv') or [0., 0.] for c in corners]
            triangles = topology.triangles(points)
            groups = [list(range(len(corners)))] if len(corners) in (3, 4) else triangles
            for group in groups:
                offset = len(positions)
                counts.append(len(group))
                positions.extend(points[i] for i in group)
                normals.extend(ns[i] for i in group)
                uvs.extend(tex[i] for i in group)
                output_indices.extend([[offset + i for i in t] for t in triangles]
                                      if len(corners) in (3, 4) else [[offset, offset+1, offset+2]])
    else:
        points = mesh.verts[mesh.faces]
        ns = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        ns /= np.maximum(np.linalg.norm(ns, axis=1, keepdims=True), 1e-12)
        ns = np.repeat(ns[:, None, :], 3, axis=1) if mesh.vert_normals is None else mesh.vert_normals[mesh.faces]
        counts = [3] * len(points)
        positions = points.reshape(-1, 3).tolist()
        normals = ns.reshape(-1, 3).tolist()
        uvs = mesh.vert_uvs[mesh.faces].reshape(-1, 2).tolist()
        output_indices = np.arange(len(positions)).reshape(-1, 3)
    ns = np.asarray(normals, np.float32)
    lengths = np.linalg.norm(ns, axis=1, keepdims=True)
    ns = np.divide(ns, lengths, out=np.tile([0., 1., 0.], (len(ns), 1)), where=lengths > 1e-12)
    values = np.asarray(_native.mesh_corner_tangents(counts, positions, ns.tolist(), uvs), np.float32)
    result = values[np.asarray(output_indices)]
    # UV-degenerate triangles retain the original shading normal.
    coords = mesh.vert_uvs[mesh.faces]
    d1, d2 = coords[:, 1] - coords[:, 0], coords[:, 2] - coords[:, 0]
    valid = np.abs(d1[:, 0]*d2[:, 1] - d1[:, 1]*d2[:, 0]) > 1e-12
    result[~valid] = 0
    result.flags.writeable = False
    if result.nbytes > 16 * 1024 * 1024:
        return result
    _CACHE[key] = result
    while len(_CACHE) > 8 or sum(value.nbytes for value in _CACHE.values()) > 16 * 1024 * 1024:
        _CACHE.popitem(last=False)
    return result


def transform(values, linear):
    """Transform tangent vectors and reflection sign, retaining corner order."""
    out = values.copy()
    vectors = out[..., :3] @ linear.T
    lengths = np.linalg.norm(vectors, axis=-1, keepdims=True)
    out[..., :3] = np.divide(vectors, lengths, out=np.zeros_like(vectors), where=lengths > 1e-12)
    out[..., 3] *= -1 if np.linalg.det(linear) < 0 else 1
    return out
