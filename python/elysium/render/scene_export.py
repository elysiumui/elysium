"""Native animated scene bundle exporter with canonical .esk and editable geometry.

Rendering is performed by the shipped scene renderer. Export never imports a
model or frames from another authoring application. A staging directory becomes
the final bundle only after every frame and manifest has been written.
"""

import hashlib
import json
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image

from . import mesh_document, scene, scene_animation, scene_actions


def mask_path(mask, scale=1.0):
    """Exact run rectangles preserve internal transparent holes (no hull)."""
    runs = {}
    rectangles = []
    for y, row in enumerate(mask):
        padded = np.r_[False, row, False].astype(np.int8)
        edges = np.flatnonzero(np.diff(padded))
        current = set(zip(edges[::2], edges[1::2]))
        for run in list(runs):
            if run not in current:
                rectangles.append((*run, runs.pop(run), y))
        for run in current:
            runs.setdefault(run, y)
    rectangles.extend((*run, start, len(mask)) for run, start in runs.items())
    return " ".join(
        f"M{x0 / scale:g},{y0 / scale:g}h{(x1 - x0) / scale:g}v{(y1 - y0) / scale:g}h{(x0 - x1) / scale:g}Z"
        for x0, x1, y0, y1 in rectangles
    )


def idle_clip(window,placements,identity,fps):
    """Resolve an authored idle clip and duration-preserving output frame count."""
    if identity is None:return None,0
    library=scene_actions.read(window,placements)
    action=next((a for a in library['items'] if a['id']==identity),None)
    if action is None:raise ValueError('The selected idle action no longer exists')
    timing=action['timing']
    fps=scene_animation.settings({'fps':fps})['fps']
    count=((timing['end']-timing['start']+1)*fps+timing['fps']-1)//timing['fps']
    if count>600:raise ValueError('The idle action exceeds 600 output frames; shorten its range or lower the export frame rate')
    return action,count


def export_bundle(
    placements,
    window,
    destination,
    *,
    size=384,
    scale=2,
    end_frame=72,
    idle_frames=60,
    close_object="Dome",
    progress=None,
    start_frame=0,
    fps=None,
    flight_seconds=None,
    project_root=None,
    idle_action_id=None,
):
    playback = scene_animation.settings(getattr(window, 'scene_timeline', None))
    playback = scene_animation.settings({**playback,
        'fps': playback['fps'] if fps is None else fps,
        'flight_seconds': playback['flight_seconds'] if flight_seconds is None else flight_seconds})
    if isinstance(size, bool) or not isinstance(size, int) or not 64 <= size <= 1024:
        raise ValueError("Export size must be 64–1024 logical pixels")
    if scale not in (1, 2):
        raise ValueError("Export scale must be 1 or 2")
    if any(isinstance(f,bool) or not isinstance(f,int) for f in (start_frame,end_frame)) or not 0 <= start_frame <= end_frame <= 360000 or end_frame-start_frame > 3600:
        raise ValueError("Export range must be ordered within 0–360000 and contain at most 3601 frames")
    if not isinstance(idle_frames, int) or not 0 <= idle_frames <= 600:
        raise ValueError("Idle frame count must be 0–600")
    library=scene_actions.read(window,placements)
    idle_action,idle_count=idle_clip(window,placements,idle_action_id,playback['fps'])
    if idle_action is not None:idle_frames=idle_count
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"Export destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    placements = deepcopy(placements)
    meshes = [p for p in placements if p.kind == "Mesh3D"]
    if not meshes:
        raise ValueError("Export requires at least one native mesh")
    from elysium.project_code import source_path, copy_source
    from elysium.scene_code import validate_source
    code_value = getattr(window, 'code_file', '')
    if code_value and not Path(code_value).is_absolute() and project_root is None:
        raise ValueError('A relative paired Python file requires the source project folder')
    paired_source = source_path(code_value, project_root or '.')
    if paired_source is not None:
        validate_source(paired_source)
    if len(placements) > 65534:
        raise ValueError('Animated object picking supports at most 65534 objects')
    camera = scene.camera(window.scene_camera)
    close_ids = [
        i for i, p in enumerate(placements) if p.name == close_object and p.kind == "Mesh3D"
    ]
    if close_object and len(close_ids) != 1:
        raise ValueError("Close object must identify exactly one visible mesh")
    scene.world_matrices(placements)
    for p in placements:
        scene_animation.tracks(p)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        paired_code = copy_source(paired_source, project_root or '.', staging)
        assets = staging / "assets"
        assets.mkdir()
        # Every referenced dependency is owned by the portable authoring copy.
        for p in placements:
            if p.kind != "Mesh3D":
                continue
            if p.mesh_kind.startswith("file:"):
                mesh_document.bind(p, mesh_document.resolve(p.mesh_kind), label=p.name)
            for field in (
                "pbr_albedo_map",
                "pbr_normal_map",
                "pbr_metallic_rough_map",
                "pbr_ao_map",
                "pbr_emissive_map",
            ):
                value = getattr(p, field, "")
                if value:
                    source = Path(value)
                    if not source.is_file():
                        raise ValueError(f"Missing material dependency: {source.name}")
                    name = hashlib.sha256(source.read_bytes()).hexdigest()[:16] + source.suffix
                    shutil.copyfile(source, assets / name)
                    # Keep an absolute staging path while rendering; rewrite for persistence below.
                    setattr(p, field, str(assets / name))
        idle_placements=None
        if idle_action is not None:
            # Unkeyed idle channels inherit the fully deployed pose, so a
            # partial idle action cannot snap unrelated wings back to rest.
            idle_placements=scene_animation.pose(placements,end_frame)
            idle_window=deepcopy(window)
            scene_actions.switch(idle_window,idle_placements,idle_action_id)
        entries = []
        total = end_frame - start_frame + 1 + idle_frames
        pixels = size * scale
        for index in range(total):
            frame = start_frame + min(index, end_frame-start_frame)
            source_action=library['active']
            if idle_placements is not None and index>end_frame-start_frame:
                offset=index-(end_frame-start_frame+1)
                frame=min(idle_action['timing']['end'],idle_action['timing']['start']+offset*idle_action['timing']['fps']/playback['fps'])
                posed=scene_animation.pose(idle_placements,frame)
                source_action=idle_action_id
            else:
                posed = scene_animation.pose(placements, frame)
            rgba, ids = scene.render(
                posed, pixels, pixels, **camera, shading="material", grid=False,
                lighting=getattr(window, "scene_lighting", None)
            )
            image = Image.frombytes("RGBA", (pixels, pixels), rgba)
            filename = f"assets/frame-{index:04d}.png"
            image.save(staging / filename)
            alpha = np.frombuffer(rgba, dtype=np.uint8).reshape(pixels, pixels, 4)[:, :, 3]
            # Hit masks use the same actual pixels as the rendered pose, at asset resolution.
            hit_path = mask_path(alpha >= 128, scale)
            close_path = (
                mask_path((ids == close_ids[0]) & (alpha >= 128), scale) if close_ids else ""
            )
            close_file = f"assets/close-{index:04d}.png"
            close_pixels = (
                ((ids == close_ids[0]) & (alpha >= 128)).astype(np.uint8) * 255
                if close_ids
                else np.zeros_like(alpha)
            )
            Image.fromarray(close_pixels).save(staging / close_file)
            object_file = f"assets/objects-{index:04d}.png"
            object_pixels = np.where(alpha >= 128, ids + 1, 0).astype(np.uint16)
            Image.fromarray(object_pixels).save(staging / object_file)
            entries.append(
                {"object_src": object_file,
                    "src": filename,
                    "source_frame": frame,
                    "source_action": source_action,
                    "close_src": close_file,
                    "hit_path": hit_path,
                    "close_path": close_path,
                }
            )
            if progress:
                progress(index + 1, total)
        manifest = {
            "schema_version": "1.0",
            "id": "dev.elysium.authored-scene",
            "name": destination.stem,
            "version": "1.0.0",
            "kind": "application",
            "color_space": "srgb",
        }
        document = {
            "root": {
                "type": "scene",
                "id": "root",
                "size": {"w": size, "h": size},
                "background": {"type": "color", "value": "#00000000"},
                "children": [
                    {
                        "type": "image",
                        "id": "authored-scene",
                        "src": entries[0]["src"],
                        "d": f"M0,0h{size}v{size}h{-size}Z",
                    }
                ],
            }
        }
        animation = {
            "schema_version": 1,
            "fps": playback['fps'],
            "flight_seconds": playback['flight_seconds'],
            "loop": playback['loop'],
            "source_start": start_frame,
            "size": size,
            "asset_scale": scale,
            "deploy_frames": end_frame - start_frame + 1,
            "idle_frames": idle_frames,
            "close_object": close_object,
            "camera": camera,
            "frames": entries,
            "code_file": paired_code,
            "objects": [{"id": p.entity_id, "name": p.name,
                         "hook": str(p.props.get('hook') or (p.name or p.kind).strip().replace(' ', '_').lower()+'.click')}
                        for p in placements],
        }
        if idle_action is not None:
            animation['idle_action']={'id':idle_action_id,'name':idle_action['name'],**idle_action['timing']}
        window_json = deepcopy(window.to_json())
        if getattr(window,'scene_actions',None) is not None:window_json['scene_actions']=library
        window_json["code_file"] = paired_code
        for p in placements:
            for field in (
                "pbr_albedo_map",
                "pbr_normal_map",
                "pbr_metallic_rough_map",
                "pbr_ao_map",
                "pbr_emissive_map",
            ):
                value = getattr(p, field, "")
                if value:
                    setattr(p, field, str(Path(value).relative_to(staging)))
        authored = {
            "window": window_json,
            "placements": [p.to_json() for p in placements],
            "mesh_document": mesh_document.capture(placements),
        }
        for name, data in (
            ("manifest.json", manifest),
            ("document.json", document),
            ("scene-animation.json", animation),
            ("designer_layout.json", authored),
        ):
            (staging / name).write_text(json.dumps(data, indent=2, allow_nan=False))
        (staging / "main.py").write_text(
            'from pathlib import Path\nfrom elysium.scene_player import run\n\nif __name__ == "__main__":\n    run(Path(__file__).resolve().parent)\n'
        )
        os.rename(staging, destination)
        return {
            "path": str(destination),
            "frames": total,
            "fps": playback['fps'],
            "size": size,
            "asset_scale": scale,
        }
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def package_app(bundle, destination, *, name=None, cancel=None, progress=None):
    """Package an exported scene with Python and Elysium; no Designer dependency.

    PyInstaller is the optional, standard build dependency. The returned macOS
    application owns its bundle identifier, so it can be launched independently.
    """
    import importlib.util
    import subprocess
    import sys

    bundle = Path(bundle).resolve()
    destination = Path(destination).resolve()
    if not (bundle / "scene-animation.json").is_file():
        raise ValueError("Choose an exported animated scene bundle")
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError("Install the Elysium build extra (PyInstaller) before packaging")
    name = name or bundle.stem.replace("-", " ").title()
    if not name.strip() or any(c in name for c in "/\\\0"):
        raise ValueError("Invalid application name")
    app_path = destination / (name + ".app" if sys.platform == "darwin" else name)
    if app_path.exists():
        raise FileExistsError(f"Application already exists: {app_path}")
    code_args = []
    animation = json.loads((bundle/'scene-animation.json').read_text())
    if animation.get('code_file'):
        source = (bundle/animation['code_file']).resolve()
        if not source.is_relative_to(bundle) or not source.is_file():
            raise ValueError('Missing or out-of-bundle paired Python source')
        code_root = source.parent
        while (code_root/'__init__.py').is_file(): code_root = code_root.parent
        module = '.'.join(source.relative_to(code_root).with_suffix('').parts)
        if not all(part.isidentifier() for part in module.split('.')):
            raise ValueError('Paired source package/file names must be Python identifiers for application packaging')
        code_args = ['--paths',str(code_root),'--hidden-import',module]
    destination.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".elysium-app-build-", dir=destination))
    staging = work / "dist"
    launcher = work / "main.py"
    launcher.write_text(
        'from pathlib import Path\nfrom elysium.scene_player import run\n\nif __name__ == "__main__":\n    run(Path(__file__).resolve().parent / "scene")\n'
    )
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        name,
        "--distpath",
        str(staging),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
        "--add-data",
        str(bundle) + os.pathsep + "scene",
    ]
    args += code_args
    if sys.platform == "darwin":
        args += [
            "--osx-bundle-identifier",
            "dev.elysium.scene." + hashlib.sha256(name.encode()).hexdigest()[:12],
        ]
    args.append(str(launcher))
    log_path = destination / (name + "-build-" + work.name.rsplit("-",1)[-1] + ".log")
    try:
        if cancel and cancel():
            raise InterruptedError("Application build cancelled")
        with log_path.open("x") as log:
            build_env = os.environ.copy()
            build_env.pop("PYTHONPATH", None)
            process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=build_env)
            try:
                import time
                if progress: progress(str(log_path))
                while process.poll() is None:
                    if cancel and cancel():
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait()
                        raise InterruptedError("Application build cancelled")
                    if progress: progress(str(log_path))
                    time.sleep(0.1)
                if process.returncode:
                    raise RuntimeError(f"Application packaging failed; details: {log_path}")
                if cancel and cancel():
                    raise InterruptedError("Application build cancelled")
                # Publish only a completed app. Cancellation/failure leaves no
                # partial application that could be mistaken for a success.
                ready = staging / app_path.name
                if app_path.exists():
                    raise FileExistsError(f"Application already exists: {app_path}")
                os.rename(ready, app_path)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
        return {"path": str(app_path), "log": str(log_path)}
    finally:
        shutil.rmtree(work, ignore_errors=True)
