"""Model-space dimensions and editable native primitive contracts."""

from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, pbr, primitives


@pytest.mark.parametrize(
    "kind,parameters,dimensions",
    [
        ("Cube", {"size": 3.25}, [3.25] * 3),
        ("Sphere", {"radius": 1.5}, [3.0] * 3),
        ("Cylinder", {"radius": 0.75, "height": 4}, [1.5, 4, 1.5]),
        ("Cone", {"radius": 0.75, "height": 4}, [1.5, 4, 1.5]),
        ("Plane", {"width": 3, "depth": 5}, [3, 0, 5]),
        ("Torus", {"major_radius": 2, "minor_radius": 0.5}, [5, 1, 5]),
    ],
)
def test_requested_dimensions_centering_and_valid_surface(kind, parameters, dimensions):
    mesh, values = primitives.build(kind, parameters)
    mesh_document.validate(mesh)
    np.testing.assert_allclose(np.ptp(mesh.verts, axis=0), dimensions, atol=1e-6)
    np.testing.assert_allclose(mesh.verts.max(axis=0) + mesh.verts.min(axis=0), 0, atol=1e-6)
    tri = mesh.verts[mesh.faces].astype(np.float64)
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    assert (np.linalg.norm(cross, axis=1) > 1e-10).all()
    if kind == "Plane":
        assert (cross[:, 1] > 0).all()
    else:
        assert np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() > 0
        _, inverse = np.unique(np.round(mesh.verts, 6), axis=0, return_inverse=True)
        edges = Counter(
            tuple(sorted((int(a), int(b))))
            for face in inverse[mesh.faces]
            for a, b in zip(face, np.roll(face, -1))
        )
        assert set(edges.values()) == {2}
    assert all(values[key] == value for key, value in parameters.items())


@pytest.mark.parametrize(
    "kind,params",
    [
        ("Cube", {"size": 0}),
        ("Sphere", {"rings": 2}),
        ("Cylinder", {"segments": 3.1}),
        ("Cone", {"height": float("nan")}),
        ("Plane", {"width": True}),
        ("Torus", {"minor_radius": 2}),
        ("Cube", {"missing": 1}),
    ],
)
def test_invalid_primitive_update_is_atomic(kind, params):
    p = SimpleNamespace(kind="Mesh3D", props={})
    primitives.bind(p, kind)
    before = deepcopy(p.__dict__)
    with pytest.raises((TypeError, ValueError)):
        primitives.update(p, params)
    assert p.__dict__ == before


def test_regeneration_never_discards_later_geometry_edits():
    p = SimpleNamespace(kind="Mesh3D", props={})
    primitives.bind(p, "Cube")
    mesh = mesh_document.resolve(p.mesh_kind)
    mesh_document.bind(p, mesh_document.with_vertices(mesh, mesh.verts * [1, 2, 1]))
    key = p.mesh_kind
    with pytest.raises(ValueError, match="after geometry editing"):
        primitives.update(p, {"size": 5})
    assert p.mesh_kind == key


def test_public_creation_schema_rejects_wrong_parameter_before_call():
    from elysium.aether.tools import REGISTRY
    from elysium.aether.types import ToolCall

    result = REGISTRY.dispatch(
        ToolCall("invalid", "mesh.primitive_create", {"kind": "Cube", "parameters": {"radius": 1}}),
        None,
    )
    assert not result.ok
    assert "Additional properties" in result.error


@pytest.mark.parametrize(
    "metadata",
    [
        {"kind": "Unknown", "parameters": {}},
        {"kind": "Cube", "parameters": {}},
        {"kind": "Cube", "parameters": {"size": "broken"}},
        {"kind": "Cube", "parameters": {"size": 0}},
    ],
)
def test_invalid_saved_metadata_does_not_break_inspector(metadata):
    p = SimpleNamespace(
        kind="Mesh3D",
        mesh_kind="mesh:test",
        props={"primitive": {**metadata, "mesh_key": "mesh:test"}},
    )
    assert primitives.settings(p) is None


def test_unchanged_parameters_preserve_geometry_identity():
    p = SimpleNamespace(kind="Mesh3D", props={})
    key = primitives.bind(p, "Cube")
    assert primitives.update(p, {"size": 2}) == key
    assert p.mesh_kind == key


@pytest.mark.parametrize(
    "kind,parameters,counts,sizes",
    [
        ("Cylinder", {"segments": 8}, (16, 24, 10), {4: 8, 8: 2}),
        ("Cone", {"segments": 8}, (9, 16, 9), {3: 8, 8: 1}),
        ("Plane", {"segments": 2}, (9, 12, 4), {4: 4}),
        ("Sphere", {"rings": 4, "segments": 8}, (26, 56, 32), {3: 16, 4: 16}),
        ("Torus", {"major_segments": 8, "minor_segments": 4}, (32, 64, 32), {4: 32}),
    ],
)
def test_authored_primitive_polygon_connectivity(kind, parameters, counts, sizes):
    mesh, _ = primitives.build(kind, parameters)
    doc = mesh.topology
    assert tuple(len(doc[k]) for k in ("vertices", "edges", "faces")) == counts
    assert dict(Counter(len(f["corners"]) for f in doc["faces"])) == sizes
    restored = mesh_document.from_json(mesh_document.to_json(mesh))
    assert restored.topology == doc


def test_cylinder_welded_source_preserves_uv_seam_and_separate_cap_normals():
    from elysium.render import topology

    mesh, _ = primitives.build("Cylinder", {"segments": 8})
    doc = mesh.topology
    first = doc["vertices"][0]["id"]
    corners = [c for f in doc["faces"] for c in f["corners"] if c["vertex"] == first]
    assert {tuple(c["uv"]) for c in corners} >= {(0.0, 0.0), (1.0, 0.0)}
    assert {tuple(c["normal"]) for c in corners} >= {(1.0, 0.0, 0.0), (0.0, -1.0, 0.0)}
    _, compiled_ids, _ = topology.compile(doc)
    assert compiled_ids.count(first) == 3
    # The source rim vertex moves as one component despite three render corners.
    moved = topology.move_vertices(mesh, [first], [0.1, 0, 0])
    _, ids, _ = topology.compile(moved.topology)
    np.testing.assert_allclose(moved.verts[np.array(ids) == first], [[1.1, -1, 0]] * 3)


@pytest.mark.parametrize(
    "kind,parameters,euler",
    [
        ("Sphere", {"rings": 4, "segments": 8}, 2),
        ("Torus", {"major_segments": 8, "minor_segments": 4}, 0),
    ],
)
def test_curved_polygon_primitives_close_seams_without_losing_corner_uvs(kind, parameters, euler):
    mesh, _ = primitives.build(kind, parameters)
    doc = mesh.topology
    assert len(doc["vertices"]) - len(doc["edges"]) + len(doc["faces"]) == euler
    usages = {}
    corner_uvs = {}
    for f in doc["faces"]:
        ids = [c["vertex"] for c in f["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            usages.setdefault(tuple(sorted((a, b))), []).append((a, b))
        for c in f["corners"]:
            corner_uvs.setdefault(c["vertex"], set()).add(tuple(c["uv"]))
    assert all(len(v) == 2 and v[0] == v[1][::-1] for v in usages.values())
    assert any(len(uvs) > 1 for uvs in corner_uvs.values())
    if kind == "Sphere":
        poles = [v for v in doc["vertices"] if abs(v["position"][1]) == 1]
        assert len(poles) == 2
        assert all(len(corner_uvs[v["id"]]) == parameters["segments"] for v in poles)


@pytest.mark.parametrize('segments', [3, 7, 8, 32])
def test_sphere_uvs_have_blender_orientation_and_polar_midpoints(segments):
    mesh, _ = primitives.build('Sphere', {'rings': 4, 'segments': segments})
    faces = mesh.topology['faces']
    for face in faces:
        coords = np.asarray([c['uv'] for c in face['corners']])
        assert np.ptp(coords[:, 0]) <= 1/segments + 1e-7
        if len(coords) == 3:
            pole = next(i for i, uv in enumerate(coords) if uv[1] in (0., 1.))
            others = np.delete(coords, pole, axis=0)
            assert coords[pole, 0] == pytest.approx(others[:, 0].mean(), abs=1e-7)
    first = faces[0]['corners']
    assert first[0]['uv'] == pytest.approx([.5-.5/segments, 1.])
    assert first[1]['uv'] == pytest.approx([.5-1/segments, .75])
    assert first[2]['uv'] == pytest.approx([.5, .75])


# ---------------------------------------------------------------------------
# NP-05: second cone radius, cap fill, geometry-hash regeneration lock.
# ---------------------------------------------------------------------------

from _native_session import native_session  # noqa: E402,F401


def _source_edges(mesh):
    usage = Counter()
    for face in mesh.topology["faces"]:
        ids = [c["vertex"] for c in face["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            usage[tuple(sorted((a, b)))] += 1
    return usage


def _signed_volume(mesh):
    tri = mesh.verts[mesh.faces].astype(np.float64)
    return np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6


def test_cone_second_radius_builds_watertight_frustum():
    n, r1, r2, h = 64, 1.0, 0.5, 2.0
    mesh, values = primitives.build("Cone", {"radius": r1, "radius2": r2, "height": h, "segments": n})
    assert values["radius2"] == r2 and values["cap_fill"] == "ngon"
    np.testing.assert_allclose(mesh.verts.min(axis=0), [-r1, -h / 2, -r1], atol=1e-6)
    np.testing.assert_allclose(mesh.verts.max(axis=0), [r1, h / 2, r1], atol=1e-6)
    top = mesh.verts[np.isclose(mesh.verts[:, 1], h / 2)]
    np.testing.assert_allclose(np.linalg.norm(top[:, [0, 2]], axis=1), r2, atol=1e-6)
    assert set(_source_edges(mesh).values()) == {2}
    assert dict(Counter(len(f["corners"]) for f in mesh.topology["faces"])) == {4: n, n: 2}
    volume = _signed_volume(mesh)
    exact = np.pi * h * (r1 * r1 + r1 * r2 + r2 * r2) / 3
    assert volume > 0 and abs(volume - exact) / exact < 0.02
    tri = mesh.verts[mesh.faces].astype(np.float64)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    assert (np.einsum("ij,ij->i", normals, tri.mean(axis=1)) > 0).all()


def test_pbr_cone_mesh_frustum_is_outward_and_validates_radii():
    frustum = pbr.cone_mesh(1.0, 2.0, 12, radius2=0.25)
    mesh_document.validate(frustum)
    assert len(frustum.verts) == 26 and len(frustum.faces) == 48
    tri = frustum.verts[frustum.faces].astype(np.float64)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    assert (np.einsum("ij,ij->i", normals, tri.mean(axis=1) - [0, 1, 0]) > 0).all()
    legacy = pbr.cone_mesh(1.0, 1.5, 18)
    np.testing.assert_array_equal(legacy.faces, pbr.MESH_LIBRARY["Cone"]().faces)
    for kwargs in ({"radius2": -1}, {"radius2": float("nan")}, {"radius": 0, "radius2": 0}, {"radius2": True}):
        with pytest.raises(ValueError):
            pbr.cone_mesh(**{"radius": 1.0, "height": 1.0, "segs": 8, **kwargs})


@pytest.mark.parametrize("cap_fill", ["ngon", "trifan", "nothing"])
@pytest.mark.parametrize(
    "kind,parameters,boundary",
    [
        ("Cone", {"segments": 8}, 8),
        ("Cone", {"segments": 8, "radius2": 0.5}, 16),
        ("Cylinder", {"segments": 8}, 16),
    ],
)
def test_cap_fill_variants(kind, parameters, boundary, cap_fill):
    n = parameters["segments"]
    mesh, values = primitives.build(kind, {**parameters, "cap_fill": cap_fill})
    assert values["cap_fill"] == cap_fill
    mesh_document.validate(mesh)
    usage = _source_edges(mesh)
    faces = Counter(len(f["corners"]) for f in mesh.topology["faces"])
    apex = kind == "Cone" and parameters.get("radius2", 0) == 0
    centres = [v for v in mesh.topology["vertices"] if abs(v["position"][0]) < 1e-9 and abs(v["position"][2]) < 1e-9]
    if cap_fill == "nothing":
        # Open ends: every rim edge is used once, nothing else changes.
        assert Counter(usage.values()) == {2: len(usage) - boundary, 1: boundary}
        assert dict(faces) == ({3: n} if apex else {4: n})
        assert len(centres) == (1 if apex else 0)  # only the apex itself survives
        assert _signed_volume(mesh) > 0
        return
    assert set(usage.values()) == {2}
    assert _signed_volume(mesh) > 0
    if cap_fill == "ngon":
        expected = {3: n, n: 1} if apex else {4: n, n: 2}
    elif apex:
        expected = {3: 2 * n}
    else:
        expected = {4: n, 3: 2 * n}
    assert dict(faces) == expected
    if cap_fill == "trifan":
        assert len(centres) == 2  # apex + base centre, or both cap centres
    restored = mesh_document.from_json(mesh_document.to_json(mesh))
    assert restored.topology == mesh.topology


def test_choice_parameters_validate_and_public_schema_exposes_enum():
    from elysium.aether.tools import REGISTRY
    from elysium.aether.tools.primitives import _parameter_schema
    from elysium.aether.types import ToolCall

    with pytest.raises(ValueError, match="cap_fill must be one of"):
        primitives.build("Cylinder", {"cap_fill": "hexagon"})
    with pytest.raises(TypeError, match="cap_fill must be one of"):
        primitives.build("Cone", {"cap_fill": 3})
    with pytest.raises(ValueError, match="unknown Cube parameters"):
        primitives.build("Cube", {"cap_fill": "ngon"})
    assert _parameter_schema("Cylinder")["properties"]["cap_fill"]["enum"] == ["ngon", "trifan", "nothing"]
    assert _parameter_schema("Cone")["properties"]["radius2"] == {"type": "number", "minimum": 0.0, "maximum": 1e6}
    assert "cap_fill" not in _parameter_schema("Cube")["properties"]
    result = REGISTRY.dispatch(
        ToolCall("bad-enum", "mesh.primitive_create", {"kind": "Cylinder", "parameters": {"cap_fill": "hexagon"}}),
        None,
    )
    assert not result.ok and "hexagon" in result.error


def test_non_geometry_publishes_keep_regeneration():
    from elysium.render import mesh_materials, mesh_normals, mesh_uv, topology

    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cyl", entity_id="cyl")
    first = primitives.bind(p, "Cylinder", {"segments": 8})
    mesh_uv.project(p, "planar_xy")
    assert p.mesh_kind != first and primitives.settings(p) is not None
    mesh_normals.set_policy(p, "smooth", angle=60)
    assert primitives.settings(p) is not None
    mesh_materials.add(p, "Red", {"base_color": [1, 0, 0]})
    assert primitives.settings(p) is not None
    regenerated = primitives.update(p, {"segments": 12})
    assert regenerated == p.mesh_kind
    assert len([f for f in mesh_document.resolve(regenerated).topology["faces"] if len(f["corners"]) == 4]) == 12
    source = mesh_document.resolve(p.mesh_kind)
    vertex = source.topology["vertices"][0]["id"]
    mesh_document.bind(p, topology.move_vertices(source, [vertex], [0.1, 0, 0]))
    assert primitives.settings(p) is None
    with pytest.raises(ValueError, match="after geometry editing"):
        primitives.update(p, {"segments": 6})


def test_regeneration_clears_stale_component_selection():
    from elysium.render import topology

    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cube", entity_id="cube")
    primitives.bind(p, "Cube")
    face = mesh_document.resolve(p.mesh_kind).topology["faces"][0]["id"]
    topology.select(p, "faces", [face])
    assert p.props["components3d"] == {"mode": "faces", "ids": [face]}
    primitives.update(p, {"size": 3})
    assert "components3d" not in p.props
    assert primitives.settings(p)["parameters"] == {"size": 3.0}


def test_legacy_metadata_without_geometry_hash_uses_mesh_key_rule():
    mesh = primitives.build("Cube")[0]
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cube")
    key = mesh_document.bind(p, mesh)
    p.props["primitive"] = {"kind": "Cube", "parameters": {"size": 2.0}, "mesh_key": key}
    assert primitives.settings(p)["parameters"] == {"size": 2.0}
    mesh_document.bind(p, mesh)  # Any rebind invalidates legacy metadata.
    assert primitives.settings(p) is None


def test_old_cone_metadata_without_radius2_still_regenerates():
    mesh = primitives.build("Cone", {"segments": 8})[0]
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cone")
    key = mesh_document.bind(p, mesh)
    p.props["primitive"] = {"kind": "Cone", "parameters": {"radius": 1.0, "height": 2.0, "segments": 8},
                            "mesh_key": key, "geometry_hash": mesh_document.geometry_hash(mesh)}
    current = primitives.settings(p)
    assert current["parameters"] == {"radius": 1.0, "radius2": 0.0, "height": 2.0, "segments": 8, "cap_fill": "ngon"}
    primitives.update(p, {"radius2": 0.5})
    assert primitives.settings(p)["parameters"]["radius2"] == 0.5
    assert len(mesh_document.resolve(p.mesh_kind).topology["faces"]) == 10


def test_parameter_metadata_round_trips_through_save_and_reopen(native_session):
    from elysium.aether import Session
    from elysium.aether._headless import MODELS, HeadlessDesigner

    d, session, call = native_session
    created = call("mesh.primitive_create", kind="Cone", parameters={"radius2": 0.5, "cap_fill": "trifan"})
    expected = {"radius": 1.0, "radius2": 0.5, "height": 2.0, "segments": 32, "cap_fill": "trifan"}
    assert created["parameters"] == expected
    read = call("mesh.primitive_parameters", id=created["placement_id"])["primitive"]
    assert read["parameters"] == expected and read["kind"] == "Cone"
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    fresh = Session(designer=reopened, designer_models=MODELS)
    p = reopened.placements[0]
    assert primitives.settings(p)["parameters"] == expected
    from elysium.aether.tools.primitives import primitive_parameters, primitive_update
    with mesh_document.using(reopened):
        assert primitive_parameters(fresh, fresh.id_for(p))["primitive"]["parameters"] == expected
        updated = primitive_update(fresh, fresh.id_for(p), {"segments": 8, "cap_fill": "ngon"})
    assert updated["parameters"] == {**expected, "segments": 8, "cap_fill": "ngon"}
    assert dict(Counter(len(f["corners"]) for f in mesh_document.resolve(p.mesh_kind, store=reopened.mesh_store).topology["faces"])) == {4: 8, 8: 2}


def test_primitive_update_undo_and_redo_through_persistent_dispatch(native_session):
    d, session, call = native_session
    cube = call("mesh.primitive_create", kind="Cube", parameters={"size": 2})["placement_id"]
    before = d._snapshot()
    call("mesh.primitive_update", id=cube, parameters={"size": 4})
    after = d._snapshot()
    assert primitives.settings(d.placements[0])["parameters"] == {"size": 4.0}
    d._restore(before)
    assert primitives.settings(d.placements[0])["parameters"] == {"size": 2.0}
    np.testing.assert_allclose(np.abs(mesh_document.resolve(d.placements[0].mesh_kind, store=d.mesh_store).verts), 1)
    d._restore(after)
    assert primitives.settings(d.placements[0])["parameters"] == {"size": 4.0}
    np.testing.assert_allclose(np.abs(mesh_document.resolve(d.placements[0].mesh_kind, store=d.mesh_store).verts), 2)


def test_duplicate_then_update_one_leaves_source_unchanged(native_session):
    d, session, call = native_session
    source = call("mesh.primitive_create", kind="Cube", parameters={"size": 2})["placement_id"]
    copy = call("placement.duplicate", id=source)["placement_id"]
    original_key = d.placements[0].mesh_kind
    assert d.placements[1].mesh_kind != original_key
    assert primitives.settings(d.placements[1]) is not None
    call("mesh.primitive_update", id=copy, parameters={"size": 5})
    assert d.placements[0].mesh_kind == original_key
    assert primitives.settings(d.placements[0])["parameters"] == {"size": 2.0}
    assert primitives.settings(d.placements[1])["parameters"] == {"size": 5.0}
    np.testing.assert_allclose(np.abs(mesh_document.resolve(original_key, store=d.mesh_store).verts), 1)


def test_failed_primitive_update_rolls_back_document_file_and_store(native_session):
    d, session, call = native_session
    cube = call("mesh.primitive_create", kind="Cube", parameters={"size": 2})["placement_id"]
    layout = d.skin_path / "designer_layout.json"
    saved = layout.read_bytes()
    keys = set(d.mesh_store.keys())
    key = d.placements[0].mesh_kind
    result = call.expect_failure("mesh.primitive_update", id=cube, parameters={"size": 0})
    assert "size must be between" in result.error
    assert layout.read_bytes() == saved
    assert set(d.mesh_store.keys()) == keys and d.placements[0].mesh_kind == key
    assert primitives.settings(d.placements[0])["parameters"] == {"size": 2.0}
