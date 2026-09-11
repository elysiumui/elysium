"""Atomic, cancellable scene-preview jobs with genuine numerical passes."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import uuid

import numpy as np
from PIL import Image

from . import mesh_document, pbr, scene, scene_animation, scene_lighting


CHANNELS = ("beauty", "diffuse", "specular", "emission", "normal", "depth")


def selected(channels=None):
    if channels is None:
        return list(CHANNELS)
    if not isinstance(channels, list) or any(not isinstance(v, str) or v not in CHANNELS for v in channels) or len(set(channels)) != len(channels):
        raise ValueError("Render PNG channels must be unique supported pass names")
    return list(channels)


def validate(destination, size, start, end):
    if type(size) is not int or not 16 <= size <= 1024:
        raise ValueError("Render size must be 16–1024 pixels")
    if any(type(v) is not int for v in (start, end)) or not 0 <= start <= end <= 3600:
        raise ValueError("Render range must satisfy 0 ≤ start ≤ end ≤ 3600")
    if not isinstance(destination, (str, Path)) or not str(destination).strip():
        raise ValueError("Choose a new render output folder")
    path = Path(destination).expanduser().resolve()
    if path.exists():
        raise ValueError("Render output folder already exists; choose a new folder")
    return path


def render(placements, window, destination, *, size=256, start=0, end=0, progress=None, cancelled=None, channels=None):
    channels = selected(channels)
    path = validate(destination, size, start, end)
    placements, window = deepcopy(placements), deepcopy(window)
    if not any(p.kind == "Mesh3D" and getattr(p, "visible", True) for p in placements):
        raise ValueError("Scene render requires a visible mesh")
    camera = scene.camera(window.scene_camera)
    lighting = scene_lighting.read(window)
    source = mesh_document.capture(placements)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{path.name}-", dir=path.parent))
    entries = []
    try:
        for frame in range(start, end + 1):
            if cancelled and cancelled():
                raise InterruptedError("Render cancelled before publication")
            passes = {}
            rgba, _ = scene.render(scene_animation.pose(placements, frame), size, size,
                                   **camera, lighting=lighting, shading="material", grid=False,
                                   pass_output=passes)
            stem = f"frame-{frame:04d}"
            if "beauty" in channels:
                Image.frombytes("RGBA", (size, size), rgba).save(staging / f"{stem}-beauty.png")
            np.savez_compressed(staging / f"{stem}-passes.npz", **passes)
            alpha = np.frombuffer(rgba, np.uint8).reshape(size, size, 4)[:, :, 3:4]
            for channel in ("diffuse", "specular", "emission", "normal", "depth"):
                if channel == "normal":
                    pixels = np.clip(passes[channel] * .5 + .5, 0, 1)
                elif channel == "depth":
                    depth = passes[channel]
                    valid = depth[passes['mask']]
                    near, far = (float(valid.min()), float(valid.max())) if len(valid) else (0, 0)
                    mapped = np.zeros_like(depth)
                    mapped[passes['mask']] = 1 - (valid - near) / max(far - near, 1e-8)
                    pixels = np.repeat(mapped[:, :, None], 3, axis=2)
                else:
                    pixels = pbr._linear_to_srgb(pbr._aces(passes[channel]))
                image = np.concatenate([(np.clip(pixels, 0, 1) * 255).astype(np.uint8), alpha], axis=2)
                if channel in channels:
                    Image.fromarray(image).save(staging / f"{stem}-{channel}.png")
            entries.append({"frame": frame, "prefix": stem, "depth_display_range_m": [near, far]})
            if progress:
                progress(len(entries), end - start + 1)
        if cancelled and cancelled():
            raise InterruptedError("Render cancelled before publication")
        manifest = {"schema_version": 1, "renderer": "scene_direct_ibl_preview", "size": size,
                    "fps": 60, "png_channels": channels, "frames": entries, "camera": camera, "lighting": lighting,
                    "passes": {"beauty_linear": "linear RGB radiance before display transform",
                               "diffuse": "direct plus approximate IBL diffuse radiance",
                               "specular": "direct plus approximate IBL specular and clearcoat radiance",
                               "emission": "surface emission radiance",
                               "normal": "unit world-space Y-up shading normal, mapped and face-forwarded",
                               "depth": "camera-axis distance in meters; infinity for misses",
                               "mask": "geometric first-hit boolean"},
                    "display_transform": "ACES approximation then sRGB for radiance PNGs; normal RGB=(N+1)/2; depth white-near/black-far, ranges per frame",
                    "limits": "Direct/IBL preview, not a converged path-traced render. Area lights use 16 samples. NPZ retains signed normals, linear radiance and meter depth.",
                    "source": {"window": window.to_json(), "placements": [p.to_json() for p in placements], "mesh_document": source}}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
        # Refuse races as well as destinations present before starting.
        if path.exists():
            raise FileExistsError("Render output appeared while rendering")
        staging.rename(path)
        return {"path": str(path), "frames": len(entries), "manifest": str(path / 'manifest.json')}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def status(designer):
    return deepcopy({k: v for k, v in getattr(designer, '_scene_render_job', {'status': 'idle'}).items() if not k.startswith('_')})


def start(designer, destination, *, size=256, first=0, last=0, channels=None):
    if status(designer)['status'] == 'running':
        raise ValueError("A scene render is already running")
    channels = selected(channels)
    path = validate(destination, size, first, last)
    placements, window = deepcopy(designer.placements), deepcopy(designer.window_doc)
    mesh_document.capture(placements)
    scene_lighting.read(window)
    scene.camera(window.scene_camera)
    cancel = threading.Event()
    job = {'id': uuid.uuid4().hex, 'status': 'running', 'completed': 0, 'total': last - first + 1,
           'path': str(path), '_cancel': cancel}
    designer._scene_render_job = job

    def progress(n, total):
        job.update(completed=n, total=total)
        designer.menu_status = f"Scene render: {n}/{total} frames"

    def work():
        try:
            result = render(placements, window, path, size=size, start=first, end=last,
                            progress=progress, cancelled=cancel.is_set, channels=channels)
            job.update(status='complete', result=result)
            designer.menu_status = f"Scene render complete: {path.name}"
        except InterruptedError as exc:
            job.update(status='cancelled', error=str(exc))
            designer.menu_status = str(exc)
        except Exception as exc:
            job.update(status='failed', error=str(exc))
            designer.menu_status = f"Scene render failed: {exc}"

    threading.Thread(target=work, daemon=True).start()
    return status(designer)


def cancel(designer):
    job = getattr(designer, '_scene_render_job', {})
    if job.get('status') == 'running':
        job['_cancel'].set()
        job['cancellation_requested'] = True
    return status(designer)
