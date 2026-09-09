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


def test_point_wire_construction_round_trip_keeps_existing_attributes():
    mesh = cube()
    original = deepcopy(mesh.topology)
    first, a = topology.add_vertex(mesh, [3, 0, 0])
    second, b = topology.add_vertex(first, [3, 1, 0])
    connected, edge = topology.connect_vertices(second, [a, b])
    extended, endpoints = topology.extrude_vertices(connected, [a, b], [0, 0, 2])
    doc = extended.topology
    assert [len(doc[k]) for k in ("vertices", "edges", "faces")] == [12, 15, 6]
    assert doc["faces"] == original["faces"]
    assert all(e in doc["edges"] for e in original["edges"])
    assert len(topology.loose_edges(doc)) == 3
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    assert [points[v] for v in endpoints] == [[3, 0, 2], [3, 1, 2]]
    assert edge in {e["id"] for e in doc["edges"]}
    assert mesh_document.from_json(mesh_document.to_json(extended)).topology == doc
    assert mesh.topology == original


@pytest.mark.parametrize(
    "operation,kwargs",
    [
        ("add_vertex", {"position": [float("nan"), 0, 0]}),
        ("add_vertex", {"position": [1, 2]}),
        ("extrude_vertices", {"offset": [0, 0, 0]}),
        ("extrude_vertices", {"offset": [0, float("inf"), 0]}),
        ("connect", {}),  # A single selected point cannot define an edge.
    ],
)
def test_invalid_wire_commands_never_publish_a_revision(operation, kwargs):
    p = SimpleNamespace(kind="Mesh3D", name="Wire", props={}, mesh_kind="")
    mesh_document.bind(p, cube())
    topology.select(p, "vertices", ["v1"])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        topology.edit_selected(p, operation, **kwargs)
    assert p.__dict__ == before


def test_vertex_wire_construction_empty_mesh_selection_and_rejections():
    mesh = cube()
    empty = topology.delete_components(mesh, "faces", [f["id"] for f in mesh.topology["faces"]])
    p = SimpleNamespace(kind="Mesh3D", name="Wire", props={}, mesh_kind="")
    mesh_document.bind(p, empty)
    first = topology.edit_selected(p, "add_vertex", position=[0, 0, 0])
    a = first["selection"]["ids"][0]
    second = topology.edit_selected(p, "add_vertex", position=[1, 0, 0])
    b = second["selection"]["ids"][0]
    topology.select(p, "vertices", [a, b])
    edge = topology.edit_selected(p, "connect")
    assert edge["selection"]["mode"] == "edges"
    assert (edge["vertices"], edge["edges"], edge["faces"]) == (2, 1, 0)
    topology.select(p, "vertices", [a, b])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="already connected"):
        topology.edit_selected(p, "connect")
    assert p.__dict__ == before
    p.props["components3d"]["ids"].append("v999999")
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="existing vertices"):
        topology.edit_selected(p, "extrude_vertices", offset=[0, 1, 0])
    assert p.__dict__ == before
    # Coincident authoring points stay separate; connecting them is rejected.
    coincident, c = topology.add_vertex(mesh_document.resolve(p.mesh_kind), [1, 0, 0])
    with pytest.raises(ValueError, match="coincident"):
        topology.connect_vertices(coincident, [b, c])


def test_boundary_edge_extrusion_preserves_winding_attributes_and_shared_vertices():
    mesh = primitives.build("Plane", {"segments": 1})[0]
    doc = deepcopy(mesh.topology)
    doc["faces"][0]["material"] = 2
    for edge in doc["edges"]:
        edge["seam"], edge["sharp"] = True, True
    mesh = topology.compile(doc)[0]
    result, caps = topology.extrude_edges(mesh, [e["id"] for e in doc["edges"]], [0, 1, 0])
    assert [len(result.topology[k]) for k in ("vertices", "edges", "faces")] == [8, 12, 5]
    assert result.topology["faces"][0] == doc["faces"][0]
    assert all(e in result.topology["edges"] for e in doc["edges"])
    assert all(f["material"] == 2 for f in result.topology["faces"])
    assert all(e["seam"] and e["sharp"] for e in result.topology["edges"] if e["id"] in caps)
    assert all(
        len(u) == 1 or u[0] == u[1][::-1] for u in topology.edge_usage(result.topology).values()
    )
    assert mesh_document.from_json(mesh_document.to_json(result)).topology == result.topology


def test_wire_edge_extrusion_makes_quads_and_selects_parallel_edges():
    mesh = cube()
    empty = topology.delete_components(mesh, "faces", [f["id"] for f in mesh.topology["faces"]])
    mesh, a = topology.add_vertex(empty, [0, 0, 0])
    mesh, b = topology.add_vertex(mesh, [1, 0, 0])
    mesh, edge = topology.connect_vertices(mesh, [a, b])
    p = SimpleNamespace(kind="Mesh3D", name="Surface", props={}, mesh_kind="")
    mesh_document.bind(p, mesh)
    topology.select(p, "edges", [edge])
    result = topology.edit_selected(p, "extrude_edges", offset=[0, 1, 0])
    assert (result["vertices"], result["edges"], result["faces"]) == (4, 4, 1)
    assert result["selection"]["mode"] == "edges" and result["selection"]["ids"] != [edge]
    actual = mesh_document.resolve(p.mesh_kind)
    positions = {v["id"]: v["position"] for v in actual.topology["vertices"]}
    face = actual.topology["faces"][0]
    np.testing.assert_allclose(
        topology.normal([positions[c["vertex"]] for c in face["corners"]]), [0, 0, -1]
    )
    # Sweep the selected cap again. The join keeps a consistent outward winding.
    result = topology.edit_selected(p, "extrude_edges", offset=[0, 1, 0])
    assert (result["vertices"], result["edges"], result["faces"]) == (6, 7, 2)
    assert all(
        len(u) == 1 or u[0] == u[1][::-1]
        for u in topology.edge_usage(mesh_document.resolve(p.mesh_kind).topology).values()
    )


def test_edge_extrusion_rejects_interior_or_degenerate_sweeps_atomically():
    p = SimpleNamespace(kind="Mesh3D", name="Invalid", props={}, mesh_kind="")
    mesh = cube()
    mesh_document.bind(p, mesh)
    topology.select(p, "edges", [mesh.topology["edges"][0]["id"]])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="shared by two faces"):
        topology.edit_selected(p, "extrude_edges", offset=[0, 1, 0])
    assert p.__dict__ == before
    plane = primitives.build("Plane", {"segments": 1})[0]
    edge = plane.topology["edges"][0]
    points = {v["id"]: v["position"] for v in plane.topology["vertices"]}
    parallel = (np.array(points[edge["vertices"][1]]) - points[edge["vertices"][0]]).tolist()
    original = mesh_document.to_json(plane)
    with pytest.raises(ValueError):
        topology.extrude_edges(plane, [edge["id"]], parallel)
    assert mesh_document.to_json(plane) == original


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), True),
        (("vertices",), None),
        (("edges",), {}),
        (("faces",), "invalid"),
        (("next_id",), False),
        (("vertices", 0), []),
        (("vertices", 0, "id"), "x1"),
        (("vertices", 0, "id"), "v01"),
        (("vertices", 0, "id"), "v٠١"),
        (("vertices", 0, "position"), None),
        (("vertices", 0, "position"), [True, 0, 0]),
        (("vertices", 0, "position"), [10**500, 0, 0]),
        (("vertices", 0, "part"), 0),
        (("part_names",), "Wing"),
        (("part_names",), [["Wing"]]),
        (("part_names",), ["Wing", "Wing"]),
        (("part_pivots",), [[0, 0, 0]]),
        (("faces", 0, "corners"), None),
        (("faces", 0, "material"), 2**31),
        (("faces", 0, "corners", 0, "uv"), ["0", "1"]),
        (("faces", 0, "corners", 0, "normal"), [0, float("nan"), 0]),
        (("faces", 0, "corners", 0, "vertex"), []),
        (("edges", 0, "vertices"), [1, 2]),
        (("edges", 0, "seam"), "false"),
        (("edges", 0, "sharp"), 1),
        (("edges", 0, "id"), "e1"),
    ],
)
def test_malformed_topology_is_rejected_as_validation_error(path, value):
    source = deepcopy(cube().topology)
    target = source
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    before = deepcopy(source)
    with pytest.raises(ValueError):
        topology.compile(source)
    # Validation never repairs or mutates the supplied source.
    assert repr(source) == repr(before)


def test_unknown_topology_fields_and_part_name_disagreement_reject_before_restore():
    mesh = cube()
    source = deepcopy(mesh.topology)
    source["faces"][0]["unsupported_attribute"] = "retain or reject, never silently discard"
    with pytest.raises(ValueError, match="component fields"):
        topology.compile(source)
    source = deepcopy(mesh.topology)
    source["part_names"] = ["Body"]
    source["part_pivots"] = [[0, 0, 0]]
    for vertex in source["vertices"]:
        vertex["part"] = 0
    asset = mesh_document.to_json(topology.compile(source)[0])
    asset["part_names"] = ["Other"]
    before = set(primitives.pbr.MESH_LIBRARY)
    with pytest.raises(ValueError, match="part_names disagree"):
        mesh_document.restore({"schema_version": 2, "assets": {"invalid-parts": asset}})
    assert set(primitives.pbr.MESH_LIBRARY) == before


def test_quad_torus_edge_loop_and_ring_selection_preserves_geometry():
    mesh = primitives.build(
        "Torus", {"major_segments": 8, "minor_segments": 4, "major_radius": 1, "minor_radius": 0.25}
    )[0]
    positions = {v["id"]: np.array(v["position"]) for v in mesh.topology["vertices"]}
    seed = next(
        e["id"]
        for e in mesh.topology["edges"]
        if all(abs(np.linalg.norm(positions[v][[0, 2]]) - 1.25) < 1e-6 for v in e["vertices"])
    )
    p = SimpleNamespace(kind="Mesh3D", name="Torus", props={}, mesh_kind="")
    mesh_document.bind(p, mesh)
    key = p.mesh_kind
    geometry = mesh_document.to_json(mesh_document.resolve(key))
    topology.select(p, "edges", [seed])
    loop = topology.expand_edge_selection(p, "loop")
    assert len(loop["ids"]) == 8
    chosen = [e for e in mesh.topology["edges"] if e["id"] in loop["ids"]]
    assert all(
        abs(np.linalg.norm(positions[v][[0, 2]]) - 1.25) < 1e-6
        for e in chosen
        for v in e["vertices"]
    )
    topology.select(p, "edges", [seed])
    ring = topology.expand_edge_selection(p, "ring")
    assert len(ring["ids"]) == 4
    assert set(loop["ids"]) & set(ring["ids"]) == {seed}
    assert p.mesh_kind == key
    assert mesh_document.to_json(mesh_document.resolve(key)) == geometry
    p.props["components3d"]["ids"].append("e999999")
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="no longer exist"):
        topology.expand_edge_selection(p, "loop")
    assert p.__dict__ == before


def test_edge_loop_stops_at_irregular_vertices_and_ring_crosses_quad_faces():
    mesh = cube()
    p = SimpleNamespace(kind="Mesh3D", name="Cube", props={}, mesh_kind="")
    mesh_document.bind(p, mesh)
    seed = mesh.topology["edges"][0]["id"]
    topology.select(p, "edges", [seed])
    assert topology.expand_edge_selection(p, "loop")["ids"] == [seed]
    assert len(topology.expand_edge_selection(p, "ring")["ids"]) == 4


def test_proportional_move_has_measured_smooth_radius_and_preserves_attributes():
    mesh = primitives.build("Plane", {"width": 2, "depth": 2, "segments": 2})[0]
    original = deepcopy(mesh.topology)
    center = next(v["id"] for v in original["vertices"] if v["position"] == [0, 0, 0])
    moved = topology.move_vertices(mesh, [center], [0, 0.5, 0], radius=1.5)
    points = {tuple(v["position"][::2]): v["position"][1] for v in moved.topology["vertices"]}
    assert points[(0, 0)] == pytest.approx(0.5)
    assert points[(1, 0)] == pytest.approx(0.5 * 7 / 27)
    assert points[(0, -1)] == pytest.approx(0.5 * 7 / 27)
    assert 0 < points[(1, 1)] < 0.005
    assert moved.topology["edges"] == original["edges"]
    for before, after in zip(original["faces"], moved.topology["faces"]):
        assert before["id"] == after["id"] and before["material"] == after["material"]
        assert [(c["id"], c["vertex"], c["uv"]) for c in before["corners"]] == [
            (c["id"], c["vertex"], c["uv"]) for c in after["corners"]
        ]
    at_boundary = topology.move_vertices(mesh, [center], [0, 0.5, 0], radius=1)
    assert all(
        v["position"] == old["position"]
        for old, v in zip(original["vertices"], at_boundary.topology["vertices"])
        if v["id"] != center
    )
    assert mesh.topology == original
    assert mesh_document.from_json(mesh_document.to_json(moved)).topology == moved.topology


def test_proportional_radius_uses_nearest_selected_point_not_centroid():
    mesh = primitives.build("Plane", {"width": 2, "depth": 2, "segments": 2})[0]
    selected = [
        v["id"] for v in mesh.topology["vertices"] if v["position"] in ([-1, 0, 0], [1, 0, 0])
    ]
    moved = topology.move_vertices(mesh, selected, [0, 0.5, 0], radius=0.8)
    center = next(
        v for v in moved.topology["vertices"] if v["position"][0] == 0 and v["position"][2] == 0
    )
    assert center["position"] == [0, 0, 0]
    assert sum(v["position"][1] == 0.5 for v in moved.topology["vertices"]) == 2


@pytest.mark.parametrize("radius", [-1, float("nan"), float("inf"), True])
def test_invalid_proportional_radius_is_atomic(radius):
    p = SimpleNamespace(kind="Mesh3D", name="Plane", props={}, mesh_kind="")
    mesh_document.bind(p, cube())
    topology.select(p, "vertices", ["v1"])
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError, match="radius"):
        topology.edit_selected(p, "move", offset=[0, 0.5, 0], radius=radius)
    assert p.__dict__ == before


def test_merge_cube_edge_preserves_winding_attributes_and_source():
    mesh = cube()
    doc = deepcopy(mesh.topology)
    for face in doc['faces']:
        face['material'] = 3
    mesh = topology.compile(doc)[0]
    before = mesh_document.to_json(mesh)
    chosen = [v['id'] for v in doc['vertices'] if v['position'][1:] == [1, -1]]
    merged, survivor = topology.merge_center(mesh, chosen)
    result = merged.topology
    assert [len(result[k]) for k in ('vertices', 'edges', 'faces')] == [7, 11, 6]
    assert sorted(len(f['corners']) for f in result['faces']) == [3, 3, 4, 4, 4, 4]
    assert next(v['position'] for v in result['vertices'] if v['id'] == survivor) == [0, 1, -1]
    assert all(f['material'] == 3 for f in result['faces'])
    assert {f['id'] for f in result['faces']} == {f['id'] for f in doc['faces']}
    corners = {c['id']: c for f in doc['faces'] for c in f['corners']}
    assert all(c['uv'] == corners[c['id']]['uv'] for f in result['faces'] for c in f['corners'])
    uses = topology.edge_usage(result)
    assert all(len(u) == 2 for u in uses.values())
    assert signed_volume(merged) > 0
    assert mesh_document.to_json(mesh) == before


def test_merge_all_preserves_single_loose_point_and_named_part():
    mesh = cube()
    merged, survivor = topology.merge_center(mesh, [v['id'] for v in mesh.topology['vertices']])
    assert merged.topology['schema_version'] == 2
    assert merged.topology['edges'] == merged.topology['faces'] == []
    assert merged.topology['vertices'][0]['id'] == survivor
    np.testing.assert_array_equal(merged.verts, [[0, 0, 0]])
    restored = mesh_document.from_json(mesh_document.to_json(merged))
    assert restored.topology == merged.topology


def test_merge_duplicate_wires_unions_edge_flags():
    mesh = cube()
    mesh = topology.delete_components(mesh, 'faces', [f['id'] for f in mesh.topology['faces']])
    points = []
    for p in ([0, 0, 0], [2, 0, 0], [1, 1, 0]):
        mesh, identity = topology.add_vertex(mesh, p)
        points.append(identity)
    mesh, first = topology.connect_vertices(mesh, [points[0], points[2]])
    mesh, _second = topology.connect_vertices(mesh, [points[1], points[2]])
    doc = deepcopy(mesh.topology)
    doc['edges'][0]['seam'] = True
    doc['edges'][1]['sharp'] = True
    merged, survivor = topology.merge_center(topology.compile(doc)[0], points[:2])
    assert len(merged.topology['edges']) == 1
    edge = merged.topology['edges'][0]
    assert edge['id'] == first and edge['seam'] and edge['sharp']
    assert set(edge['vertices']) == {survivor, points[2]}


def test_merge_pinched_polygon_rejects_atomically():
    mesh = primitives.build('Plane', {'width': 2, 'depth': 2, 'segments': 1})[0]
    vertices = mesh.topology['vertices']
    ids = [v['id'] for v in vertices if v['position'][0] == v['position'][2]]
    p = SimpleNamespace(kind='Mesh3D', name='Plane', props={}, mesh_kind='')
    mesh_document.bind(p, mesh, label='Plane')
    topology.select(p, 'vertices', ids)
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match='pinch'):
        topology.edit_selected(p, 'merge_center')
    assert vars(p) == before


@pytest.mark.parametrize('identities', [[], ['v1'], ['v1', 'v99999']])
def test_merge_rejects_insufficient_or_stale_selection(identities):
    with pytest.raises(ValueError, match='at least two existing'):
        topology.merge_center(cube(), identities)


@pytest.mark.parametrize('operation,values,expected', [
    ('rotate', [0, 90, 0], [[-1, 1, -1], [-1, 1, 1], [1, 1, -1], [1, 1, 1]]),
    ('scale', [.5, 1, 2], [[-.5, 1, -2], [-.5, 1, 2], [.5, 1, -2], [.5, 1, 2]]),
])
def test_component_transform_uses_selected_center_and_preserves_other_vertices(operation, values, expected):
    mesh = cube()
    chosen = [v['id'] for v in mesh.topology['vertices'] if v['position'][1] == 1]
    original = mesh_document.to_json(mesh)
    result = topology.transform_vertices(mesh, chosen, operation, values)
    selected = sorted(v['position'] for v in result.topology['vertices'] if v['id'] in chosen)
    # Round only for ordering of +/-90 degree trigonometric near-equalities.
    np.testing.assert_allclose(sorted(np.round(selected, 10).tolist()), expected, atol=1e-12)
    before = {v['id']:v for v in mesh.topology['vertices']}
    assert all(v == before[v['id']] for v in result.topology['vertices'] if v['id'] not in chosen)
    assert result.topology['edges'] == mesh.topology['edges']
    assert mesh_document.to_json(mesh) == original


def test_proportional_rotation_weights_angles_and_preserves_radial_distance():
    mesh = cube()
    mesh = topology.delete_components(mesh, 'faces', [f['id'] for f in mesh.topology['faces']])
    chosen = []
    for position in ([-1,0,0], [1,0,0], [0,1,0]):
        mesh, identity = topology.add_vertex(mesh, position)
        chosen.append(identity)
    result = topology.transform_vertices(mesh, chosen[:2], 'rotate', [0,0,90], radius=3)
    probe = result.topology['vertices'][2]['position']
    t = 1 - np.sqrt(2) / 3
    theta = np.pi/2 * t*t*(3-2*t)
    np.testing.assert_allclose(probe, [-np.sin(theta), np.cos(theta), 0], atol=1e-12)
    assert np.linalg.norm(probe) == pytest.approx(1)


def test_zero_scale_collapse_rejects_before_mesh_binding():
    p = SimpleNamespace(kind='Mesh3D', name='Cube', props={}, mesh_kind='')
    mesh = cube()
    mesh_document.bind(p, mesh, label='Cube')
    topology.select(p, 'faces', [f['id'] for f in mesh.topology['faces']])
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match='zero area|degenerate'):
        topology.edit_selected(p, 'scale', scale=[0,0,0])
    assert vars(p) == before


def test_dissolve_planar_region_preserves_boundary_ids_and_corner_uvs():
    mesh = primitives.build('Plane', {'width':2, 'depth':2, 'segments':2})[0]
    original = mesh_document.to_json(mesh)
    usage = topology.edge_usage(mesh.topology)
    ids = [e['id'] for e in mesh.topology['edges'] if len(usage[tuple(sorted(e['vertices']))]) == 2]
    result, joined = topology.dissolve_edges(mesh, ids)
    doc = result.topology
    assert [len(doc[k]) for k in ('vertices','edges','faces')] == [8,8,1]
    assert joined == [mesh.topology['faces'][0]['id']]
    assert len(doc['faces'][0]['corners']) == 8
    corners = {c['id']:c for f in mesh.topology['faces'] for c in f['corners']}
    assert all(c['uv'] == corners[c['id']]['uv'] for c in doc['faces'][0]['corners'])
    assert {e['id'] for e in doc['edges']} == {e['id'] for e in mesh.topology['edges']} - set(ids)
    assert mesh_document.to_json(mesh) == original
    assert mesh_document.from_json(mesh_document.to_json(result)).topology == doc


def test_dissolve_single_edge_retains_unaffected_polygons_and_orphan_wires():
    mesh = primitives.build('Plane', {'width':2, 'depth':2, 'segments':2})[0]
    usage = topology.edge_usage(mesh.topology)
    seed = next(e['id'] for e in mesh.topology['edges'] if len(usage[tuple(sorted(e['vertices']))]) == 2)
    mesh, first = topology.add_vertex(mesh, [5,0,0])
    mesh, second = topology.add_vertex(mesh, [6,0,0])
    mesh, wire = topology.connect_vertices(mesh, [first, second])
    result, joined = topology.dissolve_edges(mesh, [seed])
    assert [len(result.topology[k]) for k in ('vertices','edges','faces')] == [11,12,3]
    assert sorted(len(f['corners']) for f in result.topology['faces']) == [4,4,6]
    assert any(e['id'] == wire for e in result.topology['edges'])
    before = {f['id']:f for f in mesh.topology['faces']}
    assert all(f == before[f['id']] for f in result.topology['faces'] if f['id'] not in joined)


@pytest.mark.parametrize('case', ['boundary','nonplanar','material'])
def test_dissolve_invalid_regions_reject_atomically(case):
    mesh = cube() if case == 'nonplanar' else primitives.build('Plane', {'width':2,'depth':2,'segments':2})[0]
    doc = deepcopy(mesh.topology)
    if case == 'material':
        for i,f in enumerate(doc['faces']):
            f['material'] = i
    mesh = topology.compile(doc)[0]
    usage = topology.edge_usage(doc)
    seed = next(e['id'] for e in doc['edges'] if len(usage[tuple(sorted(e['vertices']))]) == (1 if case == 'boundary' else 2))
    p = SimpleNamespace(kind='Mesh3D', name='Dissolve', props={}, mesh_kind='')
    mesh_document.bind(p, mesh, label='Dissolve')
    topology.select(p, 'edges', [seed])
    before = deepcopy(vars(p))
    with pytest.raises(ValueError):
        topology.edit_selected(p, 'dissolve_edges')
    assert vars(p) == before


def test_center_loop_cut_cube_preserves_volume_and_watertight_winding():
    mesh = cube()
    doc = mesh.topology
    points = {v['id']:v['position'] for v in doc['vertices']}
    seed = next(e['id'] for e in doc['edges'] if all(points[v][0] == -1 and points[v][2] == -1 for v in e['vertices']))
    original = mesh_document.to_json(mesh)
    result, selected = topology.loop_cut(mesh, [seed])
    assert [len(result.topology[k]) for k in ('vertices','edges','faces')] == [12,20,10]
    assert len(selected) == 4
    points = {v['id']:v['position'] for v in result.topology['vertices']}
    assert all(points[v][1] == 0 for e in result.topology['edges'] if e['id'] in selected for v in e['vertices'])
    assert all(len(f['corners']) == 4 for f in result.topology['faces'])
    assert signed_volume(result) == pytest.approx(8)
    assert all(len(u) == 2 and u[0] == u[1][::-1] for u in topology.edge_usage(result.topology).values())
    assert mesh_document.to_json(mesh) == original
    assert mesh_document.from_json(mesh_document.to_json(result)).topology == result.topology


def test_loop_cut_interpolates_uvs_and_inherits_edge_flags():
    mesh = primitives.build('Plane', {'width':2,'depth':2,'segments':1})[0]
    doc = deepcopy(mesh.topology)
    doc['edges'][0]['seam'] = doc['edges'][0]['sharp'] = True
    doc['faces'][0]['material'] = 3
    for corner, uv in zip(doc['faces'][0]['corners'], [[0,0],[1,0],[1,1],[0,1]]):
        corner['uv'] = uv
        corner['normal'] = [0,1,0]
    mesh = topology.compile(doc)[0]
    result, selected = topology.loop_cut(mesh, [doc['edges'][0]['id']])
    assert [len(result.topology[k]) for k in ('vertices','edges','faces')] == [6,7,2]
    assert len(selected) == 1
    assert sum(e['seam'] and e['sharp'] for e in result.topology['edges']) == 2
    assert all(f['material'] == 3 for f in result.topology['faces'])
    old = {c['id']:c for c in doc['faces'][0]['corners']}
    corners = [c for f in result.topology['faces'] for c in f['corners']]
    assert all(c == old[c['id']] for c in corners if c['id'] in old)
    assert len([c for c in corners if c['id'] not in old]) == 4
    assert all(.5 in c['uv'] for c in corners if c['id'] not in old)


def test_loop_cut_crosses_bounded_quad_strip_without_t_junctions():
    mesh = primitives.build('Plane', {'width':2,'depth':2,'segments':2})[0]
    points = {v['id']:v['position'] for v in mesh.topology['vertices']}
    seed = next(e['id'] for e in mesh.topology['edges'] if all(points[v] in [[0,0,-1],[0,0,0]] for v in e['vertices']))
    result, selected = topology.loop_cut(mesh, [seed])
    assert [len(result.topology[k]) for k in ('vertices','edges','faces')] == [12,17,6]
    assert len(selected) == 2
    assert all(len(f['corners']) == 4 for f in result.topology['faces'])
    assert len(topology.loose_edges(result.topology)) == 0


def test_loop_cut_rejects_triangle_strip_without_mutation():
    mesh = primitives.build('Cone', {'radius':1,'height':2,'segments':8})[0]
    p = SimpleNamespace(kind='Mesh3D', name='Cone', props={}, mesh_kind='')
    mesh_document.bind(p, mesh, label='Cone')
    topology.select(p, 'edges', [mesh.topology['edges'][0]['id']])
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match='quad'):
        topology.edit_selected(p, 'loop_cut')
    assert vars(p) == before
