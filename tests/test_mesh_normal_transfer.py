from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import (
    mesh_document,
    mesh_edit,
    mesh_modifiers,
    mesh_normals,
    primitives,
    scene,
    topology,
)


def pair():
    result = []
    for name in ("Source", "Target"):
        p = SimpleNamespace(kind="Mesh3D", props={}, name=name, entity_id=name)
        primitives.bind(p, "Cube")
        result.append(p)
    return result


def saved(p):
    return mesh_document.to_json(mesh_document.resolve(p.mesh_kind))


def test_flat_source_transfer_preserves_geometry_uv_and_adds_sharp_breaks():
    source, target = pair()
    mesh_normals.set_policy(target, "smooth")
    before = saved(target)
    src_before = saved(source)
    result = mesh_normals.transfer([source, target], target, source)
    assert result["policy"]["mode"] == "authored"
    m = mesh_document.resolve(target.mesh_kind)
    assert (np.count_nonzero(np.abs(m.vert_normals) > 1e-6, axis=1) == 1).all()
    after = saved(target)
    assert after["topology"]["vertices"] == before["topology"]["vertices"]
    for new, old in zip(after["topology"]["edges"], before["topology"]["edges"]):
        assert {k: v for k, v in new.items() if k != "sharp"} == {
            k: v for k, v in old.items() if k != "sharp"
        }
        assert new["sharp"]
    for f, old in zip(after["topology"]["faces"], before["topology"]["faces"]):
        assert f["id"] == old["id"] and f["material"] == old["material"]
        for c, prior in zip(f["corners"], old["corners"]):
            assert {k: v for k, v in c.items() if k != "normal"} == {
                k: v for k, v in prior.items() if k != "normal"
            }
    assert saved(source) == src_before
    capture = mesh_document.capture([source, target])
    mesh_document.restore(capture, [source, target])
    assert saved(target) == after


def test_world_transfer_respects_parent_rotation_and_local_ignores_it():
    source, target = pair()
    mesh_normals.set_policy(source, "flat")
    parent = SimpleNamespace(kind="SceneGroup", props={}, entity_id="Parent", name="Parent")
    placements = [source, target, parent]
    scene.update(parent, {"rotation": [0, 0, 90]})
    scene.set_parent(placements, source, parent, keep_world=False)
    mesh_normals.transfer(placements, target, source, space="local")
    local = mesh_document.resolve(target.mesh_kind)
    normals = {c["id"]: c["normal"] for f in local.topology["faces"] for c in f["corners"]}
    mesh_normals.transfer(placements, target, source, space="world")
    for face in mesh_document.resolve(target.mesh_kind).topology["faces"]:
        for c in face["corners"]:
            n = normals[c["id"]]
            np.testing.assert_allclose(c["normal"], [-n[1], n[0], n[2]], atol=1e-7)


def test_transfer_reads_evaluated_weighted_source_and_retains_target_stack():
    source, target = pair()
    doc = topology.document(mesh_document.resolve(source.mesh_kind))
    for v in doc["vertices"]:
        v["position"] = (np.asarray(v["position"]) * [1, 2, 3]).tolist()
    mesh_document.bind(source, topology.compile(doc)[0])
    mesh_normals.set_policy(source, "smooth")
    mesh_modifiers.add(source, "WeightedNormals")
    mesh_modifiers.add(target, "Array")
    expected = mesh_edit.evaluate(source).topology
    stack = deepcopy(target.props["modifiers3d"])
    mesh_normals.transfer([source, target], target, source)
    actual = mesh_document.resolve(target.mesh_kind).topology
    for sf, tf in zip(expected["faces"], actual["faces"]):
        np.testing.assert_allclose(
            [c["normal"] for c in sf["corners"]], [c["normal"] for c in tf["corners"]], atol=1e-7
        )
    assert target.props["modifiers3d"] == stack


def test_matching_counts_with_different_corner_order_are_rejected_atomically():
    source, target = pair()
    doc = topology.document(mesh_document.resolve(target.mesh_kind))
    for f in doc["faces"]:
        f["corners"] = f["corners"][1:] + f["corners"][:1]
    mesh_document.bind(target, topology.compile(doc)[0])
    before = deepcopy(target.__dict__)
    with pytest.raises(ValueError, match="ordering"):
        mesh_normals.transfer([source, target], target, source)
    assert target.__dict__ == before


def test_changed_source_topology_rejects_without_target_mutation():
    source, target = pair()
    mesh_modifiers.add(source, "EdgeSplit")
    before = deepcopy(target.__dict__)
    with pytest.raises(ValueError, match="ordering"):
        mesh_normals.transfer([source, target], target, source)
    assert target.__dict__ == before


@pytest.mark.parametrize("case", ["self", "space", "missing", "nonmesh"])
def test_invalid_transfer_is_atomic(case):
    source, target = pair()
    placements = [source, target]
    space = "world"
    if case == "self":
        source = target
    if case == "space":
        space = "camera"
    if case == "missing":
        placements = [target]
    if case == "nonmesh":
        source.kind = "Button"
    before = deepcopy(target.__dict__)
    with pytest.raises(ValueError):
        mesh_normals.transfer(placements, target, source, space=space)
    assert target.__dict__ == before


@pytest.mark.parametrize("scale_x", [2, -2])
def test_world_transfer_uses_inverse_transpose_for_nonuniform_reflected_scale(scale_x):
    source, target = pair()
    mesh_normals.set_policy(source, "smooth")
    scene.update(source, {"scale": [scale_x, 1, 1]})
    scene.update(target, {"scale": [1, 2, 1]})
    mesh_normals.transfer([source, target], target, source)
    m = mesh_document.resolve(target.mesh_kind)
    direction = np.array([1 / scale_x, 2, 1])
    direction /= np.linalg.norm(direction)
    np.testing.assert_allclose(m.vert_normals, np.sign(m.verts) * direction, atol=1e-7)


def test_transfer_does_not_clear_existing_sharp_edges_or_seams():
    source, target = pair()
    mesh_normals.set_policy(source, "smooth")
    doc = topology.document(mesh_document.resolve(target.mesh_kind))
    for e in doc["edges"]:
        e["sharp"] = True
        e["seam"] = True
    mesh_document.bind(target, topology.compile(doc)[0])
    mesh_normals.transfer([source, target], target, source)
    assert all(
        e["sharp"] and e["seam"] for e in mesh_document.resolve(target.mesh_kind).topology["edges"]
    )


def test_neutral_taper_preserves_transferred_custom_normals():
    source, target = pair()
    mesh_normals.set_policy(source, "smooth")
    scene.update(source, {"scale": [2, 1, 1]})
    mesh_normals.transfer([source, target], target, source)
    before = saved(target)
    target.props["taper3d"] = {"axis": "z", "start": [1, 1, 7], "end": [1, 1, 3]}
    assert mesh_document.to_json(mesh_edit.evaluate(target)) == before
    mesh_modifiers.add(target, "Array", {"count": 2})
    result = mesh_edit.evaluate(target)
    assert len(result.topology["vertices"]) == 16
    assert all(c["normal"] is not None for f in result.topology["faces"] for c in f["corners"])


def test_neutral_taper_on_zero_span_axis_is_valid_and_keeps_normals():
    p = pair()[0]
    mesh_document.bind(p, primitives.build("Plane", {})[0])
    mesh_normals.set_policy(p, "smooth")
    before = saved(p)
    mesh_edit.taper_set(p, {"axis": "y", "start": [1, 1, 1], "end": [1, 1, 1]})
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == before
