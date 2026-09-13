from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import (
    mesh_document,
    mesh_uv,
    mesh_uv_islands,
    mesh_uv_stitch,
    mesh_uv_unwrap,
    primitives,
)


def fixture():
    p = SimpleNamespace(
        kind="Mesh3D", name="Stitch plane", mesh_kind="", entity_id="uv-stitch", props={}
    )
    mesh_document.bind(p, primitives.build("Plane", {"segments": 2})[0])
    mesh_uv.seams(p, [e["id"] for e in mesh_uv.source(p)["edges"]])
    mesh_uv_unwrap.unwrap(p)
    islands = mesh_uv_islands.read(p)
    return p, islands[0], islands[1]


def test_stitch_rotates_and_translates_whole_island_and_clears_only_joined_seam():
    p, fixed, moving = fixture()
    mesh_uv.transform(p, moving["corner_ids"], angle=37, offset=[0.4, -0.3])
    before = mesh_uv.source(p)
    result = mesh_uv_stitch.stitch(
        p, fixed["corner_ids"] + moving["corner_ids"], static_corner_id=fixed["corner_ids"][0]
    )
    after = mesh_uv.source(p)
    assert result["joined_edges"] == 1
    assert len(mesh_uv_islands.read(p)) == 3
    assert before["vertices"] == after["vertices"]
    moved = set(moving["face_ids"])
    for a, b in zip(before["faces"], after["faces"]):
        if a["id"] not in moved:
            assert a == b
        else:
            uv_a = np.array([c["uv"] for c in a["corners"]])
            uv_b = np.array([c["uv"] for c in b["corners"]])
            np.testing.assert_allclose(
                np.linalg.norm(uv_a[:, None] - uv_a[None, :], axis=2),
                np.linalg.norm(uv_b[:, None] - uv_b[None, :], axis=2),
                atol=1e-10,
            )
    changed = [(a, b) for a, b in zip(before["edges"], after["edges"]) if a != b]
    assert len(changed) == 1 and changed[0][0]["seam"] and not changed[0][1]["seam"]
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_uv.source(p) == after


def test_pinned_island_can_be_chosen_as_static_and_stays_exact():
    p, moving, fixed = fixture()
    mesh_uv.pin(p, fixed["corner_ids"])
    before = mesh_uv.source(p)
    result = mesh_uv_stitch.stitch(
        p, moving["corner_ids"] + fixed["corner_ids"], static_corner_id=fixed["corner_ids"][0]
    )
    assert result["fixed_face_ids"] == fixed["face_ids"]
    after = mesh_uv.source(p)
    for a, b in zip(before["faces"], after["faces"]):
        if a["id"] in fixed["face_ids"]:
            assert a == b


@pytest.mark.parametrize(
    "fault,message", [("scale", "stretch"), ("pin", "pinned"), ("mirror", "overlap")]
)
def test_incompatible_stitch_rejects_atomically(fault, message):
    p, fixed, moving = fixture()
    if fault == "scale":
        mesh_uv.transform(p, moving["corner_ids"], scale=[2, 2])
    elif fault == "pin":
        mesh_uv.pin(p, moving["corner_ids"])
    else:
        mesh_uv.transform(p, moving["corner_ids"], scale=[-1, 1])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match=message):
        mesh_uv_stitch.stitch(
            p, fixed["corner_ids"] + moving["corner_ids"], static_corner_id=fixed["corner_ids"][0]
        )
    assert p.__dict__ == before


@pytest.mark.parametrize("selection", ["all", "one", "diagonal"])
def test_stitch_requires_exactly_two_edge_neighbors(selection):
    p, first, _second = fixture()
    islands = mesh_uv_islands.read(p)
    corners = None if selection == "all" else first["corner_ids"]
    if selection == "diagonal":
        corners = first["corner_ids"] + islands[3]["corner_ids"]
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_uv_stitch.stitch(p, corners)
    assert p.__dict__ == before


def test_stitch_can_join_uvs_while_retaining_every_authored_seam():
    p, fixed, moving = fixture()
    mesh_uv.transform(p, moving["corner_ids"], angle=37, offset=[0.4, -0.3])
    before = mesh_uv.source(p)
    result = mesh_uv_stitch.stitch(
        p,
        fixed["corner_ids"] + moving["corner_ids"],
        static_corner_id=fixed["corner_ids"][0],
        clear_seams=False,
    )
    after = mesh_uv.source(p)
    assert result["joined_edges"] == 1
    assert len(mesh_uv_islands.read(p)) == 3
    assert before["edges"] == after["edges"] and before["vertices"] == after["vertices"]
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_uv.source(p) == after


@pytest.mark.parametrize("invalid", [0, 1, "false", None])
def test_invalid_clear_seams_option_rejects_without_mutation(invalid):
    p, fixed, moving = fixture()
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match="Clear seams"):
        mesh_uv_stitch.stitch(p, fixed["corner_ids"] + moving["corner_ids"], clear_seams=invalid)
    assert vars(p) == before


def test_midpoint_stitch_moves_both_and_preserves_other_islands():
    p, first, second = fixture()
    mesh_uv.transform(p, second["corner_ids"], angle=37, offset=[0.4, -0.3])
    before = mesh_uv.source(p)
    result = mesh_uv_stitch.stitch(
        p, first["corner_ids"] + second["corner_ids"], midpoints=True, clear_seams=False
    )
    after = mesh_uv.source(p)
    assert not result["fixed_face_ids"]
    assert set(result["moved_face_ids"]) == set(first["face_ids"] + second["face_ids"])
    assert after["vertices"] == before["vertices"] and after["edges"] == before["edges"]
    assert len(mesh_uv_islands.read(p)) == 3
    for a, b in zip(before["faces"], after["faces"]):
        if a["id"] not in result["moved_face_ids"]:
            assert a == b
        else:
            av = np.array([c["uv"] for c in a["corners"]])
            bv = np.array([c["uv"] for c in b["corners"]])
            assert not np.allclose(av, bv)
            # The snapped shared edge shortens when the original islands differ
            # in rotation; unstitched corners follow their half-rotation transform.
            assert np.isfinite(bv).all()
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_uv.source(p) == after


@pytest.mark.parametrize("which", [0, 1])
def test_midpoint_rejects_pins_in_either_island_atomically(which):
    p, first, second = fixture()
    mesh_uv.pin(p, [first, second][which]["corner_ids"])
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match="pinned"):
        mesh_uv_stitch.stitch(p, first["corner_ids"] + second["corner_ids"], midpoints=True)
    assert vars(p) == before


@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_midpoint_requires_boolean(value):
    p, first, second = fixture()
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match="Midpoints"):
        mesh_uv_stitch.stitch(p, first["corner_ids"] + second["corner_ids"], midpoints=value)
    assert vars(p) == before


def test_stitch_respects_seams_even_where_coordinates_touch():
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Plane", entity_id="plane")
    mesh_document.bind(p, primitives.build("Plane", {"segments": 2})[0])
    mesh_uv.project(p, "planar_xz")
    before = mesh_uv.source(p)
    mesh_uv.seams(p, [e["id"] for e in before["edges"]])
    before = mesh_uv.source(p)
    assert len(mesh_uv_islands.groups(before)) == 1
    assert len(mesh_uv_islands.groups(before, respect_seams=True)) == 4
    selection = [c["id"] for f in before["faces"][:2] for c in f["corners"]]
    with pytest.raises(ValueError, match="exactly two"):
        mesh_uv_stitch.stitch(p, selection, respect_seams=False)
    result = mesh_uv_stitch.stitch(p, selection)
    assert result["joined_edges"] == 1
    after = mesh_uv.source(p)
    assert after["faces"] == before["faces"]
    assert sum(e["seam"] for e in after["edges"]) == 11


def test_midpoint_shared_endpoints_equal_arithmetic_mean():
    p, first, second = fixture()
    mesh_uv.transform(p, second["corner_ids"], angle=37, offset=[0.4, -0.3])
    before = mesh_uv.source(p)
    docs = {f["id"]: f for f in before["faces"]}
    a = {c["vertex"]: np.array(c["uv"]) for fid in first["face_ids"] for c in docs[fid]["corners"]}
    b = {c["vertex"]: np.array(c["uv"]) for fid in second["face_ids"] for c in docs[fid]["corners"]}
    expected = {v: (a[v] + b[v]) / 2 for v in a.keys() & b.keys()}
    mesh_uv_stitch.stitch(p, first["corner_ids"] + second["corner_ids"], midpoints=True)
    for f in mesh_uv.source(p)["faces"]:
        if f["id"] in first["face_ids"] + second["face_ids"]:
            for c in f["corners"]:
                if c["vertex"] in expected:
                    np.testing.assert_allclose(c["uv"], expected[c["vertex"]], atol=1e-12)
