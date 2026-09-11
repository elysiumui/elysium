"""Validated constant color DAGs for retained native material surfaces."""

import math
from copy import deepcopy

import numpy as np

KINDS = ("Color", "Value", "Add", "Multiply", "Mix")


def empty():
    return {"schema_version": 1, "next_id": 1, "nodes": [], "output": None}


def evaluate(graph):
    if (
        not isinstance(graph, dict)
        or set(graph) != {"schema_version", "next_id", "nodes", "output"}
        or type(graph["schema_version"]) is not int
        or graph["schema_version"] != 1
        or type(graph["next_id"]) is not int
        or graph["next_id"] < 1
        or not isinstance(graph["nodes"], list)
        or len(graph["nodes"]) > 64
    ):
        raise ValueError("Invalid material color graph")
    nodes = {}
    for node in graph["nodes"]:
        if not isinstance(node, dict) or set(node) != {"id", "name", "kind", "value", "inputs"}:
            raise ValueError("Invalid color node fields")
        nid = node["id"]
        if (
            not isinstance(nid, str)
            or not nid.startswith("n")
            or not nid[1:].isascii()
            or not nid[1:].isdigit()
            or nid[1:][:1] == "0"
            or not 0 < int(nid[1:]) < graph["next_id"]
            or nid in nodes
        ):
            raise ValueError("Invalid or duplicate color node identity")
        if not isinstance(node["name"], str) or not node["name"].strip() or len(node["name"]) > 100:
            raise ValueError("Node name requires 1–100 nonblank characters")
        kind = node["kind"]
        if kind not in KINDS:
            raise ValueError("Unknown material color node kind")
        value = node["value"]
        if kind == "Color":
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("Color node requires three linear RGB components")
            values = value
        else:
            values = [value]
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values
        ):
            raise ValueError("Node values require finite numbers from 0 to 1")
        inputs = node["inputs"]
        if (
            not isinstance(inputs, dict)
            or set(inputs) - ({"a", "b"} if kind in ("Add", "Multiply", "Mix") else set())
            or any(not isinstance(v, str) for v in inputs.values())
        ):
            raise ValueError("Invalid color node inputs")
        nodes[nid] = node
    if graph["output"] is not None and (
        not isinstance(graph["output"], str) or graph["output"] not in nodes
    ):
        raise ValueError("Color output references a missing node")
    resolved, visiting = {}, set()

    def value(nid):
        if nid in resolved:
            return resolved[nid]
        if nid not in nodes:
            raise ValueError("Color input references a missing node")
        if nid in visiting:
            raise ValueError("Material color graph cannot contain a cycle")
        visiting.add(nid)
        n = nodes[nid]
        kind = n["kind"]
        if kind in ("Color", "Value"):
            out = np.asarray(n["value"], dtype=float)
        else:
            a = value(n["inputs"]["a"]) if "a" in n["inputs"] else np.zeros(3)
            b = value(n["inputs"]["b"]) if "b" in n["inputs"] else np.ones(3)
            out = (
                a + b
                if kind == "Add"
                else a * b
                if kind == "Multiply"
                else a * (1 - n["value"]) + b * n["value"]
            )
        out = np.clip(out, 0, 1)
        visiting.remove(nid)
        resolved[nid] = out
        return out

    for nid in nodes:
        value(nid)
    return (
        None
        if graph["output"] is None
        else np.broadcast_to(resolved[graph["output"]], (3,)).tolist()
    )


def add(graph, kind):
    result = deepcopy(graph)
    evaluate(result)
    if kind not in KINDS or len(result["nodes"]) >= 64:
        raise ValueError("Choose a supported node; maximum 64 nodes")
    nid = f"n{result['next_id']}"
    result["next_id"] += 1
    result["nodes"].append(
        {
            "id": nid,
            "kind": kind,
            "name": f"{kind} {nid[1:]}",
            "value": [0.5, 0.5, 0.5] if kind == "Color" else 0.5 if kind in ("Value", "Mix") else 0,
            "inputs": {},
        }
    )
    evaluate(result)
    return result, nid


def update(graph, nid, *, name=None, value=None, inputs=None):
    result = deepcopy(graph)
    evaluate(result)
    node = next((n for n in result["nodes"] if n["id"] == nid), None)
    if node is None:
        raise ValueError("Color node no longer exists")
    if name is not None:
        node["name"] = name
    if value is not None:
        node["value"] = deepcopy(value)
    if inputs is not None:
        node["inputs"] = deepcopy(inputs)
    evaluate(result)
    return result


def output(graph, nid):
    result = deepcopy(graph)
    result["output"] = nid
    evaluate(result)
    return result


def remove(graph, nid):
    result = deepcopy(graph)
    evaluate(result)
    if not any(n["id"] == nid for n in result["nodes"]):
        raise ValueError("Color node no longer exists")
    result["nodes"] = [n for n in result["nodes"] if n["id"] != nid]
    for node in result["nodes"]:
        node["inputs"] = {k: v for k, v in node["inputs"].items() if v != nid}
    if result["output"] == nid:
        result["output"] = None
    evaluate(result)
    return result
