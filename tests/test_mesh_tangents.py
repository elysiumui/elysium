from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from elysium import _native
from elysium.render import mesh_document, mesh_materials, mesh_normals, mesh_tangents, pbr, primitives, scene, topology


def sphere():
    p = SimpleNamespace(kind='Mesh3D', props={}, visible=True, name='Sphere', entity_id='sphere')
    primitives.bind(p, 'Sphere', {'rings': 4, 'segments': 8})
    mesh_normals.set_policy(p, 'smooth')
    return p, mesh_document.resolve(p.mesh_kind)


def test_smooth_sphere_tangents_are_shared_at_matching_corners_and_orthogonal():
    _, m = sphere()
    before = deepcopy(m.topology)
    frames = mesh_tangents.corner_tangents(m)
    normals = m.vert_normals[m.faces]
    np.testing.assert_allclose(np.sum(frames[..., :3]*normals, axis=-1), 0, atol=2e-7)
    np.testing.assert_allclose(np.linalg.norm(frames[..., :3], axis=-1), 1, atol=2e-7)
    groups = {}
    for indices, values in zip(m.faces, frames):
        for vertex, frame in zip(indices, values):
            groups.setdefault(int(vertex), []).append(frame)
    for values in groups.values():
        np.testing.assert_allclose(values, np.broadcast_to(values[0], (len(values), 4)), atol=2e-7)
    assert m.topology == before


def test_uv_normal_and_geometry_edits_invalidate_derived_cache():
    _, m = sphere()
    first = mesh_tangents.corner_tangents(m)
    assert mesh_tangents.corner_tangents(m) is first
    # Clear polygon source to exercise writable render-mesh inputs.
    m.topology = None
    first = mesh_tangents.corner_tangents(m)
    m.vert_uvs[:, 0] *= -1
    mirrored = mesh_tangents.corner_tangents(m)
    assert mirrored is not first
    np.testing.assert_allclose(mirrored[..., 3], -first[..., 3])
    m.verts[:, 0] *= 2
    geometry = mesh_tangents.corner_tangents(m)
    assert geometry is not mirrored
    m.vert_normals[:] = [0, 1, 0]
    assert mesh_tangents.corner_tangents(m) is not geometry


def test_source_quad_uses_four_corner_generation(monkeypatch):
    _, m = sphere()
    mesh_tangents._CACHE.clear()
    original = _native.mesh_corner_tangents
    seen = []
    def record(counts, *args):
        seen.extend(counts)
        return original(counts, *args)
    monkeypatch.setattr(_native, 'mesh_corner_tangents', record)
    mesh_tangents.corner_tangents(m)
    assert seen.count(4) == 16 and seen.count(3) == 16


def test_mapping_uses_barycentric_frames_without_reorthogonalizing():
    _, m = sphere()
    obj = pbr.MeshObject(m, [pbr.Material(normal_map=np.array([[[204, 128, 230]]], np.uint8))])
    index = np.array([12]); u, v = np.array([.2]), np.array([.6])
    fallback = np.array([[0., 1., 0.]])
    n = pbr._shading_normals(obj, index, u, v, fallback)
    frame = mesh_tangents.corner_tangents(m)[index][0]
    t = .2*frame[0, :3] + .2*frame[1, :3] + .6*frame[2, :3]
    sign = frame[0, 3]
    rgb = np.array([204, 128, 230])/255*2-1
    expected = t*rgb[0] + sign*np.cross(n[0], t)*rgb[1] + n[0]*rgb[2]
    expected /= np.linalg.norm(expected)
    actual = pbr._mapped_normals(obj, obj.materials[0], index, np.array([[.5, .5]]), n, m.verts, u, v)
    np.testing.assert_allclose(actual[0], expected, atol=2e-7)


def test_composition_preserves_frames_with_reflection_and_nonuniform_scale(tmp_path):
    p, m = sphere()
    image = tmp_path/'normal.png'; Image.new('RGB', (2, 2), (204, 128, 230)).save(image)
    slot = mesh_materials.read(p)['table']['slots'][0]['id']
    mesh_materials.set_image(p, slot, str(image), 'normal')
    scene.update(p, {"scale": [-2., 3., .5]})
    world = scene.world_matrices([p])[0]
    obj, _ = scene.compose([p], materials=True)
    expected = mesh_tangents.transform(mesh_tangents.corner_tangents(m), world[:3, :3])[:, ::-1]
    np.testing.assert_allclose(obj.mesh.corner_tangents, expected, atol=1e-7)
    assert obj.mesh.topology is None
    assert 'corner_tangents' not in mesh_document.to_json(m)


@pytest.mark.parametrize('counts,positions,normals,uvs', [
    ([5], [[0., 0., 0.]]*5, [[0., 1., 0.]]*5, [[0., 0.]]*5),
    ([3], [[0., 0., 0.]]*2, [[0., 1., 0.]]*3, [[0., 0.]]*3),
    ([3], [[float('nan'), 0., 0.]]*3, [[0., 1., 0.]]*3, [[0., 0.]]*3),
    ([3], [[0., 0., 0.]]*3, [[0., 0., 0.]]*3, [[0., 0.]]*3),
])
def test_native_rejects_invalid_data_before_callbacks(counts, positions, normals, uvs):
    with pytest.raises(ValueError):
        _native.mesh_corner_tangents(counts, positions, normals, uvs)
