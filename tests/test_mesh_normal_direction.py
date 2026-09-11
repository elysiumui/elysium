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
    topology,
)


def fixture():
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Sphere", entity_id="sphere")
    primitives.bind(p, "Sphere", {"rings": 4, "segments": 8})
    mesh_normals.set_policy(p, "smooth")
    return p


def doc(p):
    return topology.document(mesh_document.resolve(p.mesh_kind))


def corner_map(d):
    m, ids, fids = topology.compile(d)
    return {(fid, ids[i]): m.vert_normals[i] for tri, fid in zip(m.faces, fids) for i in tri}


def test_selected_direction_preserves_other_corners_geometry_and_stack():
    p = fixture()
    before = doc(p)
    prior = corner_map(before)
    face = before["faces"][0]["id"]
    mesh_modifiers.add(p, "Array")
    stack = deepcopy(p.props["modifiers3d"])
    result = mesh_normals.set_direction(p, [face], [2, 3, 4])
    after = doc(p)
    actual = corner_map(after)
    assert result["policy"]["mode"] == "authored"
    assert after["vertices"] == before["vertices"]
    assert p.props["modifiers3d"] == stack
    for f, old in zip(after["faces"], before["faces"]):
        assert f["id"] == old["id"] and f["material"] == old["material"]
        for c, oc in zip(f["corners"], old["corners"]):
            assert {k: v for k, v in c.items() if k != "normal"} == {
                k: v for k, v in oc.items() if k != "normal"
            }
            expected = (
                np.array([2, 3, 4]) / np.linalg.norm([2, 3, 4])
                if f["id"] == face
                else prior[f["id"], c["vertex"]]
            )
            np.testing.assert_allclose(actual[f["id"], c["vertex"]], expected, atol=1e-7)
    assert mesh_edit.evaluate(p).topology is not None
    assert any(e["sharp"] for e in after["edges"])
    payload = mesh_document.capture([p])
    saved = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    mesh_document.restore(payload, [p])
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == saved


@pytest.mark.parametrize(
    "normal", [[0, 0, 0], [float("nan"), 1, 0], [True, 0, 0], [1, 2], [1, "2", 3], None]
)
def test_invalid_vector_is_atomic(normal):
    p = fixture()
    before = doc(p)
    with pytest.raises(ValueError):
        mesh_normals.set_direction(p, [before["faces"][0]["id"]], normal)
    assert doc(p) == before


@pytest.mark.parametrize("ids", [[], ["missing"], ["f1", "f1"], "f1", [42]])
def test_invalid_selection_is_atomic(ids):
    p = fixture()
    before = doc(p)
    with pytest.raises(ValueError):
        mesh_normals.set_direction(p, ids, [0, 1, 0])
    assert doc(p) == before


@pytest.mark.parametrize("scale", [1e308, 1e-308])
def test_finite_extreme_vectors_normalize_without_overflow(scale):
    p = fixture()
    faces = [f["id"] for f in doc(p)["faces"]]
    mesh_normals.set_direction(p, faces, [scale, scale, 0])
    for value in corner_map(doc(p)).values():
        np.testing.assert_allclose(value, [2**-0.5, 2**-0.5, 0], atol=1e-7)
