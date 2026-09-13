"""NP-06 (a)(b)(c): object-level spaces, gizmo deltas and apply subsets."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from _native_session import native_session  # noqa: F401
from elysium import scene_identity
from elysium.render import mesh_document, mesh_modifiers, pbr, primitives, scene


def cube(name="Cube"):
    p = SimpleNamespace(kind="Mesh3D", props={}, name=name, entity_id=scene_identity.new_id(), visible=True)
    primitives.bind(p, "Cube")
    return p


def group(name="Group"):
    return SimpleNamespace(kind="SceneGroup", props={}, name=name, entity_id=scene_identity.new_id(), visible=True)


def rot(rotation):
    return pbr._euler_rot(*np.radians(rotation)).astype(np.float64)


def rig():
    """A rotated, non-uniformly scaled parent with a rotated, pivoted child."""
    parent, child = group("Parent"), cube("Child")
    objects = [parent, child]
    scene.update(parent, {"location": [1, 2, 3], "rotation": [0, 30, 0], "scale": [2, 2, 2]})
    scene.update(child, {"location": [1, 0, 0], "rotation": [0, 0, 45], "pivot": [0.5, 0, 0]})
    scene.set_parent(objects, child, parent, keep_world=False)
    return objects, parent, child


def world_of(objects, p):
    return scene.world_matrices(objects)[objects.index(p)]


def test_world_space_location_lands_the_origin_at_the_request():
    objects, parent, child = rig()
    scene.set_transform(objects, child, {"location": [4, 5, 6]}, space="world")
    np.testing.assert_allclose(world_of(objects, child)[:3, 3], [4, 5, 6], atol=1e-9)
    assert scene.describe(objects, child, "world")["location"] == pytest.approx([4, 5, 6])
    # Only the location channel was rewritten.
    assert scene.transform(child)["rotation"] == [0, 0, 45] and scene.transform(child)["pivot"] == [0.5, 0, 0]


def test_world_space_rotation_matches_request_and_keeps_scale():
    objects, parent, child = rig()
    scene.update(child, {"scale": [1.5, 1.5, 1.5]})
    scene.set_transform(objects, child, {"rotation": [20, -35, 70]}, space="world")
    rotation, scale = scene.decompose_linear(world_of(objects, child)[:3, :3])
    np.testing.assert_allclose(rotation, rot([20, -35, 70]), atol=1e-6)
    np.testing.assert_allclose(scale, [3, 3, 3], atol=1e-6)
    described = scene.describe(objects, child, "world")
    np.testing.assert_allclose(described["rotation"], [20, -35, 70], atol=1e-4)
    np.testing.assert_allclose(described["scale"], [3, 3, 3], atol=1e-6)


def test_parent_space_location_is_origin_and_local_space_matches_update():
    objects, parent, child = rig()
    scene.set_transform(objects, child, {"location": [2, 3, 4]}, space="parent")
    np.testing.assert_allclose(scene.matrix(child)[:3, 3], [2, 3, 4], atol=1e-12)
    assert scene.describe(objects, child, "parent")["location"] == pytest.approx([2, 3, 4])
    # The stored location differs by the pivot term because the pivot is nonzero.
    assert scene.transform(child)["location"] != pytest.approx([2, 3, 4])
    a, b = deepcopy(child), deepcopy(child)
    expected = scene.update(a, {"location": [7, 8, 9], "rotation": [1, 2, 3]})
    assert scene.set_transform([parent, b], b, {"location": [7, 8, 9], "rotation": [1, 2, 3]}) == expected
    assert a.props == b.props


def test_delta_location_follows_local_world_plane_and_free_directions():
    p = cube()
    scene.update(p, {"rotation": [0, 90, 0]})
    scene.transform_delta([p], p, "location", 2.0, axis="X", space="local")
    np.testing.assert_allclose(scene.matrix(p)[:3, 3], [0, 0, -2], atol=1e-9)
    scene.transform_delta([p], p, "location", 3.0, axis="Z", space="world")
    np.testing.assert_allclose(scene.matrix(p)[:3, 3], [0, 0, 1], atol=1e-9)
    scene.transform_delta([p], p, "location", 1.0, axis="Y", plane=True, free_axis=[3, 4, 0], space="world")
    np.testing.assert_allclose(scene.matrix(p)[:3, 3], [1, 0, 1], atol=1e-9)
    result = scene.transform_delta([p], p, "rotation", 90.0, free_axis=[0, 2, 0], space="world")
    # free_axis is normalised: 90 degrees about +Y, not 180. Compare matrices,
    # since Euler triples are ambiguous at 180 degrees.
    np.testing.assert_allclose(rot(scene.transform(p)["rotation"]), rot([0, 180, 0]), atol=1e-6)
    np.testing.assert_allclose(result["world_matrix"], scene.world_matrices([p])[0])


def test_world_rotation_delta_keeps_pivot_fixed_and_parent_delta_premultiplies():
    objects, parent, child = rig()
    scene.update(parent, {"scale": [1, 1, 1]})
    pivot_world = (world_of(objects, child) @ [0.5, 0, 0, 1])[:3]
    before = world_of(objects, child)[:3, :3]
    scene.transform_delta(objects, child, "rotation", 40.0, axis="Y", space="world")
    after = world_of(objects, child)
    np.testing.assert_allclose((after @ [0.5, 0, 0, 1])[:3], pivot_world, atol=1e-6)
    np.testing.assert_allclose(after[:3, :3], rot([0, 40, 0]) @ before, atol=1e-6)
    local_before = scene.matrix(child)[:3, :3]
    scene.transform_delta(objects, child, "rotation", 25.0, axis="X", space="parent")
    np.testing.assert_allclose(scene.matrix(child)[:3, :3], rot([25, 0, 0]) @ local_before, atol=1e-6)


def test_scale_deltas_local_uniform_world_and_shear_rejection():
    p = cube()
    scene.update(p, {"rotation": [0, 30, 0], "scale": [2, 3, 4]})
    scene.transform_delta([p], p, "scale", 0.5, axis="Y", space="local")
    np.testing.assert_allclose(scene.transform(p)["scale"], [2, 1.5, 4], atol=1e-9)
    scene.transform_delta([p], p, "scale", 2.0, space="world")
    np.testing.assert_allclose(scene.transform(p)["scale"], [4, 3, 8], atol=1e-9)
    before = deepcopy(p.props)
    with pytest.raises(ValueError, match="shear"):
        scene.transform_delta([p], p, "scale", 2.0, axis="X", space="world")
    assert p.props == before
    q = cube()
    scene.update(q, {"rotation": [0, 90, 0]})
    scene.transform_delta([q], q, "scale", 3.0, axis="X", space="world")
    np.testing.assert_allclose(scene.transform(q)["scale"], [1, 1, 3], atol=1e-9)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"group": "location", "amount": float("nan"), "axis": "X"},
        {"group": "location", "amount": 1.0, "axis": "W"},
        {"group": "location", "amount": 1.0, "axis": "X", "space": "Global"},
        {"group": "rotation", "amount": 1.0, "axis": "X", "plane": True},
        {"group": "rotation", "amount": 1.0, "free_axis": [0, 0, 0]},
        {"group": "scale", "amount": 0.0},
        {"group": "location", "amount": 1.0, "plane": True},
        {"group": "location", "amount": 1.0},
        {"group": "size", "amount": 1.0, "axis": "X"},
        {"group": "location", "amount": True, "axis": "X"},
    ],
)
def test_invalid_delta_inputs_leave_props_unchanged(kwargs):
    p = cube()
    scene.update(p, {"rotation": [10, 20, 30]})
    before = deepcopy(p.props)
    with pytest.raises(ValueError):
        scene.transform_delta([p], p, **kwargs)
    assert p.props == before


def test_describe_world_rejects_shear_and_tool_reports_space():
    parent, child = group("Parent"), cube("Child")
    objects = [parent, child]
    scene.update(parent, {"scale": [1, 3, 1]})
    scene.update(child, {"rotation": [0, 0, 30]})
    scene.set_parent(objects, child, parent, keep_world=False)
    with pytest.raises(ValueError, match="shear"):
        scene.describe(objects, child, "world")
    with pytest.raises(ValueError, match="shear"):
        scene.set_transform(objects, child, {"rotation": [0, 0, 0]}, space="world")
    assert scene.describe(objects, child, "parent")["location"] == [0, 0, 0]
    from elysium.aether.tools.scene import transform_get
    session = SimpleNamespace(designer=SimpleNamespace(placements=objects), lookup=lambda _: child,
                              id_for=lambda p: p.entity_id)
    for space in ("local", "parent"):
        result = transform_get(session, child.entity_id, space=space)
        assert result["space"] == space and result["parent_id"] == parent.entity_id
    with pytest.raises(ValueError, match="shear"):
        transform_get(session, child.entity_id, space="world")


def apply_fixture():
    a, b = cube("A"), cube("B")
    objects = [a, b]
    scene.update(a, {"location": [2, 1, 3], "rotation": [10, 20, 30], "scale": [2, 3, 1], "pivot": [1, 0, 0]})
    scene.set_parent(objects, b, a, keep_world=False)
    source = mesh_document.resolve(a.mesh_kind)
    world = scene.world_matrices(objects)
    return objects, a, b, source, world


def assert_world_geometry_preserved(objects, a, b, source, world):
    mesh = mesh_document.resolve(a.mesh_kind)
    new_world = scene.world_matrices(objects)
    expected = source.verts @ world[0][:3, :3].T + world[0][:3, 3]
    actual = mesh.verts @ new_world[0][:3, :3].T + new_world[0][:3, 3]
    np.testing.assert_allclose(actual, expected, atol=1e-5)
    np.testing.assert_allclose(new_world[1], world[1], atol=1e-6)
    np.testing.assert_array_equal(mesh.vert_uvs, source.vert_uvs)
    return mesh


def test_apply_location_only_keeps_world_geometry_and_rotation():
    objects, a, b, source, world = apply_fixture()
    scene.apply_transform(objects, a, rotation=False, scale=False)
    values = scene.transform(a)
    assert values["location"] == [0, 0, 0] and values["rotation"] == [10, 20, 30]
    assert values["scale"] == [2, 3, 1] and values["pivot"] == [1, 0, 0]
    mesh = assert_world_geometry_preserved(objects, a, b, source, world)
    np.testing.assert_allclose(mesh.verts.mean(axis=0) - source.verts.mean(axis=0), np.linalg.inv(scene.matrix(a)[:3, :3]) @ [2, 1, 3], atol=1e-5)


def test_apply_rotation_only():
    objects, a, b, source, world = apply_fixture()
    scene.apply_transform(objects, a, location=False, scale=False)
    values = scene.transform(a)
    assert values["rotation"] == [0, 0, 0] and values["location"] == [2, 1, 3] and values["scale"] == [2, 3, 1]
    assert_world_geometry_preserved(objects, a, b, source, world)


def test_apply_scale_only_negative_flips_winding():
    objects, a, b, source, world = apply_fixture()
    scene.update(a, {"scale": [-2, 3, 1]})
    world = scene.world_matrices(objects)
    scene.apply_transform(objects, a, location=False, rotation=False)
    values = scene.transform(a)
    assert values["scale"] == [1, 1, 1] and values["rotation"] == [10, 20, 30] and values["location"] == [2, 1, 3]
    mesh = assert_world_geometry_preserved(objects, a, b, source, world)
    tri = mesh.verts[mesh.faces].astype(np.float64)
    assert np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() > 0
    # Baked normals stay outward after the winding flip.
    centroids = tri.mean(axis=1) - mesh.verts.mean(axis=0)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    assert (np.einsum("ij,ij->i", normals, centroids) > 0).all()


def test_apply_all_matches_previous_behaviour_with_pivot_reset():
    objects, a, b, source, world = apply_fixture()
    scene.apply_transform(objects, a)
    assert scene.transform(a) == scene.DEFAULT
    mesh = assert_world_geometry_preserved(objects, a, b, source, world)
    np.testing.assert_allclose(mesh.verts, source.verts @ world[0][:3, :3].T + world[0][:3, 3], atol=1e-6)


def test_apply_nothing_and_scene_group_reject():
    objects, a, b, source, world = apply_fixture()
    before = deepcopy(a.props)
    with pytest.raises(ValueError, match="at least one channel"):
        scene.apply_transform(objects, a, location=False, rotation=False, scale=False)
    assert a.props == before
    g = group()
    with pytest.raises(ValueError, match="mesh geometry"):
        scene.apply_transform([g], g, rotation=False)


def test_apply_subset_keeps_modifier_stack_evaluating():
    objects, a, b, source, world = apply_fixture()
    mesh_modifiers.add(a, "Array", {"count": 2, "offset": [3, 0, 0]})
    scene.apply_transform(objects, a, location=False)
    from elysium.render import mesh_edit
    assert len(mesh_edit.evaluate(a).topology["vertices"]) == 16
    assert scene.transform(a)["location"] == [2, 1, 3]


def test_tool_delta_reports_world_matrix_and_failure_rolls_back(native_session):
    d, session, call = native_session
    cube_id = call("mesh.primitive_create", kind="Cube")["placement_id"]
    call("scene.transform_set", id=cube_id, transform={"rotation": [0, 30, 0]})
    result = call("scene.transform_delta", id=cube_id, group="location", amount=2.0, axis="Z", space="local")
    assert result["space"] == "local"
    np.testing.assert_allclose(np.asarray(result["world_matrix"])[:3, 3], [np.sin(np.radians(30)) * 2, 0, np.cos(np.radians(30)) * 2], atol=1e-9)
    np.testing.assert_allclose(result["world_matrix"], scene.world_matrices(d.placements)[0])
    world_get = call("scene.transform_get", id=cube_id, space="world")
    np.testing.assert_allclose(world_get["transform"]["rotation"], [0, 30, 0], atol=1e-9)
    call("scene.transform_set", id=cube_id, transform={"location": [0, 0, 0]}, space="world")
    np.testing.assert_allclose(scene.world_matrices(d.placements)[0][:3, 3], 0, atol=1e-9)
    layout = d.skin_path / "designer_layout.json"
    saved = layout.read_bytes()
    before = d._snapshot()
    failed = call.expect_failure("scene.transform_delta", id=cube_id, group="scale", amount=2.0, axis="X", space="world")
    assert "shear" in failed.error
    assert layout.read_bytes() == saved and d._snapshot() == before
    applied = call("scene.transform_apply", id=cube_id, rotation=False)
    assert applied["transform"]["rotation"] == [0, 30, 0]


def sheared_rig():
    """A non-uniformly scaled grandparent under a rotated parent: every world
    matrix from the parent down has a sheared linear part."""
    g, parent, child = group("G"), group("P"), cube("C")
    objects = [g, parent, child]
    scene.update(g, {"scale": [1, 3, 1]})
    scene.update(parent, {"rotation": [0, 0, 30], "location": [1, 0, 0]})
    scene.update(child, {"location": [0, 1, 0], "rotation": [0, 45, 0]})
    scene.set_parent(objects, parent, g, keep_world=False)
    scene.set_parent(objects, child, parent, keep_world=False)
    with pytest.raises(ValueError, match="shear"):
        scene.decompose_linear(world_of(objects, child)[:3, :3])
    return objects, parent, child


@pytest.mark.parametrize("space", ["world", "parent", "local"])
def test_location_delta_works_on_a_sheared_chain_in_every_space(space):
    objects, parent, child = sheared_rig()
    before = world_of(objects, child)[:3, 3].copy()
    frames = {
        "world": np.eye(3),
        "parent": world_of(objects, parent)[:3, :3],
        "local": world_of(objects, child)[:3, :3],
    }
    # A move needs a direction, not a decomposition: +X of the chosen space,
    # two world units along it.
    scene.transform_delta(objects, child, "location", 2.0, axis="X", space=space)
    step = frames[space][:, 0]
    expected = before + 2.0 * step / np.linalg.norm(step)
    np.testing.assert_allclose(world_of(objects, child)[:3, 3], expected, atol=1e-9)
    # Nothing but the location channel moved.
    assert scene.transform(child)["rotation"] == [0, 45, 0]
    assert scene.transform(child)["scale"] == [1, 1, 1]


def test_free_and_plane_location_deltas_survive_a_sheared_chain():
    objects, parent, child = sheared_rig()
    before = world_of(objects, child)[:3, 3].copy()
    scene.transform_delta(objects, child, "location", 1.0, free_axis=[0, 0, 5], space="local")
    moved = world_of(objects, child)[:3, 3]
    np.testing.assert_allclose(np.linalg.norm(moved - before), 1.0, atol=1e-9)
    scene.transform_delta(objects, child, "location", 1.0, axis="Y", plane=True,
                          free_axis=[1, 2, 0], space="parent")
    np.testing.assert_allclose(
        np.linalg.norm(world_of(objects, child)[:3, 3] - moved), 1.0, atol=1e-9)


@pytest.mark.parametrize("group_name,kwargs",
                         [("rotation", {"axis": "X"}), ("scale", {"axis": "X"})])
@pytest.mark.parametrize("space", ["world", "parent", "local"])
def test_rotation_and_scale_deltas_still_refuse_a_sheared_chain(space, group_name, kwargs):
    objects, parent, child = sheared_rig()
    before = deepcopy(child.props)
    with pytest.raises(ValueError, match="shear") as raised:
        scene.transform_delta(objects, child, group_name, 2.0, space=space, **kwargs)
    # No space works here, so the message must not send the user to one.
    assert "space" not in str(raised.value)
    assert child.props == before


def test_shear_message_names_a_space_that_actually_works():
    p = cube()
    scene.update(p, {"rotation": [0, 30, 0], "scale": [2, 3, 4]})
    with pytest.raises(ValueError, match="use local space") as raised:
        scene.transform_delta([p], p, "scale", 2.0, axis="X", space="world")
    # The named space is not advice taken on faith: it commits.
    named = str(raised.value).split("use ")[1].split(" space")[0]
    scene.transform_delta([p], p, "scale", 2.0, axis="X", space=named)
    np.testing.assert_allclose(scene.transform(p)["scale"], [4, 3, 4], atol=1e-9)


def test_transform_delta_tool_description_matches_the_sheared_chain_behaviour():
    # The tool description is the only place this contract is visible to the
    # agent that calls it (and it is generated verbatim into the published
    # catalog), so it must not tell the agent a move is rejected here.
    from elysium.aether.tools import REGISTRY
    description = REGISTRY.get("scene.transform_delta").description
    objects, parent, child = sheared_rig()
    assert "A location delta only needs a direction" in description
    before = world_of(objects, child)[:3, 3].copy()
    scene.transform_delta(objects, child, "location", 2.0, axis="X", space="world")
    np.testing.assert_allclose(world_of(objects, child)[:3, 3], before + [2, 0, 0], atol=1e-9)
    # ...and the rejection it does describe is scoped to rotation and scale.
    assert "rotation and scale results that would shear" in description
    assert "; results that would shear" not in description
    for group_name in ("rotation", "scale"):
        with pytest.raises(ValueError, match="shear"):
            scene.transform_delta(objects, child, group_name, 2.0, axis="X", space="world")


def test_scene_transforms_doc_still_describes_the_delta_the_code_performs():
    # docs/architecture/scene-transforms.md is the contract the separate
    # Designer repo's gizmo is written against; 517312b changed the location
    # delta underneath it. Pin each documented claim to observed behaviour.
    from pathlib import Path
    doc = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "scene-transforms.md"
    if not doc.is_file():
        pytest.skip("architecture docs are not part of the installed package")
    text = doc.read_text(encoding="utf-8")
    objects, parent, child = sheared_rig()
    # 1. A location delta commits here, so the doc must not say the deltas
    #    all reject, and must name the frame the move actually uses.
    before = world_of(objects, child)[:3, 3].copy()
    scene.transform_delta(objects, child, "location", 2.0, axis="X", space="parent")
    assert "the deltas below all reject" not in text
    assert "_axis_directions" in text
    # 2. `amount` is still a world distance because `F v` is normalised.
    moved = world_of(objects, child)[:3, 3]
    np.testing.assert_allclose(np.linalg.norm(moved - before), 2.0, atol=1e-9)
    assert "(F v / ‖F v‖)" in text
    assert "`loc' = loc + Pl⁻¹ F v · amount`" not in text
    # 3. transform_delta composes its own remedy, so the doc cannot quote one
    #    fixed shear string: the variant this rig raises must be covered.
    with pytest.raises(ValueError, match="shear") as raised:
        scene.transform_delta(objects, child, "rotation", 10.0, axis="X", space="world")
    assert str(raised.value).split("; ", 1)[1] in text
