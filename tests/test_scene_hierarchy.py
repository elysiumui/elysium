from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from elysium import scene_identity
from elysium.render import mesh_document, primitives, scene


def cube(name):
    p = SimpleNamespace(kind="Mesh3D", props={}, name=name, entity_id=scene_identity.new_id())
    primitives.bind(p, "Cube")
    return p


def test_wing_hinge_moves_engine_and_cannon_about_root():
    wing, engine, cannon = (cube(n) for n in ("Wing", "Engine", "Cannon"))
    objects = [wing, engine, cannon]
    scene.update(wing, {"location": [1, 0, 0]})
    scene.update(engine, {"location": [2, 0, 0]})
    scene.update(cannon, {"location": [6, 0, 0]})
    scene.set_parent(objects, engine, wing)
    scene.set_parent(objects, cannon, wing)
    scene.update(wing, {"rotation": [0, 0, 90]})
    world = scene.world_matrices(objects)
    np.testing.assert_allclose(world[1][:3, 3], [1, 1, 0], atol=1e-6)
    np.testing.assert_allclose(world[2][:3, 3], [1, 5, 0], atol=1e-6)
    # Rename has no effect on identity-based hierarchy.
    wing.name = "Renamed"
    np.testing.assert_allclose(scene.world_matrices(objects), world)


def test_cycles_rejected_atomically_and_unparent_preserves_shear():
    a, b, c = (cube(n) for n in "ABC")
    objects = [a, b, c]
    scene.update(a, {"rotation": [10, 20, 30], "scale": [2, 3, 4]})
    scene.set_parent(objects, b, a, keep_world=False)
    scene.update(b, {"rotation": [12, -17, 27]})
    scene.set_parent(objects, c, b, keep_world=False)
    before = deepcopy(a.props)
    with pytest.raises(ValueError, match="cycle"):
        scene.set_parent(objects, a, c)
    assert a.props == before
    world = scene.world_matrices(objects)
    scene.set_parent(objects, b, None)
    np.testing.assert_allclose(scene.world_matrices(objects), world, atol=1e-6)


def test_apply_preserves_world_geometry_child_matrix_and_uvs():
    a, b = cube("A"), cube("B")
    objects = [a, b]
    scene.update(
        a,
        {"location": [2, 1, 3], "rotation": [10, 20, 30], "scale": [-2, 3, 1], "pivot": [1, 0, 0]},
    )
    scene.set_parent(objects, b, a, keep_world=False)
    original_mesh = mesh_document.resolve(a.mesh_kind)
    original_uvs = None if original_mesh.vert_uvs is None else original_mesh.vert_uvs.copy()
    world = scene.world_matrices(objects)
    expected = original_mesh.verts @ world[0][:3, :3].T + world[0][:3, 3]
    scene.apply_transform(objects, a)
    mesh = mesh_document.resolve(a.mesh_kind)
    np.testing.assert_allclose(mesh.verts, expected, atol=1e-6)
    np.testing.assert_allclose(scene.world_matrices(objects)[1], world[1], atol=1e-6)
    assert scene.transform(a) == scene.DEFAULT
    if original_uvs is not None:
        np.testing.assert_array_equal(mesh.vert_uvs, original_uvs)


def test_removing_parent_preserves_surviving_descendants():
    a, b, c = (cube(n) for n in "ABC")
    objects = [a, b, c]
    scene.set_parent(objects, b, a, keep_world=False)
    scene.set_parent(objects, c, b, keep_world=False)
    scene.update(a, {"rotation": [0, 0, 22], "location": [2, 3, 4]})
    before = scene.world_matrices(objects)
    scene.detach_children(objects, [a])
    np.testing.assert_allclose(scene.world_matrices([b, c]), before[1:], atol=1e-6)


def test_missing_parent_fails_before_restoring_mesh_assets():
    p = cube("Bad")
    p.props["parent3d"] = {"id": "entity:missing"}
    with pytest.raises(ValueError, match="Missing parent"):
        mesh_document.capture([p])
