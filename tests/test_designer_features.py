"""Tests for the Phase 11 / 13 / 14 / 17 / 19 Designer feature
roadmap items shipped in the "complete the roadmap" pass:

  * Curves (Phase 14): trim, blend, rebuild
  * Motion paths (Phase 11): attach to NURBSCurve
  * Sim (Phase 17): cache + reset
  * Rigging extras (Phase 19): orient joint, pole-vector constraint
  * Deformers (Phase 17): flare / squash / wave

Tests skip the OS-window machinery via the ``object.__new__`` trick
used elsewhere in the suite, then drive each feature method directly
and assert the post-condition (placement state mutated / Mesh
re-registered / status message readable).
"""
from __future__ import annotations

import math
import pathlib
import sys

import pytest


def _load_designer_module():
    sys.path.insert(0, "elysium-designer")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "elysium_designer_main_feat",
        "elysium-designer/__main__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("elysium_designer_main_feat", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def designer_mod():
    return _load_designer_module()


def _make_designer(designer_mod, tmp_path):
    d = object.__new__(designer_mod.Designer)
    d.placements = []
    d.sel_kind = "none"
    d.sel_idx = -1
    d.sel_set = set()
    d.menu_status = ""
    d._undo_stack = []
    d._redo_stack = []
    d._undo_limit = 100
    d._name_counters = {}
    # The bare object.__new__ instance lacks the full window_doc /
    # landmark / pending-state graph required by _snapshot.  These
    # tests are about feature mutations, not undo semantics, so we
    # stub the undo entry-point.
    d._push_undo = lambda *a, **k: None
    designer_mod._DESIGNER_PREFS_PATH = tmp_path / "designer-prefs.json"
    return d


def _make_curve(designer_mod, name: str,
                  points: list[tuple[float, float]],
                  origin: tuple[float, float] = (100.0, 100.0),
                  closed: bool = False):
    return designer_mod.Placement(
        kind="NURBSCurve",
        x=origin[0], y=origin[1],
        w=10.0, h=10.0,
        name=name,
        nurbs_points=list(points),
        nurbs_closed=closed,
    )


# ---------------------------------------------------------------------------
# Phase 14 — Curves
# ---------------------------------------------------------------------------


def test_trim_shrinks_control_points(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    pts = [(0.0, 0.0), (10.0, 5.0), (20.0, 0.0),
            (30.0, 5.0), (40.0, 0.0), (50.0, 5.0)]
    curve = _make_curve(designer_mod, "C", pts)
    d.placements = [curve]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._trim_selected_curve(t_start=0.2, t_end=0.8)
    assert len(curve.nurbs_points) < len(pts)
    assert len(curve.nurbs_points) >= 2


def test_trim_noop_when_not_a_curve(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    img = designer_mod.Placement(
        kind="Image", x=0, y=0, w=10, h=10, name="img")
    d.placements = [img]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._trim_selected_curve()
    assert "only works on NURBSCurve" in d.menu_status


def test_blend_adds_bridge_placement(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    c0 = _make_curve(designer_mod, "C0",
                      [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)])
    c1 = _make_curve(designer_mod, "C1",
                      [(50.0, 0.0), (60.0, 5.0), (70.0, 10.0)],
                      origin=(200.0, 100.0))
    d.placements = [c0, c1]
    d.sel_kind = "placement"
    d.sel_set = {0, 1}
    d._blend_selected_curves()
    # Bridge placement appended at index 2.
    assert len(d.placements) == 3
    assert d.placements[2].kind == "NURBSCurve"
    assert d.placements[2].name.startswith("BlendBridge")
    # Bridge has 4 control points (start → tangent → tangent → end).
    assert len(d.placements[2].nurbs_points) == 4


def test_blend_needs_two_curves(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    c0 = _make_curve(designer_mod, "C0",
                      [(0.0, 0.0), (10.0, 0.0)])
    d.placements = [c0]
    d.sel_kind = "placement"
    d.sel_set = {0}
    d._blend_selected_curves()
    # No bridge created.
    assert len(d.placements) == 1
    assert "exactly 2" in d.menu_status


def test_rebuild_resamples_to_target_n(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    # 12-point hand-authored curve → rebuild to 8 uniform CPs.
    pts = [(i * 5.0, math.sin(i * 0.3) * 5.0) for i in range(12)]
    curve = _make_curve(designer_mod, "C", pts)
    d.placements = [curve]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._rebuild_selected_curve(target_n=8)
    assert 5 <= len(curve.nurbs_points) <= 9


# ---------------------------------------------------------------------------
# Phase 11 — Motion paths
# ---------------------------------------------------------------------------


def test_motion_path_attaches_target_to_curve(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    curve = _make_curve(designer_mod, "C",
                         [(0.0, 0.0), (50.0, 0.0)])
    target = designer_mod.Placement(
        kind="Shape", x=0, y=0, w=20, h=20,
        name="follower", props={})
    d.placements = [curve, target]
    d.sel_kind = "placement"
    d.sel_set = {0, 1}
    d._attach_motion_path()
    assert "motion_path" in target.props
    assert target.props["motion_path"]["curve_name"] == "C"


def test_motion_path_needs_curve_and_target(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    c0 = _make_curve(designer_mod, "C", [(0, 0), (10, 0)])
    d.placements = [c0]
    d.sel_kind = "placement"
    d.sel_set = {0}
    d._attach_motion_path()
    # Only a curve  no non-curve target  status reflects the need.
    assert "need one NURBSCurve" in d.menu_status


# ---------------------------------------------------------------------------
# Phase 17 — Sim cache + reset
# ---------------------------------------------------------------------------


def test_sim_cache_snapshot_then_reset_restores(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(kind="Shape", x=0, y=0, w=20, h=20,
                                  name="P")
    p._t_dx = 0.0; p._t_dy = 0.0
    p._t_rotation = 0.0; p._t_scale = 1.0; p._t_opacity = 1.0
    d.placements = [p]
    d._simulate_cache()
    assert len(d._sim_cache) == 1
    assert d._sim_cache[0]["name"] == "P"
    # Mutate live state.
    p._t_dx = 50.0
    p._t_rotation = 1.5
    p._t_opacity = 0.3
    # Reset returns it to the snapshot.
    d._simulate_reset()
    assert p._t_dx == 0.0
    assert p._t_rotation == 0.0
    assert p._t_opacity == 1.0


def test_sim_reset_without_cache_returns_to_bind_pose(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(kind="Shape", x=0, y=0, w=20, h=20,
                                  name="P")
    # Give it at least one AnimState so the "bind pose" branch hits.
    state = designer_mod.AnimState(name="bind")
    p.states = [state]
    p.current_state = 1
    p._t_dx = 99.0
    p._t_dy = 88.0
    p._t_rotation = 0.7
    p._t_scale = 1.5
    p._t_opacity = 0.5
    d.placements = [p]
    d._sim_cache = None
    d._simulate_reset()
    assert p._t_dx == 0.0
    assert p._t_dy == 0.0
    assert p._t_rotation == 0.0
    assert p._t_scale == 1.0
    assert p._t_opacity == 1.0
    assert p.current_state == 0


# ---------------------------------------------------------------------------
# Phase 19 — Rigging extras
# ---------------------------------------------------------------------------


def test_orient_joint_rotates_toward_child(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    root = designer_mod.Placement(
        kind="Joint", x=100, y=100, w=24, h=24,
        name="Root", props={"joint_radius": 8.0})
    child = designer_mod.Placement(
        kind="Joint", x=140, y=160, w=24, h=24,
        name="Child", props={"joint_radius": 8.0})
    child.parent_name = "Root"
    d.placements = [root, child]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._orient_selected_joint()
    # Bone-length recorded.
    assert root.props.get("bone_length", 0) > 0
    # Rotation set non-zero  the root joint now faces its child.
    assert root._t_rotation != 0.0


def test_orient_joint_noop_when_no_child(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    root = designer_mod.Placement(
        kind="Joint", x=100, y=100, w=24, h=24,
        name="Root", props={"joint_radius": 8.0})
    d.placements = [root]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._orient_selected_joint()
    assert "no child joint" in d.menu_status


def test_pole_vector_records_anchor(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    j = designer_mod.Placement(
        kind="Joint", x=200, y=300, w=24, h=24,
        name="Mid", props={"joint_radius": 8.0})
    d.placements = [j]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._pole_vector_constraint()
    assert "pole_vector" in j.props
    pole = j.props["pole_vector"]
    assert pole[0] == pytest.approx(212.0)   # x + w/2
    assert pole[1] == pytest.approx(312.0)   # y + h/2


# ---------------------------------------------------------------------------
# Phase 17 — Deformer extensions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind, axis",
                         [("flare", "y"), ("flare", "x"),
                          ("squash", "y"), ("squash", "z"),
                          ("wave", "y"), ("wave", "x")])
def test_extended_deformers_modify_mesh(designer_mod, tmp_path,
                                          kind, axis):
    """Each new deformer (flare / squash / wave) must read the
    source mesh, produce a new mesh, register it, and re-point the
    placement at the new name."""
    pytest.importorskip("numpy")
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(
        kind="Mesh3D", x=0, y=0, w=100, h=100,
        name="M", mesh_kind="cube")
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    # The deformer applies if the mesh library has a "Cube" entry.
    from elysium.render import pbr as _pbr
    if not any(k.lower() == "cube" for k in _pbr.MESH_LIBRARY):
        pytest.skip("MESH_LIBRARY missing 'cube' entry on this build")
    d._apply_deformer(kind, 0.6, axis)
    # New mesh-kind name should differ from "cube".
    assert p.mesh_kind != "cube"
    # The new name carries the deformer's kind prefix.
    assert kind.title() in p.mesh_kind


# ---------------------------------------------------------------------------
# Phase 17 — Modal-editor deformers (lattice / cluster / wire / wrap /
# shrinkwrap / jiggle / softmod / nonlinear / blendshape)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind",
                         ["lattice", "cluster", "wire", "wrap",
                          "shrinkwrap", "jiggle", "softmod",
                          "nonlinear", "blendshape"])
def test_modal_deformer_open_editor_applies_default(designer_mod,
                                                       tmp_path, kind):
    """Opening a modal deformer's editor must lazy-init the editor
    state, apply the deformer at the default amount, and produce a
    fresh mesh-kind name."""
    pytest.importorskip("numpy")
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(
        kind="Mesh3D", x=0, y=0, w=100, h=100,
        name="M", mesh_kind="cube")
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    from elysium.render import pbr as _pbr
    if not any(k.lower() == "cube" for k in _pbr.MESH_LIBRARY):
        pytest.skip("MESH_LIBRARY missing 'cube' entry on this build")
    d._open_deformer_editor(kind)
    # Editor state recorded with kind + default amount + open flag.
    assert hasattr(d, "_deformer_editors")
    entry = d._deformer_editors.get(kind)
    assert entry is not None
    assert entry["open"] is True
    assert entry["kind"] == kind
    assert 0.0 < entry["amount"] <= 1.0
    # Deformer was applied — mesh-kind moved away from "cube".
    assert p.mesh_kind != "cube"
    # The new name carries the deformer's kind prefix.
    assert kind.title() in p.mesh_kind


def test_scrub_deformer_editor_reapplies(designer_mod, tmp_path):
    pytest.importorskip("numpy")
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(
        kind="Mesh3D", x=0, y=0, w=100, h=100,
        name="M", mesh_kind="cube")
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    from elysium.render import pbr as _pbr
    if not any(k.lower() == "cube" for k in _pbr.MESH_LIBRARY):
        pytest.skip("MESH_LIBRARY missing 'cube' entry on this build")
    d._open_deformer_editor("cluster")
    first_kind = p.mesh_kind
    d._scrub_deformer_editor("cluster", 0.9, axis="x")
    # Second application produces a new mesh-kind name (counter ticks).
    assert p.mesh_kind != first_kind
    assert d._deformer_editors["cluster"]["amount"] == pytest.approx(0.9)
    assert d._deformer_editors["cluster"]["axis"] == "x"


def test_close_deformer_editor(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._deformer_editors = {"jiggle": {"open": True, "kind": "jiggle",
                                         "amount": 0.5, "axis": "y"}}
    d._close_deformer_editor("jiggle")
    assert d._deformer_editors["jiggle"]["open"] is False


# ---------------------------------------------------------------------------
# Phase 19 — Modal rigging editors
# ---------------------------------------------------------------------------


def test_skin_weights_editor_requires_skinned_mesh(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._open_skin_weights_editor()
    assert "select a skinned Mesh3D" in d.menu_status


def test_skin_weights_editor_populates_rows(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(
        kind="Mesh3D", x=0, y=0, w=100, h=100,
        name="M", mesh_kind="cube")
    p.skin_joints = ["J0", "J1"]
    p.skin_weights = [[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]]
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._open_skin_weights_editor()
    se = d.skin_weights_editor
    assert se["open"] is True
    assert se["mesh_name"] == "M"
    assert se["joints"] == ["J0", "J1"]
    assert len(se["rows"]) == 3
    assert se["rows"][1]["J0"] == pytest.approx(0.5)


def test_skin_weights_set_normalises_row(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(
        kind="Mesh3D", x=0, y=0, w=100, h=100,
        name="M", mesh_kind="cube")
    p.skin_joints = ["J0", "J1"]
    p.skin_weights = [[1.0, 0.0]]
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._open_skin_weights_editor()
    d._set_skin_weight(0, "J1", 1.0)
    # Row must sum to 1.0 after the edit (renormalised across both
    # joints, so J0=0.5 + J1=0.5 since both were 1.0 pre-norm).
    assert sum(p.skin_weights[0]) == pytest.approx(1.0)
    assert p.skin_weights[0][0] == pytest.approx(0.5)
    assert p.skin_weights[0][1] == pytest.approx(0.5)


def test_shape_editor_creates_target(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = designer_mod.Placement(
        kind="Mesh3D", x=0, y=0, w=100, h=100,
        name="M", mesh_kind="cube")
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._open_shape_editor()
    assert d.shape_editor["open"] is True
    idx = d._add_blend_shape_target("Smile")
    assert idx == 0
    assert d.shape_editor["targets"][0]["name"] == "Smile"
    d._set_blend_shape_weight(0, 0.7)
    assert d.shape_editor["targets"][0]["weight"] == pytest.approx(0.7)


def test_pose_editor_save_and_apply(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    j = designer_mod.Placement(
        kind="Joint", x=100, y=100, w=24, h=24,
        name="J", props={"joint_radius": 8.0})
    j._t_rotation = 1.2
    d.placements = [j]
    d._open_pose_editor()
    idx = d._save_current_pose("StandTall")
    assert idx == 0
    assert d.pose_editor["poses"][0]["name"] == "StandTall"
    # Mutate then recall.
    j._t_rotation = 0.0
    j.x = 200
    d._apply_pose(0)
    assert j._t_rotation == pytest.approx(1.2)
    assert j.x == pytest.approx(100)


def test_humanik_auto_binds_by_name(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    head = designer_mod.Placement(
        kind="Joint", x=100, y=100, w=24, h=24,
        name="Head", props={"joint_radius": 8.0})
    neck = designer_mod.Placement(
        kind="Joint", x=100, y=120, w=24, h=24,
        name="Neck", props={"joint_radius": 8.0})
    d.placements = [head, neck]
    d._open_humanik_editor()
    assert d.humanik["open"] is True
    assert d.humanik["bindings"].get("head") == "Head"
    assert d.humanik["bindings"].get("neck") == "Neck"


def test_humanik_bind_region(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._open_humanik_editor()
    d._bind_humanik_region("spine", "MySpineJoint")
    assert d.humanik["bindings"]["spine"] == "MySpineJoint"
    d._bind_humanik_region("eyebrow", "X")
    assert "unknown region" in d.menu_status


# ---------------------------------------------------------------------------
# G11 — XGen / Bifrost procedural primitives
# ---------------------------------------------------------------------------


def test_create_xgen_fur(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    # _form_rect needs minimal state — stub it.
    d._form_rect = lambda: (0.0, 0.0, 800.0, 600.0)
    d._create_xgen_fur()
    assert len(d.placements) == 1
    p = d.placements[0]
    assert p.kind == "XGenFur"
    assert "density" in p.props
    assert p.props["density"] > 0


def test_create_bifrost_particles(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._form_rect = lambda: (0.0, 0.0, 800.0, 600.0)
    d._create_bifrost_particles()
    p = d.placements[0]
    assert p.kind == "BifrostParticles"
    assert p.props["particle_count"] > 0
    assert p.props["lifetime"] > 0


def test_create_bifrost_fluid(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._form_rect = lambda: (0.0, 0.0, 800.0, 600.0)
    d._create_bifrost_fluid()
    p = d.placements[0]
    assert p.kind == "BifrostFluid"
    assert p.props["viscosity"] > 0
    assert p.props["density"] > 0
