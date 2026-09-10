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
    p, first, second = fixture()
    islands = mesh_uv_islands.read(p)
    corners = None if selection == "all" else first["corner_ids"]
    if selection == "diagonal":
        corners = first["corner_ids"] + islands[3]["corner_ids"]
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_uv_stitch.stitch(p, corners)
    assert p.__dict__ == before
