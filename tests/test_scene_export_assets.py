"""A packaged export carries every file its placements point at.

`mesh_document.rewrite_asset_paths` is the one rule for what counts as an
asset reference. Enumerating the five `pbr_*_map` fields by hand left
`texture_path`, `image_path`, `mesh_part_textures` and the
`texture_layers` stack unstaged *and* unrewritten, so the packaged
`designer_layout.json` shipped absolute paths into the author's machine and
the recipient opened it with those textures missing — silently, because the
"Missing material dependency" guard never ran for them either.
"""
import json
from pathlib import Path

import pytest
from elysium.aether._headless import AppWindow, Placement
from elysium.render import mesh_document, scene_export
from PIL import Image


def texture(directory: Path, name: str, colour) -> str:
    path = directory / name
    Image.new("RGBA", (4, 4), colour).save(path)
    return str(path)


@pytest.fixture
def authored(tmp_path):
    """One mesh referencing all six kinds of on-disk asset reference."""
    art = tmp_path / "art"
    art.mkdir()
    mesh = Placement(kind="Mesh3D", name="Dome", mesh_kind="Cube", w=64, h=64)
    mesh.pbr_albedo_map = texture(art, "albedo.png", (255, 0, 0, 255))
    mesh.pbr_normal_map = texture(art, "normal.png", (128, 128, 255, 255))
    mesh.texture_path = texture(art, "diffuse.png", (0, 255, 0, 255))
    mesh.image_path = texture(art, "raster.png", (0, 0, 255, 255))
    mesh.mesh_part_textures = {"wing": texture(art, "wing.png", (255, 255, 0, 255))}
    mesh.texture_layers = [{"path": texture(art, "layer.png", (255, 0, 255, 255)),
                            "blend": "normal", "opacity": 1.0}]
    adopted = set(mesh_document._PROCESS_STORE.keys())
    yield mesh, AppWindow(name="MainWindow", w=128, h=128)
    # `export_bundle` ends in a store-less `mesh_document.capture`, which
    # adopts every referenced key — here the "Cube" preset — into the
    # process store. Leaving it there made the whole suite order-dependent:
    # `test_mesh_store_lifecycle` asserts a refused `mesh.register_from_file`
    # leaves no "Cube" behind, and only alphabetical collection (m before s)
    # kept that green. Release exactly what the export adopted.
    for key in set(mesh_document._PROCESS_STORE.keys()) - adopted:
        mesh_document.forget(key)


def run_export(authored, destination, placements=None):
    """``(export result, packaged designer_layout.json)``."""
    mesh, window = authored
    result = scene_export.export_bundle(placements or [mesh], window, destination,
                                        size=64, scale=1, end_frame=0,
                                        idle_frames=0, close_object="")
    return result, json.loads((destination / "designer_layout.json").read_text())


def export(authored, destination) -> dict:
    return run_export(authored, destination)[1]


def references(placement_json) -> list[str]:
    """Every on-disk reference the packaged placement spells out."""
    mesh, texture_group = placement_json["mesh"], placement_json["texture"]
    return [placement_json["pbr_maps"]["albedo"],
            placement_json["pbr_maps"]["normal"],
            texture_group["path"],
            placement_json["image_path"],
            *mesh["part_textures"].values(),
            *(layer["path"] for layer in placement_json["texture_layers"])]


def _asset_values(placement_json) -> set[str]:
    """Every string the placement JSON carries, flattened, so a path can be
    looked for by value on any platform."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, str):
            found.add(node)
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(placement_json)
    return found


def test_every_asset_reference_is_staged_and_spelled_relative(authored, tmp_path):
    package = tmp_path / "scene.package"
    packaged = export(authored, package)
    spelled = references(packaged["placements"][0])
    assert len(spelled) == 6
    for value in spelled:
        assert not Path(value).is_absolute(), f"{value} leaks an authoring path"
        assert value.startswith("assets/"), value
        assert (package / value).is_file(), f"{value} was never copied into the package"
    # Six distinct files, none of them the author's original directory.
    assert len(set(spelled)) == 6
    assert not any(str(tmp_path / "art") in value for value in spelled)


# ---------------------------------------------------------------------------
# Which references are hard dependencies.
#
# A mesh's material maps decide how it renders, so a package missing one
# renders *wrong* rather than plainly: those have always failed the export
# loudly and still do. Every other reference degrades — nothing in the
# framework validates `image_path` or `texture_path` when the user edits
# them, so a file since moved or deleted is an ordinary state of a working
# document, and aborting the whole export over one would break documents
# that packaged fine before staging covered these fields at all.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", mesh_document.REQUIRED_ASSET_PATH_FIELDS)
def test_a_missing_material_map_still_fails_the_export(authored, tmp_path, field):
    mesh, _window = authored
    original = getattr(mesh, field)
    setattr(mesh, field, str(tmp_path / "gone.png"))
    try:
        with pytest.raises(ValueError, match="Missing material dependency"):
            export(authored, tmp_path / f"broken-{field}.package")
    finally:
        setattr(mesh, field, original)


@pytest.mark.parametrize("field, value", [
    ("texture_path", lambda gone: gone),
    ("image_path", lambda gone: gone),
    ("mesh_part_textures", lambda gone: {"wing": gone}),
    ("texture_layers", lambda gone: [{"path": gone, "blend": "normal"}]),
])
def test_a_stale_reference_degrades_the_package_instead_of_failing_it(
        authored, tmp_path, field, value):
    mesh, _window = authored
    gone = str(tmp_path / "gone.png")
    setattr(mesh, field, value(gone))
    result, packaged = run_export(authored, tmp_path / f"stale-{field}.package")
    assert result["missing_dependencies"] == ["gone.png"]
    # The reference travels unchanged, so rebinding it fixes the source too.
    # Compare the value, not the serialised text: json.dumps escapes
    # every backslash, so a Windows path never appears verbatim.
    assert gone in _asset_values(packaged["placements"][0])
    # Everything that *is* on disk still travelled into the package.
    staged = [v for v in references(packaged["placements"][0]) if v != gone]
    assert staged and all(v.startswith("assets/") for v in staged)


def test_a_stale_reference_on_a_non_mesh_placement_does_not_abort_the_export(
        authored, tmp_path):
    """The staging loop covers every placement now, not just Mesh3D, so a
    deleted `image_path` on an Image placement — a state nothing in the
    framework prevents — used to kill the whole export."""
    _mesh, _window = authored
    logo = Placement(kind="Image", name="Logo", w=32, h=32)
    logo.image_path = str(tmp_path / "deleted-logo.png")
    result, packaged = run_export(authored, tmp_path / "with-image.package",
                                  placements=[_mesh, logo])
    assert result["missing_dependencies"] == ["deleted-logo.png"]
    assert packaged["placements"][1]["image_path"] == logo.image_path
    for value in references(packaged["placements"][0]):
        assert value.startswith("assets/"), value


def test_a_complete_export_reports_no_missing_dependency(authored, tmp_path):
    result, _packaged = run_export(authored, tmp_path / "whole.package")
    assert result["missing_dependencies"] == []


def test_the_exports_above_leave_the_process_store_as_they_found_it():
    """Runs after the fixture teardown of every test in this module.

    `export_bundle` finishes with a store-less `mesh_document.capture`,
    which adopts each referenced key into the *process* store. A module
    that leaves "Cube" there makes the whole suite order-dependent — the
    mesh-store lifecycle tests assert a refused `mesh.register_from_file`
    leaves no preset behind — and only alphabetical collection order was
    hiding it.
    """
    assert "Cube" not in mesh_document._PROCESS_STORE
