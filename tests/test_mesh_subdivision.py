from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_edit, mesh_modifiers, primitives, topology


def placement(kind="Cube", parameters=None):
    p = SimpleNamespace(kind="Mesh3D", name=kind, entity_id="subdivision", props={}, mesh_kind="")
    mesh_document.bind(p, primitives.build(kind, parameters or {})[0])
    return p


@pytest.mark.parametrize("levels,counts", [(1, [26, 48, 24]), (2, [98, 192, 96])])
def test_catmull_clark_closed_cube_counts_winding_and_source_preservation(levels, counts):
    p = placement()
    source = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    mesh_modifiers.add(p, "Subdivision", {"levels": levels})
    evaluated = mesh_edit.evaluate(p)
    assert [len(evaluated.topology[k]) for k in ("vertices", "edges", "faces")] == counts
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == source
    assert all(
        len(u) == 2 and u[0] == u[1][::-1] for u in topology.edge_usage(evaluated.topology).values()
    )
    if levels == 1:
        np.testing.assert_allclose(
            [v["position"] for v in evaluated.topology["vertices"][:8]],
            np.array([v["position"] for v in source["topology"]["vertices"]]) * 5 / 9,
        )


@pytest.mark.parametrize(
    "method,boundary,corner",
    [
        ("catmull-clark", "all", 0.75),
        ("catmull-clark", "keep_corners", 1),
        ("simple", "all", 1),
    ],
)
def test_plane_boundary_rules_and_linear_face_varying_uvs(method, boundary, corner):
    p = placement("Plane")
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    for face in doc["faces"]:
        for c in face["corners"]:
            point = points[c["vertex"]]
            c["uv"] = [(point[0] + 1) / 2, (point[2] + 1) / 2]
    mesh_document.bind(p, topology.compile(doc)[0])
    source = mesh_document.resolve(p.mesh_kind)
    mesh_modifiers.add(p, "Subdivision", {"method": method, "boundary": boundary})
    result = mesh_edit.evaluate(p)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [9, 12, 4]
    np.testing.assert_allclose(
        [v["position"] for v in result.topology["vertices"][:4]],
        np.array([v["position"] for v in source.topology["vertices"]]) * corner,
    )
    assert sum(len(u) == 1 for u in topology.edge_usage(result.topology).values()) == 8
    uv = [c["uv"] for f in result.topology["faces"] for c in f["corners"]]
    assert [0.5, 0.5] in uv and [0.0, 0.0] in uv and [1.0, 1.0] in uv


def test_subdivision_retains_materials_named_parts_and_split_edge_flags():
    p = placement()
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    doc["edges"][0].update(seam=True, sharp=True)
    for face in doc["faces"]:
        face["material"] = 3
    doc["part_names"] = ["Hull"]
    doc["part_pivots"] = [[0, 0, 0]]
    for v in doc["vertices"]:
        v["part"] = 0
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_modifiers.add(p, "Subdivision")
    result = mesh_edit.evaluate(p).topology
    assert result["part_names"] == ["Hull"] and result["part_pivots"] == [[0, 0, 0]]
    assert {v["part"] for v in result["vertices"]} == {0}
    assert {f["material"] for f in result["faces"]} == {3}
    assert sum(e["seam"] and e["sharp"] for e in result["edges"]) == 2
    assert {c["id"] for f in doc["faces"] for c in f["corners"]} <= {
        c["id"] for f in result["faces"] for c in f["corners"]
    }


def test_subdivision_saved_stack_reopens_and_applies_exact_evaluation():
    p = placement()
    mesh_modifiers.add(p, "Subdivision", {"levels": 2})
    mesh_modifiers.add(p, "Array", {"offset": [4, 0, 0]})
    expected = mesh_document.to_json(mesh_edit.evaluate(p))
    saved = mesh_document.capture([p])
    assert len(saved["assets"][p.mesh_kind]["topology"]["vertices"]) == 8
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == expected
    mesh_modifiers.apply_all(p)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == expected


def test_face_varying_uv_islands_and_custom_normals_remain_independent():
    p = placement()
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    for index, face in enumerate(doc["faces"]):
        face["material"] = index
        for corner, uv in zip(face["corners"], ((0, 0), (1, 0), (1, 1), (0, 1))):
            corner["uv"] = [uv[0] + index * 10, uv[1]]
            corner["normal"] = [1, 0, 0]
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_modifiers.add(p, "Subdivision")
    result = mesh_edit.evaluate(p).topology
    shared_uvs = {}
    for face in result["faces"]:
        origin = face["material"] * 10
        for c in face["corners"]:
            assert origin <= c["uv"][0] <= origin + 1 and 0 <= c["uv"][1] <= 1
            assert c["normal"] == [1, 0, 0]
            shared_uvs.setdefault(c["vertex"], set()).add(tuple(c["uv"]))
    assert any(len(values) > 1 for values in shared_uvs.values())


@pytest.mark.parametrize(
    "values",
    [{"levels": 0}, {"levels": 5}, {"levels": True}, {"method": "loop"}, {"boundary": "unknown"}],
)
def test_subdivision_invalid_parameters_do_not_mutate(values):
    p = placement()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_modifiers.add(p, "Subdivision", values)
    assert p.__dict__ == before


def test_subdivision_growth_limit_and_nonmanifold_input_are_atomic():
    p = placement()
    mesh_modifiers.add(p, "Subdivision", {"levels": 4})
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="limit"):
        mesh_modifiers.add(p, "Subdivision", {"levels": 4})
    assert p.__dict__ == before
    p = placement()
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    doc["faces"][0]["corners"].reverse()
    mesh_document.bind(p, topology.compile(doc)[0])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="manifold"):
        mesh_modifiers.add(p, "Subdivision")
    assert p.__dict__ == before
