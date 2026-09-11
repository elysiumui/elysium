from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import material_graph as graph
from elysium.render import mesh_document, mesh_materials, primitives, scene


def mixed():
    g, a = graph.add(graph.empty(), "Color")
    g = graph.update(g, a, value=[1, 0, 0])
    g, b = graph.add(g, "Color")
    g = graph.update(g, b, value=[0, 0, 1])
    g, c = graph.add(g, "Mix")
    g = graph.update(g, c, value=0.25, inputs={"a": a, "b": b})
    return graph.output(g, c), a, b, c


def test_mix_dag_output_and_remove_fallbacks():
    g, _a, b, c = mixed()
    assert graph.evaluate(g) == [0.75, 0, 0.25]
    g = graph.remove(g, b)
    assert graph.evaluate(g) == [1, 0.25, 0.25]
    g = graph.remove(g, c)
    assert graph.evaluate(g) is None
    g, n = graph.add(g, "Value")
    assert n == "n4"
    g = graph.update(g, n, value=0.8)
    assert graph.evaluate(graph.output(g, n)) == [0.8] * 3


@pytest.mark.parametrize("kind,expected", [("Add", [1, 0.5, 1]), ("Multiply", [0.4, 0, 0])])
def test_arithmetic_broadcasts_and_clamps(kind, expected):
    g, a = graph.add(graph.empty(), "Color")
    g = graph.update(g, a, value=[0.8, 0, 0])
    g, b = graph.add(g, "Color")
    g = graph.update(g, b, value=[0.5, 0.5, 1])
    g, c = graph.add(g, kind)
    g = graph.update(g, c, inputs={"a": a, "b": b})
    assert graph.evaluate(graph.output(g, c)) == expected


@pytest.mark.parametrize(
    "failure",
    [
        "cycle",
        "missing",
        "nan",
        "bool",
        "out_of_range",
        "wrong_vector",
        "duplicate",
        "unknown_port",
        "bad_output",
    ],
)
def test_rejects_invalid_and_disconnected_graphs_atomically(failure):
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cube")
    primitives.bind(p, "Cube")
    slot = mesh_materials.add(p)["slot_id"]
    g, a, _b, c = mixed()
    mesh_materials.graph_set(p, slot, g)
    before = deepcopy(p.__dict__)
    bad = deepcopy(g)
    if failure == "cycle":
        bad["nodes"][2]["inputs"]["a"] = c
    elif failure == "missing":
        bad["nodes"][2]["inputs"]["b"] = "n999"
    elif failure in ("nan", "bool", "out_of_range", "wrong_vector"):
        bad["nodes"][0]["value"] = {
            "nan": [float("nan"), 0, 0],
            "bool": [True, 0, 0],
            "out_of_range": [2, 0, 0],
            "wrong_vector": [1, 0],
        }[failure]
    elif failure == "duplicate":
        bad["nodes"][1]["id"] = a
    elif failure == "unknown_port":
        bad["nodes"][2]["inputs"]["normal"] = a
    elif failure == "bad_output":
        bad["output"] = "n99"
    with pytest.raises(ValueError):
        mesh_materials.graph_set(p, slot, bad)
    assert p.__dict__ == before


def test_graph_drives_actual_scene_surface_and_only_assigned_faces():
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cube", entity_id="cube", visible=True)
    primitives.bind(p, "Cube")
    slot = mesh_materials.add(p)["slot_id"]
    g, *_ = mixed()
    mesh_materials.graph_set(p, slot, g)
    doc = mesh_document.resolve(p.mesh_kind).topology
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    face = next(
        f["id"] for f in doc["faces"] if all(points[c["vertex"]][2] > 0 for c in f["corners"])
    )
    mesh_materials.assign(p, [face], slot)
    obj, _ = scene.compose([p], materials=True)
    assert obj.materials[1].base_color == (0.75, 0, 0.25)
    assert np.count_nonzero(obj.mesh.face_mats == 1) == 2
    rgba, _ = scene.render(
        [p],
        48,
        48,
        yaw=0,
        pitch=0,
        projection="orthographic",
        ortho_scale=3,
        grid=False,
        shading="material",
    )
    color = np.frombuffer(rgba, np.uint8).reshape(48, 48, 4)[24, 24, :3].astype(int)
    assert color[0] > color[2] > color[1] + 30
    mesh_materials.graph_set(p, slot, graph.output(g, None))
    obj, _ = scene.compose([p], materials=True)
    assert np.allclose(obj.materials[1].base_color, [0.55] * 3)
