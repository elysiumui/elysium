# Blue Morpho — 3D Model & Animation Spec (Elysium Logo Intro)

**Deliverable:** a photorealistic, life-sized **Blue Morpho** butterfly 3D model
+ flight animation for the Elysium logo intro screen. The butterfly enters from
the **top-right**, glides gently to **screen center**, and settles into the logo
lockup.

**Hard requirement:** the asset must import cleanly into the **Elysium Designer**
and remain editable there (mesh, materials, and the flight states). This spec is
written against the Designer's actual 3D pipeline so the result is drop-in. The
existing low-fidelity placeholder lives beside this file
(`examples/butterfly/`); the new asset replaces it at production quality.

---

## 1. The shot

| | |
|---|---|
| **Subject** | One Blue Morpho butterfly, photoreal, life-sized |
| **Entrance** | Top-right of frame, smaller/further (scale ≈ 0.55) |
| **Path** | Smooth glide diagonally down-left to dead center |
| **Settle** | Comes to rest centered (scale 1.0), wings easing to a slow idle flap, then the Elysium wordmark fades in beneath/around it |
| **Duration** | ~3.0 s entrance + ~1.0 s settle (tunable in Designer) |
| **Frame rate** | Authored and previewed at **60 fps** |
| **Mood** | Calm, premium, "gentle" — no frantic wingbeats; slow, weighty glide |

The Designer already models this as two **states** on a `Mesh3D` placement —
`top-right` → `centered` — so the *flight path* is data, not baked animation
(see §6). Your job is the **model + materials + wing articulation**, plus
optional baked idle/flap clips.

---

## 2. Biological reference & realism

Target species: **Morpho didius / Morpho menelaus** (the large iridescent-blue
morphos).

- **Wingspan (life-sized):** 14–16 cm tip-to-tip. Model at **real-world scale**
  (≈ **0.15 m** wingspan) so material/normal detail is physically plausible.
- **Body length:** ~3.5–4 cm; slender furred thorax/abdomen, dark.
- **Dorsal (top) wings:** the iconic **structural iridescent blue** with a thin
  dark/black border. This blue is *not* pigment — it is structural colour, so it
  must shift with view/light angle (see iridescence in §4).
- **Ventral (under) wings:** matte brown/grey with **ocelli (eyespots)** and
  cryptic banding. Both sides matter — the wings rotate during flap.
- **Wings:** very thin, membranous, faintly **translucent** at the edges, with
  visible **vein structure** and a fine **scale micro-texture**.
- **Antennae:** clubbed, paired; **legs:** six, thin (can be low-detail/tucked).

Provide your photo/reference board with the delivery.

---

## 3. Geometry & topology

- **Style:** clean, predominantly **quad** topology; production-photoreal but
  real-time-friendly.
- **Polygon budget:** **40k–120k triangles** total (the Designer rasterizes the
  mesh per frame for the intro — keep it lean; favour normal maps over geometry
  for scale/vein detail). Provide a higher-poly source if you have it, but the
  delivered mesh must sit in this budget.
- **Parts — must be SEPARATE, named objects** (the Designer articulates wings by
  name and the existing `.3ds` already uses `Wing_Right`-style names):

  | Object name | Notes |
  |---|---|
  | `Body` | thorax + abdomen + head |
  | `Wing_Left` | left fore+hind wing, joined as one object |
  | `Wing_Right` | right fore+hind wing, joined as one object |
  | `Antenna_Left`, `Antenna_Right` | optional but preferred |
  | `Legs` | optional, single low-detail object |

  Keep names ASCII, no spaces. Left/Right from the **butterfly's** point of view.

- **Wing pivots (critical):** each wing object's **origin/pivot must sit at the
  wing root hinge** (where the wing meets the thorax), with the hinge axis
  running front-to-back along the body. The Designer's procedural flap rotates
  each wing about its own origin — a mis-placed pivot makes the flap look broken.
- **Neutral pose:** wings **flat-to-slightly-raised** (≈ 10–15° above horizontal),
  symmetric — this is the rest pose the flap oscillates around.
- **Model origin:** world origin at the **body centroid** (between the wing
  hinges). The whole asset should be centered on (0,0,0).
- **Orientation:** **+Y up**, butterfly facing **toward camera / +Z**, dorsal
  (blue) side up. Apply/freeze all transforms (scale 1,1,1; rotation 0) before
  export.
- **UVs:** non-overlapping, one UV set; lay wings out so dorsal and ventral get
  full texel density; symmetric wings may mirror UVs. Target **~10–12 px/mm** at
  4K.

---

## 4. Materials (PBR) — map to the Designer's shader

The Designer renderer is **PBR metallic-roughness** and understands these inputs
(author your maps so they bind to these): `albedo` / `albedo_map`,
`normal_map`, `roughness`, `metallic`, `specular`, `clearcoat` +
`clearcoat_roughness`, **`iridescence`**, `sheen`, `anisotropy`, `ao_map`,
`emissive` / `emissive_map`, `opacity` (alpha). Deliver **glTF-style PBR**
(see §7) so these populate automatically.

**Texture maps (deliver at 4096², plus 2K downscales):**

| Map | Wings (dorsal) | Wings (ventral) | Body |
|---|---|---|---|
| **Base color / albedo** | deep saturated morpho blue with the dark border; remember the *structural* blue is largely the iridescence layer, so keep albedo a believable blue-violet base | matte brown/grey + eyespots + banding | dark brown, slightly desaturated |
| **Normal** | wing-scale micro-relief + vein ridges | vein + scale relief | fur/segment relief |
| **Roughness** | low-ish, with subtle streak variation (0.2–0.4) | higher/matte (0.6–0.8) | 0.5–0.7 |
| **Metallic** | 0 (dielectric; the "metal sheen" is iridescence + clearcoat, not metalness) | 0 | 0 |
| **Opacity/alpha** | feathered translucency at wing margins; crisp cutout for the scalloped silhouette | same | opaque |

**Key looks:**
- **Iridescence** is the headline. Author the dorsal wings with an **iridescence
  layer** (thin-film) so the blue shifts toward cyan/violet at grazing angles.
  In the Designer this is the `iridescence` / `clearcoat` PBR channel — set a
  strong iridescence with a thin-film thickness tuned to peak in blue (~430–470
  nm look). The placeholder uses `clearcoat 0.2`, `clearcoat_roughness 0.1`,
  `metallic 0.25`, `specular 0.6`, `roughness 0.35` as a starting point — beat it.
- **Two-sided wings:** wings are single-membrane; enable **double-sided** and
  ensure the ventral texture shows on the back faces.
- **Thin translucency / subsurface:** a faint light-through at the wing edges
  reads as "real." If your DCC bakes it, deliver a subtle SSS/translucency
  contribution in the albedo/opacity; otherwise note it.
- **Color space:** base-color/emissive = **sRGB**; normal/roughness/metallic/AO =
  **linear (raw)**.

---

## 5. Rig & articulation

The wingbeat is **procedural** in the Designer (it oscillates the `Wing_Left` /
`Wing_Right` objects about their pivots using `flap_freq` and `flap_amp`), so a
heavy skeleton is **not required**. Requirements:

- Wings must be **independent objects with correct root pivots** (see §3) so the
  procedural flap works with zero extra setup.
- If you deliver **FBX/glTF with a skeleton** (optional, for authored clips),
  use a minimal rig: `root` → `thorax` → `wing_L`, `wing_R` (+ optional
  `antenna_L/R`). Bind wings rigidly to their wing bone (no complex skinning
  needed). Keep bone names lowercase/ASCII.
- No corrective shapes / blendshapes required. A subtle **wing-curl** along the
  flap is welcome if it survives export, but not at the cost of import cleanliness.

---

## 6. Animation

Two layers; be explicit about which you deliver.

**A. Flight path (Designer-driven — you mainly validate it).**
The intro is two `Mesh3D` **states** the Designer tweens (values are screen-space
offsets/scale, already in the placeholder — match these as the baseline):

| State | dx | dy | scale | opacity | duration | easing |
|---|---|---|---|---|---|---|
| `top-right` (start) | +450 | −250 | 0.55 | 1.0 | ~0.05 s hold | `ease_in_out` |
| `centered` (end) | 0 | 0 | 1.0 | 1.0 | ~2.5–3.0 s | `ease_in_out` |

Deliver the model so that, at `centered`, it sits upright facing camera at a
pleasing 3/4 (slight `pitch ≈ 0.1 rad`, `dist ≈ 1.4`). If you storyboard a
curved glide (arc rather than straight line), provide it as a note / path
reference and we add intermediate states.

**B. Wingbeat + idle (procedural by default; baked optional).**
- **Wingbeat rate:** slow and graceful, **~2.0–2.5 Hz** during glide, easing to a
  **~1.0–1.5 Hz** idle once centered. (Placeholder: `flap_freq 2.5`,
  `flap_amp 0.7` rad.)
- **Amplitude:** wings sweep roughly **−35° to +60°** from the rest pose; gentle,
  not a full clap.
- **Phase:** left/right symmetric.
- If you **bake** clips instead of relying on procedural flap, deliver named
  looping actions: **`flap_glide`** (2.5 Hz loop), **`flap_idle`** (1.2 Hz loop),
  and an optional **`settle`** transition. 60 fps, linear/loop-safe.

Keep everything **gentle** — this is a logo reveal, not a nature documentary.

---

## 7. Export & import requirements

**Preferred delivery format: glTF 2.0 binary (`.glb`)**, single file, **embedded
textures + PBR materials.** The Designer imports `.glb` / `.gltf` / `.fbx` /
`.obj` / `.3ds`; only glTF/FBX carry full PBR + named parts + animation, so:

1. **Primary:** `blue_morpho.glb` — meshes (`Body`, `Wing_Left`, `Wing_Right`, …
   named as §3), PBR metallic-roughness materials with the maps from §4,
   wing pivots correct, any baked clips from §6B. **Y-up, meters, transforms
   applied.**
2. **Also deliver** the raw maps (4K PNG/EXR) **and** an **FBX** with the same
   names (belt-and-suspenders for re-import / re-authoring).
3. A **`.3ds`** export is optional/legacy (matches the current loader) but **loses
   PBR** — only include if trivial.

**Import sanity rules (your asset must satisfy these):**
- Loads via Designer → **Import Model**, appears as a single **`Mesh3D`**
  placement, no missing-texture or unit/scale surprises.
- At default camera (`pitch 0.1`, `dist 1.4`) the butterfly **fills a sensible
  portion of frame**, upright, dorsal-blue toward camera.
- `Wing_Left` / `Wing_Right` **flap correctly** when `flap_amp`/`flap_freq` are
  driven (no detached/offset wings → pivots are right).
- Iridescent blue **reads at multiple view angles**; ventral shows on wing
  backs.
- Triangulated-on-import is fine (quads welcome in source). Keep the `.glb`
  **under ~40 MB**.

---

## 8. Drop-in target (for reference)

The asset slots into a `Mesh3D` placement like the placeholder's
`examples/butterfly/butterfly.esk/designer_layout.json`:

```jsonc
{
  "kind": "Mesh3D",
  "name": "BlueMorpho",
  "pbr": { "metallic": 0.25, "roughness": 0.35, "specular": 0.6,
           "clearcoat": 0.2, "clearcoat_roughness": 0.1, "iridescence": 0.9 },
  "mesh": { "kind": "file:.../blue_morpho.glb",
            "yaw": 0.0, "pitch": 0.1, "dist": 1.4,
            "flap_freq": 2.5, "flap_amp": 0.7 },
  "states": [ { "name": "top-right", "dx": 450, "dy": -250, "scale": 0.55, ... },
              { "name": "centered",  "dx": 0,   "dy": 0,    "scale": 1.0,  ... } ]
}
```

Once imported you (the Designer user) can retune `pbr.*`, `flap_freq/amp`,
`pitch/dist`, and the state `dx/dy/scale/duration/easing` live — so deliver the
model **neutral and correct**, not pre-baked to one look.

---

## 9. Deliverables checklist

- [ ] `blue_morpho.glb` (primary; PBR + named parts + correct pivots, Y-up, meters)
- [ ] `blue_morpho.fbx` (same names/rig; for re-authoring)
- [ ] Texture set, 4K + 2K: base color, normal, roughness, metallic, AO,
      opacity, (iridescence/thickness if separate) — dorsal **and** ventral
- [ ] Editable **source file** (`.blend` / `.ma` / `.max`) with layers + materials
- [ ] Optional baked clips: `flap_glide`, `flap_idle`, `settle` (60 fps loops)
- [ ] A short **turntable** render (mp4) + a still beauty render for sign-off
- [ ] `README` listing object names, real-world scale, up-axis, units, and any
      translucency/SSS notes

## 10. Acceptance criteria

1. Imports into Elysium Designer as a `Mesh3D` with no errors, correct scale and
   upright dorsal-blue orientation.
2. Photoreal, life-sized Blue Morpho; **iridescent** blue shifts with angle;
   ventral side believable; wings faintly translucent at the margins.
3. `Wing_Left` / `Wing_Right` flap cleanly from the procedural `flap_*` controls.
4. The `top-right → centered` states play the intro glide smoothly at 60 fps and
   settle into the logo composition.
5. Stays within the poly/file budgets and remains **editable** in the Designer.
