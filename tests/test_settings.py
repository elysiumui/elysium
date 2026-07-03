"""Tier-2 Phase-8: per-user settings (QSettings equivalent)."""
from __future__ import annotations

import json

from elysium.settings import Settings, config_dir


def _s(tmp_path, **kw):
    return Settings("testapp", path=tmp_path / "settings.json", **kw)


def test_roundtrip_persists_to_disk(tmp_path):
    s = _s(tmp_path)
    s.set("name", "Ada")
    s.set("count", 7)
    s.save()
    again = _s(tmp_path)
    assert again.get("name") == "Ada"
    assert again.get("count") == 7


def test_dotted_keys_form_groups(tmp_path):
    s = _s(tmp_path)
    s.set("window.size", [1200, 800])
    s.set("window.pos", [10, 20])
    s.save()
    raw = json.loads((tmp_path / "settings.json").read_text())
    assert raw["window"] == {"size": [1200, 800], "pos": [10, 20]}


def test_group_context_scopes_keys(tmp_path):
    s = _s(tmp_path)
    with s.group("palette"):
        s.set("recent", ["#f00"])
        assert s.get("recent") == ["#f00"]
    assert s.get("palette.recent") == ["#f00"]   # stored fully-qualified
    assert s.get("recent") is None               # not at top level


def test_defaults_used_when_absent(tmp_path):
    s = _s(tmp_path, defaults={"theme": "dark", "nested": {"x": 1}})
    assert s.get("theme") == "dark"
    assert s.get("nested.x") == 1
    s.set("theme", "light")
    assert s.get("theme") == "light"             # explicit overrides default


def test_change_callback_fires_on_real_change(tmp_path):
    s = _s(tmp_path)
    seen = []
    s.on_change(lambda k, v: seen.append((k, v)))
    s.set("a.b", 1)
    s.set("a.b", 1)   # no change → no callback
    s.set("a.b", 2)
    assert seen == [("a.b", 1), ("a.b", 2)]


def test_contains_remove_keys(tmp_path):
    s = _s(tmp_path)
    s.set("a", 1)
    s.set("b.c", 2)
    assert "a" in s and s.contains("b.c")
    assert set(s.keys()) == {"a", "b.c"}
    s.remove("a")
    assert "a" not in s


def test_atomic_write_no_partial_file(tmp_path, monkeypatch):
    # Simulate a crash mid-write: the temp file write fails, the real file
    # must be left untouched (not truncated).
    s = _s(tmp_path)
    s.set("keep", "safe")
    s.save()
    original = (tmp_path / "settings.json").read_text()

    import pathlib
    real_write = pathlib.Path.write_text

    def boom(self, *a, **k):
        if self.name.endswith(".tmp"):
            raise OSError("disk full")
        return real_write(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "write_text", boom)
    s.set("new", "value")
    s.save()  # swallows the error
    monkeypatch.undo()
    # Original file intact (os.replace never ran).
    assert (tmp_path / "settings.json").read_text() == original


def test_dict_sugar(tmp_path):
    s = _s(tmp_path)
    s["x.y"] = 5
    assert s["x.y"] == 5


def test_config_dir_is_namespaced():
    d = config_dir("myapp")
    assert d.name == "myapp"
    assert "elysium" in str(d)


def test_autosave_writes_immediately(tmp_path):
    s = _s(tmp_path, autosave=True)
    s.set("k", "v")            # no explicit save()
    assert json.loads((tmp_path / "settings.json").read_text())["k"] == "v"
