from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_uv, mesh_uv_unwrap, primitives, topology


def placement(kind="Plane", params=None):
    p = SimpleNamespace(kind="Mesh3D", name=kind, mesh_kind="", entity_id="uv-unwrap", props={})
    mesh_document.bind(p, primitives.build(kind, params or {})[0])
    return p


def pin_positions(p, positions):
    doc = mesh_uv.source(p)
    ids = {v["id"] for v in doc["vertices"] if v["position"] in positions}
    corners = [c["id"] for f in doc["faces"] for c in f["corners"] if c["vertex"] in ids]
    mesh_uv.pin(p, corners)
    return corners


def test_pinned_conformal_plane_restores_distorted_uvs_and_preserves_every_attribute():
    p = placement(params={"segments": 2})
    mesh_uv.project(p, "planar_xz")
    pin_positions(p, [[-1, 0, -1], [1, 0, 1]])
    original = mesh_uv.source(p)
    unpinned = [c["id"] for f in original["faces"] for c in f["corners"] if not c.get("pin")]
    mesh_uv.transform(p, unpinned, offset=[0.2, 0.1], scale=[1.4, 0.8])
    result = mesh_uv_unwrap.unwrap(p)
    assert result["charts"] == 1 and result["pinned_corners"] == 2
    final = mesh_uv.source(p)
    for a, b in zip(original["faces"], final["faces"]):
        for c, d in zip(a["corners"], b["corners"]):
            np.testing.assert_allclose(c["uv"], d["uv"], atol=1e-8)
            if c.get("pin"):
                assert c == d
            d["uv"] = c["uv"]
    assert final == original
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    mesh_document.validate(mesh_document.resolve(p.mesh_kind))


def test_unpinned_folded_plane_unwrap_preserves_triangle_shape_with_uniform_scale():
    p = placement(params={"segments": 2})
    doc = mesh_uv.source(p)
    for v in doc["vertices"]:
        if v["position"][0] > 0:
            v["position"][1] = v["position"][0]
            v["position"][0] = 0
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_uv_unwrap.unwrap(p)
    result = mesh_uv.source(p)
    positions = {v["id"]: np.array(v["position"]) for v in result["vertices"]}
    ratios = []
    for f in result["faces"]:
        cs = f["corners"]
        xyz = np.array([positions[c["vertex"]] for c in cs])
        uv = np.array([c["uv"] for c in cs])
        for tri in topology.triangles(xyz):
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                ratios.append(np.linalg.norm(uv[a] - uv[b]) / np.linalg.norm(xyz[a] - xyz[b]))
    np.testing.assert_allclose(ratios, ratios[0], atol=1e-7)


def test_pins_allow_exact_zero_solution_for_remaining_uv_corner():
    p = placement()
    mesh_uv.project(p, "planar_xz")
    corners = [c for f in mesh_uv.read(p)["faces"] for c in f["corners"]]
    mesh_uv.pin(p, [c["id"] for c in corners if c["uv"] != [0.0, 0.0]])
    origin = next(c["id"] for c in corners if c["uv"] == [0.0, 0.0])
    expected = mesh_uv.source(p)
    mesh_uv.transform(p, [origin], offset=[0.2, 0.1])
    result = mesh_uv_unwrap.unwrap(p)
    assert result["pinned_corners"] == 3
    assert mesh_uv.source(p) == expected


def test_closed_cube_requires_seams_then_unwraps_six_face_charts():
    p = placement("Cube")
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="Mark seams"):
        mesh_uv_unwrap.unwrap(p)
    assert before == p.__dict__
    doc = mesh_uv.source(p)
    mesh_uv.seams(p, [e["id"] for e in doc["edges"]])
    result = mesh_uv_unwrap.unwrap(p)
    assert result["charts"] == 6
    assert [len(mesh_uv.source(p)[k]) for k in ("vertices", "edges", "faces")] == [8, 12, 6]
    assert all(c["uv"] is not None for f in mesh_uv.source(p)["faces"] for c in f["corners"])


def test_open_cylinder_needs_longitudinal_seam_to_make_one_disk_chart():
    p = placement("Cylinder", {"segments": 8})
    doc = mesh_uv.source(p)
    caps = [f["id"] for f in doc["faces"] if len(f["corners"]) == 8]
    topology.select(p, "faces", caps)
    topology.edit_selected(p, "delete")
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="Mark seams"):
        mesh_uv_unwrap.unwrap(p)
    assert p.__dict__ == before
    doc = mesh_uv.source(p)
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    edge = next(
        e["id"] for e in doc["edges"] if points[e["vertices"][0]][1] != points[e["vertices"][1]][1]
    )
    mesh_uv.seams(p, [edge])
    result = mesh_uv_unwrap.unwrap(p)
    assert result["charts"] == 1
    mesh_document.validate(mesh_document.resolve(p.mesh_kind))


def test_conflicting_pins_on_uncut_shared_vertex_reject_atomically():
    p = placement(params={"segments": 2})
    mesh_uv.project(p, "planar_xz")
    ids = pin_positions(p, [[0, 0, 0]])
    mesh_uv.transform(p, [ids[0]], offset=[0.25, 0])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="Conflicting pins"):
        mesh_uv_unwrap.unwrap(p)
    assert p.__dict__ == before


def test_reversed_fully_pinned_uvs_reject_without_changing_source():
    p = placement()
    mesh_uv.project(p, "planar_xz")
    mesh_uv.transform(p, scale=[-1, 1])
    ids = [c["id"] for f in mesh_uv.read(p)["faces"] for c in f["corners"]]
    mesh_uv.pin(p, ids)
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="folded or collapsed"):
        mesh_uv_unwrap.unwrap(p)
    assert p.__dict__ == before


def test_selected_face_unwrap_leaves_other_faces_and_corners_unchanged():
    p = placement("Cube")
    before = mesh_uv.source(p)
    result = mesh_uv_unwrap.unwrap(p, [before["faces"][0]["id"]])
    after = mesh_uv.source(p)
    assert result["charts"] == 1 and after["faces"][1:] == before["faces"][1:]
    assert after["vertices"] == before["vertices"] and after["edges"] == before["edges"]
