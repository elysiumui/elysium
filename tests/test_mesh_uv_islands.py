from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_uv, mesh_uv_islands, primitives, topology


def placement(kind="Cube", params=None):
    p = SimpleNamespace(kind="Mesh3D", name=kind, mesh_kind="", entity_id="uv-islands", props={})
    mesh_document.bind(p, primitives.build(kind, params or {})[0])
    return p


def cube_islands():
    p = placement()
    doc = mesh_uv.source(p)
    for i, f in enumerate(doc["faces"]):
        for c, uv in zip(f["corners"], ((0, 0), (1, 0), (1, 1), (0, 1))):
            c["uv"] = [uv[0] * (i + 1) + i * 10, uv[1] * (i + 1)]
    mesh_document.bind(p, topology.compile(doc)[0])
    return p


def without_uv(doc):
    doc = deepcopy(doc)
    for f in doc["faces"]:
        for c in f["corners"]:
            c["uv"] = None
    return doc


def test_islands_follow_corner_uv_continuity_not_seam_flags_alone():
    p = placement("Plane", {"segments": 2})
    mesh_uv.project(p, "planar_xz")
    assert len(mesh_uv_islands.read(p)) == 1
    doc = mesh_uv.source(p)
    mesh_uv.seams(p, [e["id"] for e in doc["edges"]])
    assert len(mesh_uv_islands.read(p)) == 1
    mesh_uv.transform(p, [c["id"] for c in doc["faces"][0]["corners"]], offset=[2, 0])
    assert len(mesh_uv_islands.read(p)) == 2


def test_unprojected_faces_are_excluded_and_stale_selection_rejects():
    p = placement()
    doc = mesh_uv.source(p)
    assert mesh_uv_islands.read(p) == []
    mesh_uv.project(p, "planar_xz", face_ids=[doc["faces"][0]["id"]])
    assert len(mesh_uv_islands.read(p)) == 1
    with pytest.raises(ValueError):
        mesh_uv_islands.pack(p, [doc["faces"][1]["corners"][0]["id"]])


def test_pack_preserves_shape_relative_scale_topology_and_margin():
    p = cube_islands()
    before = mesh_uv.source(p)
    old = mesh_uv_islands.read(p)
    result = mesh_uv_islands.pack(p, margin=0.025)
    after = mesh_uv.source(p)
    new = mesh_uv_islands.read(p)
    assert without_uv(before) == without_uv(after)
    assert result["islands"] == 6
    for a, b in zip(old, new):
        np.testing.assert_allclose(
            np.array(b["max"]) - b["min"], (np.array(a["max"]) - a["min"]) * result["scale"]
        )
        assert min(b["min"]) >= 0.025 - 1e-9 and max(b["max"]) <= 0.975 + 1e-9
    for i, a in enumerate(new):
        for b in new[i + 1 :]:
            assert any(
                a["max"][axis] + 0.05 <= b["min"][axis] + 1e-9
                or b["max"][axis] + 0.05 <= a["min"][axis] + 1e-9
                for axis in range(2)
            )
    mesh_document.validate(mesh_document.resolve(p.mesh_kind))
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_uv.source(p) == after


def test_pack_one_island_fills_unit_tile_with_margin():
    p = placement("Plane")
    mesh_uv.project(p, "planar_xz")
    mesh_uv.transform(p, offset=[10, -4], scale=[3, 3])
    mesh_uv_islands.pack(p, margin=0.05)
    island = mesh_uv_islands.read(p)[0]
    np.testing.assert_allclose(island["min"], [0.05, 0.05])
    np.testing.assert_allclose(island["max"], [0.95, 0.95])


def test_corner_seed_expands_whole_island_and_preserves_unselected_islands():
    p = cube_islands()
    before = mesh_uv.source(p)
    corner = before["faces"][0]["corners"][0]["id"]
    mesh_uv_islands.pack(p, [corner])
    after = mesh_uv.source(p)
    assert before["faces"][1:] == after["faces"][1:]
    assert before["faces"][0] != after["faces"][0]


def test_normalize_equal_density_preserves_centers_shape_total_area_and_attributes():
    p = cube_islands()
    before = mesh_uv.source(p)
    old = mesh_uv_islands.read(p)
    result = mesh_uv_islands.normalize(p)
    after = mesh_uv.source(p)
    new = mesh_uv_islands.read(p)
    assert without_uv(before) == without_uv(after)
    old_area = sum(float(np.prod(np.array(a["max"]) - a["min"])) for a in old)
    new_area = sum(float(np.prod(np.array(a["max"]) - a["min"])) for a in new)
    assert new_area == pytest.approx(old_area)
    dimensions = [np.array(a["max"]) - a["min"] for a in new]
    for d in dimensions:
        np.testing.assert_allclose(d, dimensions[0])
    for a, b in zip(old, new):
        np.testing.assert_allclose(np.array(a["min"]) + a["max"], np.array(b["min"]) + b["max"])
    assert result["uv_area_per_surface_area"] == pytest.approx(old_area / 24)


@pytest.mark.parametrize(
    "operation",
    [
        lambda p: mesh_uv_islands.pack(p, margin=-0.01),
        lambda p: mesh_uv_islands.pack(p, margin=0.5),
        lambda p: mesh_uv_islands.pack(p, margin=float("inf")),
        lambda p: mesh_uv_islands.pack(p, ["stale"]),
        lambda p: mesh_uv_islands.normalize(p, []),
    ],
)
def test_invalid_island_edits_are_atomic(operation):
    p = cube_islands()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        operation(p)
    assert before == p.__dict__


def test_degenerate_projection_rejects_packing_and_normalizing_without_mutation():
    p = placement("Plane")
    mesh_uv.project(p, "planar_xy")
    before = deepcopy(p.__dict__)
    for operation in (mesh_uv_islands.pack, mesh_uv_islands.normalize):
        with pytest.raises(ValueError):
            operation(p)
        assert before == p.__dict__
