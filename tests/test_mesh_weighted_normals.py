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


def box():
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Box", entity_id="weighted")
    primitives.bind(p, "Cube")
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    for v in doc["vertices"]:
        v["position"] = (np.asarray(v["position"]) * [1, 2, 3]).tolist()
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_normals.set_policy(p, "smooth")
    return p


@pytest.mark.parametrize(
    "mode,direction",
    [("face_area", [6, 3, 2]), ("corner_angle", [1, 1, 1]), ("face_angle", [6, 3, 2])],
)
def test_weighted_box_matches_analytic_normals_without_source_mutation(mode, direction):
    p = box()
    before = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    mesh_modifiers.add(p, "WeightedNormals", {"mode": mode})
    result = mesh_edit.evaluate(p)
    expected = np.sign(result.verts) * np.asarray(direction) / np.linalg.norm(direction)
    np.testing.assert_allclose(result.vert_normals, expected, atol=1e-7)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == before
    assert result.topology["vertices"] == before["topology"]["vertices"]
    assert result.topology["edges"] == before["topology"]["edges"]
    for f, old in zip(result.topology["faces"], before["topology"]["faces"]):
        for c, prior in zip(f["corners"], old["corners"]):
            assert {k: v for k, v in c.items() if k != "normal"} == {
                k: v for k, v in prior.items() if k != "normal"
            }


def test_weight_bias_threshold_bands_and_extremes():
    p = box()
    mesh_modifiers.add(p, "WeightedNormals", {"weight": 75, "threshold": 0})
    m = mesh_edit.evaluate(p)
    direction = np.array([24, 12 / 12.5, 8 / 12.5**2])
    np.testing.assert_allclose(
        m.vert_normals, np.sign(m.verts) * direction / np.linalg.norm(direction), atol=1e-7
    )
    mesh_modifiers.update(p, "mod1", values={"weight": 75, "threshold": 10})
    m = mesh_edit.evaluate(p)
    direction = np.array([24, 12 / 12.5, 8 / 12.5])
    np.testing.assert_allclose(
        m.vert_normals, np.sign(m.verts) * direction / np.linalg.norm(direction), atol=1e-7
    )
    for weight in (1, 100):
        mesh_modifiers.update(p, "mod1", values={"weight": weight, "threshold": 0})
        m = mesh_edit.evaluate(p)
        assert np.isfinite(m.vert_normals).all()
        np.testing.assert_allclose(np.linalg.norm(m.vert_normals, axis=1), 1, atol=1e-7)


def test_sharp_fans_and_angle_policy_are_preserved_when_requested():
    p = box()
    mesh_normals.set_policy(p, "smooth", angle=80)
    mesh_modifiers.add(p, "WeightedNormals", {"keep_sharp": True})
    assert (np.count_nonzero(np.abs(mesh_edit.evaluate(p).vert_normals) > 1e-6, axis=1) == 1).all()
    mesh_normals.set_policy(p, "smooth")
    edges = [e["id"] for e in mesh_document.resolve(p.mesh_kind).topology["edges"]]
    mesh_normals.set_sharp(p, edges)
    assert (np.count_nonzero(np.abs(mesh_edit.evaluate(p).vert_normals) > 1e-6, axis=1) == 1).all()
    mesh_modifiers.update(p, "mod1", values={"keep_sharp": False})
    assert (np.count_nonzero(np.abs(mesh_edit.evaluate(p).vert_normals) > 1e-6, axis=1) == 3).all()


def test_flat_policy_stays_flat_and_apply_bakes_exact_custom_normals():
    p = box()
    mesh_normals.set_policy(p, "flat")
    before = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    mesh_modifiers.add(p, "WeightedNormals")
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == before
    mesh_normals.set_policy(p, "smooth")
    expected = mesh_document.to_json(mesh_edit.evaluate(p))
    mesh_modifiers.apply_all(p)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == expected
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == expected


@pytest.mark.parametrize(
    "values",
    [
        {"mode": "bad"},
        {"weight": 0},
        {"weight": 101},
        {"weight": True},
        {"threshold": float("nan")},
        {"threshold": -1},
        {"threshold": 11},
        {"keep_sharp": 1},
    ],
)
def test_invalid_weighted_settings_are_atomic(values):
    p = box()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_modifiers.add(p, "WeightedNormals", values)
    assert p.__dict__ == before
