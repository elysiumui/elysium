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


def fixture(kind="Cube", settings=None):
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Split", entity_id="split")
    mesh_document.bind(p, primitives.build(kind, settings or {})[0])
    mesh_normals.set_policy(p, "smooth")
    return p


def counts(mesh):
    return [len(mesh.topology[k]) for k in ("vertices", "edges", "faces")]


def test_cube_default_splits_six_sheets_and_retains_source_attributes():
    p = fixture()
    source = deepcopy(mesh_document.to_json(mesh_document.resolve(p.mesh_kind)))
    mesh_modifiers.add(p, "EdgeSplit")
    result = mesh_edit.evaluate(p)
    assert counts(result) == [24, 24, 6]
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == source
    assert len({tuple(v["position"]) for v in result.topology["vertices"]}) == 8
    assert all(len(v) == 1 for v in topology.edge_usage(result.topology).values())
    assert (np.count_nonzero(np.abs(result.vert_normals) > 1e-6, axis=1) == 1).all()
    for f, old in zip(result.topology["faces"], source["topology"]["faces"]):
        assert f["id"] == old["id"]
        for c, prior in zip(f["corners"], old["corners"]):
            assert {k: v for k, v in c.items() if k != "vertex"} == {
                k: v for k, v in prior.items() if k != "vertex"
            }
    expected = mesh_document.to_json(result)
    mesh_modifiers.apply_all(p)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == expected
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == expected


@pytest.mark.parametrize("angle,expected", [(89, [24, 24, 6]), (90, [8, 12, 6]), (180, [8, 12, 6])])
def test_cube_split_angle_boundary(angle, expected):
    p = fixture()
    mesh_modifiers.add(p, "EdgeSplit", {"angle": angle})
    assert counts(mesh_edit.evaluate(p)) == expected


def test_single_sharp_edge_keeps_closed_vertex_fans_connected():
    p = fixture()
    src = mesh_document.resolve(p.mesh_kind)
    mesh_normals.set_sharp(p, [src.topology["edges"][0]["id"]])
    mesh_modifiers.add(p, "EdgeSplit", {"use_angle": False})
    assert counts(mesh_edit.evaluate(p)) == [8, 12, 6]
    mesh_normals.set_sharp(p, [e["id"] for e in src.topology["edges"]])
    assert counts(mesh_edit.evaluate(p)) == [24, 24, 6]
    assert all(e["sharp"] for e in mesh_edit.evaluate(p).topology["edges"])
    mesh_modifiers.update(p, "mod1", values={"use_sharp": False})
    assert counts(mesh_edit.evaluate(p)) == [8, 12, 6]


@pytest.mark.parametrize("angle", [0, 0.000001])
def test_zero_angle_splits_coplanar_faces(angle):
    p = fixture("Plane", {"segments": 2})
    mesh_modifiers.add(p, "EdgeSplit", {"angle": angle})
    assert counts(mesh_edit.evaluate(p)) == [16, 16, 4]


def test_seam_flags_and_loose_edges_survive_vertex_duplication():
    p = fixture()
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    for e in doc["edges"]:
        e["seam"] = True
    v = deepcopy(doc["vertices"][0])
    v["id"] = topology._id(doc, "v")
    v["position"] = [3, 3, 3]
    doc["vertices"].append(v)
    wire = {
        "id": topology._id(doc, "e"),
        "vertices": [doc["vertices"][0]["id"], v["id"]],
        "sharp": False,
        "seam": False,
    }
    doc["edges"].append(wire)
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_modifiers.add(p, "EdgeSplit")
    result = mesh_edit.evaluate(p).topology
    assert len(result["vertices"]) == 25 and len(result["edges"]) == 25
    assert next(e for e in result["edges"] if e["id"] == wire["id"]) == wire
    assert sum(e["seam"] for e in result["edges"]) == 24


@pytest.mark.parametrize(
    "values",
    [
        {"angle": -1},
        {"angle": 181},
        {"angle": float("nan")},
        {"angle": True},
        {"use_angle": 1},
        {"use_sharp": "yes"},
    ],
)
def test_invalid_settings_do_not_mutate(values):
    p = fixture()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_modifiers.add(p, "EdgeSplit", values)
    assert p.__dict__ == before
