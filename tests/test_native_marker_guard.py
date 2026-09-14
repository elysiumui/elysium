"""Every ``elysium._native`` import in a guarded test file is marked or in a test body.

``tests/conftest.py`` skips ``native``-marked tests when the compiled
extension is absent.  The marker only helps when it is actually applied, and
only for imports that run at test time:

* a test that does ``from elysium._native import _native`` in its body
  without ``@pytest.mark.native`` (or a module-level ``pytestmark``, or one
  of the older ``native_only`` / ``skipif(not _native_available())`` guards)
  hard-fails with ``ModuleNotFoundError`` on a checkout without the built
  ``.so`` instead of skipping -- which is exactly what
  ``test_paint_focus_ring_renders`` did while the rest of its file was being
  marked;
* an import of the extension at module scope (directly, or inside a
  top-level ``if``/``try``/``with`` or a class body) runs during collection,
  before any marker or hook can intervene, and turns the whole file into a
  collection error -- taking its non-native tests with it.  ``pytestmark``
  cannot rescue that, so it is reported whether or not the module is marked.
  This is the shape ``test_mesh_tangents.py`` had before the guard existed.

Two checks, one per failure mode:

``test_guarded_file_marks_every_native_import`` is a headless static check
(``ast`` only; nothing is imported) over the files that have adopted the
guard.  ``test_guarded_files_collect_without_the_extension`` is the ground
truth for the collection-time case: it runs ``pytest --collect-only`` on the
same files in a subprocess with ``elysium._native._native`` made
unimportable, so it does not depend on the ``.so`` being absent (CI always
builds the wheel first).

Add a file to ``GUARDED_FILES`` once it passes/skips cleanly with the
extension renamed away; the suite as a whole does not yet (many older files
construct ``elysium.App`` unguarded and fail through the ``_NotBuiltYet``
placeholder), so this list is deliberately partial.

Limitation of the static check: within function bodies, only imports written
directly inside a ``test_*`` function (or nested within it) are seen.  An
import in a shared helper called from an unmarked test is not attributed to
that test.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

# Files in which every test that imports the extension is guarded.
GUARDED_FILES = [
    "test_a11y_semantics.py",
    "test_butterfly.py",
    "test_mesh_tangents.py",
    "test_phase1.py",
    "test_phase2.py",
    "test_phase2_5_audit.py",
    "test_scene_playback.py",
    "test_text_native.py",
]

NATIVE_FLAGS = ("_native_available", "_NATIVE_AVAILABLE", "native")


def _imports_native(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom) and n.module:
            if n.module.startswith("elysium._native"):
                return True
            if n.module == "elysium" and any(a.name == "_native" for a in n.names):
                return True
        if isinstance(n, ast.Import):
            if any(a.name.startswith("elysium._native") for a in n.names):
                return True
    return False


def _dotted(expr: ast.AST) -> str:
    if isinstance(expr, ast.Call):
        expr = expr.func
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
    return ".".join(reversed(parts))


def _is_guard(expr: ast.AST) -> bool:
    """``pytest.mark.native``, ``native_only`` or a skipif on the native flag."""
    name = _dotted(expr)
    leaf = name.rsplit(".", 1)[-1]
    if leaf in ("native", "native_only"):
        return True
    if leaf == "skipif" and isinstance(expr, ast.Call):
        cond = expr.args[0] if expr.args else next(
            (k.value for k in expr.keywords if k.arg == "condition"), None)
        return cond is not None and any(f in ast.unparse(cond) for f in NATIVE_FLAGS)
    return False


def _module_guarded(tree: ast.Module) -> bool:
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets):
            v = n.value
            elems = v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
            if any(_is_guard(e) for e in elems):
                return True
    return False


def _import_time_statements(nodes):
    """Statements that execute when the module is imported, in source order.

    Descends into compound statements (``if``/``try``/``with``/``for``, class
    bodies, ``except`` handlers) but never into a function body: those run
    later, at test time, and are the static check's other half.
    """
    for n in nodes:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield n
        for field in ("body", "handlers", "orelse", "finalbody"):
            yield from _import_time_statements(getattr(n, field, []))


def _test_functions(tree: ast.Module):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield m


def unguarded_native_tests(source: str) -> list[str]:
    """Extension imports that would fail without the ``.so`` instead of skipping.

    ``<module>:<lineno>`` for every import that runs at collection time
    (reported regardless of ``pytestmark``), then ``<test_name>:<lineno>`` for
    every ``test_*`` function that imports the extension without a guard.
    """
    tree = ast.parse(source)
    bad = [
        f"<module>:{n.lineno}"
        for n in _import_time_statements(tree.body)
        if isinstance(n, (ast.Import, ast.ImportFrom)) and _imports_native(n)
    ]
    if _module_guarded(tree):
        return bad
    return bad + [
        f"{fn.name}:{fn.lineno}"
        for fn in _test_functions(tree)
        if fn.name.startswith("test_")
        and _imports_native(fn)
        and not any(_is_guard(d) for d in fn.decorator_list)
    ]


@pytest.mark.parametrize("filename", GUARDED_FILES)
def test_guarded_file_marks_every_native_import(filename):
    path = TESTS / filename
    assert path.is_file(), f"{filename} is in GUARDED_FILES but does not exist"
    bad = unguarded_native_tests(path.read_text(encoding="utf-8"))
    assert not bad, (
        f"tests/{filename}: elysium._native is imported at module scope (a "
        f"collection error without the built .so; move it into the test body) "
        f"or inside a test without @pytest.mark.native / an equivalent guard: "
        f"{', '.join(bad)}")


def test_guarded_files_are_real_and_use_the_extension():
    """The list stays meaningful: every entry exists and imports the extension."""
    for filename in GUARDED_FILES:
        source = (TESTS / filename).read_text(encoding="utf-8")
        assert _imports_native(ast.parse(source)), (
            f"tests/{filename} no longer imports elysium._native; drop it from GUARDED_FILES")


# --- ground truth: collection with the extension unimportable -----------------

# Loaded with ``-p`` before any conftest, so nothing has imported elysium yet.
# ``import elysium`` then takes its ImportError branch (_NATIVE_AVAILABLE = False)
# exactly as on a checkout without the built .so; a module-scope extension
# import in a test file fails at collection.  The report file proves the block
# took effect, so the check cannot pass vacuously while the .so is present.
_BLOCK_NATIVE_PLUGIN = '''
import os
import sys
from importlib.abc import MetaPathFinder


class _BlockNative(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "elysium._native._native":
            raise ImportError("elysium._native._native blocked: simulating a checkout without the .so")
        return None


sys.meta_path.insert(0, _BlockNative())


def pytest_collection_finish(session):
    import elysium
    with open(os.environ["BLOCK_NATIVE_REPORT"], "w", encoding="utf-8") as f:
        f.write(repr(elysium._NATIVE_AVAILABLE))
'''


def _collect_only_without_native(files, tmp_path):
    (tmp_path / "block_native.py").write_text(_BLOCK_NATIVE_PLUGIN, encoding="utf-8")
    report = tmp_path / "native_available.txt"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(tmp_path), env.get("PYTHONPATH")) if p)
    env["BLOCK_NATIVE_REPORT"] = str(report)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "-p", "block_native", *map(str, files)],
        capture_output=True, text=True, env=env, cwd=TESTS.parent, timeout=300)
    return result, report


def test_guarded_files_collect_without_the_extension(tmp_path):
    """No guarded file errors at collection when the .so is unimportable.

    This is what the ``native`` marker cannot protect against: a module-scope
    ``from elysium._native import _native`` raises before any hook runs and
    loses every test in the file, marked or not.
    """
    result, report = _collect_only_without_native(
        [TESTS / f for f in GUARDED_FILES], tmp_path)
    assert result.returncode == 0, (
        "pytest --collect-only failed with elysium._native._native blocked:\n"
        + result.stdout + result.stderr)
    assert report.read_text(encoding="utf-8") == "False", (
        "the block did not take effect; the check proved nothing:\n"
        + result.stdout + result.stderr)


def test_collection_check_catches_a_module_scope_import(tmp_path):
    """The subprocess check itself fails on the shape it exists to catch."""
    bad = tmp_path / "test_hoisted.py"
    bad.write_text(
        "import pytest\n"
        "from elysium._native import _native\n"
        "pytestmark = pytest.mark.native\n\n"
        "def test_x():\n    assert _native\n",
        encoding="utf-8")
    result, report = _collect_only_without_native([bad], tmp_path)
    assert result.returncode != 0
    assert "error during collection" in result.stdout, result.stdout + result.stderr


# --- the detector itself ------------------------------------------------------

_UNGUARDED = '''
import pytest

def test_a():
    from elysium._native import _native as n
    assert n

@pytest.mark.native
def test_b():
    from elysium._native import _native as n
    assert n

@native_only
def test_c():
    from elysium import _native
    assert _native

@pytest.mark.skipif(not _native_available(), reason="native extension not built")
def test_d():
    import elysium._native._native as n
    assert n

@pytest.mark.skipif(sys.platform == "win32", reason="not a native guard")
def test_e():
    from elysium._native import _native as n
    assert n

def test_f():
    assert True
'''


def test_detector_flags_only_the_unguarded_native_imports():
    assert unguarded_native_tests(_UNGUARDED) == ["test_a:4", "test_e:24"]


def test_detector_accepts_a_module_level_pytestmark():
    marked = "import pytest\npytestmark = pytest.mark.native\n" + _UNGUARDED
    assert unguarded_native_tests(marked) == []
    listed = "import pytest\npytestmark = [pytest.mark.slow, native_only]\n" + _UNGUARDED
    assert unguarded_native_tests(listed) == []
    unrelated = "import pytest\npytestmark = pytest.mark.slow\n" + _UNGUARDED
    assert unguarded_native_tests(unrelated) == ["test_a:6", "test_e:26"]


# The regression the guard exists for: test_mesh_tangents.py's in-body import
# hoisted above its module-level pytestmark.  The marker does not help here.
_HOISTED = '''
import pytest
from elysium import _native
pytestmark = pytest.mark.native

def test_a():
    assert _native
'''


def test_detector_flags_a_module_scope_import_despite_pytestmark():
    assert unguarded_native_tests(_HOISTED) == ["<module>:3"]
    # ...and before any per-test findings when the module is not marked.
    unmarked = _HOISTED.replace("pytestmark = pytest.mark.native\n", "") + _UNGUARDED
    assert unguarded_native_tests(unmarked)[0] == "<module>:3"


@pytest.mark.parametrize("wrapper", [
    "if sys.platform != 'win32':\n    from elysium._native import _native\n",
    "try:\n    pass\nexcept Exception:\n    from elysium._native import _native\n",
    "try:\n    from elysium._native import _native\nfinally:\n    pass\n",
    "with open('x'):\n    import elysium._native._native\n",
    "class TestNative:\n    from elysium import _native\n",
], ids=["if", "except-handler", "try", "with", "class-body"])
def test_detector_sees_import_time_imports_inside_compound_statements(wrapper):
    source = "import pytest\npytestmark = pytest.mark.native\n" + wrapper
    found = unguarded_native_tests(source)
    assert len(found) == 1 and found[0].startswith("<module>:"), found


def test_detector_leaves_function_scope_to_the_marker_check():
    """A helper's import is not an import-time import (existing helper limitation)."""
    source = (
        "import pytest\npytestmark = pytest.mark.native\n\n"
        "def _helper():\n    from elysium._native import _native\n    return _native\n\n"
        "def test_a():\n    assert _helper()\n")
    assert unguarded_native_tests(source) == []
