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


@pytest.mark.parametrize(
    "yaw,pitch,colors",
    [
        (np.pi, 0, ((150, 65, 65), (75, 145, 80))),
        (np.pi / 2, 0, ((75, 145, 80), (65, 100, 170))),
        (0, np.pi / 2, ((150, 65, 65), (65, 100, 170))),
    ],
)
def test_axis_orthographic_views_show_meter_grid_and_world_axes(yaw, pitch, colors):
    rgba, ids = scene.render(
        [], 120, 120, yaw=yaw, pitch=pitch, projection="orthographic", ortho_scale=6
    )
    pixels = np.frombuffer(rgba, np.uint8).reshape(120, 120, 4)
    assert (ids == -1).all()
    for color in colors:
        assert np.count_nonzero(np.all(pixels[:, :, :3] == color, axis=2)) >= 100
    # Six meters span 119 sample intervals. Antialiasing changes line
    # brightness with subpixel phase; compare line centers, not RGB repeats.
    columns = np.flatnonzero(np.any(pixels[10, :, :3] != (48, 49, 52), axis=1))
    groups = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
    assert len(groups) == 7
    np.testing.assert_allclose([g.mean() for g in groups], np.linspace(0, 119, 7), atol=0.75)


def test_orthographic_grid_does_not_overlay_mesh_or_change_hit_identity():
    p = primitive()
    view = {"yaw": np.pi, "pitch": 0, "projection": "orthographic", "ortho_scale": 6}
    plain, ids = scene.render([p], 120, 120, grid=False, **view)
    gridded, grid_ids = scene.render([p], 120, 120, grid=True, **view)
    plain = np.frombuffer(plain, np.uint8).reshape(120, 120, 4)
    gridded = np.frombuffer(gridded, np.uint8).reshape(120, 120, 4)
    np.testing.assert_array_equal(ids, grid_ids)
    np.testing.assert_array_equal(plain[ids >= 0], gridded[ids >= 0])
    assert (plain[ids < 0, 3] == 0).all()
    assert (gridded[ids < 0, 3] == 255).all()


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


def test_empty_and_wire_mesh_render_grid_and_frame_without_false_object_hits():
    from elysium.render import topology

    p = primitive("Plane")
    mesh = mesh_document.resolve(p.mesh_kind)
    wire = topology.delete_components(mesh, "edges", [mesh.topology["edges"][0]["id"]])
    mesh_document.bind(p, wire)
    target, distance = scene.frame([p])
    np.testing.assert_allclose(target, [0, 0, 0])
    assert distance > 0
    for candidate in (
        wire,
        topology.delete_components(mesh, "faces", [f["id"] for f in mesh.topology["faces"]]),
    ):
        mesh_document.bind(p, candidate)
        rgba, ids = scene.render([p], 40, 40, component_output={})
        assert (ids == -1).all()
        assert len(rgba) == 40 * 40 * 4
        assert np.isfinite(scene.frame([p])[1])
