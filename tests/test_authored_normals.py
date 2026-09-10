"""Authored normals affect lighting without changing intersection geometry."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from elysium.render import mesh_document, pbr, primitives, scene


@pytest.mark.parametrize("scale", [(1, 1, 1), (2, 1, .5), (-2, 1, .5)])
def test_material_shading_uses_interpolated_inverse_transpose_normals(monkeypatch, scale):
    mesh = pbr.Mesh(
        np.array([[-1, -1, 0], [1, -1, 0], [0, 1, 0]], dtype=np.float32),
        np.array([[0, 1, 2]]),
        vert_normals=np.array([[-.6, 0, .8], [.6, 0, .8], [0, .6, .8]], dtype=np.float32),
    )
    obj = pbr.MeshObject(mesh, [pbr.Material()], rotation=(.1, .2, .3), scale=scale)
    captured = []
    original = pbr._shade_pixels

    def record(normals, *args, **kwargs):
        captured.append(normals.copy())
        return original(normals, *args, **kwargs)

    monkeypatch.setattr(pbr, "_shade_pixels", record)
    hits = {}
    env = pbr.to_environment(pbr.STUDIOS["Default Soft Studio"])
    smooth = pbr.render_mesh(41, 41, obj, env, cam_yaw=0, cam_pitch=0, hit_output=hits)
    mask = hits["face_index"] >= 0
    assert mask.any()
    # Independent normal transform: inverse scale followed by the object rotation.
    corner = (mesh.vert_normals / scale) @ pbr._euler_rot(*obj.rotation).T
    corner /= np.linalg.norm(corner, axis=1, keepdims=True)
    u, v = hits["barycentric_u"][mask], hits["barycentric_v"][mask]
    expected = corner[0] * (1-u-v)[:, None] + corner[1] * u[:, None] + corner[2] * v[:, None]
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    expected *= np.where(np.sum(expected * -hits["ray_direction"][mask], axis=1) < 0, -1, 1)[:, None]
    np.testing.assert_allclose(captured[0], expected, atol=2e-7)
    flat_hits = {}
    flat = pbr.render_mesh(41, 41, replace(obj, mesh=replace(mesh, vert_normals=None)), env,
                           cam_yaw=0, cam_pitch=0, hit_output=flat_hits)
    assert smooth != flat
    for key in hits:
        np.testing.assert_array_equal(hits[key], flat_hits[key])


def placement(kind):
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True)
    primitives.bind(p, kind)
    return p


def test_composition_preserves_mixed_flat_and_smooth_normals_under_reflection():
    cube, sphere = placement("Cube"), placement("Sphere")
    scene.update(sphere, {"scale": [-2, 1, .5], "location": [3, 0, 0]})
    obj, face_objects = scene.compose([cube, sphere])
    n_cube = len(mesh_document.resolve(cube.mesh_kind).verts)
    assert not obj.mesh.vert_normals[:n_cube].any()
    positions = obj.mesh.verts[n_cube:] - [3, 0, 0]
    # Ellipsoid gradient in world space.
    expected = positions / np.array([4, 1, .25])
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    np.testing.assert_allclose(obj.mesh.vert_normals[n_cube:], expected, atol=2e-7)
    tri = obj.mesh.verts[obj.mesh.faces[face_objects == 1]]
    geometric = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    smooth = obj.mesh.vert_normals[obj.mesh.faces[face_objects == 1]].mean(axis=1)
    assert (np.sum(geometric * smooth, axis=1) > 0).all()


@pytest.mark.parametrize("shading", ["solid", "material"])
def test_scene_smooth_shading_preserves_source_and_component_depth(shading):
    p = placement("Sphere")
    source = mesh_document.resolve(p.mesh_kind)
    before = mesh_document.to_json(source)
    smooth_hits, flat_hits = {}, {}
    options = dict(grid=False, distance=4, shading=shading)
    smooth, smooth_ids = scene.render([p], 64, 64, component_output=smooth_hits, **options)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == before
    mesh_document.bind(p, replace(source, vert_normals=None, topology=None))
    flat, flat_ids = scene.render([p], 64, 64, component_output=flat_hits, **options)
    assert smooth != flat
    np.testing.assert_array_equal(smooth_ids, flat_ids)
    for key in ("face_index", "depth"):
        np.testing.assert_array_equal(smooth_hits[key], flat_hits[key])


def test_zero_and_singular_normal_fallback_remains_finite():
    mesh = pbr.Mesh(np.zeros((3, 3)), np.array([[0, 1, 2]]), vert_normals=np.zeros((3, 3)))
    obj = pbr.MeshObject(mesh, [pbr.Material()])
    fallback = np.array([[0., 0., 1.]])
    np.testing.assert_array_equal(pbr._shading_normals(obj, np.array([0]), np.array([.2]),
                                                       np.array([.3]), fallback), fallback)
    assert not pbr._transform_normals(np.ones((3, 3)), np.diag([0, 1, 1])).any()
