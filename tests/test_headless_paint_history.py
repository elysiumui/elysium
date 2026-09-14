"""Committed paint survives a rollback and rides the undo stack.

``paint_masks`` is keyed by ``id(placement)`` and ``_restore`` rebuilds
every Placement from JSON, so paint that a snapshot does not carry is
orphaned the moment the document is restored: a failed command used to
throw away paint an earlier *committed* command had made, and the
``/snapshot`` preview then rendered nothing for it.
"""
import hashlib
import tempfile
from pathlib import Path

import pytest
from _native_session import native_session  # noqa: F401
from elysium.render import designer_preview, pbr
from PIL import Image


@pytest.fixture
def painted(native_session, tmp_path, monkeypatch):
    """A committed Cube carrying a committed paint stamp."""
    d, _session, call = native_session
    cube = call("mesh.primitive_create", kind="Cube")["placement_id"]
    source = tmp_path / "red.png"
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(source)
    call("texture.stamp_region", id=cube, src=str(source))
    monkeypatch.setattr(pbr, "render_mesh",
                        lambda w, h, obj, env, **kw: b"\0" * (w * h * 4))
    return d, call, cube


def mask(d):
    return d.paint_masks.get(id(d.placements[0]))


def coverage(d):
    m = mask(d)
    return 0 if m is None else int(m.buf[..., 3].sum())


def preview_stamps_the_mask(d) -> bool:
    """True when the preview actually composited the placement's mask.

    ``designer_preview`` writes the mask it is about to draw to a cache
    file named by the buffer's digest, so the file appearing is proof the
    overlay reached the display list.
    """
    m = mask(d)
    assert m is not None
    digest = hashlib.md5(m.buf.tobytes()).hexdigest()[:14]
    stamp = Path(tempfile.gettempdir()) / "elysium-aether-snap" / f"pm-{digest}.png"
    stamp.unlink(missing_ok=True)
    designer_preview._MESH_CACHE.clear()
    designer_preview.paint_designer_png(d)
    return stamp.is_file()


def test_a_failed_command_does_not_discard_committed_paint(painted):
    d, call, _cube = painted
    before = coverage(d)
    assert before > 0 and preview_stamps_the_mask(d)
    call.expect_failure("scene.transform_set", id="no-such-placement",
                        transform={"location": [1, 2, 3]})
    assert coverage(d) == before
    assert preview_stamps_the_mask(d)


def test_paint_is_re_keyed_onto_the_placements_a_restore_rebuilds(painted):
    d, call, _cube = painted
    before = coverage(d)
    call.expect_failure("scene.transform_set", id="no-such-placement",
                        transform={"location": [1, 2, 3]})
    # The mask is found under the *new* placement object, and no mask is
    # left behind under the identity of the one that was replaced.
    assert list(d.paint_masks) == [id(d.placements[0])]
    assert list(d._brush_dirty) == [id(d.placements[0])]
    assert coverage(d) == before


def test_undo_and_redo_carry_the_paint_layer_with_the_document(painted):
    d, call, cube = painted
    stamped = coverage(d)
    call("scene.transform_set", id=cube, transform={"location": [1, 2, 3]})
    assert coverage(d) == stamped

    assert d.undo()                       # undo the transform
    assert coverage(d) == stamped
    assert preview_stamps_the_mask(d)
    assert d.redo()
    assert coverage(d) == stamped

    assert d.undo() and d.undo()          # transform, then the stamp itself
    assert coverage(d) == 0               # undoing the stamp removes the paint
    assert d.redo()
    assert coverage(d) == stamped
    assert preview_stamps_the_mask(d)


def test_removing_a_placement_and_undoing_it_brings_the_paint_back(painted):
    d, call, cube = painted
    stamped = coverage(d)
    call("placement.remove", id=cube)
    assert d.placements == []
    # Nothing orphaned rides along in the next checkpoint either.
    assert d._paint_snapshot() == {}
    assert d.undo()
    assert len(d.placements) == 1
    assert coverage(d) == stamped


# ---------------------------------------------------------------------------
# Snapshots must not re-deflate a mask nothing touched. `_snapshot` runs
# before every mutating command and on every undo/redo, so compressing each
# live mask unconditionally billed commands that never touch paint (measured
# 59 ms against 3 ms for one 2048x2048 mask) and gave every undo entry its own
# multi-megabyte copy of identical bytes.
# ---------------------------------------------------------------------------

def count_serialisations(monkeypatch):
    from elysium.render.texture import PaintMask
    calls = []
    original = PaintMask.to_bytes

    def counted(self):
        calls.append(id(self))
        return original(self)

    monkeypatch.setattr(PaintMask, "to_bytes", counted)
    return calls


def test_an_untouched_mask_is_compressed_once_and_shared(painted, monkeypatch):
    d, _call, _cube = painted
    assert coverage(d) > 0
    serialised = count_serialisations(monkeypatch)
    first = d._snapshot()["paint"]
    assert len(serialised) == 1
    records = [first, *(d._snapshot()["paint"] for _ in range(4))]
    assert len(serialised) == 1, "an unchanged mask was deflated again"
    entity = d.placements[0].entity_id
    # One immutable bytes object, so every history entry holding it costs
    # nothing extra rather than another copy of the same megabytes.
    assert len({id(r[entity]["data"]) for r in records}) == 1


def test_painting_again_produces_a_fresh_record(painted, monkeypatch):
    d, _call, _cube = painted
    entity = d.placements[0].entity_id
    before = d._snapshot()["paint"][entity]
    serialised = count_serialisations(monkeypatch)
    m = mask(d)
    m.stamp(float(m.w) / 2, float(m.h) / 2, 4.0, (0, 0, 255, 255))
    after = d._snapshot()["paint"][entity]
    assert len(serialised) == 1
    assert after["data"] != before["data"]
    # And the fresh record is what the mask actually holds.
    from elysium.render.texture import PaintMask
    rebuilt = PaintMask.from_bytes(after["data"], after["w"], after["h"])
    assert (rebuilt.buf == m.buf).all()


def test_the_memo_does_not_outlive_the_placement_it_belongs_to(painted):
    d, call, cube = painted
    entity = d.placements[0].entity_id
    assert entity in d._snapshot()["paint"]
    call("placement.remove", id=cube)
    assert d._snapshot()["paint"] == {}
    assert d._paint_digest_cache == {}
