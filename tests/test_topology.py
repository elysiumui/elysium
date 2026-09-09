import json
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, primitives, topology


def cube():
    return primitives.build("Cube", {"size": 2})[0]


def top_face(mesh):
    doc = topology.document(mesh)
    verts = {v["id"]: v["position"] for v in doc["vertices"]}
    return next(f for f in doc["faces"] if all(verts[c["vertex"]][1] == 1 for c in f["corners"]))


def signed_volume(mesh):
    tri = mesh.verts[mesh.faces]
    return np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6


def test_cube_has_six_authored_quads_and_twelve_compiled_triangles():
    mesh = cube()
    assert len(mesh.topology["vertices"]) == 8
    assert len(mesh.topology["edges"]) == 12
    assert len(mesh.topology["faces"]) == 6
    assert all(len(f["corners"]) == 4 for f in mesh.topology["faces"])
    assert len(mesh.faces) == 12
    assert signed_volume(mesh) == pytest.approx(8)


def test_face_extrusion_preserves_ids_and_builds_watertight_correctly_wound_sides():
    mesh = cube()
    original = mesh_document.to_json(mesh)
    face = top_face(mesh)
    result = topology.extrude(mesh, [face["id"]], 1.0)
    doc = result.topology
    assert signed_volume(result) == pytest.approx(12)
    assert len(doc["vertices"]) == 12 and len(doc["edges"]) == 20 and len(doc["faces"]) == 10
    np.testing.assert_allclose(result.verts.min(axis=0), [-1, -1, -1])
    np.testing.assert_allclose(result.verts.max(axis=0), [1, 2, 1])
    before_faces = {f["id"]: f for f in mesh.topology["faces"]}
    after_faces = {f["id"]: f for f in doc["faces"]}
    for key, f in before_faces.items():
        if key != face["id"]:
            assert after_faces[key] == f
    assert [c["id"] for c in after_faces[face["id"]]["corners"]] == [
        c["id"] for c in face["corners"]
    ]
    assert mesh_document.to_json(mesh) == original
    # Closed manifold: every edge has exactly two opposite directed uses.
    usages = {tuple(e["vertices"]): [] for e in doc["edges"]}
    for f in doc["faces"]:
        ids = [c["vertex"] for c in f["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            usages[tuple(sorted((a, b)))].append((a, b))
    assert all(len(v) == 2 and v[0] == v[1][::-1] for v in usages.values())


def test_component_move_changes_only_selected_vertices_and_preserves_corner_data():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    for i, f in enumerate(doc["faces"]):
        f["material"] = i
        for j, c in enumerate(f["corners"]):
            c["uv"] = [j % 2, j // 2]
    mesh = topology.compile(doc)[0]
    vertex = doc["vertices"][0]["id"]
    edited = topology.move_vertices(mesh, [vertex], [0.25, 0, 0])
    for before, after in zip(doc["vertices"], edited.topology["vertices"]):
        if before["id"] != vertex:
            assert before == after
    assert [f["material"] for f in edited.topology["faces"]] == list(range(6))
    assert [[c["uv"] for c in f["corners"]] for f in edited.topology["faces"]] == [
        [c["uv"] for c in f["corners"]] for f in doc["faces"]
    ]


def test_owned_polygon_asset_reopens_with_ids_and_uv_seams_after_cache_clear():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    for i, f in enumerate(doc["faces"]):
        for j, c in enumerate(f["corners"]):
            c["uv"] = [i * 0.1, j * 0.2]
    mesh = topology.compile(doc)[0]
    p = SimpleNamespace(kind="Mesh3D", entity_id="cube", props={}, mesh_kind="")
    key = mesh_document.bind(p, mesh)
    saved = json.loads(json.dumps(mesh_document.capture([p])))
    assert saved["schema_version"] == 2
    from elysium.render import pbr

    pbr.MESH_LIBRARY.pop(key)
    mesh_document.restore(saved, [p])
    actual = mesh_document.resolve(key)
    assert actual.topology == doc
    np.testing.assert_array_equal(actual.vert_uvs, mesh.vert_uvs)
    np.testing.assert_array_equal(actual.faces, mesh.faces)


def test_invalid_edit_is_atomic_and_malformed_topology_is_rejected():
    mesh = cube()
    before = mesh_document.to_json(mesh)
    for ids, distance in [([], 1), (["missing"], 1), ([top_face(mesh)["id"]], float("nan"))]:
        with pytest.raises(ValueError):
            topology.extrude(mesh, ids, distance)
        assert mesh_document.to_json(mesh) == before
    malformed = deepcopy(before)
    malformed["topology"]["vertices"][0]["position"][0] += 1
    with pytest.raises(ValueError):
        mesh_document.from_json(malformed)
    malformed = deepcopy(before)
    malformed["topology"]["faces"][0]["corners"][0]["id"] = malformed["topology"]["vertices"][0][
        "id"
    ]
    with pytest.raises(ValueError, match="identity"):
        mesh_document.from_json(malformed)


def test_concave_polygon_triangulates_without_filling_its_notch():
    points = [[0, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0], [1, 2, 0], [0, 2, 0]]
    result = topology.triangles(points)
    p = np.asarray(points)
    area = sum(np.linalg.norm(np.cross(p[b] - p[a], p[c] - p[a])) / 2 for a, b, c in result)
    assert area == pytest.approx(3)
    with pytest.raises(ValueError):
        topology.triangles([[0, 0, 0], [2, 2, 0], [0, 2, 0], [2, 0, 0]])


def test_inset_even_distance_manifold_volume_uvs_and_persistence():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    selected = top_face(mesh)["id"]
    face = next(f for f in doc["faces"] if f["id"] == selected)
    verts = {v["id"]: v["position"] for v in doc["vertices"]}
    face["material"] = 3
    for c in face["corners"]:
        x, _, z = verts[c["vertex"]]
        c["uv"] = [(x + 1) / 2, (z + 1) / 2]
    mesh = topology.compile(doc)[0]
    result = topology.inset(mesh, [selected], 0.25)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [12, 20, 10]
    assert signed_volume(result) == pytest.approx(8)
    inner = next(f for f in result.topology["faces"] if f["id"] == selected)
    positions = {v["id"]: v["position"] for v in result.topology["vertices"]}
    assert [c["id"] for c in inner["corners"]] == [c["id"] for c in face["corners"]]
    for c in inner["corners"]:
        x, y, z = positions[c["vertex"]]
        assert (abs(x), y, abs(z)) == pytest.approx((0.75, 1, 0.75))
        assert c["uv"] == pytest.approx([(x + 1) / 2, (z + 1) / 2])
    borders = result.topology["faces"][6:]
    assert all(f["material"] == 3 for f in borders)
    usages = {}
    for f in result.topology["faces"]:
        ids = [c["vertex"] for c in f["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            usages.setdefault(tuple(sorted((a, b))), []).append((a, b))
    assert all(len(v) == 2 and v[0] == v[1][::-1] for v in usages.values())
    reopened = mesh_document.from_json(json.loads(json.dumps(mesh_document.to_json(result))))
    assert reopened.topology == result.topology
    assert mesh.topology == doc


@pytest.mark.parametrize("thickness", [0, -1, 1, 1.1, float("nan"), float("inf")])
def test_inset_invalid_or_collapsed_is_atomic(thickness):
    mesh = cube()
    original = mesh_document.to_json(mesh)
    with pytest.raises(ValueError):
        topology.inset(mesh, [top_face(mesh)["id"]], thickness)
    assert mesh_document.to_json(mesh) == original


def test_inset_multiple_faces_remain_individual_and_watertight():
    mesh = cube()
    result = topology.inset(mesh, [f["id"] for f in mesh.topology["faces"]], 0.2)
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [32, 60, 30]
    assert signed_volume(result) == pytest.approx(8)


def test_inset_oblique_triangle_has_even_perpendicular_thickness():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    face = doc["faces"][0]
    face["corners"].pop()
    doc["faces"] = [face]
    topology._edges(doc)
    mesh = topology.compile(doc)[0]
    result = topology.inset(mesh, [face["id"]], 0.1)
    vertices = {v["id"]: np.array(v["position"]) for v in result.topology["vertices"]}
    before = [vertices[c["vertex"]] for c in face["corners"]]
    after = [vertices[c["vertex"]] for c in result.topology["faces"][0]["corners"]]
    for i, a in enumerate(before):
        edge = before[(i + 1) % 3] - a
        for j in (i, (i + 1) % 3):
            assert np.linalg.norm(np.cross(after[j] - a, edge)) / np.linalg.norm(
                edge
            ) == pytest.approx(0.1)


def test_cylinder_nozzle_inset_then_inward_extrusion_has_expected_cavity_volume():
    n, thickness, depth = 8, 0.2, 0.4
    mesh = primitives.build("Cylinder", {"segments": n})[0]
    face = top_face(mesh)
    inset_mesh = topology.inset(mesh, [face["id"]], thickness)
    result = topology.extrude(inset_mesh, [face["id"]], -depth)
    inner_radius = 1 - thickness / np.cos(np.pi / n)
    area = n / 2 * np.sin(2 * np.pi / n)
    assert signed_volume(result) == pytest.approx(
        2 * area - depth * area * inner_radius**2, rel=1e-6
    )
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [32, 56, 26]
    # Inner wall UVs inherit their boundary rather than replacing all UVs by zero.
    for f in result.topology["faces"][-n:]:
        a, b, c, d = f["corners"]
        assert a["uv"] == d["uv"] and b["uv"] == c["uv"] and a["uv"] != b["uv"]
    assert mesh_document.from_json(mesh_document.to_json(result)).topology == result.topology


def test_extrusion_propagates_parallel_edge_flags_and_rejects_inconsistent_winding():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    face = top_face(mesh)
    selected_ids = {c["vertex"] for c in face["corners"]}
    edge = next(e for e in doc["edges"] if set(e["vertices"]) <= selected_ids)
    edge["seam"] = edge["sharp"] = True
    mesh = topology.compile(doc)[0]
    result = topology.extrude(mesh, [face["id"]], 1)
    marked = [e for e in result.topology["edges"] if e["seam"] and e["sharp"]]
    assert len(marked) == 2 and edge in marked
    neighbor = next(
        f
        for f in doc["faces"]
        if f["id"] != face["id"] and len({c["vertex"] for c in f["corners"]} & selected_ids) == 2
    )
    neighbor["corners"].reverse()
    malformed_winding = topology.compile(doc)[0]
    with pytest.raises(ValueError, match="winding"):
        topology.extrude(malformed_winding, [face["id"], neighbor["id"]], 1)


def test_move_rejects_mixed_valid_and_stale_component_ids_atomically():
    mesh = cube()
    p = SimpleNamespace(kind="Mesh3D", entity_id="stale", name="Stale", props={}, mesh_kind="")
    mesh_document.bind(p, mesh)
    p.props["components3d"] = {"mode": "edges", "ids": [mesh.topology["edges"][0]["id"], "e9999"]}
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="existing"):
        topology.edit_selected(p, "move", offset=[0.1, 0, 0])
    assert p.__dict__ == before


def test_individual_extrusion_separates_adjacent_caps_and_preserves_closed_shell():
    mesh = cube()
    before = deepcopy(mesh.topology)
    identities = [f["id"] for f in before["faces"]]
    result = topology.extrude(mesh, identities, 0.25, individual=True)
    doc = result.topology
    assert [len(doc[k]) for k in ("vertices", "edges", "faces")] == [32, 60, 30]
    assert signed_volume(result) == pytest.approx(14)
    positions = {v["id"]: np.array(v["position"]) for v in doc["vertices"]}
    old_positions = {v["id"]: np.array(v["position"]) for v in before["vertices"]}
    caps = {f["id"]: f for f in doc["faces"] if f["id"] in identities}
    cap_vertices = set()
    for original in before["faces"]:
        direction = topology.normal([old_positions[c["vertex"]] for c in original["corners"]])
        cap = caps[original["id"]]
        for a, b in zip(original["corners"], cap["corners"]):
            assert a["id"] == b["id"]
            assert b["vertex"] not in cap_vertices
            cap_vertices.add(b["vertex"])
            np.testing.assert_allclose(
                positions[b["vertex"]], old_positions[a["vertex"]] + direction * 0.25
            )
            assert a["uv"] == b["uv"] and a["normal"] == b["normal"]
    usages = {}
    for face in doc["faces"]:
        ids = [c["vertex"] for c in face["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            usages.setdefault(tuple(sorted((a, b))), []).append((a, b))
    assert all(len(v) == 2 and v[0] == v[1][::-1] for v in usages.values())
    assert mesh.topology == before
    assert mesh_document.from_json(mesh_document.to_json(result)).topology == doc


def test_individual_extrusion_rejects_stale_selection_without_partial_publication():
    mesh = cube()
    p = SimpleNamespace(
        kind="Mesh3D", entity_id="individual", name="Individual", props={}, mesh_kind=""
    )
    mesh_document.bind(p, mesh)
    topology.select(p, "faces", [f["id"] for f in mesh.topology["faces"]])
    before = deepcopy(p.__dict__)
    p.props["components3d"]["ids"].append("f999999")
    invalid = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="no longer exists"):
        topology.edit_selected(p, "extrude_individual", distance=0.25)
    assert p.__dict__ == invalid
    p.props = before["props"]
    result = topology.edit_selected(p, "extrude_individual", distance=0.25)
    assert (result["vertices"], result["edges"], result["faces"]) == (32, 60, 30)
    assert result["selection"] == before["props"]["components3d"]


def test_delete_face_and_fill_boundary_restore_oriented_geometry():
    mesh = cube()
    face_id = top_face(mesh)["id"]
    cut = topology.delete_components(mesh, "faces", [face_id])
    assert [len(cut.topology[k]) for k in ("vertices", "edges", "faces")] == [8, 12, 5]
    uses = topology.edge_usage(cut.topology)
    boundary = [e["id"] for e in cut.topology["edges"] if len(uses[tuple(e["vertices"])]) == 1]
    assert len(boundary) == 4
    filled, identity = topology.fill_loop(cut, "edges", boundary)
    assert [len(filled.topology[k]) for k in ("vertices", "edges", "faces")] == [8, 12, 6]
    assert signed_volume(filled) == pytest.approx(8)
    assert filled.topology["edges"] == mesh.topology["edges"]
    assert len(next(f for f in filled.topology["faces"] if f["id"] == identity)["corners"]) == 4
    assert all(
        len(v) == 2 and v[0] == v[1][::-1] for v in topology.edge_usage(filled.topology).values()
    )
    assert mesh_document.from_json(mesh_document.to_json(filled)).topology == filled.topology


def test_delete_edges_keeps_wires_and_loose_vertices_in_compiled_document():
    mesh = primitives.build("Plane", {"segments": 1})[0]
    edge = mesh.topology["edges"][0]
    wire = topology.delete_components(mesh, "edges", [edge["id"]])
    assert [len(wire.topology[k]) for k in ("vertices", "edges", "faces")] == [4, 3, 0]
    assert wire.verts.shape == (4, 3) and wire.faces.shape == (0, 3)
    assert len(topology.loose_edges(wire.topology)) == 3
    restored = mesh_document.from_json(mesh_document.to_json(wire))
    assert restored.topology == wire.topology
    vertex = edge["vertices"][0]
    moved = topology.move_vertices(restored, [vertex], [0, 0.5, 0])
    assert len(moved.verts) == 4 and len(moved.topology["edges"]) == 3
    with pytest.raises(ValueError, match="closed loop"):
        topology.fill_loop(wire, "edges", [e["id"] for e in wire.topology["edges"]])


@pytest.mark.parametrize("mode", ["vertices", "edges", "faces"])
def test_delete_all_retains_valid_empty_mesh_and_identity_counter(mode):
    mesh = cube()
    empty = topology.delete_components(mesh, mode, [v["id"] for v in mesh.topology[mode]])
    assert empty.verts.shape == (0, 3) and empty.faces.shape == (0, 3)
    assert not any(empty.topology[k] for k in ("vertices", "edges", "faces"))
    assert empty.topology["next_id"] == mesh.topology["next_id"]
    assert mesh_document.from_json(mesh_document.to_json(empty)).topology == empty.topology


def test_fill_rejects_closed_shell_stale_and_disconnected_selections_atomically():
    mesh = cube()
    before = mesh_document.to_json(mesh)
    for ids in (
        [mesh.topology["edges"][0]["id"], "e999999"],
        [e["id"] for e in mesh.topology["edges"]],
    ):
        with pytest.raises(ValueError):
            topology.fill_loop(mesh, "edges", ids)
    top = {c["vertex"] for c in top_face(mesh)["corners"]}
    boundary = [e["id"] for e in mesh.topology["edges"] if set(e["vertices"]) <= top]
    with pytest.raises(ValueError, match="two faces"):
        topology.fill_loop(mesh, "edges", boundary)
    assert mesh_document.to_json(mesh) == before


def test_extrude_and_inset_preserve_preexisting_wires():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    doc["schema_version"] = 2
    loose_vertex = {"id": topology._id(doc, "v"), "position": [3, 0, 0], "part": None}
    doc["vertices"].append(loose_vertex)
    edge = {
        "id": topology._id(doc, "e"),
        "vertices": [doc["vertices"][0]["id"], loose_vertex["id"]],
        "seam": True,
        "sharp": True,
    }
    doc["edges"].append(edge)
    wired = topology.compile(doc)[0]
    selected = top_face(wired)["id"]
    for result in (
        topology.extrude(wired, [selected], 0.25),
        topology.inset(wired, [selected], 0.2),
    ):
        assert edge in result.topology["edges"] and loose_vertex in result.topology["vertices"]
        assert len(result.verts) >= len(wired.verts)
