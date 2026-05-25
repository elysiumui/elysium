"""Vectorised Cook-Torrance / GGX PBR shading + analytic IBL.

Renders a unit sphere into an RGBA buffer using:
  • Per-pixel ray-sphere intersection.
  • Disney-style metallic-roughness BRDF
      f = F_schlick * D_ggx * G_smith / (4 nl nv) + (1-F) * diffuse / π
  • Optional clear-coat lobe on top.
  • Analytic Hosek-Wilkie–inspired sky + ground for the indirect (IBL)
    term, with a tiny "studio" key-light + fill-light for direct.
  • ACES tone-mapping + sRGB encode.

Vectorised with NumPy so a 384×384 preview redraws at >30 FPS on M-series
silicon. Material params are mutated by the UI between frames.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np


# --- Material -------------------------------------------------------------

@dataclass
class Material:
    base_color: Tuple[float, float, float] = (0.85, 0.10, 0.18)   # albedo (linear)
    metallic:   float = 0.0
    roughness:  float = 0.4
    specular:   float = 0.5                                       # F0 for dielectrics
    clear_coat: float = 0.0
    clear_coat_roughness: float = 0.05
    anisotropy: float = 0.0
    emissive:   Tuple[float, float, float] = (0.0, 0.0, 0.0)
    # When False (default), an albedo_map's alpha channel is treated as
    # decorative-only and ignored — texture pixels with alpha < 255
    # still paint the model's surface with their RGB. The geometry's
    # own silhouette is what controls visibility. Set to True only for
    # explicit sticker / cutout effects (e.g. a wing photo where the
    # white-keyed background really should make the wings transparent).
    albedo_alpha_cutout:  bool = False
    # Texture maps (sampled at UV during shading). Each is an
    # ndarray (H, W, 4) uint8 or None.
    albedo_map:           np.ndarray | None = None    # multiplies base_color
    metallic_rough_map:   np.ndarray | None = None    # glTF spec: G=roughness, B=metallic
    ao_map:               np.ndarray | None = None    # R = ambient occlusion
    emissive_map:         np.ndarray | None = None    # multiplied into emissive
    normal_map:           np.ndarray | None = None    # tangent-space normals (rgb)
    # UV tiling on the maps (the mesh's own UVs are pre-multiplied by this).
    uv_scale: Tuple[float, float] = (1.0, 1.0)
    uv_offset: Tuple[float, float] = (0.0, 0.0)


def material_with_albedo(path) -> Material:
    """Convenience: build a default plastic Material with an albedo map."""
    from PIL import Image
    img = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8).copy()
    return Material(albedo_map=img)


_TEX_CACHE: dict[str, np.ndarray] = {}


def _load_texture(src) -> np.ndarray | None:
    """Resolve a Material texture slot to a numpy RGBA array, caching
    by path. Accepts either a string/Path filename or an already-loaded
    array (passes arrays through)."""
    if src is None: return None
    if isinstance(src, np.ndarray): return src
    key = str(src)
    cached = _TEX_CACHE.get(key)
    if cached is not None: return cached
    try:
        from PIL import Image
        img = Image.open(key).convert("RGBA")
        arr = np.asarray(img, dtype=np.uint8)
    except Exception as e:
        print(f"_load_texture: failed to load {key}: {e}", flush=True)
        return None
    _TEX_CACHE[key] = arr
    return arr


def _sample_texture(tex, uv: np.ndarray) -> np.ndarray:
    """Bilinear-ish (nearest for speed) wrap-mode lookup. `uv` is (..., 2)
    float32 in [0, 1] tile-space (already scaled/offset). Returns (..., 4)
    uint8. ``tex`` may be a numpy array or a path — strings are loaded
    via the cache on first use."""
    if not isinstance(tex, np.ndarray):
        loaded = _load_texture(tex)
        if loaded is None:
            return np.zeros(uv.shape[:-1] + (4,), dtype=np.uint8)
        tex = loaded
    H, W = tex.shape[:2]
    u = (np.mod(uv[..., 0], 1.0) * (W - 1)).astype(np.int32)
    v = (np.mod(1.0 - uv[..., 1], 1.0) * (H - 1)).astype(np.int32)
    return tex[v, u]


# --- Environment ----------------------------------------------------------

@dataclass
class Environment:
    """Analytic environment: zenith + horizon + ground gradient + sun.

    Optionally backed by a real equirectangular HDRI map. When `hdri`
    is set, `_sample_env` samples from it (with a `diffuse_blur` mip
    swap for indirect/diffuse lookups) instead of the analytic gradient.

    `hdri`        : (H, W, 3) float32 — radiance map, linear (already
                    decoded from .hdr RGBE or .exr).
    `hdri_intensity` : scalar gain (1.0 = neutral).
    """
    zenith:      Tuple[float, float, float] = (0.05, 0.10, 0.20)
    horizon:     Tuple[float, float, float] = (0.55, 0.50, 0.45)
    ground:      Tuple[float, float, float] = (0.02, 0.02, 0.02)
    sun_dir:     Tuple[float, float, float] = (0.35, 0.85, 0.40)
    sun_color:   Tuple[float, float, float] = (8.0, 7.0, 6.0)
    sun_softness: float = 0.06
    fill_dir:    Tuple[float, float, float] = (-0.6, 0.3, -0.5)
    fill_color:  Tuple[float, float, float] = (0.6, 0.7, 0.9)
    # Optional HDRI maps.
    hdri:        np.ndarray | None = None
    hdri_blur:   np.ndarray | None = None        # diffuse-irradiance mip (blurred)
    hdri_intensity: float = 1.0


# --- HDRI loading (.hdr / .exr) ------------------------------------------

def load_hdri(path: str | Path, intensity: float = 1.0) -> Environment:
    """Load an equirectangular HDRI (RGBE .hdr or .exr) into an Environment.
    Builds a pre-blurred irradiance map for IBL diffuse lookups."""
    suf = Path(path).suffix.lower()
    if suf == ".hdr":
        hdri = _load_hdr_rgbe(Path(path))
    elif suf == ".exr":
        hdri = _load_exr(Path(path))
    else:
        # PNG fallback — treat as already linear.
        hdri = (load_rgba_array(path)[..., :3].astype(np.float32) / 255.0)
    # Diffuse mip: heavy box blur.
    h, w = hdri.shape[:2]
    blur = _box_blur(hdri, radius=max(8, min(h, w) // 16))
    return Environment(hdri=hdri.astype(np.float32),
                       hdri_blur=blur.astype(np.float32),
                       hdri_intensity=float(intensity))


def load_rgba_array(path: str | Path) -> np.ndarray:
    """Load an image as an (H, W, 4) uint8 numpy array. Convenience for
    callers that don't want the texture module."""
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    return np.asarray(img, dtype=np.uint8).copy()


def _box_blur(img: np.ndarray, radius: int = 8) -> np.ndarray:
    """Separable box blur, wraps horizontally (env is panoramic)."""
    if radius <= 0:
        return img.copy()
    h, w = img.shape[:2]
    # Horizontal pass with wrap.
    cum = np.concatenate([img[:, -radius:], img, img[:, :radius]], axis=1)
    box = np.cumsum(cum, axis=1)
    win = 2 * radius + 1
    out = (box[:, win - 1:] - box[:, :-win + 1]) / win
    out = out[:, :w]
    # Vertical pass without wrap (top/bottom clamp).
    pad = np.concatenate([np.repeat(out[:1], radius, axis=0),
                          out,
                          np.repeat(out[-1:], radius, axis=0)], axis=0)
    box = np.cumsum(pad, axis=0)
    out = (box[win - 1:] - box[:-win + 1]) / win
    return out[:h]


def _load_hdr_rgbe(path: Path) -> np.ndarray:
    """Tiny RGBE/.hdr loader (Radiance format). Returns (H, W, 3) float32."""
    data = path.read_bytes()
    # Header is ASCII terminated by an empty line.
    head_end = data.find(b"\n\n")
    if head_end < 0:
        raise ValueError("not a Radiance .hdr")
    header = data[:head_end].decode("latin-1")
    body_start = head_end + 2
    # Resolution: "-Y h +X w" (or similar). Search for that line.
    import re
    m = re.search(r"-Y\s+(\d+)\s+\+X\s+(\d+)", data[head_end:head_end+200].decode("latin-1"))
    if not m:
        raise ValueError("can't find resolution in .hdr header")
    h = int(m.group(1)); w = int(m.group(2))
    # Advance to start of scanlines (after the resolution line).
    res_end = data.find(b"\n", head_end + 2) + 1
    pos = res_end
    out = np.empty((h, w, 3), dtype=np.float32)
    for y in range(h):
        # Each scanline begins with `0x02 0x02 (w>>8) (w&0xff)` if RLE.
        if pos + 4 > len(data):
            raise ValueError("scanline past end")
        if data[pos] == 2 and data[pos+1] == 2:
            sw = (data[pos+2] << 8) | data[pos+3]
            if sw != w:
                raise ValueError("RLE width mismatch")
            pos += 4
            chans = [bytearray(w) for _ in range(4)]
            for c in range(4):
                x = 0
                while x < w:
                    n = data[pos]; pos += 1
                    if n > 128:
                        n -= 128
                        v = data[pos]; pos += 1
                        for k in range(n):
                            chans[c][x + k] = v
                        x += n
                    else:
                        for k in range(n):
                            chans[c][x + k] = data[pos]; pos += 1
                        x += n
            rgbe = np.stack([np.frombuffer(b, dtype=np.uint8) for b in chans],
                            axis=-1)
        else:
            rgbe = np.frombuffer(data, dtype=np.uint8,
                                 count=w * 4, offset=pos).reshape(w, 4).copy()
            pos += w * 4
        # Convert RGBE → float radiance.
        r, g, b, e = (rgbe[:, 0].astype(np.float32),
                      rgbe[:, 1].astype(np.float32),
                      rgbe[:, 2].astype(np.float32),
                      rgbe[:, 3].astype(np.int32))
        f = np.ldexp(1.0, e - 128 - 8).astype(np.float32)
        out[y, :, 0] = r * f
        out[y, :, 1] = g * f
        out[y, :, 2] = b * f
    return out


def _load_exr(path: Path) -> np.ndarray:
    """OpenEXR loader (requires optional `OpenEXR` python package). Falls
    back to raising a friendly error otherwise."""
    try:
        import OpenEXR, Imath          # type: ignore
    except ImportError:
        raise RuntimeError("EXR support requires `pip install OpenEXR Imath`")
    f = OpenEXR.InputFile(str(path))
    dw = f.header()["dataWindow"]
    h = dw.max.y - dw.min.y + 1
    w = dw.max.x - dw.min.x + 1
    pt = Imath.PixelType(Imath.PixelType.FLOAT)
    r = np.frombuffer(f.channel("R", pt), dtype=np.float32).reshape(h, w)
    g = np.frombuffer(f.channel("G", pt), dtype=np.float32).reshape(h, w)
    b = np.frombuffer(f.channel("B", pt), dtype=np.float32).reshape(h, w)
    return np.stack([r, g, b], axis=-1)


# --- PBR math (vectorised) ------------------------------------------------

def _normalize(v):
    n = np.sqrt(np.sum(v * v, axis=-1, keepdims=True))
    return v / np.maximum(n, 1e-8)


def _dot(a, b):
    return np.sum(a * b, axis=-1, keepdims=True)


def _D_ggx(nh, alpha):
    a2 = alpha * alpha
    d = nh * nh * (a2 - 1.0) + 1.0
    return a2 / (math.pi * d * d + 1e-8)


def _G_smith(nv, nl, alpha):
    k = (alpha + 1.0) ** 2 / 8.0
    gv = nv / (nv * (1.0 - k) + k)
    gl = nl / (nl * (1.0 - k) + k)
    return gv * gl


def _F_schlick(F0, vh):
    return F0 + (1.0 - F0) * np.power(np.clip(1.0 - vh, 0.0, 1.0), 5)


def _sample_env(env: Environment, dir_, *, blurred: bool = False):
    """Cheap analytic environment lookup (or HDRI panorama lookup when
    `env.hdri` is set). `dir_` is unit-length world-space.

    `blurred=True` taps the pre-blurred mip for IBL diffuse/indirect."""
    # HDRI panorama path.
    if env.hdri is not None:
        src = env.hdri_blur if (blurred and env.hdri_blur is not None) else env.hdri
        H, W = src.shape[:2]
        # Equirectangular: x = atan2(z, x) / (2π) + 0.5; y = acos(-y) / π
        d = dir_.astype(np.float32)
        u = np.arctan2(d[..., 2], d[..., 0]) / (2.0 * math.pi) + 0.5
        v = np.arccos(np.clip(-d[..., 1], -1.0, 1.0)) / math.pi
        x = (np.mod(u, 1.0) * (W - 1)).astype(np.int32)
        y = np.clip((v * (H - 1)).astype(np.int32), 0, H - 1)
        env_rgb = src[y, x] * env.hdri_intensity
        return env_rgb.astype(np.float32)

    # Analytic fallback.
    y = np.clip(dir_[..., 1:2], -1.0, 1.0)
    z  = np.array(env.zenith,  dtype=np.float32)
    h  = np.array(env.horizon, dtype=np.float32)
    g  = np.array(env.ground,  dtype=np.float32)
    above = h + (z - h) * np.clip(y, 0.0, 1.0)
    below = h + (g - h) * np.clip(-y, 0.0, 1.0)
    base = np.where(y > 0, above, below)
    sun_d = _normalize(np.array(env.sun_dir, dtype=np.float32))
    cos_sun = np.sum(dir_ * sun_d, axis=-1, keepdims=True)
    sun = np.clip((cos_sun - (1.0 - env.sun_softness)) / max(env.sun_softness, 1e-4),
                  0.0, 1.0)
    base = base + (sun * sun) * np.array(env.sun_color, dtype=np.float32)
    return base.astype(np.float32)


def _sample_material_textures(mat: Material, uvs: np.ndarray | None) -> dict:
    """Sample whichever texture maps are bound. Returns a dict of override
    arrays keyed by:
      base_color  : (P, 3) float32 in [0, 1]
      metallic    : (P,)   float32
      roughness   : (P,)   float32
      ao          : (P, 1) float32 — multiplies indirect
      emissive    : (P, 3) float32 — additive
    Missing keys → use the Material's scalar value at shade time."""
    if uvs is None:
        return {}
    out: dict = {}
    uv = uvs * np.array(mat.uv_scale, dtype=np.float32) + np.array(mat.uv_offset, dtype=np.float32)
    if mat.albedo_map is not None:
        tex = _sample_texture(mat.albedo_map, uv)
        # Albedo textures are stored sRGB-encoded (standard PNG convention).
        # Linearise before PBR math — otherwise we apply the gamma curve
        # twice (once on read, once in _linear_to_srgb at output), which
        # shifts hues toward warm tones and darkens blues. This was the
        # cause of "the blue Morpho atlas renders as red wings".
        srgb = tex[..., :3].astype(np.float32) / 255.0
        # sRGB → linear (piecewise gamma 2.4 approximation).
        linear = np.where(srgb <= 0.04045,
                           srgb / 12.92,
                           ((srgb + 0.055) / 1.055) ** 2.4)
        base = linear * np.array(mat.base_color, dtype=np.float32)
        out["base_color"] = base
        # By default, an albedo's alpha channel is decorative-only — it
        # tints colour, not visibility. A texture must NEVER be allowed
        # to punch holes in the mesh silhouette. Callers that genuinely
        # want a cutout / sticker effect can opt-in via
        # `Material.albedo_alpha_cutout = True`.
        if tex.shape[-1] >= 4 and getattr(mat, "albedo_alpha_cutout", False):
            out["alpha"] = tex[..., 3].astype(np.float32) / 255.0
    if mat.metallic_rough_map is not None:
        tex = _sample_texture(mat.metallic_rough_map, uv)
        # glTF convention: G = roughness, B = metallic
        out["roughness"] = (tex[..., 1].astype(np.float32) / 255.0) * mat.roughness * 2
        out["metallic"]  = (tex[..., 2].astype(np.float32) / 255.0) * max(mat.metallic, 1.0)
    if mat.ao_map is not None:
        tex = _sample_texture(mat.ao_map, uv)
        out["ao"] = (tex[..., 0:1].astype(np.float32) / 255.0)
    if mat.emissive_map is not None:
        tex = _sample_texture(mat.emissive_map, uv)
        out["emissive"] = tex[..., :3].astype(np.float32) / 255.0
    return out


def _resolve(name: str, mat_value, override: dict | None):
    if override and name in override:
        return override[name]
    return mat_value


def _shade_pixels(N, V, L, light_color, mat: Material,
                  override: dict | None = None) -> np.ndarray:
    """Direct lighting from one light. N, V, L are unit-length per pixel."""
    H = _normalize(L + V)
    nl = np.clip(_dot(N, L), 0.0, 1.0)
    nv = np.clip(_dot(N, V), 0.0, 1.0) + 1e-5
    nh = np.clip(_dot(N, H), 0.0, 1.0)
    vh = np.clip(_dot(V, H), 0.0, 1.0)

    base = _resolve("base_color",
                    np.array(mat.base_color, dtype=np.float32),
                    override)
    if override and isinstance(_resolve("metallic", None, override), np.ndarray):
        metallic = override["metallic"][:, None]
    else:
        metallic = float(mat.metallic)
    rough_val = _resolve("roughness", float(mat.roughness), override)
    if isinstance(rough_val, np.ndarray):
        alpha = np.maximum(rough_val * rough_val, 1e-3)[:, None]
    else:
        alpha = max(rough_val * rough_val, 1e-3)

    # F0: 4% reflectance for dielectrics; base_color for metals.
    F0_d = np.array([0.04 * mat.specular * 2.0] * 3, dtype=np.float32)
    F0 = (1.0 - metallic) * F0_d + metallic * base
    F = _F_schlick(F0, vh)

    D = _D_ggx(nh, alpha)
    G = _G_smith(nv, nl, alpha)
    spec = F * D * G / (4.0 * nl * nv + 1e-5)

    kD = (1.0 - F) * (1.0 - metallic)
    diff = kD * base / math.pi

    direct = (diff + spec) * light_color * nl

    # Clear-coat layer (achromatic dielectric on top).
    if mat.clear_coat > 0:
        cc_alpha = max(mat.clear_coat_roughness ** 2, 1e-3)
        D_cc = _D_ggx(nh, cc_alpha)
        G_cc = _G_smith(nv, nl, cc_alpha)
        F_cc = _F_schlick(np.array([0.04, 0.04, 0.04], dtype=np.float32), vh) * mat.clear_coat
        spec_cc = F_cc * D_cc * G_cc / (4.0 * nl * nv + 1e-5)
        # Below the clearcoat the energy is attenuated by 1-F_cc.
        direct = direct * (1.0 - F_cc) + spec_cc * light_color * nl

    return direct


def _ibl_indirect(N, V, mat: Material, env: Environment,
                  override: dict | None = None) -> np.ndarray:
    """Crude split-sum approximation: diffuse irradiance ≈ env(N),
    specular ≈ env(reflect(-V, N)) blurred by roughness."""
    base = _resolve("base_color",
                    np.array(mat.base_color, dtype=np.float32),
                    override)
    metallic = _resolve("metallic", float(mat.metallic), override)
    if isinstance(metallic, np.ndarray):
        metallic = metallic[:, None]
    rough_val = _resolve("roughness", float(mat.roughness), override)
    if isinstance(rough_val, np.ndarray):
        rough = rough_val[:, None]
    else:
        rough = rough_val

    F0_d = np.array([0.04 * mat.specular * 2.0] * 3, dtype=np.float32)
    F0 = (1.0 - metallic) * F0_d + metallic * base
    nv = np.clip(_dot(N, V), 0.0, 1.0)
    F = F0 + (np.maximum(np.array([1.0, 1.0, 1.0]) - F0, F0) - F0) * np.power(1.0 - nv, 5)

    # Diffuse: roughly the irradiance at N — use the pre-blurred mip if avail.
    diffuse_env = _sample_env(env, N, blurred=True)
    diffuse = (1.0 - F) * (1.0 - metallic) * base * diffuse_env

    # Specular: reflected dir, blurred for roughness.
    R = _normalize(2.0 * _dot(N, V) * N - V)
    spec_env = _sample_env(env, R)
    # Mix in a less-directional (blurred-mip) sample for high roughness.
    spec_env_blur = _sample_env(env, N, blurred=True)
    blur = rough
    spec_env = spec_env * (1.0 - blur) + spec_env_blur * blur
    specular = F * spec_env

    indirect = diffuse + specular

    # Clear-coat indirect.
    if mat.clear_coat > 0:
        cc_F = 0.04 + (1.0 - 0.04) * np.power(1.0 - nv, 5)
        cc_F = cc_F * mat.clear_coat
        cc_R = R  # same reflection
        cc_env = _sample_env(env, cc_R)
        cc_env_blur = _sample_env(env, N, blurred=True)
        cc_blur = mat.clear_coat_roughness
        cc_env = cc_env * (1.0 - cc_blur) + cc_env_blur * cc_blur
        indirect = indirect * (1.0 - cc_F) + cc_env * cc_F

    return indirect


def _aces(x):
    """ACES filmic tone-mapping curve."""
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0)


def _linear_to_srgb(c):
    return np.where(c <= 0.0031308, c * 12.92,
                    1.055 * np.power(np.maximum(c, 0.0), 1.0 / 2.4) - 0.055)


# --- Sphere ray-march -----------------------------------------------------

def render_sphere(w: int, h: int, mat: Material, env: Environment,
                  cam_dist: float = 2.6) -> bytes:
    """Render a unit sphere centred at the origin into an `w*h*4` RGBA byte
    buffer (premultiplied alpha)."""
    j, i = np.meshgrid(np.arange(h, dtype=np.float32),
                       np.arange(w, dtype=np.float32),
                       indexing="ij")
    # NDC in [-1, 1].
    u = (i / (w - 1)) * 2.0 - 1.0
    v = -((j / (h - 1)) * 2.0 - 1.0)
    aspect = w / h
    u = u * aspect

    # Camera at +Z looking toward origin (perspective).
    fov = math.radians(35)
    f = 1.0 / math.tan(fov * 0.5)
    ray_d = _normalize(np.stack([u, v, np.full_like(u, -f)], axis=-1))
    ray_o = np.array([0.0, 0.0, cam_dist], dtype=np.float32)

    # Ray-sphere intersection (radius 1.0).
    b = np.sum(ray_d * (-ray_o), axis=-1, keepdims=True)
    c = np.sum(ray_o * ray_o) - 1.0
    disc = b * b - c
    hit = disc[..., 0] > 0
    t = b - np.sqrt(np.maximum(disc, 0.0))
    P = ray_o + ray_d * t                       # surface point
    N = _normalize(P)
    V = _normalize(-ray_d)

    # Direct lights.
    L_key  = _normalize(np.array(env.sun_dir, dtype=np.float32))
    L_fill = _normalize(np.array(env.fill_dir, dtype=np.float32))
    direct_key  = _shade_pixels(N, V, L_key,
                                np.array(env.sun_color, dtype=np.float32) * 0.5, mat)
    direct_fill = _shade_pixels(N, V, L_fill,
                                np.array(env.fill_color, dtype=np.float32), mat)

    # Indirect (IBL).
    indirect = _ibl_indirect(N, V, mat, env)

    color = direct_key + direct_fill + indirect + np.array(mat.emissive,
                                                            dtype=np.float32)

    # Background = environment sampled along view ray.
    bg = _sample_env(env, ray_d) * 0.5         # half-strength backdrop
    pixel = np.where(hit[..., None], color, bg)

    # Tone-map + sRGB encode.
    pixel = _aces(pixel)
    pixel = _linear_to_srgb(pixel)

    rgb = np.clip(pixel * 255.0, 0.0, 255.0).astype(np.uint8)
    alpha = np.full((h, w, 1), 255, dtype=np.uint8)
    rgba = np.concatenate([rgb, alpha], axis=-1)
    return rgba.tobytes()


# --- PNG encoder (no Skia dep needed for the offscreen preview) -----------

def rgba_to_png(rgba: bytes, w: int, h: int) -> bytes:
    """Encode an RGBA8 byte buffer (row-major, ``w * h * 4`` bytes) as PNG
    via PIL/libpng.

    The previous hand-rolled encoder produced a structurally valid PNG that
    PIL decoded correctly but Skia mis-decoded into a 1-row image (only the
    first scanline of pixel data made it through, leaving a 280×1 strip on
    the Designer canvas when the result was blitted to a 280×280 destination).
    Using libpng's encoder via PIL avoids whatever Skia disagreed with."""
    import io
    from PIL import Image
    im = Image.frombuffer("RGBA", (w, h), rgba, "raw", "RGBA", 0, 1)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


# --- Material library presets --------------------------------------------

PRESETS: dict[str, Material] = {
    "Plastic — Red":    Material(base_color=(0.85, 0.10, 0.10), metallic=0.0, roughness=0.30),
    "Plastic — Glossy":  Material(base_color=(0.15, 0.30, 0.85), metallic=0.0, roughness=0.10),
    "Plastic — Matte":   Material(base_color=(0.40, 0.40, 0.42), metallic=0.0, roughness=0.85),
    "Metal — Gold":      Material(base_color=(1.00, 0.78, 0.34), metallic=1.0, roughness=0.18),
    "Metal — Silver":    Material(base_color=(0.95, 0.95, 0.95), metallic=1.0, roughness=0.08),
    "Metal — Copper":    Material(base_color=(0.95, 0.64, 0.54), metallic=1.0, roughness=0.20),
    "Metal — Chrome":    Material(base_color=(0.92, 0.92, 0.92), metallic=1.0, roughness=0.02),
    "Metal — Brushed":   Material(base_color=(0.70, 0.71, 0.72), metallic=1.0, roughness=0.45),
    "Paint — Car Black": Material(base_color=(0.02, 0.02, 0.02), metallic=0.0, roughness=0.18,
                                  clear_coat=1.0, clear_coat_roughness=0.04),
    "Paint — Candy Red": Material(base_color=(0.85, 0.05, 0.10), metallic=1.0, roughness=0.30,
                                  clear_coat=1.0, clear_coat_roughness=0.03),
    "Paint — Pearl":     Material(base_color=(0.92, 0.90, 0.96), metallic=0.4, roughness=0.20,
                                  clear_coat=1.0, clear_coat_roughness=0.05),
    "Glass — Frosted":   Material(base_color=(0.95, 0.95, 0.98), metallic=0.0, roughness=0.55,
                                  clear_coat=1.0, clear_coat_roughness=0.45),
    "Rubber — Tire":     Material(base_color=(0.05, 0.05, 0.05), metallic=0.0, roughness=0.95),
    "Wax":               Material(base_color=(0.95, 0.90, 0.70), metallic=0.0, roughness=0.65,
                                  clear_coat=0.3, clear_coat_roughness=0.30),
    "Emissive — Lamp":   Material(base_color=(0.10, 0.10, 0.10), metallic=0.0, roughness=0.4,
                                  emissive=(2.5, 1.6, 0.6)),
    # Phase 1n — generic-named replacement for the original
    # "Iridescent — Wing" preset. "Membrane" covers wings, fins, sails,
    # leaves, and any thin iridescent surface, so the preset doesn't
    # read as butterfly-specific in the materials picker. The old
    # "Iridescent — Wing" key is kept as an alias below for back-compat.
    "Iridescent — Membrane": Material(base_color=(0.30, 0.55, 0.95), metallic=0.85, roughness=0.30,
                                       clear_coat=0.8, clear_coat_roughness=0.10),
    "Body — Charcoal":   Material(base_color=(0.08, 0.06, 0.05), metallic=0.0, roughness=0.55),
}
# Back-compat aliases (Phase 1n).
PRESETS["Iridescent — Wing"] = PRESETS["Iridescent — Membrane"]


# =========================================================================
# Triangle-mesh PBR renderer
# =========================================================================

@dataclass
class Mesh:
    """A triangle mesh with optional per-face material indices.

    verts:        (N, 3) float32 — vertex positions
    faces:        (M, 3) int32   — vertex indices per triangle
    face_mats:    (M,)   int32   — index into `materials` for each face
                                   (omit → all faces share materials[0])
    """
    verts:     np.ndarray
    faces:     np.ndarray
    face_mats: np.ndarray | None = None
    # Per-vertex normals are computed on demand from face normals if absent.
    vert_normals: np.ndarray | None = None
    # Per-vertex UVs for texture sampling (None ⇒ no UV channel).
    vert_uvs: np.ndarray | None = None
    # Rigged-mesh metadata. Populated by the .3ds loader (and any other
    # loader that preserves named sub-meshes). Per-vertex part_id indexes
    # `part_names` / `part_pivots`. The flap helper uses these to rotate
    # named wings around their proper pivots instead of guessing left/right
    # by x-coordinate.
    vert_part_ids: np.ndarray | None = None       # (N,) uint8
    part_names:    list[str]  | None = None       # part_id → original name
    part_pivots:   np.ndarray | None = None       # (P, 3) float32 world pivot


# --- BVH acceleration structure ------------------------------------------

@dataclass
class _BVHNode:
    """A single BVH node. `tri_start`/`tri_end` is non-empty only for leaves."""
    aabb_min: np.ndarray                       # (3,)
    aabb_max: np.ndarray                       # (3,)
    left:  int = -1
    right: int = -1
    tri_start: int = -1
    tri_end:   int = -1


@dataclass
class BVH:
    """Flat array-of-nodes BVH built from triangle AABBs.

    Built once per (mesh+world-transform) by `build_bvh`; queried via
    `intersect_rays_bvh`. Vectorised stack-walk over rays."""
    nodes:    list[_BVHNode]          # flat
    tri_order: np.ndarray             # (M,) int32 — triangle indices in leaves
    # AABBs and centroids cached for traversal speed:
    node_min: np.ndarray              # (N, 3) float32
    node_max: np.ndarray              # (N, 3) float32
    node_left:  np.ndarray            # (N,) int32
    node_right: np.ndarray            # (N,) int32
    node_tri_start: np.ndarray        # (N,) int32
    node_tri_end:   np.ndarray        # (N,) int32


def build_bvh(verts: np.ndarray, faces: np.ndarray, leaf_max: int = 4) -> BVH:
    """Median-split BVH. Trivial cost-model but plenty fast for ≤50 k tris."""
    tri_min = np.minimum(np.minimum(verts[faces[:, 0]], verts[faces[:, 1]]),
                         verts[faces[:, 2]])
    tri_max = np.maximum(np.maximum(verts[faces[:, 0]], verts[faces[:, 1]]),
                         verts[faces[:, 2]])
    tri_center = (tri_min + tri_max) * 0.5
    M = faces.shape[0]
    order = np.arange(M, dtype=np.int32)
    nodes: list[_BVHNode] = []

    def build(start: int, end: int) -> int:
        idx = len(nodes)
        seg = order[start:end]
        aabb_min = tri_min[seg].min(axis=0)
        aabb_max = tri_max[seg].max(axis=0)
        node = _BVHNode(aabb_min=aabb_min, aabb_max=aabb_max)
        nodes.append(node)
        if end - start <= leaf_max:
            node.tri_start = start
            node.tri_end   = end
            return idx
        # Pick the longest axis and split at median centroid.
        extents = aabb_max - aabb_min
        axis = int(np.argmax(extents))
        centers = tri_center[seg, axis]
        med = np.median(centers)
        left_mask = centers <= med
        # Avoid degenerate (all-same) splits.
        if left_mask.all() or (~left_mask).all():
            mid = (end - start) // 2
            sort_idx = np.argsort(centers, kind="stable")
            order[start:end] = seg[sort_idx]
            split = start + mid
        else:
            left_idx  = seg[left_mask]
            right_idx = seg[~left_mask]
            order[start:start+len(left_idx)]            = left_idx
            order[start+len(left_idx):start+len(left_idx)+len(right_idx)] = right_idx
            split = start + len(left_idx)
        node.left  = build(start, split)
        node.right = build(split, end)
        return idx

    build(0, M)
    n = len(nodes)
    return BVH(
        nodes=nodes,
        tri_order=order.copy(),
        node_min=np.stack([n_.aabb_min for n_ in nodes], axis=0).astype(np.float32),
        node_max=np.stack([n_.aabb_max for n_ in nodes], axis=0).astype(np.float32),
        node_left =np.array([n_.left  for n_ in nodes], dtype=np.int32),
        node_right=np.array([n_.right for n_ in nodes], dtype=np.int32),
        node_tri_start=np.array([n_.tri_start for n_ in nodes], dtype=np.int32),
        node_tri_end  =np.array([n_.tri_end   for n_ in nodes], dtype=np.int32),
    )


def _ray_aabb(ray_o: np.ndarray, inv_d: np.ndarray,
              bbmin: np.ndarray, bbmax: np.ndarray) -> np.ndarray:
    """Vectorised ray-AABB slab test. Returns hit-mask (P,) for one AABB."""
    t1 = (bbmin - ray_o) * inv_d
    t2 = (bbmax - ray_o) * inv_d
    tmin = np.maximum.reduce([np.minimum(t1[..., 0], t2[..., 0]),
                              np.minimum(t1[..., 1], t2[..., 1]),
                              np.minimum(t1[..., 2], t2[..., 2])])
    tmax = np.minimum.reduce([np.maximum(t1[..., 0], t2[..., 0]),
                              np.maximum(t1[..., 1], t2[..., 1]),
                              np.maximum(t1[..., 2], t2[..., 2])])
    return (tmax >= np.maximum(tmin, 0.0))


@dataclass
class MeshObject:
    """A mesh placed in world space, with one or more materials and a
    rotation/translation/scale transform (the wireframing rig)."""
    mesh:      Mesh
    materials: list[Material]
    rotation:  Tuple[float, float, float] = (0.0, 0.0, 0.0)   # XYZ Euler, radians
    translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale:       Tuple[float, float, float] = (1.0, 1.0, 1.0)


_BVH_CACHE: dict[int, tuple[int, BVH]] = {}


def _cached_bvh_for(obj: MeshObject, verts_w: np.ndarray) -> BVH:
    """Cache a BVH per MeshObject identity. Re-builds when the world-space
    verts' content hash changes (i.e. after rotation/scale change)."""
    key = id(obj)
    h = int(verts_w.tobytes().__hash__() if hasattr(verts_w.tobytes(), "__hash__")
            else hash(verts_w.tobytes()))
    cached = _BVH_CACHE.get(key)
    if cached is not None and cached[0] == h:
        return cached[1]
    bvh = build_bvh(verts_w, obj.mesh.faces)
    _BVH_CACHE[key] = (h, bvh)
    # GC: cap cache size.
    if len(_BVH_CACHE) > 32:
        for k in list(_BVH_CACHE.keys())[:16]:
            _BVH_CACHE.pop(k, None)
    return bvh


def _euler_rot(a: float, b: float, c: float) -> np.ndarray:
    """ZYX Euler-to-rotation matrix, returning a 3×3 float32 matrix."""
    cx, sx = math.cos(a), math.sin(a)
    cy, sy = math.cos(b), math.sin(b)
    cz, sz = math.cos(c), math.sin(c)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    return (Rz @ Ry @ Rx).astype(np.float32)


def _world_transform(obj: MeshObject) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (world_verts, world_normals, face_centers) for a MeshObject."""
    R = _euler_rot(*obj.rotation)
    s = np.array(obj.scale, dtype=np.float32)
    t = np.array(obj.translation, dtype=np.float32)
    verts = obj.mesh.verts * s
    verts = verts @ R.T + t
    # Face normals from world verts.
    v0 = verts[obj.mesh.faces[:, 0]]
    v1 = verts[obj.mesh.faces[:, 1]]
    v2 = verts[obj.mesh.faces[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    centers = (v0 + v1 + v2) / 3.0
    return verts, n.astype(np.float32), centers.astype(np.float32)


# --- Möller–Trumbore ray–triangle (vectorised over triangles) ------------

def _intersect_rays_mesh_brute(ray_o: np.ndarray, ray_d: np.ndarray,
                               verts: np.ndarray, faces: np.ndarray,
                               tri_subset: np.ndarray | None = None
                               ) -> tuple[np.ndarray, np.ndarray,
                                          np.ndarray, np.ndarray]:
    """Brute Möller–Trumbore. Returns (t_min, face_idx, bary_u, bary_v).

    `bary_u`, `bary_v` are the barycentric coordinates of the hit point
    so the caller can interpolate per-vertex attributes (UVs, normals)."""
    eps = 1e-6
    if tri_subset is None:
        sel_faces = faces
        sel_global = np.arange(faces.shape[0], dtype=np.int64)
    else:
        sel_faces = faces[tri_subset]
        sel_global = tri_subset
    v0 = verts[sel_faces[:, 0]]
    v1 = verts[sel_faces[:, 1]]
    v2 = verts[sel_faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0
    P = ray_o.shape[0]
    pv = np.cross(ray_d[:, None, :], e2[None, :, :])
    det = np.sum(e1[None, :, :] * pv, axis=-1)
    inv_det = 1.0 / np.where(np.abs(det) < eps, 1e30, det)
    tv = ray_o[:, None, :] - v0[None, :, :]
    u = np.sum(tv * pv, axis=-1) * inv_det
    qv = np.cross(tv, e1[None, :, :])
    v = np.sum(ray_d[:, None, :] * qv, axis=-1) * inv_det
    t = np.sum(e2[None, :, :] * qv, axis=-1) * inv_det
    hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > eps)
    t = np.where(hit, t, np.inf)
    local_idx = np.argmin(t, axis=1)
    t_min = t[np.arange(P), local_idx]
    face_idx = sel_global[local_idx]
    bu = u[np.arange(P), local_idx]
    bv = v[np.arange(P), local_idx]
    miss = ~np.isfinite(t_min)
    face_idx = np.where(miss, -1, face_idx)
    return (t_min.astype(np.float32), face_idx.astype(np.int64),
            bu.astype(np.float32), bv.astype(np.float32))


def _intersect_rays_bvh(ray_o: np.ndarray, ray_d: np.ndarray,
                        verts: np.ndarray, faces: np.ndarray,
                        bvh: BVH) -> tuple[np.ndarray, np.ndarray,
                                            np.ndarray, np.ndarray]:
    """BVH-accelerated traversal. Returns (t, face_idx, bary_u, bary_v)."""
    P = ray_o.shape[0]
    inv_d = 1.0 / np.where(np.abs(ray_d) < 1e-12, 1e-12, ray_d)
    t_best   = np.full(P, np.inf, dtype=np.float32)
    face_idx = np.full(P, -1,    dtype=np.int64)
    bary_u   = np.zeros(P,        dtype=np.float32)
    bary_v   = np.zeros(P,        dtype=np.float32)

    stack: list[tuple[int, np.ndarray]] = [(0, np.ones(P, dtype=bool))]
    while stack:
        nidx, mask = stack.pop()
        if not mask.any():
            continue
        bbmin = bvh.node_min[nidx]
        bbmax = bvh.node_max[nidx]
        sub_o = ray_o[mask]
        sub_d_inv = inv_d[mask]
        aabb_hit = _ray_aabb(sub_o, sub_d_inv, bbmin, bbmax)
        if not aabb_hit.any():
            continue
        mask_idx = np.where(mask)[0]
        live_idx = mask_idx[aabb_hit]
        ts = bvh.node_tri_start[nidx]
        te = bvh.node_tri_end[nidx]
        if ts >= 0:
            tri_subset = bvh.tri_order[ts:te]
            t_min, f_min, bu, bv = _intersect_rays_mesh_brute(
                ray_o[live_idx], ray_d[live_idx], verts, faces, tri_subset)
            better = t_min < t_best[live_idx]
            sub_set = live_idx[better]
            t_best[sub_set]   = t_min[better]
            face_idx[sub_set] = f_min[better]
            bary_u[sub_set]   = bu[better]
            bary_v[sub_set]   = bv[better]
        else:
            live_mask = np.zeros(P, dtype=bool)
            live_mask[live_idx] = True
            stack.append((int(bvh.node_left[nidx]),  live_mask))
            stack.append((int(bvh.node_right[nidx]), live_mask))

    return t_best, face_idx, bary_u, bary_v


def _intersect_rays_mesh(ray_o: np.ndarray, ray_d: np.ndarray,
                         verts: np.ndarray, faces: np.ndarray,
                         bvh: BVH | None = None
                         ) -> tuple[np.ndarray, np.ndarray,
                                    np.ndarray, np.ndarray]:
    """Returns (t, face_idx, bary_u, bary_v). Bary coords let callers
    interpolate per-vertex attributes (UVs, vertex normals)."""
    if bvh is None or faces.shape[0] < 64:
        return _intersect_rays_mesh_brute(ray_o, ray_d, verts, faces)
    return _intersect_rays_bvh(ray_o, ray_d, verts, faces, bvh)


# --- Mesh PBR render -----------------------------------------------------

def render_mesh(w: int, h: int, obj: MeshObject, env: Environment,
                cam_dist: float = 3.5, cam_yaw: float = 0.4, cam_pitch: float = 0.25,
                wireframe: bool = False, wireframe_width: float = 1.0,
                transparent_bg: bool = False) -> bytes:
    """Render a MeshObject with Cook-Torrance PBR + IBL. Returns RGBA bytes.

    When ``transparent_bg`` is True, pixels that don't hit the mesh
    are written as fully-transparent (alpha=0) instead of the env's
    half-strength backdrop — the right thing for compositing the mesh
    over a translucent UI."""
    # Camera basis: orbit around origin.
    cy_, sy_ = math.cos(cam_yaw), math.sin(cam_yaw)
    cp_, sp_ = math.cos(cam_pitch), math.sin(cam_pitch)
    cam_pos = np.array([cam_dist * cp_ * sy_,
                        cam_dist * sp_,
                        cam_dist * cp_ * cy_], dtype=np.float32)
    look = -cam_pos / max(np.linalg.norm(cam_pos), 1e-8)
    up_w = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(look, up_w); right /= max(np.linalg.norm(right), 1e-8)
    up = np.cross(right, look)

    # Ray grid.
    j, i = np.meshgrid(np.arange(h, dtype=np.float32),
                       np.arange(w, dtype=np.float32),
                       indexing="ij")
    u = (i / (w - 1)) * 2.0 - 1.0
    v = -((j / (h - 1)) * 2.0 - 1.0)
    aspect = w / h
    fov = math.radians(38)
    f = 1.0 / math.tan(fov * 0.5)
    rd = (u[..., None] * aspect) * right + v[..., None] * up + f * look
    rd = rd / np.maximum(np.linalg.norm(rd, axis=-1, keepdims=True), 1e-8)
    rd_flat = rd.reshape(-1, 3)
    ro_flat = np.broadcast_to(cam_pos, rd_flat.shape).copy()

    # Mesh world geom + intersect.
    verts_w, face_normals, face_centers = _world_transform(obj)
    # BVH is built lazily and cached on the Mesh object (works because the
    # mesh's local-space triangle topology is what's split — world transform
    # only changes the AABBs by a rigid motion, but we rebuild against the
    # transformed verts so AABBs are tight).
    bvh = _cached_bvh_for(obj, verts_w)
    t_min, face_idx, bary_u, bary_v = _intersect_rays_mesh(
        ro_flat, rd_flat, verts_w, obj.mesh.faces, bvh=bvh)
    hit_mask = face_idx >= 0

    # Shade hit pixels.
    color_buf = np.zeros((w * h, 3), dtype=np.float32)

    # Background — environment along the view ray, unless the caller
    # wants the bg punched out for compositing.
    if not transparent_bg:
        bg = _sample_env(env, rd_flat) * 0.55
        color_buf[:] = bg

    if hit_mask.any():
        fidx = face_idx[hit_mask]
        N = face_normals[fidx]
        # Flip normals if back-facing (front-facing only).
        V = -rd_flat[hit_mask]
        n_dot_v = np.sum(N * V, axis=-1, keepdims=True)
        N = np.where(n_dot_v < 0, -N, N)

        # Material per-face.
        if obj.mesh.face_mats is not None:
            mat_idx = obj.mesh.face_mats[fidx]
        else:
            mat_idx = np.zeros_like(fidx)

        # Per-hit UVs from barycentric coords (if the mesh has UVs).
        uvs_hit = None
        if obj.mesh.vert_uvs is not None:
            bu = bary_u[hit_mask]
            bv = bary_v[hit_mask]
            verts_uv = obj.mesh.vert_uvs[obj.mesh.faces[fidx]]   # (P, 3, 2)
            w0 = 1.0 - bu - bv
            uvs_hit = (verts_uv[:, 0] * w0[:, None]
                       + verts_uv[:, 1] * bu[:, None]
                       + verts_uv[:, 2] * bv[:, None])

        unique_mats = np.unique(mat_idx)
        shaded = np.zeros((fidx.shape[0], 3), dtype=np.float32)
        # Per-hit alpha — starts opaque; texture sampler may pull it down
        # for alpha-keyed maps (e.g. wing photo with white background).
        hit_alpha = np.ones(fidx.shape[0], dtype=np.float32)
        L_key  = _normalize(np.array(env.sun_dir, dtype=np.float32))[None, :]
        L_fill = _normalize(np.array(env.fill_dir, dtype=np.float32))[None, :]
        for m in unique_mats:
            mask = mat_idx == m
            mat = obj.materials[m] if m < len(obj.materials) else obj.materials[0]
            # Sample texture maps at the hit UVs (where available).
            tex_override = _sample_material_textures(
                mat, uvs_hit[mask] if uvs_hit is not None else None)
            Nm, Vm = N[mask], V[mask]
            dk = _shade_pixels(Nm, Vm,
                               np.broadcast_to(L_key, Nm.shape),
                               np.array(env.sun_color, dtype=np.float32) * 0.5,
                               mat, tex_override)
            df = _shade_pixels(Nm, Vm,
                               np.broadcast_to(L_fill, Nm.shape),
                               np.array(env.fill_color, dtype=np.float32),
                               mat, tex_override)
            ind = _ibl_indirect(Nm, Vm, mat, env, tex_override)
            emiss = np.array(mat.emissive, dtype=np.float32)
            if tex_override and "emissive" in tex_override:
                emiss = emiss + tex_override["emissive"]
            # AO multiplies the indirect term.
            ao = tex_override.get("ao", 1.0) if tex_override else 1.0
            shaded[mask] = dk + df + ind * ao + emiss
            if tex_override and "alpha" in tex_override:
                hit_alpha[mask] = tex_override["alpha"]
        color_buf[hit_mask] = shaded

    # Wireframe overlay (rasterised after shading).
    if wireframe:
        _draw_wireframe(color_buf, w, h, verts_w, obj.mesh.faces,
                        cam_pos, look, right, up, f, aspect,
                        line_w=wireframe_width)

    # Tone-map + sRGB.
    img = color_buf.reshape(h, w, 3)
    img = _aces(img); img = _linear_to_srgb(img)
    rgb = np.clip(img * 255.0, 0.0, 255.0).astype(np.uint8)
    if transparent_bg:
        # Combine triangle-hit alpha with any texture-supplied alpha.
        full_alpha = np.zeros(w * h, dtype=np.float32)
        if hit_mask.any():
            full_alpha[hit_mask] = hit_alpha
        alpha = (np.clip(full_alpha, 0, 1) * 255).astype(np.uint8).reshape(h, w, 1)
    else:
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
    rgba = np.concatenate([rgb, alpha], axis=-1)
    return rgba.tobytes()


def render_mesh_uvmap(w: int, h: int, obj: MeshObject,
                       cam_dist: float = 3.5,
                       cam_yaw: float = 0.4,
                       cam_pitch: float = 0.25) -> tuple:
    """Like ``render_mesh_partmap`` but also returns the per-pixel UV
    coordinates of the hit point (barycentric interpolation over the
    hit face's three vertex UVs). Returns
        face_idx : (h, w) int32  — -1 for miss
        part_id  : (h, w) int16  — -1 for miss
        uv_xy    : (h, w, 2) float32  — (u, v) per hit pixel; (nan, nan) for miss
    Camera maths are byte-identical to ``render_mesh`` so the same
    pixel grid is sampled."""
    cy_, sy_ = math.cos(cam_yaw), math.sin(cam_yaw)
    cp_, sp_ = math.cos(cam_pitch), math.sin(cam_pitch)
    cam_pos = np.array([cam_dist * cp_ * sy_,
                        cam_dist * sp_,
                        cam_dist * cp_ * cy_], dtype=np.float32)
    look = -cam_pos / max(np.linalg.norm(cam_pos), 1e-8)
    up_w = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(look, up_w); right /= max(np.linalg.norm(right), 1e-8)
    up = np.cross(right, look)
    j, i = np.meshgrid(np.arange(h, dtype=np.float32),
                       np.arange(w, dtype=np.float32),
                       indexing="ij")
    u = (i / (w - 1)) * 2.0 - 1.0
    v = -((j / (h - 1)) * 2.0 - 1.0)
    aspect = w / h
    fov = math.radians(38)
    f = 1.0 / math.tan(fov * 0.5)
    rd = (u[..., None] * aspect) * right + v[..., None] * up + f * look
    rd = rd / np.maximum(np.linalg.norm(rd, axis=-1, keepdims=True), 1e-8)
    rd_flat = rd.reshape(-1, 3)
    ro_flat = np.broadcast_to(cam_pos, rd_flat.shape).copy()
    verts_w, _, _ = _world_transform(obj)
    bvh = _cached_bvh_for(obj, verts_w)
    _, face_idx, bary_u, bary_v = _intersect_rays_mesh(
        ro_flat, rd_flat, verts_w, obj.mesh.faces, bvh=bvh)
    face_idx_2d = face_idx.reshape(h, w).astype(np.int32)
    bu = bary_u.reshape(h, w).astype(np.float32)
    bv = bary_v.reshape(h, w).astype(np.float32)
    part_id_2d = np.full((h, w), -1, dtype=np.int16)
    uv_xy = np.full((h, w, 2), np.nan, dtype=np.float32)
    if obj.mesh.vert_part_ids is not None or obj.mesh.vert_uvs is not None:
        hit = face_idx_2d >= 0
        if hit.any():
            fidx = face_idx_2d[hit]
            if obj.mesh.vert_part_ids is not None:
                v0 = obj.mesh.faces[fidx, 0]
                part_id_2d[hit] = obj.mesh.vert_part_ids[v0].astype(np.int16)
            if obj.mesh.vert_uvs is not None:
                vuv = obj.mesh.vert_uvs[obj.mesh.faces[fidx]]
                w0 = 1.0 - bu[hit] - bv[hit]
                u_ = (vuv[:, 0, 0] * w0 + vuv[:, 1, 0] * bu[hit]
                       + vuv[:, 2, 0] * bv[hit])
                v_ = (vuv[:, 0, 1] * w0 + vuv[:, 1, 1] * bu[hit]
                       + vuv[:, 2, 1] * bv[hit])
                uv_xy[hit, 0] = u_
                uv_xy[hit, 1] = v_
    return face_idx_2d, part_id_2d, uv_xy


def render_mesh_partmap(w: int, h: int, obj: MeshObject,
                         cam_dist: float = 3.5,
                         cam_yaw: float = 0.4,
                         cam_pitch: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    """Run only the geometric pass of ``render_mesh`` (no shading) and
    return:

      face_idx : (h, w) int32   — per-pixel hit face index; -1 = miss
      part_id  : (h, w) int16   — per-pixel mesh part id; -1 = miss

    The camera math here is byte-for-byte identical to ``render_mesh`` so
    pixel coordinates can be compared directly between the rendered RGBA
    bytes (used to paint the canvas) and the part map (used to find
    where each wing / body / antenna lives on screen).
    """
    cy_, sy_ = math.cos(cam_yaw), math.sin(cam_yaw)
    cp_, sp_ = math.cos(cam_pitch), math.sin(cam_pitch)
    cam_pos = np.array([cam_dist * cp_ * sy_,
                        cam_dist * sp_,
                        cam_dist * cp_ * cy_], dtype=np.float32)
    look = -cam_pos / max(np.linalg.norm(cam_pos), 1e-8)
    up_w = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(look, up_w); right /= max(np.linalg.norm(right), 1e-8)
    up = np.cross(right, look)
    j, i = np.meshgrid(np.arange(h, dtype=np.float32),
                       np.arange(w, dtype=np.float32),
                       indexing="ij")
    u = (i / (w - 1)) * 2.0 - 1.0
    v = -((j / (h - 1)) * 2.0 - 1.0)
    aspect = w / h
    fov = math.radians(38)
    f = 1.0 / math.tan(fov * 0.5)
    rd = (u[..., None] * aspect) * right + v[..., None] * up + f * look
    rd = rd / np.maximum(np.linalg.norm(rd, axis=-1, keepdims=True), 1e-8)
    rd_flat = rd.reshape(-1, 3)
    ro_flat = np.broadcast_to(cam_pos, rd_flat.shape).copy()
    verts_w, _, _ = _world_transform(obj)
    bvh = _cached_bvh_for(obj, verts_w)
    _, face_idx, _, _ = _intersect_rays_mesh(
        ro_flat, rd_flat, verts_w, obj.mesh.faces, bvh=bvh)
    face_idx_2d = face_idx.reshape(h, w).astype(np.int32)
    # Derive part_id per pixel from each face's first vertex's part_id.
    part_id_2d = np.full((h, w), -1, dtype=np.int16)
    if obj.mesh.vert_part_ids is not None:
        hit = face_idx_2d >= 0
        if hit.any():
            face_v0 = obj.mesh.faces[face_idx_2d[hit], 0]
            part_id_2d[hit] = obj.mesh.vert_part_ids[face_v0].astype(np.int16)
    return face_idx_2d, part_id_2d


def world_to_screen_xy(world_xyz: tuple[float, float, float],
                        w: int, h: int,
                        cam_dist: float = 3.5,
                        cam_yaw: float = 0.4,
                        cam_pitch: float = 0.25) -> tuple[float, float, float]:
    """Project a world-space point through the same camera as
    ``render_mesh`` and return ``(image_x, image_y, depth)`` in pixels of
    the rendered ``w×h`` image (origin top-left). Depth is the +look-axis
    distance — negative means behind the camera."""
    cy_, sy_ = math.cos(cam_yaw), math.sin(cam_yaw)
    cp_, sp_ = math.cos(cam_pitch), math.sin(cam_pitch)
    cam_pos = np.array([cam_dist * cp_ * sy_,
                        cam_dist * sp_,
                        cam_dist * cp_ * cy_], dtype=np.float32)
    look = -cam_pos / max(np.linalg.norm(cam_pos), 1e-8)
    up_w = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(look, up_w); right /= max(np.linalg.norm(right), 1e-8)
    up = np.cross(right, look)
    rel = np.asarray(world_xyz, dtype=np.float32) - cam_pos
    z = float(np.dot(rel, look))
    x = float(np.dot(rel, right))
    y = float(np.dot(rel, up))
    aspect = w / h
    fov = math.radians(38)
    f = 1.0 / math.tan(fov * 0.5)
    if abs(z) < 1e-6: z = 1e-6
    ndc_x = (x * f) / (z * aspect)
    ndc_y = (y * f) / z
    img_x = (ndc_x * 0.5 + 0.5) * (w - 1)
    img_y = (1.0 - (ndc_y * 0.5 + 0.5)) * (h - 1)
    return (img_x, img_y, z)


def _draw_wireframe(color_buf, w, h, verts, faces, cam_pos, look, right, up,
                    f, aspect, line_w=1.0, edge_color=(1.0, 1.0, 1.0)):
    """Project edges to screen and rasterise them with a 1-px alpha-blend."""
    # Build unique edge list.
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]],
                       axis=0)
    e = np.sort(e, axis=1)
    e = np.unique(e, axis=0)
    p0 = verts[e[:, 0]]
    p1 = verts[e[:, 1]]
    # Project to camera space.
    def proj(P):
        rel = P - cam_pos
        x = np.sum(rel * right, axis=-1)
        y = np.sum(rel * up, axis=-1)
        z = np.sum(rel * look, axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sx = (x / (z * aspect / f) * 0.5 + 0.5) * (w - 1)
            sy = (-y / (z / f) * 0.5 + 0.5) * (h - 1)
        return np.stack([sx, sy, z], axis=-1)
    a = proj(p0); b = proj(p1)
    edge_rgb = np.array(edge_color, dtype=np.float32)
    for (sa, sb) in zip(a, b):
        if sa[2] <= 0.05 or sb[2] <= 0.05:
            continue
        steps = int(max(2, max(abs(sb[0] - sa[0]), abs(sb[1] - sa[1]))))
        for k in range(steps + 1):
            u = k / steps
            x = int(sa[0] + (sb[0] - sa[0]) * u + 0.5)
            y = int(sa[1] + (sb[1] - sa[1]) * u + 0.5)
            if 0 <= x < w and 0 <= y < h:
                i = y * w + x
                # 70 % overlay so the shaded surface still shows through.
                color_buf[i] = 0.30 * color_buf[i] + 0.70 * edge_rgb


# =========================================================================
# Procedural mesh generators
# =========================================================================

def sphere_mesh(rings: int = 14, sectors: int = 22, radius: float = 1.0) -> Mesh:
    """UV-sphere with `rings` × `sectors` quads triangulated."""
    verts = []
    for r in range(rings + 1):
        phi = math.pi * (r / rings)
        for s in range(sectors + 1):
            th = 2 * math.pi * (s / sectors)
            x = radius * math.sin(phi) * math.cos(th)
            y = radius * math.cos(phi)
            z = radius * math.sin(phi) * math.sin(th)
            verts.append((x, y, z))
    faces = []
    for r in range(rings):
        for s in range(sectors):
            a = r * (sectors + 1) + s
            b = a + 1
            c = a + (sectors + 1)
            d = c + 1
            faces.append((a, c, b))
            faces.append((b, c, d))
    return Mesh(verts=np.array(verts, dtype=np.float32),
                faces=np.array(faces, dtype=np.int32))


def cube_mesh(size: float = 1.0) -> Mesh:
    s = size * 0.5
    v = np.array([(-s,-s,-s),( s,-s,-s),( s, s,-s),(-s, s,-s),
                  (-s,-s, s),( s,-s, s),( s, s, s),(-s, s, s)], dtype=np.float32)
    f = np.array([(0,2,1),(0,3,2),(4,5,6),(4,6,7),
                  (0,1,5),(0,5,4),(2,3,7),(2,7,6),
                  (1,2,6),(1,6,5),(0,4,7),(0,7,3)], dtype=np.int32)
    return Mesh(verts=v, faces=f)


def torus_mesh(R: float = 1.0, r: float = 0.30, major: int = 24, minor: int = 16) -> Mesh:
    verts = []
    for i in range(major + 1):
        u = 2 * math.pi * i / major
        cu, su = math.cos(u), math.sin(u)
        for j in range(minor + 1):
            v = 2 * math.pi * j / minor
            cv, sv = math.cos(v), math.sin(v)
            x = (R + r * cv) * cu
            y = r * sv
            z = (R + r * cv) * su
            verts.append((x, y, z))
    faces = []
    for i in range(major):
        for j in range(minor):
            a = i * (minor + 1) + j
            b = a + 1
            c = (i + 1) * (minor + 1) + j
            d = c + 1
            faces.append((a, c, b))
            faces.append((b, c, d))
    return Mesh(verts=np.array(verts, dtype=np.float32),
                faces=np.array(faces, dtype=np.int32))


def plane_mesh(w: float = 2.0, h: float = 2.0, segs: int = 2) -> Mesh:
    verts, faces = [], []
    for j in range(segs + 1):
        for i in range(segs + 1):
            verts.append((-w/2 + w * (i / segs), 0.0, -h/2 + h * (j / segs)))
    for j in range(segs):
        for i in range(segs):
            a = j * (segs + 1) + i
            b = a + 1
            c = a + (segs + 1)
            d = c + 1
            faces.append((a, c, b))
            faces.append((b, c, d))
    return Mesh(verts=np.array(verts, dtype=np.float32),
                faces=np.array(faces, dtype=np.int32))


def cone_mesh(radius: float = 1.0, height: float = 1.5, segs: int = 18) -> Mesh:
    verts = [(0.0, height, 0.0), (0.0, 0.0, 0.0)]
    for s in range(segs):
        th = 2 * math.pi * s / segs
        verts.append((radius * math.cos(th), 0.0, radius * math.sin(th)))
    faces = []
    for s in range(segs):
        i0 = 2 + s
        i1 = 2 + (s + 1) % segs
        faces.append((0, i0, i1))     # side
        faces.append((1, i1, i0))     # base
    return Mesh(verts=np.array(verts, dtype=np.float32),
                faces=np.array(faces, dtype=np.int32))


def _panel_mesh(curve: float = 0.4, width: float = 1.4, depth: float = 1.0,
               segs: int = 7, mat_index: int = 0,
               uv_region: tuple[float, float, float, float] | None = None,
               ) -> Mesh:
    """Curved wing patch (lying in XZ, bowed up along Y).

    Two-material butterfly wings use this with `mat_index` baked in.
    ``uv_region`` is ``(u0, v0, u1, v1)`` in the source texture's UV
    space — defaults to the full texture. The wing's `v` parameter
    (root→tip) maps to U, and its front→back to V. This lets each wing
    sample a different patch of the photo texture."""
    verts = []
    uvs   = []
    u0, v0, u1, v1 = uv_region or (0.0, 0.0, 1.0, 1.0)
    for j in range(segs + 1):
        v = j / segs                    # 0 at body, 1 at outer tip
        z_front = math.sin(v * math.pi * 0.85) * (-depth * 0.7)
        z_back  = math.sin(v * math.pi * 0.85) *  (depth * 0.9)
        y = math.sin(v * math.pi) * curve   # bow up at mid-wing
        verts.append((v * width, y, z_front))
        verts.append((v * width, y, z_back))
        # Planar UVs: V-axis (vertical in texture) follows wing length
        # root→tip, U-axis follows front-edge → back-edge so the natural
        # gradient of the wing photo lines up.
        u = u0 + (u1 - u0) * v
        uvs.append((u, v0))      # front edge
        uvs.append((u, v1))      # back edge
    faces = []
    for j in range(segs):
        a = 2 * j; b = 2 * j + 1
        c = 2 * (j + 1); d = 2 * (j + 1) + 1
        faces.append((a, c, b))
        faces.append((b, c, d))
    faces = np.array(faces, dtype=np.int32)
    return Mesh(verts=np.array(verts, dtype=np.float32),
                faces=faces,
                face_mats=np.full(len(faces), mat_index, dtype=np.int32),
                vert_uvs=np.array(uvs, dtype=np.float32))


def _ellipsoid_mesh(ax=0.15, ay=0.65, az=0.15, rings=10, sectors=14,
                    mat_index=0) -> Mesh:
    verts = []
    uvs   = []
    for r in range(rings + 1):
        phi = math.pi * (r / rings)
        for s in range(sectors + 1):
            th = 2 * math.pi * (s / sectors)
            x = ax * math.sin(phi) * math.cos(th)
            y = ay * math.cos(phi)
            z = az * math.sin(phi) * math.sin(th)
            verts.append((x, y, z))
            # Spherical UVs — won't be sampled by the wing texture but
            # keeps the merged mesh UV array shape consistent so the
            # renderer doesn't have to special-case "some verts have
            # uvs, some don't".
            uvs.append((s / sectors, r / rings))
    faces = []
    for r in range(rings):
        for s in range(sectors):
            a = r * (sectors + 1) + s
            b = a + 1
            c = a + (sectors + 1)
            d = c + 1
            faces.append((a, c, b)); faces.append((b, c, d))
    faces = np.array(faces, dtype=np.int32)
    return Mesh(verts=np.array(verts, dtype=np.float32),
                faces=faces,
                face_mats=np.full(len(faces), mat_index, dtype=np.int32),
                vert_uvs=np.array(uvs, dtype=np.float32))


def _merge(meshes: list[Mesh]) -> Mesh:
    verts_all, faces_all, mats_all, uvs_all = [], [], [], []
    offset = 0
    any_uvs = any(m.vert_uvs is not None for m in meshes)
    for m in meshes:
        verts_all.append(m.verts)
        faces_all.append(m.faces + offset)
        if m.face_mats is not None:
            mats_all.append(m.face_mats)
        else:
            mats_all.append(np.zeros(len(m.faces), dtype=np.int32))
        if any_uvs:
            uvs_all.append(m.vert_uvs if m.vert_uvs is not None
                            else np.zeros((len(m.verts), 2), dtype=np.float32))
        offset += len(m.verts)
    return Mesh(verts=np.concatenate(verts_all, axis=0),
                faces=np.concatenate(faces_all, axis=0),
                face_mats=np.concatenate(mats_all, axis=0),
                vert_uvs=(np.concatenate(uvs_all, axis=0)
                           if any_uvs else None))


def _panel_quad(width: float, depth: float, mat_index: int,
                uv_region: tuple[float, float, float, float]) -> Mesh:
    """Single rectangular wing — 4 verts, 2 triangles, lying in XZ plane.
    UVs map directly to the texture region the caller specifies. Use
    one quad per wing to project a real photo onto a 3D flap-able plane."""
    u0, v0, u1, v1 = uv_region
    verts = np.array([
        (0.0,    0.0, -depth),     # near-body, leading edge
        (width,  0.0, -depth),     # tip, leading edge
        (0.0,    0.0,  depth),     # near-body, trailing edge
        (width,  0.0,  depth),     # tip, trailing edge
    ], dtype=np.float32)
    uvs = np.array([
        (u0, v0), (u1, v0), (u0, v1), (u1, v1),
    ], dtype=np.float32)
    faces = np.array([(0, 1, 2), (2, 1, 3)], dtype=np.int32)
    return Mesh(verts=verts, faces=faces,
                face_mats=np.full(len(faces), mat_index, dtype=np.int32),
                vert_uvs=uvs)


# Procedural butterfly mesh factories (`butterfly_mesh`,
# `photo_butterfly_mesh`, `make_butterfly_object`, `make_photo_butterfly`)
# were removed deliberately — the project now uses the real .3ds asset
# from `examples/butterfly/_3ds/butterfly.3ds` exclusively. Importing
# that file via `import_mesh_from_file` registers it in `MESH_LIBRARY`
# under the file's stem at runtime; do NOT add a stub procedural
# "Butterfly" entry here.


# Mapping name → factory(): Mesh (no args). For preset library in UI.
MESH_LIBRARY: dict[str, callable] = {
    "Sphere":     lambda: sphere_mesh(),
    "Cube":       lambda: cube_mesh(),
    "Torus":      lambda: torus_mesh(),
    "Plane":      lambda: plane_mesh(),
    "Cone":       lambda: cone_mesh(),
}


def import_mesh_from_file(path) -> Mesh:
    """Load a triangle mesh from disk. Supports:

    * ``.obj`` — simple Wavefront OBJ (v + vt + f)
    * ``.gltf`` — glTF 2.0 JSON with embedded base64 buffers
    * ``.glb`` — binary glTF, first mesh primitive
    * ``.3ds`` — Autodesk 3D Studio chunk format (built-in)

    Returned geometry is normalised to fit a unit cube centred at origin."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".obj":  return _obj_to_mesh(p)
    if suf == ".gltf": return _gltf_to_mesh(p)
    if suf == ".glb":  return _glb_to_mesh(p)
    if suf == ".3ds":  return _3ds_to_mesh(p)
    raise ValueError(f"unsupported mesh format: {suf}")


def _obj_to_mesh(p: Path) -> Mesh:
    verts: list[tuple[float, float, float]] = []
    uvs:   list[tuple[float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for line in p.read_text().splitlines():
        if line.startswith("v "):
            parts = line.split()
            verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("vt "):
            parts = line.split()
            uvs.append((float(parts[1]), float(parts[2])))
        elif line.startswith("f "):
            tokens = line.split()[1:]
            # Each token is "v", "v/vt", or "v/vt/vn" — keep just the vertex.
            idx = [int(tok.split("/")[0]) - 1 for tok in tokens]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    return _normalised_mesh(np.array(verts, dtype=np.float32),
                            np.array(faces, dtype=np.int32))


def _gltf_to_mesh(p: Path) -> Mesh:
    import base64, json, struct
    data = json.loads(p.read_text())
    buffers = []
    for b in data.get("buffers", []):
        uri = b.get("uri", "")
        if uri.startswith("data:"):
            _, _, payload = uri.partition(",")
            buffers.append(base64.b64decode(payload))
        else:
            buffers.append((p.parent / uri).read_bytes())
    return _gltf_first_mesh(data, buffers)


def _glb_to_mesh(p: Path) -> Mesh:
    import json, struct
    data = p.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError("not a glb file")
    version = struct.unpack_from("<I", data, 4)[0]
    if version != 2:
        raise ValueError(f"unsupported glb version: {version}")
    # Chunks: JSON then BIN.
    off = 12
    json_len, json_type = struct.unpack_from("<II", data, off); off += 8
    if json_type != 0x4E4F534A:  # 'JSON'
        raise ValueError("first chunk is not JSON")
    js = json.loads(data[off:off+json_len])
    off += json_len
    buffers = []
    if off + 8 <= len(data):
        bin_len, bin_type = struct.unpack_from("<II", data, off); off += 8
        if bin_type == 0x004E4942:  # 'BIN'
            buffers.append(data[off:off+bin_len])
    return _gltf_first_mesh(js, buffers)


def _gltf_first_mesh(data: dict, buffers: list[bytes]) -> Mesh:
    import struct
    accessors  = data["accessors"]
    bufviews   = data["bufferViews"]

    def read_acc(ai: int, kind: str) -> np.ndarray:
        acc = accessors[ai]
        bv = bufviews[acc["bufferView"]]
        buf = buffers[bv["buffer"]]
        offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        count = acc["count"]
        ctype = acc.get("componentType", 5126)
        # Component layout.
        if kind == "VEC3":
            return np.frombuffer(buf, dtype="<f4", count=count * 3,
                                 offset=offset).reshape(count, 3).copy()
        if kind == "VEC2":
            return np.frombuffer(buf, dtype="<f4", count=count * 2,
                                 offset=offset).reshape(count, 2).copy()
        if kind == "SCALAR":
            fmt = {5121: "u1", 5123: "<u2", 5125: "<u4"}[ctype]
            return np.frombuffer(buf, dtype=fmt, count=count,
                                 offset=offset).copy().astype(np.int32)
        raise ValueError(f"unsupported accessor kind: {kind}")

    for mesh in data.get("meshes", []):
        for prim in mesh.get("primitives", []):
            attr = prim["attributes"]
            pos_idx = attr["POSITION"]
            pos = read_acc(pos_idx, "VEC3")
            uvs = None
            if "TEXCOORD_0" in attr:
                uvs = read_acc(attr["TEXCOORD_0"], "VEC2")
            ii = prim.get("indices")
            if ii is None:
                # Non-indexed: every 3 verts is one tri.
                faces = np.arange(pos.shape[0], dtype=np.int32).reshape(-1, 3)
            else:
                idx = read_acc(ii, "SCALAR")
                faces = idx.reshape(-1, 3)
            mesh_ = _normalised_mesh(pos, faces)
            mesh_.vert_uvs = uvs
            return mesh_
    raise ValueError("no mesh found in glTF")


def _3ds_to_mesh(p: Path) -> Mesh:
    """Autodesk 3D Studio (.3ds) chunk-based binary loader.

    Preserves named sub-meshes — for a butterfly that's usually
    ``Body`` / ``Wing_Left`` / ``Wing_Right``. Each part's TRI_LOCAL
    pivot (the local-frame origin) is captured into ``Mesh.part_pivots``
    so a higher-level flap routine can rotate wings around their actual
    rig pivot, not a guessed body-axis.

    Format reference: ID (u16) + length (u32, includes the 6-byte
    header) + body. Chunks nest; we descend the ones we care about and
    skip the rest. KFDATA (keyframe animation) chunks are parsed only
    for their pivot info — actual keyframe tracks are still ignored at
    this layer; the framework drives the flap procedurally.
    """
    import struct
    data = p.read_bytes()
    pos = [0]

    def u16(): v, = struct.unpack_from("<H", data, pos[0]); pos[0] += 2; return v
    def u32(): v, = struct.unpack_from("<I", data, pos[0]); pos[0] += 4; return v
    def cstr():
        end = data.index(b"\x00", pos[0])
        s = data[pos[0]:end].decode("latin-1", errors="replace")
        pos[0] = end + 1
        return s

    # Per-part collectors keyed by name. A part is a {verts, uvs, faces, pivot}.
    parts: dict[str, dict] = {}
    order: list[str] = []         # insertion order of part names
    current: dict | None = None   # the part currently being parsed

    def walk(end: int) -> None:
        nonlocal current
        while pos[0] < end:
            cid = u16()
            clen = u32()
            body_end = pos[0] + clen - 6
            if cid in (0x4D4D, 0x3D3D):   # MAIN / EDIT3DS — recurse
                walk(body_end)
            elif cid == 0x4000:           # named object: name then sub-chunks
                name = cstr()
                if name not in parts:
                    parts[name] = {"verts": None, "uvs": None,
                                   "faces": None,
                                   "pivot": np.zeros(3, dtype=np.float32)}
                    order.append(name)
                current = parts[name]
                walk(body_end)
                current = None
            elif cid == 0x4100:           # TRIANGULAR MESH container
                walk(body_end)
            elif cid == 0x4110:           # vertex list
                n = u16()
                arr = np.frombuffer(data, dtype="<f4", count=n * 3,
                                      offset=pos[0]).reshape(n, 3).copy()
                pos[0] += n * 12
                if current is not None:
                    current["verts"] = arr.astype(np.float32)
            elif cid == 0x4140:           # mapping coords (UVs) per vertex
                n = u16()
                arr = np.frombuffer(data, dtype="<f4", count=n * 2,
                                      offset=pos[0]).reshape(n, 2).copy()
                pos[0] += n * 8
                if current is not None:
                    current["uvs"] = arr.astype(np.float32)
            elif cid == 0x4120:           # face list
                n = u16()
                arr = np.frombuffer(data, dtype="<u2", count=n * 4,
                                      offset=pos[0]).reshape(n, 4).copy()
                pos[0] += n * 8
                if current is not None:
                    current["faces"] = arr[:, :3].astype(np.int32)
                # Skip sub-chunks (smoothing groups, mat assignments).
                pos[0] = body_end
            elif cid == 0x4160:           # TRI_LOCAL — local coord frame
                # 12 floats: X-axis(3), Y-axis(3), Z-axis(3), origin(3).
                if current is not None:
                    origin = np.frombuffer(data, dtype="<f4", count=3,
                                            offset=pos[0] + 36).copy()
                    current["pivot"] = origin.astype(np.float32)
                pos[0] = body_end
            else:
                pos[0] = body_end          # skip unhandled

    walk(len(data))

    parts = {n: parts[n] for n in order if parts[n]["verts"] is not None}
    if not parts:
        raise ValueError(f"no mesh data in {p}")

    # Concatenate parts into one mesh, tagging each vertex with its part id.
    verts_chunks, uvs_chunks, faces_chunks = [], [], []
    part_ids_chunks = []
    part_names: list[str] = []
    part_pivots: list[np.ndarray] = []
    v_offset = 0
    have_uvs = True
    for pid, name in enumerate(order):
        if name not in parts:
            continue
        d = parts[name]
        v = d["verts"]
        f = d["faces"] if d["faces"] is not None else np.zeros((0, 3), np.int32)
        u = d["uvs"]
        verts_chunks.append(v)
        faces_chunks.append(f + v_offset)
        part_ids_chunks.append(np.full(len(v), pid, dtype=np.uint8))
        if u is None or len(u) != len(v):
            have_uvs = False
            uvs_chunks.append(np.zeros((len(v), 2), np.float32))
        else:
            uvs_chunks.append(u)
        part_names.append(name)
        part_pivots.append(d["pivot"])
        v_offset += len(v)

    verts_all = np.concatenate(verts_chunks, axis=0)
    faces_all = (np.concatenate(faces_chunks, axis=0) if faces_chunks
                  else np.zeros((0, 3), dtype=np.int32))
    part_ids_all = np.concatenate(part_ids_chunks, axis=0)
    uvs_all = np.concatenate(uvs_chunks, axis=0) if have_uvs else None
    pivots_arr = np.stack(part_pivots, axis=0) if part_pivots else None

    # 3DS uses Z-up; swap to our Y-up convention. Apply the same swap
    # to pivots so they stay aligned with the vertices.
    swap_idx = [0, 2, 1]
    swap_sign = np.array([1, 1, -1], dtype=np.float32)
    verts_all = verts_all[:, swap_idx] * swap_sign
    if pivots_arr is not None:
        pivots_arr = pivots_arr[:, swap_idx] * swap_sign

    # Normalise to a unit cube — apply the same shift+scale to pivots
    # so they remain in the same frame as the verts.
    bb_min = verts_all.min(axis=0)
    bb_max = verts_all.max(axis=0)
    centre = (bb_min + bb_max) / 2.0
    extent = float((bb_max - bb_min).max()) or 1.0
    inv_scale = 1.0 / extent
    verts_all = (verts_all - centre) * inv_scale
    if pivots_arr is not None:
        pivots_arr = (pivots_arr - centre) * inv_scale

    mesh_ = Mesh(verts=verts_all.astype(np.float32),
                  faces=faces_all.astype(np.int32))
    if uvs_all is not None:
        uvs_all[:, 1] = 1.0 - uvs_all[:, 1]   # 3DS V is flipped
        mesh_.vert_uvs = uvs_all.astype(np.float32)
    mesh_.vert_part_ids = part_ids_all
    mesh_.part_names = part_names
    mesh_.part_pivots = (pivots_arr.astype(np.float32) if pivots_arr is not None
                          else None)
    return mesh_


def _normalised_mesh(verts: np.ndarray, faces: np.ndarray) -> Mesh:
    """Centre at origin, scale to fit a unit cube. Keeps proportions."""
    bb_min = verts.min(axis=0)
    bb_max = verts.max(axis=0)
    centre = (bb_min + bb_max) * 0.5
    extent = float((bb_max - bb_min).max())
    if extent > 0:
        verts = (verts - centre) / extent
    return Mesh(verts=verts.astype(np.float32),
                faces=faces.astype(np.int32))


# =========================================================================
# Lighting Studios — saved presets so the same model can be re-shot under
# a different "set" with one click. Mirrors KeyShot's `Studios` palette.
# =========================================================================

@dataclass
class Studio:
    name: str = "Default"
    # Sky / sun.
    zenith:   Tuple[float, float, float] = (0.05, 0.10, 0.20)
    horizon:  Tuple[float, float, float] = (0.55, 0.50, 0.45)
    ground:   Tuple[float, float, float] = (0.02, 0.02, 0.02)
    sun_dir:  Tuple[float, float, float] = (0.35, 0.85, 0.40)
    sun_color: Tuple[float, float, float] = (8.0, 7.0, 6.0)
    sun_softness: float = 0.06
    fill_dir:  Tuple[float, float, float] = (-0.6, 0.3, -0.5)
    fill_color: Tuple[float, float, float] = (0.6, 0.7, 0.9)
    # Camera framing.
    cam_yaw:   float = 0.45
    cam_pitch: float = 0.25
    cam_dist:  float = 3.5
    fov_deg:   float = 38.0
    exposure:  float = 1.0
    # Optional HDRI override.
    hdri_path: str | None = None
    hdri_intensity: float = 1.0


def to_environment(s: Studio) -> Environment:
    env = Environment(
        zenith=s.zenith, horizon=s.horizon, ground=s.ground,
        sun_dir=s.sun_dir, sun_color=s.sun_color, sun_softness=s.sun_softness,
        fill_dir=s.fill_dir, fill_color=s.fill_color,
    )
    if s.hdri_path:
        try:
            loaded = load_hdri(s.hdri_path, intensity=s.hdri_intensity)
            env.hdri = loaded.hdri
            env.hdri_blur = loaded.hdri_blur
            env.hdri_intensity = loaded.hdri_intensity
        except Exception:
            pass
    return env


STUDIOS: dict[str, Studio] = {
    "Default Soft Studio": Studio(name="Default Soft Studio"),
    "Hard Sunset": Studio(
        name="Hard Sunset",
        zenith=(0.04, 0.06, 0.16), horizon=(0.92, 0.42, 0.18),
        ground=(0.02, 0.02, 0.02),
        sun_dir=(-0.2, 0.3, -0.9), sun_color=(20.0, 6.0, 1.5),
        sun_softness=0.04,
        fill_dir=(0.7, 0.2, 0.5), fill_color=(0.20, 0.16, 0.40)),
    "Studio Beauty": Studio(
        name="Studio Beauty",
        zenith=(0.95, 0.93, 0.90), horizon=(0.55, 0.55, 0.55),
        ground=(0.10, 0.10, 0.10),
        sun_dir=(0.4, 0.9, 0.2), sun_color=(4.0, 4.0, 4.0),
        sun_softness=0.20,
        fill_dir=(-0.6, 0.4, -0.4), fill_color=(2.0, 2.0, 2.2)),
    "Night Neon": Studio(
        name="Night Neon",
        zenith=(0.01, 0.0, 0.04), horizon=(0.08, 0.02, 0.18),
        ground=(0.0, 0.0, 0.01),
        sun_dir=(0.3, 0.5, 0.8), sun_color=(0.0, 0.4, 2.0),
        sun_softness=0.10,
        fill_dir=(-0.8, 0.4, -0.2), fill_color=(2.0, 0.2, 0.8)),
    "Overcast": Studio(
        name="Overcast",
        zenith=(0.70, 0.72, 0.78), horizon=(0.55, 0.57, 0.62),
        ground=(0.18, 0.18, 0.20),
        sun_dir=(0.0, 1.0, 0.0), sun_color=(2.0, 2.0, 2.0),
        sun_softness=0.50,
        fill_dir=(0.0, 1.0, 0.0), fill_color=(1.6, 1.6, 1.6)),
    "Golden Hour": Studio(
        name="Golden Hour",
        zenith=(0.20, 0.30, 0.55), horizon=(1.00, 0.78, 0.50),
        ground=(0.04, 0.04, 0.04),
        sun_dir=(0.45, 0.30, 0.85), sun_color=(8.0, 5.5, 2.4),
        sun_softness=0.06,
        fill_dir=(-0.6, 0.4, -0.5), fill_color=(0.6, 0.7, 1.0)),
}


def _photo_with_alpha_key(path: str | Path, tolerance: float = 0.22,
                            feather: float = 0.01) -> np.ndarray:
    """Load a wing photo and synthesize an alpha channel by keying out
    pixels similar in color to the photo's corners (which are assumed
    to be background). Works for white backgrounds, off-white, neutral
    greys, even light-grey gradients — anything where the four corner
    samples agree.

    ``tolerance`` is the max chroma distance (0–1) considered "still
    background." ``feather`` widens the transition for soft edges.
    Cached by path + params."""
    key = f"alpha-key:{path}:{tolerance}:{feather}"
    if key in _TEX_CACHE: return _TEX_CACHE[key]
    base = _load_texture(path)
    if base is None: return None       # type: ignore[return-value]
    rgb = base[..., :3].astype(np.float32) / 255.0
    H, W = rgb.shape[:2]
    # Average the 4 corner patches (8×8 each) — robust to JPEG noise.
    def patch(y0, x0):
        return rgb[y0:y0 + 8, x0:x0 + 8].reshape(-1, 3).mean(axis=0)
    bg = np.mean([
        patch(0, 0), patch(0, W - 8),
        patch(H - 8, 0), patch(H - 8, W - 8),
    ], axis=0)
    # Distance from BG in normalised RGB.
    dist = np.linalg.norm(rgb - bg[None, None, :], axis=-1)
    # Smoothstep: dist < tolerance → transparent;
    #             dist > tolerance + feather → opaque.
    t = np.clip((dist - tolerance) / max(feather, 1e-4), 0.0, 1.0)
    alpha = (t * 255.0).astype(np.uint8)
    out = np.concatenate([base[..., :3], alpha[..., None]], axis=-1)
    _TEX_CACHE[key] = out
    return out


# `make_photo_butterfly` and `make_butterfly_object` were removed along
# with the procedural butterfly mesh. Load the real .3ds via
# `import_mesh_from_file(".../butterfly.3ds")` and wrap it in a
# `MeshObject` with whatever materials you need.


# --- Path tracer (Render Final) ------------------------------------------

def _sample_cosine_hemisphere(N: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Cosine-weighted hemisphere sample around each normal in N (P,3)."""
    P = N.shape[0]
    u1 = rng.random(P, dtype=np.float32)
    u2 = rng.random(P, dtype=np.float32)
    r = np.sqrt(u1)
    phi = 2.0 * math.pi * u2
    x = r * np.cos(phi)
    y = r * np.sin(phi)
    z = np.sqrt(np.maximum(1.0 - u1, 0.0))
    # Build tangent frame around N.
    up = np.where(np.abs(N[:, 1:2]) < 0.999,
                  np.array([0, 1, 0], dtype=np.float32),
                  np.array([1, 0, 0], dtype=np.float32))
    T = np.cross(up, N); T = T / np.maximum(np.linalg.norm(T, axis=-1, keepdims=True), 1e-8)
    B = np.cross(N, T)
    return T * x[:, None] + B * y[:, None] + N * z[:, None]


def _sample_ggx(N: np.ndarray, V: np.ndarray, alpha: np.ndarray,
                rng: np.random.Generator) -> np.ndarray:
    """GGX importance-sampled reflection direction."""
    P = N.shape[0]
    u1 = rng.random(P, dtype=np.float32)
    u2 = rng.random(P, dtype=np.float32)
    a = alpha[:, 0] if alpha.ndim == 2 else alpha
    phi = 2.0 * math.pi * u1
    cos_t = np.sqrt((1.0 - u2) / (1.0 + (a * a - 1.0) * u2 + 1e-8))
    sin_t = np.sqrt(np.maximum(1.0 - cos_t * cos_t, 0.0))
    hx = sin_t * np.cos(phi)
    hy = sin_t * np.sin(phi)
    hz = cos_t
    up = np.where(np.abs(N[:, 1:2]) < 0.999,
                  np.array([0, 1, 0], dtype=np.float32),
                  np.array([1, 0, 0], dtype=np.float32))
    T = np.cross(up, N); T = T / np.maximum(np.linalg.norm(T, axis=-1, keepdims=True), 1e-8)
    B = np.cross(N, T)
    H = T * hx[:, None] + B * hy[:, None] + N * hz[:, None]
    # Reflect V across H.
    vh = np.sum(V * H, axis=-1, keepdims=True)
    R = 2.0 * vh * H - V
    return _normalize(R)


def render_path_traced(w: int, h: int, obj: MeshObject, env: Environment,
                       *, samples: int = 16, max_bounces: int = 3,
                       cam_yaw: float = 0.4, cam_pitch: float = 0.25,
                       cam_dist: float = 3.5,
                       denoise: bool = True, seed: int = 1) -> bytes:
    """Monte-Carlo path tracer. Uses the existing BVH. Splits each bounce
    into a probabilistic diffuse-or-specular sample and adds direct sun NEE.
    Returns RGBA bytes (alpha = 255 everywhere).
    """
    rng = np.random.default_rng(seed)

    # Camera basis (matches render_mesh).
    cy_, sy_ = math.cos(cam_yaw), math.sin(cam_yaw)
    cp_, sp_ = math.cos(cam_pitch), math.sin(cam_pitch)
    cam_pos = np.array([cam_dist * cp_ * sy_, cam_dist * sp_, cam_dist * cp_ * cy_],
                       dtype=np.float32)
    look = -cam_pos / max(np.linalg.norm(cam_pos), 1e-8)
    up_w = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(look, up_w); right /= max(np.linalg.norm(right), 1e-8)
    up = np.cross(right, look)

    verts_w, face_normals, _ = _world_transform(obj)
    bvh = _cached_bvh_for(obj, verts_w)
    faces = obj.mesh.faces

    j, i = np.meshgrid(np.arange(h, dtype=np.float32),
                       np.arange(w, dtype=np.float32), indexing="ij")
    aspect = w / h
    fov = math.radians(38)
    f = 1.0 / math.tan(fov * 0.5)
    sun_dir = _normalize(np.array(env.sun_dir, dtype=np.float32))
    sun_color = np.array(env.sun_color, dtype=np.float32)

    accum = np.zeros((h * w, 3), dtype=np.float32)
    # AOVs for the denoiser (filled from the first bounce of the first sample).
    aov_albedo = np.zeros((h * w, 3), dtype=np.float32)
    aov_normal = np.zeros((h * w, 3), dtype=np.float32)
    aov_filled = False

    for s in range(samples):
        # Stratified jitter inside each pixel.
        jx = rng.random((h, w), dtype=np.float32)
        jy = rng.random((h, w), dtype=np.float32)
        u_nd = ((i + jx) / (w - 1)) * 2.0 - 1.0
        v_nd = -(((j + jy) / (h - 1)) * 2.0 - 1.0)
        rd = (u_nd[..., None] * aspect) * right + v_nd[..., None] * up + f * look
        rd = rd / np.maximum(np.linalg.norm(rd, axis=-1, keepdims=True), 1e-8)
        ray_d = rd.reshape(-1, 3).astype(np.float32)
        ray_o = np.broadcast_to(cam_pos, ray_d.shape).copy()

        throughput = np.ones_like(ray_d)
        radiance   = np.zeros_like(ray_d)
        alive = np.ones(ray_d.shape[0], dtype=bool)

        for bounce in range(max_bounces + 1):
            if not alive.any():
                break
            alive_idx = np.where(alive)[0]
            ro = ray_o[alive_idx]
            rd_a = ray_d[alive_idx]
            t_min, fidx, bu, bv = _intersect_rays_mesh(ro, rd_a, verts_w, faces, bvh)
            hit = fidx >= 0

            # Misses pick up the environment and terminate.
            miss = ~hit
            if miss.any():
                env_rgb = _sample_env(env, rd_a[miss])
                if bounce == 0:
                    env_rgb = env_rgb * 0.55
                miss_global = alive_idx[miss]
                radiance[miss_global] += throughput[miss_global] * env_rgb
                alive[miss_global] = False

            if not hit.any():
                break

            hit_global = alive_idx[hit]
            fi = fidx[hit]
            N = face_normals[fi]
            V = -rd_a[hit]
            nv = np.sum(N * V, axis=-1, keepdims=True)
            N = np.where(nv < 0, -N, N)
            hit_p = ro[hit] + rd_a[hit] * t_min[hit][:, None]

            # Material lookup (per-face).
            mat_idx = (obj.mesh.face_mats[fi] if obj.mesh.face_mats is not None
                       else np.zeros_like(fi))
            # UVs.
            uvs_hit = None
            if obj.mesh.vert_uvs is not None:
                verts_uv = obj.mesh.vert_uvs[obj.mesh.faces[fi]]
                w0 = 1.0 - bu[hit] - bv[hit]
                uvs_hit = (verts_uv[:, 0] * w0[:, None]
                           + verts_uv[:, 1] * bu[hit][:, None]
                           + verts_uv[:, 2] * bv[hit][:, None])

            # Gather per-hit material params (vectorise over hits).
            P = hit_global.shape[0]
            base   = np.zeros((P, 3), dtype=np.float32)
            metal  = np.zeros((P, 1), dtype=np.float32)
            rough  = np.zeros((P, 1), dtype=np.float32)
            emiss  = np.zeros((P, 3), dtype=np.float32)
            for m in np.unique(mat_idx):
                mask = mat_idx == m
                mat = obj.materials[m] if m < len(obj.materials) else obj.materials[0]
                ov = _sample_material_textures(
                    mat, uvs_hit[mask] if uvs_hit is not None else None)
                b_arr = _resolve("base_color", np.array(mat.base_color, dtype=np.float32), ov)
                if isinstance(b_arr, np.ndarray) and b_arr.ndim == 1:
                    base[mask] = b_arr[None, :]
                else:
                    base[mask] = b_arr
                m_v = _resolve("metallic", float(mat.metallic), ov)
                metal[mask] = (m_v[:, None] if isinstance(m_v, np.ndarray)
                               else float(m_v))
                r_v = _resolve("roughness", float(mat.roughness), ov)
                rough[mask] = (r_v[:, None] if isinstance(r_v, np.ndarray)
                               else float(r_v))
                e_v = (ov.get("emissive") if ov and "emissive" in ov
                       else np.array(mat.emissive, dtype=np.float32))
                if isinstance(e_v, np.ndarray) and e_v.ndim == 1:
                    emiss[mask] = e_v[None, :]
                else:
                    emiss[mask] = e_v

            # Emission contributes once per path step.
            radiance[hit_global] += throughput[hit_global] * emiss

            # Capture AOVs (albedo + normal) on first sample's first bounce.
            if not aov_filled and bounce == 0:
                aov_albedo[hit_global] = base
                aov_normal[hit_global] = N

            # F0 / probability of choosing specular lobe.
            F0 = (1.0 - metal) * 0.04 + metal * base
            # Schlick at normal incidence approximation for branching prob.
            nv_clip = np.clip(np.sum(N * V, axis=-1, keepdims=True), 0.0, 1.0)
            F = F0 + (1.0 - F0) * np.power(1.0 - nv_clip, 5)
            p_spec = np.clip(F.mean(axis=-1, keepdims=True), 0.05, 0.95)

            # --- Direct sun NEE (shadow ray) ---
            L = np.broadcast_to(sun_dir, N.shape)
            nl = np.clip(np.sum(N * L, axis=-1, keepdims=True), 0.0, 1.0)
            lit = (nl[:, 0] > 0.0)
            if lit.any():
                shadow_o = hit_p[lit] + N[lit] * 1e-3
                shadow_d = np.broadcast_to(sun_dir, shadow_o.shape).copy()
                _, sfi, _, _ = _intersect_rays_mesh(shadow_o, shadow_d,
                                                     verts_w, faces, bvh)
                unshadowed = sfi < 0
                if unshadowed.any():
                    Nu = N[lit][unshadowed]
                    Vu = V[lit][unshadowed]
                    Lu = L[lit][unshadowed]
                    mat_u = obj.materials[0]
                    # Inline a per-hit shading without override:
                    H = _normalize(Lu + Vu)
                    nl_u = np.clip(np.sum(Nu * Lu, axis=-1, keepdims=True), 0.0, 1.0)
                    nv_u = np.clip(np.sum(Nu * Vu, axis=-1, keepdims=True), 0.0, 1.0) + 1e-5
                    nh_u = np.clip(np.sum(Nu * H,  axis=-1, keepdims=True), 0.0, 1.0)
                    vh_u = np.clip(np.sum(Vu * H,  axis=-1, keepdims=True), 0.0, 1.0)
                    a_u  = np.maximum(rough[lit][unshadowed] ** 2, 1e-3)
                    F0_u = F0[lit][unshadowed]
                    Fu   = F0_u + (1.0 - F0_u) * np.power(1.0 - vh_u, 5)
                    Du   = a_u**2 / (math.pi * (nh_u**2 * (a_u**2 - 1.0) + 1.0)**2)
                    k    = (rough[lit][unshadowed] + 1.0)**2 / 8.0
                    Gv   = nv_u / (nv_u * (1 - k) + k)
                    Gl   = nl_u / (nl_u * (1 - k) + k)
                    Gu   = Gv * Gl
                    spec = Fu * Du * Gu / (4.0 * nv_u * nl_u + 1e-5)
                    diff = (1.0 - Fu) * (1.0 - metal[lit][unshadowed]) * base[lit][unshadowed] / math.pi
                    direct = (diff + spec) * sun_color * 0.5 * nl_u

                    # Scatter back to global indices.
                    lit_idx = np.where(lit)[0]
                    unshadow_idx = lit_idx[unshadowed]
                    global_idx = hit_global[unshadow_idx]
                    radiance[global_idx] += throughput[global_idx] * direct

            if bounce == max_bounces:
                alive[:] = False
                break

            # --- Sample next direction ---
            u_branch = rng.random(P, dtype=np.float32)
            choose_spec = u_branch < p_spec[:, 0]
            new_dir = np.zeros_like(N)
            new_thr_factor = np.ones_like(base)

            # Diffuse lobe.
            if (~choose_spec).any():
                m = ~choose_spec
                d = _sample_cosine_hemisphere(N[m], rng)
                new_dir[m] = d
                # cosine-pdf: cos/pi → cancels with Lambert cos/π → throughput *= base
                new_thr_factor[m] = base[m] * (1.0 - metal[m]) / np.clip(1.0 - p_spec[m], 1e-3, 1.0)

            # Specular lobe.
            if choose_spec.any():
                m = choose_spec
                a_s = np.maximum(rough[m] ** 2, 1e-3)
                rdir = _sample_ggx(N[m], V[m], a_s, rng)
                # Reject under-horizon.
                ndl = np.sum(N[m] * rdir, axis=-1, keepdims=True)
                rdir = np.where(ndl < 0, -rdir, rdir)
                new_dir[m] = rdir
                # Approximate specular contribution: F / p_spec (rough MC weight).
                new_thr_factor[m] = F[m] / np.clip(p_spec[m], 1e-3, 1.0)

            # Update throughput.
            throughput[hit_global] = throughput[hit_global] * new_thr_factor

            # Russian roulette after a couple of bounces.
            if bounce >= 1:
                lum = throughput[hit_global].max(axis=-1)
                rr_p = np.clip(lum, 0.05, 0.95)
                u_rr = rng.random(hit_global.shape[0], dtype=np.float32)
                killed = u_rr > rr_p
                if killed.any():
                    alive[hit_global[killed]] = False
                survive = ~killed
                throughput[hit_global[survive]] /= rr_p[survive, None]

            # Spawn next-bounce rays.
            ray_o[hit_global] = hit_p + N * 1e-3
            ray_d[hit_global] = new_dir

        aov_filled = True
        accum += radiance

    img_lin = (accum / max(samples, 1)).reshape(h, w, 3)

    if denoise:
        img_lin = _atrous_denoise(img_lin,
                                  aov_albedo.reshape(h, w, 3),
                                  aov_normal.reshape(h, w, 3))

    img = _aces(img_lin)
    img = _linear_to_srgb(img)
    rgb = np.clip(img * 255.0, 0.0, 255.0).astype(np.uint8)
    alpha = np.full((h, w, 1), 255, dtype=np.uint8)
    return np.concatenate([rgb, alpha], axis=-1).tobytes()


def _atrous_denoise(color: np.ndarray, albedo: np.ndarray, normal: np.ndarray,
                    iterations: int = 3,
                    sigma_color: float = 0.6,
                    sigma_normal: float = 0.2,
                    sigma_albedo: float = 0.4) -> np.ndarray:
    """Edge-avoiding À-Trous wavelet filter (Dammertz et al. 2010).
    Uses albedo+normal AOVs as edge-stopping guides so we preserve detail."""
    h, w, _ = color.shape
    out = color.copy()
    kernel = np.array([1/16, 1/4, 3/8, 1/4, 1/16], dtype=np.float32)
    for it in range(iterations):
        step = 1 << it
        acc = np.zeros_like(out)
        wsum = np.zeros((h, w, 1), dtype=np.float32)
        for dj, kj in enumerate(kernel):
            for di, ki in enumerate(kernel):
                oj = (dj - 2) * step
                oi = (di - 2) * step
                shifted_c = np.roll(out, (oj, oi), axis=(0, 1))
                shifted_a = np.roll(albedo, (oj, oi), axis=(0, 1))
                shifted_n = np.roll(normal, (oj, oi), axis=(0, 1))
                dc = np.linalg.norm(shifted_c - out, axis=-1, keepdims=True)
                da = np.linalg.norm(shifted_a - albedo, axis=-1, keepdims=True)
                dn = 1.0 - np.clip(np.sum(shifted_n * normal, axis=-1, keepdims=True), 0.0, 1.0)
                wc = np.exp(-dc / (sigma_color + 1e-6))
                wa = np.exp(-da / (sigma_albedo + 1e-6))
                wn = np.exp(-dn / (sigma_normal + 1e-6))
                wt = (kj * ki) * wc * wa * wn
                acc += shifted_c * wt
                wsum += wt
        out = acc / np.maximum(wsum, 1e-6)
    return out


# Phase 1n — back-compat aliases for the private surface-patch helpers
# (used to be wing-specific; now named generically since they're just
# curved-patch / quad geometry generators that any thin-surface mesh
# can call).
_wing_mesh = _panel_mesh
_wing_quad = _panel_quad
