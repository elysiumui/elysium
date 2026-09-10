from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_edit, mesh_modifiers, primitives, scene, topology


def placement():
    p = SimpleNamespace(
        kind="Mesh3D", name="Cube", entity_id="modifier-cube", props={}, mesh_kind=""
    )
    mesh = primitives.build("Cube", {"size": 2})[0]
    moved = topology.move_vertices(mesh, [v["id"] for v in mesh.topology["vertices"]], [2, 0, 0])
    mesh_document.bind(p, moved)
    return p


def positions(mesh):
    return sorted(tuple(v["position"]) for v in mesh.topology["vertices"])


def test_mirror_retains_source_and_reflects_winding_and_corner_attributes():
    p = placement()
    key = p.mesh_kind
    source = deepcopy(mesh_document.to_json(mesh_document.resolve(key)))
    stack = mesh_modifiers.add(p, "Mirror", {"axis": "x"})
    result = mesh_edit.evaluate(p)
    assert p.mesh_kind == key and mesh_document.to_json(mesh_document.resolve(key)) == source
    assert stack["items"][0]["id"] == "mod1"
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [16, 24, 12]
    assert {v["position"][0] for v in result.topology["vertices"]} == {-3, -1, 1, 3}
    assert all(
        len(u) == 2 and u[0] == u[1][::-1] for u in topology.edge_usage(result.topology).values()
    )
    assert result.topology["faces"][:6] == source["topology"]["faces"]
    assert [[c["uv"] for c in f["corners"]] for f in result.topology["faces"][6:]] == [
        [c["uv"] for c in reversed(f["corners"])] for f in source["topology"]["faces"]
    ]


def test_mirror_merge_joins_only_plane_vertices_into_closed_surface():
    p = placement()
    cube = primitives.build("Cube", {"size": 2})[0]
    half, _, _ = topology.bisect(cube, [0, 0, 0], [1, 0, 0], keep="negative")
    mesh_document.bind(p, half)
    mesh_modifiers.add(p, "Mirror", {"merge": True})
    result = mesh_edit.evaluate(p)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [12, 20, 10]
    assert all(
        len(u) == 2 and u[0] == u[1][::-1] for u in topology.edge_usage(result.topology).values()
    )
    assert len(mesh_document.resolve(p.mesh_kind).topology["vertices"]) == 8


def test_array_order_bypass_removal_and_apply_are_retained_and_atomic():
    p = placement()
    source = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    mesh_modifiers.add(p, "Mirror")
    mesh_modifiers.add(p, "Array", {"count": 2, "offset": [8, 0, 0]})
    first = positions(mesh_edit.evaluate(p))
    mesh_modifiers.update(p, "mod2", index=0)
    second = positions(mesh_edit.evaluate(p))
    assert first != second and len(first) == len(second) == 32
    mesh_modifiers.update(p, "mod1", enabled=False)
    assert len(mesh_edit.evaluate(p).topology["vertices"]) == 16
    mesh_modifiers.update(p, "mod1", remove=True)
    assert [m["id"] for m in mesh_modifiers.settings(p)["items"]] == ["mod2"]
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == source
    expected = mesh_document.to_json(mesh_edit.evaluate(p))
    mesh_modifiers.apply_all(p)
    assert "modifiers3d" not in p.props
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == expected
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == expected


def test_saved_stack_keeps_only_source_asset_and_reopens_evaluation():
    p = placement()
    mesh_modifiers.add(p, "Array", {"count": 3, "offset": [3, 0, 0]})
    saved = mesh_document.capture([p])
    props = deepcopy(p.props)
    expected = mesh_document.to_json(mesh_edit.evaluate(p))
    assert len(saved["assets"][p.mesh_kind]["topology"]["vertices"]) == 8
    from elysium.render import pbr

    pbr.MESH_LIBRARY.pop(p.mesh_kind)
    p.props = props
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == expected


@pytest.mark.parametrize(
    "kind,values",
    [
        ("Unknown", {}),
        ("Mirror", {"axis": "w"}),
        ("Mirror", {"merge": 1}),
        ("Mirror", {"threshold": -1}),
        ("Array", {"count": 65}),
        ("Array", {"offset": [0, float("nan"), 0]}),
        ("Mirror", {"extra": 1}),
    ],
)
def test_invalid_modifier_parameters_do_not_mutate(kind, values):
    p = placement()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_modifiers.add(p, kind, values)
    assert p.__dict__ == before


def test_invalid_stack_rejects_on_document_capture_and_restore_without_cache_mutation():
    p = placement()
    mesh_modifiers.add(p, "Mirror")
    saved = mesh_document.capture([p])
    p.props["modifiers3d"]["items"][0]["id"] = "mod0"
    with pytest.raises(ValueError):
        mesh_document.capture([p])
    with pytest.raises(ValueError):
        mesh_document.restore(saved, [p])


def test_stack_limit_rejects_before_exponential_geometry_allocation():
    p = placement()
    mesh_modifiers.add(p, "Array", {"count": 64})
    mesh_modifiers.add(p, "Array", {"count": 8})
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="limit"):
        # Three more copies would remain manageable; huge nested expansion must
        # fail before building the next document instead of freezing the GUI.
        mesh_modifiers.add(p, "Array", {"count": 64})
    assert p.__dict__ == before


def test_apply_transform_preserves_stack_without_baking_generated_copies_twice():
    p = placement()
    mesh_modifiers.add(p, "Mirror")
    scene.update(p, {"scale": [2, 2, 2]})
    scene.apply_transform([p], p)
    assert len(mesh_document.resolve(p.mesh_kind).topology["vertices"]) == 8
    assert len(mesh_edit.evaluate(p).topology["vertices"]) == 16
    assert mesh_modifiers.settings(p)["items"][0]["kind"] == "Mirror"
    assert scene.transform(p)["scale"] == [1, 1, 1]


@pytest.mark.parametrize("thickness", [0.25, -0.25])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_solidify_plane_has_closed_outward_shell_and_preserves_source(thickness, offset):
    p = placement()
    mesh_document.bind(p, primitives.build("Plane", {"segments": 2})[0])
    source = mesh_document.to_json(mesh_document.resolve(p.mesh_kind))
    mesh_modifiers.add(p, "Solidify", {"thickness": thickness, "offset": offset})
    result = mesh_edit.evaluate(p)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [18, 32, 16]
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == source
    assert all(
        len(u) == 2 and u[0] == u[1][::-1] for u in topology.edge_usage(result.topology).values()
    )
    assert sorted({round(v["position"][1], 10) for v in result.topology["vertices"]}) == sorted(
        [thickness * (offset - 1) / 2, thickness * (offset + 1) / 2]
    )
    triangles = result.verts[result.faces].astype(float)
    volume = (
        np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6
    )
    assert volume == pytest.approx(4 * abs(thickness))
    assert [[c["uv"] for c in f["corners"]] for f in result.topology["faces"][:4]] == [
        [c["uv"] for c in (f["corners"] if thickness > 0 else reversed(f["corners"]))]
        for f in source["topology"]["faces"]
    ]


def test_solidify_open_rim_and_array_stack_save_reopen_apply():
    p = placement()
    mesh_document.bind(p, primitives.build("Plane", {})[0])
    mesh_modifiers.add(p, "Solidify", {"rim": False})
    result = mesh_edit.evaluate(p)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [8, 8, 2]
    mesh_modifiers.update(p, "mod1", values={"rim": True})
    mesh_modifiers.add(p, "Array", {"count": 3})
    expected = mesh_document.to_json(mesh_edit.evaluate(p))
    assert len(expected["topology"]["faces"]) == 18
    saved = mesh_document.capture([p])
    assert len(saved["assets"][p.mesh_kind]["topology"]["vertices"]) == 4
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh_edit.evaluate(p)) == expected
    mesh_modifiers.apply_all(p)
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == expected


def test_solidify_cube_uses_normal_offset_and_retains_edge_attributes():
    p = placement()
    source = topology.document(mesh_document.resolve(p.mesh_kind))
    source["edges"][0].update(seam=True, sharp=True)
    mesh_document.bind(p, topology.compile(source)[0])
    mesh_modifiers.add(p, "Solidify", {"thickness": 0.3})
    result = mesh_edit.evaluate(p)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [16, 24, 12]
    for before, after in zip(source["vertices"], result.topology["vertices"][8:]):
        assert np.linalg.norm(np.asarray(before["position"]) - after["position"]) == pytest.approx(
            0.3
        )
    assert sum(e["seam"] and e["sharp"] for e in result.topology["edges"]) == 2


@pytest.mark.parametrize(
    "values",
    [{"thickness": 0}, {"thickness": True}, {"thickness": float("inf")}, {"offset": 2}, {"rim": 1}],
)
def test_invalid_solidify_parameters_are_atomic(values):
    p = placement()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_modifiers.add(p, "Solidify", values)
    assert p.__dict__ == before


def test_solidify_rejects_inconsistent_winding_without_publishing():
    p = placement()
    doc = topology.document(mesh_document.resolve(p.mesh_kind))
    doc["faces"][0]["corners"].reverse()
    mesh_document.bind(p, topology.compile(doc)[0])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="consistently oriented"):
        mesh_modifiers.add(p, "Solidify")
    assert p.__dict__ == before


def test_taper_failure_does_not_publish_a_broken_modifier_source():
    p = placement()
    mesh_document.bind(p, primitives.build("Plane", {})[0])
    mesh_modifiers.add(p, "Solidify")
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="nonzero extent"):
        mesh_edit.taper_set(p, {"axis": "y", "end": [0.5, 1, 0.5]})
    assert p.__dict__ == before


def test_apply_transform_validates_retained_evaluation_before_binding():
    p = placement()
    mesh_modifiers.add(p, "Mirror", {"merge": True, "threshold": 1e-6})
    scene.update(p, {"scale": [1e-7, 1, 1]})
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        scene.apply_transform([p], p)
    assert p.__dict__ == before


def test_public_modifier_handlers_expose_source_and_evaluation_separately():
    from elysium.aether.tools import scene as commands

    p = placement()
    mesh_document.bind(p, primitives.build("Plane", {})[0])
    session = SimpleNamespace(lookup=lambda identity: p)
    stack = commands.modifier_add(session, p.entity_id, "Solidify", {"thickness": 0.2})
    assert stack["items"][0]["kind"] == "Solidify"
    state = commands.modifiers_get(session, p.entity_id)
    assert len(state["source_topology"]["vertices"]) == 4
    assert len(state["evaluated_topology"]["faces"]) == 6
    commands.modifier_update(session, p.entity_id, "mod1", enabled=False)
    assert len(commands.modifiers_get(session, p.entity_id)["evaluated_topology"]["faces"]) == 1
    commands.modifier_update(session, p.entity_id, "mod1", enabled=True)
    commands.modifiers_apply(session, p.entity_id)
    state = commands.modifiers_get(session, p.entity_id)
    assert not state["stack"]["items"]
    assert state["source_topology"] == state["evaluated_topology"]
