"""Versioned, lossless mesh assets for authored Designer documents.

``pbr.MESH_LIBRARY`` holds read-only preset factories. The database for
authored geometry is a :class:`MeshStore`: an immutable asset per revision
key, owned by the document that references it. These functions serialize the
actual geometry and attributes referenced by a document and restore them into
a store before placements are painted. No pickle or executable factories are
stored, preset names are never written back into ``MESH_LIBRARY``, and
loading validates the entire asset set (and its recorded hashes) before
publishing any key.

Deprecated compatibility shim: while the GUI Designer still reads
``pbr.MESH_LIBRARY[placement.mesh_kind]()`` directly, every key a live store
holds — owned ``mesh:`` revisions and named registrations alike — is
mirrored there as a thin read-through entry that calls :func:`resolve`. The
entry carries no geometry, is installed whenever a store takes the key
(:meth:`MeshStore.put`, :func:`bind`, :func:`restore`, adoption by
:func:`capture`), never replaces a genuine factory (preset names and the
Designer's own registrations are never shadowed), and is removed once no
live store holds the key any more (:func:`sweep`, :meth:`MeshStore.retain`,
:func:`forget`, or the store being garbage-collected). It goes away once the
Designer routes its direct lookups through :func:`resolve`.

Every mesh a store holds is canonical (the :func:`from_json` form of its own
:func:`to_json` serialization: ``float32``/``int32`` arrays), so the asset
hash recorded on save is computed on exactly what :func:`restore`
reproduces. :meth:`MeshStore.put` normalises whatever it is given.

Key namespaces:

* ``mesh:<label>:<uuid>`` — owned revisions created by :func:`bind`. Globally
  unambiguous, so they may be resolved from any registered store.
* named legacy keys (``"Cube"``, ``"butterfly"``) — preset names or names
  registered from a file; looked up exactly in the current store and the
  process store, then in the preset library (exact, then case-insensitively),
  then case-insensitively in those same two stores. Never searched across
  other documents, and a preset is never shadowed by a case variant of its
  name (``cube.obj`` cannot become ``"Cube"``): exact keys always win, then
  presets in any spelling, then a case variant (the document's own store
  first, then the process store) — the order the Designer's own library
  scan follows. A named key nothing can resolve is not fatal: the
  document never owned that geometry, so :func:`capture` may omit it
  (``unresolved=``) and :func:`restore` accepts its absence, leaving the
  reference intact for a later ``mesh.register_from_file``.
* ``file:<path>`` — legacy on-disk imports, parsed on every resolve; the
  headless loader converts them to owned assets.

Eviction rule: a store holds exactly the owned revisions referenced by the
live placements. Snapshots are self-contained (they embed asset JSON), so
undo/redo/rollback rebuild the store from the snapshot, and each committed
transaction sweeps superseded keys (:func:`sweep`). Named keys are never swept.

The other half of "what a document references" is the files it points at
rather than embeds — textures. :func:`rewrite_asset_paths` is the single
rule for those, so project relocation and bundle export cover the whole
set instead of the handful of fields each call site happened to list.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import threading
import uuid
import weakref
from contextlib import contextmanager
from dataclasses import replace

import numpy as np

from . import pbr

SCHEMA_VERSION = 2
OWNED_PREFIX = "mesh:"
ARRAY_FIELDS = {
    "verts": (np.float32, 3), "faces": (np.int32, 3),
    "face_mats": (np.int32, None), "vert_normals": (np.float32, 3),
    "vert_uvs": (np.float32, 2), "vert_part_ids": (np.int32, None),
    "part_pivots": (np.float32, 3),
}


def validate(mesh: pbr.Mesh) -> None:
    """Reject malformed/non-finite data before it reaches rendering/native code."""
    for key, (_, width) in ARRAY_FIELDS.items():
        value = getattr(mesh, key)
        if value is None:
            if key in ("verts", "faces"):
                raise ValueError(f"mesh.{key} is required")
            continue
        value = np.asarray(value)
        if value.ndim != (2 if width else 1) or (width and value.shape[1] != width):
            raise ValueError(f"invalid mesh.{key} shape")
        if ARRAY_FIELDS[key][0] == np.int32 and value.dtype.kind not in "iu":
            raise ValueError(f"mesh.{key} must contain integer indices")
        if not np.isfinite(value).all():
            raise ValueError(f"non-finite mesh.{key}")
    n = len(mesh.verts)
    if len(mesh.faces) and (mesh.faces.min() < 0 or mesh.faces.max() >= n):
        raise ValueError("face index outside vertex array")
    for key in ("vert_normals", "vert_uvs", "vert_part_ids"):
        value = getattr(mesh, key)
        if value is not None and len(value) != n:
            raise ValueError(f"mesh.{key} must have one entry per vertex")
    if mesh.face_mats is not None and (
        len(mesh.face_mats) != len(mesh.faces) or (mesh.face_mats < 0).any()
    ):
        raise ValueError("invalid face material indices")
    if mesh.part_names is not None:
        if not all(isinstance(s, str) for s in mesh.part_names):
            raise ValueError("part names must be strings")
        if len(set(mesh.part_names)) != len(mesh.part_names):
            raise ValueError("part names must be unique")
    if mesh.part_pivots is not None and len(mesh.part_pivots) != len(mesh.part_names or []):
        raise ValueError("one pivot is required per part")
    if mesh.vert_part_ids is not None and len(mesh.vert_part_ids) and (
        mesh.vert_part_ids.min() < 0 or mesh.vert_part_ids.max() >= len(mesh.part_names or [])
    ):
        raise ValueError("part index outside part names")

    if mesh.topology is not None:
        from . import topology
        compiled, _, _ = topology.compile(mesh.topology)
        if mesh.part_names != compiled.part_names:
            raise ValueError("Editable topology and compiled mesh.part_names disagree")
        for key in ARRAY_FIELDS:
            a, b = getattr(mesh, key), getattr(compiled, key)
            if a is None and b is None:
                continue
            if a is None or b is None or a.shape != b.shape or not np.allclose(a, b, atol=1e-6, rtol=1e-6):
                raise ValueError(f"Editable topology and compiled mesh.{key} disagree")


def to_json(mesh: pbr.Mesh) -> dict:
    validate(mesh)
    data = {key: (None if getattr(mesh, key) is None else getattr(mesh, key).tolist())
            for key in ARRAY_FIELDS}
    data["part_names"] = None if mesh.part_names is None else list(mesh.part_names)
    if mesh.topology is not None:
        from copy import deepcopy
        data["topology"] = deepcopy(mesh.topology)
    return data


def from_json(data: dict) -> pbr.Mesh:
    if not isinstance(data, dict) or set(data) - (set(ARRAY_FIELDS) | {"part_names", "topology"}):
        raise ValueError("unknown or invalid mesh asset fields")
    kwargs = {}
    for key, (dtype, width) in ARRAY_FIELDS.items():
        value = data.get(key)
        if value is None:
            kwargs[key] = None
            continue
        raw = np.asarray(value)
        if dtype == np.int32 and (not np.isfinite(raw).all() or (raw != np.floor(raw)).any()):
            raise ValueError(f"mesh.{key} contains non-integer indices")
        if dtype == np.int32 and raw.size and (raw.min() < -(2**31) or raw.max() >= 2**31):
            raise ValueError(f"mesh.{key} index overflow")
        array = np.asarray(value, dtype=dtype)
        if array.size == 0:
            array = array.reshape((0, width) if width else (0,))
        kwargs[key] = array
    kwargs["part_names"] = data.get("part_names")
    from copy import deepcopy
    kwargs["topology"] = deepcopy(data.get("topology"))
    mesh = pbr.Mesh(**kwargs)
    validate(mesh)
    return mesh


# ---------------------------------------------------------------------------
# Document-owned mesh store.
# ---------------------------------------------------------------------------

_REGISTRY: "weakref.WeakSet[MeshStore]" = weakref.WeakSet()
# Re-entrant: a store's finalizer (below) may run inside a garbage collection
# triggered while this thread already holds the lock.
_REGISTRY_LOCK = threading.RLock()


def _stores() -> list:
    """Snapshot of every live store; safe against concurrent store creation."""
    with _REGISTRY_LOCK:
        return list(_REGISTRY)


class _ReadThrough:
    """Deprecated ``pbr.MESH_LIBRARY`` entry that forwards to :func:`resolve`.

    It exists only for Designer code that still indexes the library with a
    placement's ``mesh_kind``; it holds no geometry of its own.
    """

    __slots__ = ("key",)

    def __init__(self, key: str) -> None:
        self.key = key

    def __call__(self) -> pbr.Mesh:
        return resolve(self.key)

    def __repr__(self) -> str:
        return f"<mesh_document read-through {self.key!r}>"


def _publish_compat(key: str) -> None:
    """Mirror ``key`` into ``pbr.MESH_LIBRARY`` unless an entry already owns it.

    A genuine factory (a preset, or one the Designer registered itself) is
    never shadowed or replaced, and an existing shim is kept as-is.
    """
    if pbr.MESH_LIBRARY.get(key) is None:
        pbr.MESH_LIBRARY[key] = _ReadThrough(key)


def _held_by_a_live_store(key: str) -> bool:
    return any(key in store for store in _stores())


def _unpublish_compat(key: str) -> None:
    """Drop the shim for ``key`` once no live store holds it.

    Only our own shim is ever removed; presets and third-party factories stay.
    """
    if isinstance(pbr.MESH_LIBRARY.get(key), _ReadThrough) and not _held_by_a_live_store(key):
        pbr.MESH_LIBRARY.pop(key, None)


def _release_shims(assets: dict) -> None:
    """Finalizer of a collected store: keys nobody else holds leave the shim."""
    for key in list(assets):
        _unpublish_compat(key)


class MeshStore:
    """Document-owned immutable mesh assets keyed by revision key.

    Hashes are memoized per key and dropped whenever the key is rewritten.
    Every store registers itself so owned ``mesh:`` keys stay resolvable from
    worker threads (no context) and across documents in one process. Stored
    meshes are always canonical (see :meth:`put`).
    """

    def __init__(self) -> None:
        self._assets: dict[str, pbr.Mesh] = {}
        self._asset_hashes: dict[str, str] = {}
        self._geometry_hashes: dict[str, str] = {}
        self._lock = threading.RLock()
        with _REGISTRY_LOCK:
            _REGISTRY.add(self)
        # A store that dies without being cleared (a render job's private
        # snapshot, a superseded document store) must not leave dangling
        # shims behind. The finalizer references the asset dict, not self.
        finalizer = weakref.finalize(self, _release_shims, self._assets)
        finalizer.atexit = False

    def get(self, key: str) -> pbr.Mesh | None:
        with self._lock:
            return self._assets.get(key)

    def put(self, key: str, mesh: pbr.Mesh) -> None:
        """Store a canonical copy of ``mesh`` under ``key``.

        The copy is ``from_json(to_json(mesh))`` — float32/int32 arrays,
        exactly what :func:`restore` rebuilds from a saved document — so the
        recorded asset hash always matches a reload. Callers may pass float64
        meshes (Designer deformers, third-party importers) freely.
        """
        self._put_canonical(key, from_json(to_json(mesh)))

    def _put_canonical(self, key: str, mesh: pbr.Mesh) -> None:
        """Store a mesh that is already in ``from_json`` form (no copy)."""
        if not isinstance(key, str) or not key:
            raise ValueError("mesh asset keys must be nonempty strings")
        validate(mesh)
        with self._lock:
            self._assets[key] = mesh
            self._asset_hashes.pop(key, None)
            self._geometry_hashes.pop(key, None)
        _publish_compat(key)

    def pop(self, key: str, default=None):
        with self._lock:
            self._asset_hashes.pop(key, None)
            self._geometry_hashes.pop(key, None)
            present = key in self._assets
            value = self._assets.pop(key, default)
        if present:
            _unpublish_compat(key)
        return value

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._assets)

    def __contains__(self, key) -> bool:
        with self._lock:
            return key in self._assets

    def clear(self) -> None:
        with self._lock:
            dropped = list(self._assets)
            self._assets.clear()
            self._asset_hashes.clear()
            self._geometry_hashes.clear()
        for key in dropped:
            _unpublish_compat(key)

    def adopt_named(self, source: "MeshStore") -> list[str]:
        """Copy every named (non-``mesh:``) key of ``source`` this store lacks.

        Named keys (``mesh.register_from_file``) are bound to the process,
        not to a document revision, so they must outlive the store swaps that
        undo, rollback and reload perform. Returns the copied keys.
        """
        copied = []
        for key in source.keys():
            if key.startswith(OWNED_PREFIX) or key in self:
                continue
            mesh = source.get(key)
            if mesh is not None:
                self._put_canonical(key, mesh)
                copied.append(key)
        return copied

    def asset_hash(self, key: str) -> str:
        """Semantic hash of the complete serialized asset (memoized)."""
        with self._lock:
            value = self._asset_hashes.get(key)
            if value is None:
                mesh = self._assets.get(key)
                if mesh is None:
                    raise ValueError(f"missing mesh asset: {key}")
                value = self._asset_hashes[key] = semantic_hash(to_json(mesh))
            return value

    def geometry_hash(self, key: str) -> str:
        """Hash of positions and connectivity only (memoized)."""
        with self._lock:
            value = self._geometry_hashes.get(key)
            if value is None:
                mesh = self._assets.get(key)
                if mesh is None:
                    raise ValueError(f"missing mesh asset: {key}")
                value = self._geometry_hashes[key] = geometry_hash(mesh)
            return value

    def retain(self, keys) -> list[str]:
        """Drop owned revisions not in ``keys``; named legacy keys are kept."""
        wanted = set(keys)
        with self._lock:
            dropped = [k for k in self._assets if k.startswith(OWNED_PREFIX) and k not in wanted]
            for key in dropped:
                self._assets.pop(key, None)
                self._asset_hashes.pop(key, None)
                self._geometry_hashes.pop(key, None)
        # Outside our lock: unpublishing peeks into other stores, and two
        # stores retaining concurrently must never wait on each other.
        for key in dropped:
            _unpublish_compat(key)
        return dropped


# Compatibility fallback for callers without a document context (the GUI
# Designer, SimpleNamespace tests). It is also the second lookup for reads.
_PROCESS_STORE = MeshStore()
_CURRENT: contextvars.ContextVar = contextvars.ContextVar("mesh_store", default=None)


def default_store() -> MeshStore:
    """The store bound by :func:`using`, else the process fallback."""
    owner = _CURRENT.get()
    if owner is None:
        return _PROCESS_STORE
    return getattr(owner, "mesh_store", owner)


@contextmanager
def using(owner_or_store):
    """Route store-less bind/capture/restore/resolve calls to one document.

    The owner is looked up lazily through its ``mesh_store`` attribute, so a
    designer may swap its store (undo, reload) inside the block.
    """
    token = _CURRENT.set(owner_or_store)
    try:
        yield default_store()
    finally:
        _CURRENT.reset(token)


def forget(key: str) -> None:
    """Remove ``key`` from every registered store (simulates a fresh process)."""
    for store in _stores():
        store.pop(key, None)
    _unpublish_compat(key)


def referenced_keys(placements) -> list[str]:
    """Ordered unique mesh keys referenced by Mesh3D placements (no file: keys)."""
    keys = []
    for placement in placements or []:
        if getattr(placement, "kind", None) != "Mesh3D":
            continue
        candidates = [getattr(placement, "mesh_kind", None)]
        source = (getattr(placement, "props", None) or {}).get("skin_source_mesh")
        if source:
            candidates.append(source)
        for key in candidates:
            if isinstance(key, str) and key and not key.startswith("file:") and key not in keys:
                keys.append(key)
    return keys


def sweep(placements, *, store: MeshStore | None = None) -> list[str]:
    """Evict owned revisions no longer referenced by ``placements``."""
    return (_target(store)).retain(referenced_keys(placements))


# ---------------------------------------------------------------------------
# On-disk asset references.
# ---------------------------------------------------------------------------

#: Every placement attribute that names a single file on disk.
ASSET_PATH_FIELDS = (
    "image_path",
    "texture_path",
    "pbr_albedo_map",
    "pbr_metallic_rough_map",
    "pbr_normal_map",
    "pbr_ao_map",
    "pbr_emissive_map",
)
#: Attributes holding a collection of such files: ``mesh_part_textures`` maps
#: a part name to a path, ``texture_layers`` is a list of layers keyed "path".
ASSET_PATH_COLLECTIONS = ("mesh_part_textures", "texture_layers")
#: The subset a packaged export refuses to ship without, on a ``Mesh3D``
#: placement. A mesh's material maps decide how it renders, so a package
#: missing one renders *wrong* rather than plainly, and
#: :func:`scene_export.export_bundle` has always failed loudly on them.
#: Every other reference degrades instead: nothing in the framework
#: validates ``image_path`` or ``texture_path`` when they are edited, so a
#: file the author has since moved or deleted is an ordinary state of a
#: working document, not a reason to abort an export that used to succeed.
REQUIRED_ASSET_PATH_FIELDS = (
    "pbr_albedo_map",
    "pbr_metallic_rough_map",
    "pbr_normal_map",
    "pbr_ao_map",
    "pbr_emissive_map",
)


def rewrite_asset_paths(placement, rewrite) -> None:
    """Apply ``rewrite(path) -> path`` to every file a placement points at.

    One rule for the whole placement, instead of a field list repeated at
    each call site: a document is portable only when *all* of its
    references move together. Enumerating the five ``pbr_*_map`` fields
    alone left ``texture_path``, ``mesh_part_textures``, the
    ``texture_layers`` stack and ``image_path`` holding absolute paths
    into wherever the project used to live.

    Containers are replaced, never edited in place, so a shallow copy of a
    live placement can be rewritten without the document seeing it. Empty
    and non-string values are left alone; ``rewrite`` decides what to do
    with anything else (project relocation, for instance, keeps
    out-of-project absolute paths absolute).

    ``rewrite`` may return ``None`` to **decline** a reference, leaving the
    value exactly as it is. That is how a caller says "not mine to move" —
    a file that is not on disk to be staged, a path that is not inside the
    directory being made relative — without inventing a value, dropping the
    user's reference, or failing the whole document over one of them.
    """
    for name in ASSET_PATH_FIELDS:
        value = getattr(placement, name, None)
        if isinstance(value, str) and value:
            setattr(placement, name, _rewritten(value, rewrite))
    parts = getattr(placement, "mesh_part_textures", None)
    if isinstance(parts, dict) and parts:
        placement.mesh_part_textures = {
            part: (_rewritten(path, rewrite) if isinstance(path, str) and path else path)
            for part, path in parts.items()}
    layers = getattr(placement, "texture_layers", None)
    if isinstance(layers, list) and layers:
        placement.texture_layers = [
            {**layer, "path": _rewritten(layer["path"], rewrite)}
            if isinstance(layer, dict) and isinstance(layer.get("path"), str) and layer["path"]
            else layer
            for layer in layers]


def _rewritten(value: str, rewrite):
    """``rewrite(value)``, or ``value`` unchanged when the caller declines."""
    replacement = rewrite(value)
    return value if replacement is None else replacement


def geometry_hash(mesh: pbr.Mesh) -> str:
    """Hash positions and connectivity only.

    UVs, normals, materials, seam/sharp flags, pins, shading policy and parts
    are excluded so attribute-only publishes keep primitive regeneration
    available.
    """
    if mesh.topology is not None:
        from . import topology
        doc = mesh.topology
        payload = {
            "positions": [[v["id"], *v["position"]] for v in doc["vertices"]],
            "polygons": [[c["vertex"] for c in f["corners"]] for f in doc["faces"]],
            "wires": [list(e["vertices"]) for e in topology.loose_edges(doc)],
        }
    else:
        payload = {"positions": np.asarray(mesh.verts).tolist(),
                   "polygons": np.asarray(mesh.faces).tolist()}
    return semantic_hash(payload)


def geometry_hash_for(kind: str, *, store: MeshStore | None = None) -> str:
    """Geometry hash of a resolvable key, memoized through its owning store."""
    if isinstance(kind, str) and kind.startswith(OWNED_PREFIX):
        for candidate in _owned_lookup_order(store):
            if kind in candidate:
                return candidate.geometry_hash(kind)
    return geometry_hash(resolve(kind, store=store))


def document_hash(payload: dict) -> str:
    """Deterministic hash of a complete layout payload."""
    return semantic_hash(payload)


def _target(store):
    # Never test a store for truthiness: an empty document store is a store.
    return default_store() if store is None else store


def _owned_lookup_order(store):
    first = _target(store)
    seen = [first]
    if _PROCESS_STORE is not first:
        seen.append(_PROCESS_STORE)
    for other in _stores():
        if other not in seen:
            seen.append(other)
    return seen


def _casefold_in(folded: str, store: MeshStore) -> pbr.Mesh | None:
    # keys() is a snapshot; a concurrent pop only makes get() return None.
    for key in store.keys():
        if not key.startswith(OWNED_PREFIX) and key.casefold() == folded:
            mesh = store.get(key)
            if mesh is not None:
                return mesh
    return None


def _casefold_from_store(kind: str, target: MeshStore) -> pbr.Mesh | None:
    """Case-insensitive match for a named key in ``target``, then the process store.

    ``mesh.register_from_file`` registers CamelCase names ("Butterfly") while
    saved skins may carry the placement's ``mesh_kind`` lowercased
    ("butterfly"); the old process-wide library matched those by casefold and
    the store keeps that contract. Owned ``mesh:`` keys are exact identities
    and are never matched this way.

    The two stores scanned are the document's own and the process
    fallback — exactly the pair :func:`_exact_from_stores` consults, and
    the reason the fallback exists: a Designer that has not adopted a
    per-document store registers there, so a *read* dispatched inside a
    document context must still find those names in either spelling. No
    other *document's* store is ever scanned: a name one document
    imported must not change what another document's placements mean.
    """
    folded = kind.casefold()
    if folded.startswith(OWNED_PREFIX):  # "MESH:..." is not a named key either
        return None
    mesh = _casefold_in(folded, target)
    if mesh is None and target is not _PROCESS_STORE:
        mesh = _casefold_in(folded, _PROCESS_STORE)
    return mesh


def _exact_from_stores(kind: str, target: MeshStore) -> pbr.Mesh | None:
    """The canonical mesh a store holds under exactly ``kind``, or ``None``.

    Order: ``target``, the process store, then (owned keys only) every other
    registered store. Named legacy keys are never searched across documents.
    """
    mesh = target.get(kind)
    if mesh is None:
        mesh = _PROCESS_STORE.get(kind)
    if mesh is None and kind.startswith(OWNED_PREFIX):
        # Owned revision keys are globally unambiguous: worker threads without
        # the context variable and cross-document reads may find them anywhere.
        for other in _stores():
            if other is target or other is _PROCESS_STORE:
                continue
            mesh = other.get(kind)
            if mesh is not None:
                break
    return mesh


def _preset_factory(kind: str):
    """A genuine preset factory for ``kind`` (exact, then case-insensitive).

    Read-through shims are skipped: they would call :func:`resolve` again,
    and a key no store holds must report as missing, not recurse.
    """
    factory = pbr.MESH_LIBRARY.get(kind)
    if factory is None or isinstance(factory, _ReadThrough):
        # Iterate a snapshot: a bind on the main thread may publish a shim
        # while a render worker walks the table.
        factory = next((v for k, v in list(pbr.MESH_LIBRARY.items())
                        if k.casefold() == kind.casefold() and not isinstance(v, _ReadThrough)), None)
    return factory


def is_preset_name(name: str) -> bool:
    """True when ``name`` is a read-only preset in any spelling.

    Presets are never shadowed: a registration under such a name would be
    served for its exact spelling only, while every other spelling — and the
    Designer's own library scan — kept drawing the preset.
    """
    return isinstance(name, str) and bool(name) and _preset_factory(name) is not None


def _locate(kind: str, target: MeshStore) -> tuple:
    """``(stored mesh, preset factory)`` for ``kind``; at most one is set.

    Exact keys always win (``target``, the process store, any store for
    owned keys); then a preset in any spelling; then a case variant held by
    ``target`` itself. A stored mesh is the store's canonical object and may
    be shared; a factory must be called (and its result normalised).
    """
    mesh = _exact_from_stores(kind, target)
    if mesh is not None:
        return mesh, None
    factory = _preset_factory(kind)
    if factory is not None:
        return None, factory
    return _casefold_from_store(kind, target), None


def resolve(kind: str, *, store: MeshStore | None = None) -> pbr.Mesh:
    """Find geometry for a key.

    Order: ``file:`` import, exact store keys, read-only presets (any
    spelling), then a case variant the current store itself holds.
    """
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"missing mesh asset: {kind}")
    if kind.startswith("file:"):
        return pbr.import_mesh_from_file(kind[5:])
    mesh, factory = _locate(kind, _target(store))
    if mesh is not None:
        return mesh
    if factory is None:
        raise ValueError(f"missing mesh asset: {kind}")
    return factory()


def _resolvable(key: str, target: MeshStore) -> bool:
    """True when ``key`` names geometry this process can produce.

    Asked only about a key a caller already listed as unresolved, so that
    ``capture`` skips it for that reason alone — a mesh that resolves and
    then fails to validate is still an error, not a silent omission.
    """
    try:
        resolve(key, store=target)
    except ValueError:
        return False
    return True


def _adopt(target: MeshStore, key: str, *, source: MeshStore | None = None) -> pbr.Mesh:
    """Make ``target`` own ``key`` and return the stored (canonical) mesh.

    A mesh another store already holds is shared as-is (assets are immutable
    and already canonical); anything else — a preset, a legacy factory, a
    ``file:`` import — is normalised on the way in. Lookups follow
    :func:`resolve` through ``source`` (default: ``target`` itself).
    """
    mesh = target.get(key)
    if mesh is not None:
        return mesh
    origin = target if source is None else source
    mesh, _ = _locate(key, origin)
    if mesh is not None:
        target._put_canonical(key, mesh)
        return mesh
    target.put(key, resolve(key, store=origin))
    return target.get(key)


def snapshot_store(placements, *, source: MeshStore | None = None) -> MeshStore:
    """A private store holding every key ``placements`` reference.

    Long-running readers (a background render) take one of these so that
    the sweep a later committed edit performs on the live document store
    cannot pull a revision out from under them. Keys are resolved through
    ``source`` (default: the current document store), so named keys that
    only the live document knows are carried along too.
    """
    origin = _target(source)
    store = MeshStore()
    for key in referenced_keys(placements):
        _adopt(store, key, source=origin)
    return store


def bind(placement, mesh: pbr.Mesh, *, label: str = "", store: MeshStore | None = None) -> str:
    """Give an edited placement its own immutable mesh revision/cache key."""
    validate(mesh)
    owned = from_json(to_json(mesh))
    key = OWNED_PREFIX + (label + ":" if label else "") + uuid.uuid4().hex
    (_target(store))._put_canonical(key, owned)
    placement.mesh_kind = key
    return key


def _asset_set_hash(hashes: dict) -> str:
    lines = "\n".join(f"{key} {hashes[key]}" for key in sorted(hashes))
    return hashlib.sha256(lines.encode()).hexdigest()


def capture(placements, *, store: MeshStore | None = None, unresolved=()) -> dict:
    """Serialize every referenced asset plus per-asset and set hashes.

    Keys referenced but not yet owned by ``store`` (presets, legacy names)
    are adopted into it so the store mirrors the document exactly.

    ``unresolved`` lists legacy **named** keys this process cannot resolve
    at all — a skin saved before geometry was embedded names a mesh
    ("Butterfly") that used to live in the process-wide ``MESH_LIBRARY``
    and is simply absent here. Such a key is omitted from ``assets``
    instead of raising, so the document can still be checkpointed and
    saved; the placement keeps the name, so the reference round-trips
    unchanged and rebinding it later (``mesh.register_from_file``) embeds
    the real geometry on the next save. A name that *does* resolve is
    embedded as usual even when it is listed, and an owned ``mesh:``
    revision is never omitted — only a document that owns one may name it.
    """
    from . import mesh_edit, mesh_modifiers, scene, scene_animation
    scene.world_matrices(placements)
    for p in placements:
        scene_animation.tracks(p)
        mesh_edit.taper_settings(p)
        mesh_modifiers.settings(p)
    target = _target(store)
    tolerated = set(unresolved or ())
    assets, hashes = {}, {}
    # File imports stay explicit dependencies until native editing converts
    # them to owned mesh assets; do not alter a placement on reads. The
    # serialized asset is the stored canonical copy, never the raw factory
    # output, so it is exactly what the recorded hash was computed on.
    for key in referenced_keys(placements):
        if key in tolerated and not key.startswith(OWNED_PREFIX) \
                and not _resolvable(key, target):
            continue
        mesh = _adopt(target, key)
        assets[key] = to_json(mesh)
        hashes[key] = target.asset_hash(key)
    return {"schema_version": SCHEMA_VERSION, "assets": assets,
            "hashes": {"assets": hashes, "document": _asset_set_hash(hashes)}}


def _check_hashes(document: dict, assets: dict) -> None:
    hashes = document.get("hashes")
    if hashes is None:
        return
    if (not isinstance(hashes, dict) or set(hashes) != {"assets", "document"}
            or not isinstance(hashes["assets"], dict) or not isinstance(hashes["document"], str)
            or set(hashes["assets"]) != set(assets)
            or not all(isinstance(v, str) for v in hashes["assets"].values())):
        raise ValueError("invalid mesh document hashes")
    for key, mesh in assets.items():
        if semantic_hash(to_json(mesh)) != hashes["assets"][key]:
            raise ValueError(f"mesh asset {key} does not match its recorded hash; "
                             "the document was corrupted or edited outside the Designer")
    if _asset_set_hash(hashes["assets"]) != hashes["document"]:
        raise ValueError("mesh document hash does not match its recorded asset hashes; "
                         "the document was corrupted or edited outside the Designer")


def restore(document: dict | None, placements=None, *, store: MeshStore | None = None) -> None:
    """Parse, verify and publish an asset set into ``store`` all-or-nothing."""
    if document is None:  # Legacy document without embedded geometry.
        return
    if not isinstance(document, dict) or document.get("schema_version") not in (1, SCHEMA_VERSION):
        raise ValueError("unsupported mesh document version")
    raw = document.get("assets")
    if not isinstance(raw, dict) or not all(isinstance(k, str) and k for k in raw):
        raise ValueError("invalid mesh asset map")
    from . import mesh_edit, mesh_modifiers, scene, scene_animation
    scene.world_matrices(placements or [])
    for p in placements or []:
        scene_animation.tracks(p)
        mesh_edit.taper_settings(p)
        mesh_modifiers.settings(p)
    assets = {key: from_json(value) for key, value in raw.items()}
    for key in referenced_keys(placements):
        # An owned revision exists nowhere but the document that carries it,
        # so a missing one is a broken document. A *named* key is a legacy
        # reference the document never owned — it resolves through the
        # presets, the process store or a later rebind — so a document that
        # could not embed it (see ``capture(unresolved=...)``) still opens,
        # with the name reported by the loader. Deleting an embedded asset
        # by hand remains detected: its hash leaves ``hashes`` with it and
        # the recorded set hash no longer matches.
        if key not in assets and key.startswith(OWNED_PREFIX):
            raise ValueError(f"document is missing referenced mesh asset: {key}")
    _check_hashes(document, assets)
    target = _target(store)
    for key, mesh in assets.items():
        # Already in from_json form. The store publishes the Designer shim
        # for keys no genuine factory owns; preset names never go back into
        # the library.
        target._put_canonical(key, mesh)


def semantic_hash(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def with_vertices(mesh: pbr.Mesh, verts: np.ndarray) -> pbr.Mesh:
    """Preserve authored attributes and recompute derived normals after deformation."""
    verts = np.asarray(verts, dtype=np.float32)
    if verts.shape != mesh.verts.shape:
        raise ValueError("topology-preserving deformation changed vertex count")
    normals = None
    if mesh.vert_normals is not None:
        normals = np.zeros_like(verts)
        tri = verts[mesh.faces]
        face_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        for corner in range(3):
            np.add.at(normals, mesh.faces[:, corner], face_normals)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    if mesh.topology is not None:
        from copy import deepcopy

        from . import topology
        doc = deepcopy(mesh.topology)
        _, ids, _ = topology.compile(doc)
        positions = {}
        for identity, position in zip(ids, verts):
            if identity in positions and not np.allclose(position, positions[identity]):
                raise ValueError("Deformation split an editable vertex across corners")
            positions[identity] = position
        for vertex in doc['vertices']:
            if vertex['id'] in positions:
                vertex['position'] = positions[vertex['id']].tolist()
        for face in doc['faces']:
            for corner in face['corners']:
                corner['normal'] = None
        return topology.compile(doc)[0]
    result = replace(mesh, verts=verts.copy(), vert_normals=normals)
    validate(result)
    return result
