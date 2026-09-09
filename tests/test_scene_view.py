from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, primitives, scene


def primitive(kind="Cube"):
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True)
    primitives.bind(p, kind)
    return p


def test_model_transform_rotates_scales_about_pivot_without_editing_mesh():
    p = primitive()
    before = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    scene.update(
        p, {"location": [3, 0, 0], "pivot": [1, 0, 0], "rotation": [0, 0, 90], "scale": [2, 1, 1]}
    )
    m = scene.matrix(p)
    np.testing.assert_allclose(m @ [1, 0, 0, 1], [4, 0, 0, 1], atol=1e-6)
    np.testing.assert_allclose(m @ [2, 0, 0, 1], [4, 2, 0, 1], atol=1e-6)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == before


@pytest.mark.parametrize(
    "bad",
    [
        {"scale": [0, 1, 1]},
        {"location": [0, float("nan"), 0]},
        {"rotation": [True, 0, 0]},
        {"extra": [0, 0, 0]},
    ],
)
def test_invalid_transform_does_not_mutate(bad):
    p = primitive()
    before = deepcopy(p.props)
    with pytest.raises(ValueError):
        scene.update(p, bad)
    assert p.props == before


def test_shared_depth_hides_far_object_regardless_of_placement_order():
    near, far = primitive(), primitive()
    scene.update(near, {"location": [0, 0, 2]})
    for placements, expected in (([near, far], 0), ([far, near], 1)):
        _, ids = scene.render(placements, 40, 40, distance=10, yaw=0, pitch=0)
        assert ids[20, 20] == expected
        assert set(np.unique(ids)) <= {-1, expected}


def test_grid_and_axes_visible_in_empty_scene():
    rgba, ids = scene.render([], 80, 60)
    pixels = np.frombuffer(rgba, np.uint8).reshape(60, 80, 4)
    assert (ids == -1).all()
    assert (pixels[:, :, 3] == 255).all()
    assert len(np.unique(pixels[:, :, :3].reshape(-1, 3), axis=0)) > 3
    assert ((pixels[:, :, 0] == 150) & (pixels[:, :, 1] == 65)).any()
    assert ((pixels[:, :, 0] == 65) & (pixels[:, :, 2] == 170)).any()


def test_frame_preserves_relative_scale_and_world_position():
    a, b = primitive(), primitive()
    scene.update(b, {"location": [6, 0, 0], "scale": [2, 1, 1]})
    obj, _ = scene.compose([a, b])
    np.testing.assert_allclose(obj.mesh.verts.min(0), [-1, -1, -1])
    np.testing.assert_allclose(obj.mesh.verts.max(0), [8, 1, 1])
    target, distance = scene.frame([a, b])
    np.testing.assert_allclose(target, [3.5, 0, 0])
    assert distance > 10


def test_reflection_keeps_outward_surface_winding():
    p = primitive()
    scene.update(p, {"scale": [-1, 1, 1]})
    obj, _ = scene.compose([p])
    triangles = obj.mesh.verts[obj.mesh.faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    assert (np.sum(normals * triangles.mean(axis=1), axis=1) > 0).all()
