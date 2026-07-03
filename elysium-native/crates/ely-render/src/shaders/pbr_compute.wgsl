// Elysium PBR compute shader — Cook-Torrance / GGX shading of a triangle
// mesh, intersected per-pixel by a flat BVH walk in screen space.
//
// Bindings (group 0):
//   0  uniforms  : Uniforms (camera, lights, image size, material count)
//   1  verts     : array<vec4<f32>>            // xyz + pad per vertex
//   2  faces     : array<vec4<u32>>            // (v0,v1,v2,mat_idx) per face
//   3  normals   : array<vec4<f32>>            // face normal per face
//   4  bvh_min   : array<vec4<f32>>            // AABB min per node
//   5  bvh_max   : array<vec4<f32>>            // AABB max per node
//   6  bvh_meta  : array<vec4<i32>>            // (left, right, tri_start, tri_end)
//   7  tri_order : array<u32>                  // tri permutation for the BVH
//   8  materials : array<Material>
//   9  out_image : texture_storage_2d<rgba8unorm, write>
//
// This is the scaffold port of `pbr.render_mesh`. Direct sun + IBL only;
// the Monte-Carlo path tracer is implemented at the Python level for now.

struct Uniforms {
  // Camera basis as 4-component vectors (xyz used, w padding).
  cam_pos:   vec4<f32>,
  cam_look:  vec4<f32>,
  cam_right: vec4<f32>,
  cam_up:    vec4<f32>,
  sun_dir:   vec4<f32>,
  sun_color: vec4<f32>,
  fill_dir:  vec4<f32>,
  fill_color:vec4<f32>,
  size:      vec2<u32>,        // (w, h)
  fov_scale: f32,              // 1/tan(fov/2)
  aspect:    f32,
};

struct Material {
  base_color:  vec4<f32>,       // rgba
  params:      vec4<f32>,       // (metallic, roughness, specular, clearcoat)
  emissive:    vec4<f32>,
  cc:          vec4<f32>,       // (cc_roughness, _, _, _)
};

@group(0) @binding(0) var<uniform>             u:         Uniforms;
@group(0) @binding(1) var<storage, read>       verts:     array<vec4<f32>>;
@group(0) @binding(2) var<storage, read>       faces:     array<vec4<u32>>;
@group(0) @binding(3) var<storage, read>       normals:   array<vec4<f32>>;
@group(0) @binding(4) var<storage, read>       bvh_min:   array<vec4<f32>>;
@group(0) @binding(5) var<storage, read>       bvh_max:   array<vec4<f32>>;
@group(0) @binding(6) var<storage, read>       bvh_meta:  array<vec4<i32>>;
@group(0) @binding(7) var<storage, read>       tri_order: array<u32>;
@group(0) @binding(8) var<storage, read>       materials: array<Material>;
@group(0) @binding(9) var                       out_image: texture_storage_2d<rgba8unorm, write>;

const PI:       f32 = 3.14159265359;
const STACK:    u32 = 32u;

fn _norm(v: vec3<f32>) -> vec3<f32> {
  return v / max(length(v), 1e-8);
}

fn aabb_hit(ro: vec3<f32>, inv_d: vec3<f32>,
            bmin: vec3<f32>, bmax: vec3<f32>) -> bool {
  let t1 = (bmin - ro) * inv_d;
  let t2 = (bmax - ro) * inv_d;
  let tmin = max(max(min(t1.x, t2.x), min(t1.y, t2.y)), min(t1.z, t2.z));
  let tmax = min(min(max(t1.x, t2.x), max(t1.y, t2.y)), max(t1.z, t2.z));
  return tmax >= max(tmin, 0.0);
}

struct Hit {
  t: f32,
  face: i32,
  bu: f32,
  bv: f32,
};

fn ray_tri(ro: vec3<f32>, rd: vec3<f32>, v0: vec3<f32>,
           v1: vec3<f32>, v2: vec3<f32>) -> vec3<f32> {
  // Returns (t, u, v). t = -1 on miss.
  let e1 = v1 - v0;
  let e2 = v2 - v0;
  let pv = cross(rd, e2);
  let det = dot(e1, pv);
  if (abs(det) < 1e-6) { return vec3<f32>(-1.0, 0.0, 0.0); }
  let inv_det = 1.0 / det;
  let tv = ro - v0;
  let u  = dot(tv, pv) * inv_det;
  if (u < 0.0 || u > 1.0) { return vec3<f32>(-1.0, 0.0, 0.0); }
  let qv = cross(tv, e1);
  let v  = dot(rd, qv) * inv_det;
  if (v < 0.0 || (u + v) > 1.0) { return vec3<f32>(-1.0, 0.0, 0.0); }
  let t  = dot(e2, qv) * inv_det;
  if (t <= 1e-4) { return vec3<f32>(-1.0, 0.0, 0.0); }
  return vec3<f32>(t, u, v);
}

fn trace(ro: vec3<f32>, rd: vec3<f32>) -> Hit {
  var best: Hit = Hit(1e30, -1, 0.0, 0.0);
  var stack: array<u32, STACK>;
  var sp: i32 = 0;
  stack[0] = 0u; sp = 1;
  let inv_d = 1.0 / max(abs(rd), vec3<f32>(1e-12)) * sign(rd);

  while (sp > 0) {
    sp = sp - 1;
    let n = stack[sp];
    let bmin = bvh_min[n].xyz;
    let bmax = bvh_max[n].xyz;
    if (!aabb_hit(ro, inv_d, bmin, bmax)) { continue; }
    let bm = bvh_meta[n];
    if (bm.z >= 0) {
      let ts = u32(bm.z);
      let te = u32(bm.w);
      for (var k: u32 = ts; k < te; k = k + 1u) {
        let f = tri_order[k];
        let face = faces[f];
        let v0 = verts[face.x].xyz;
        let v1 = verts[face.y].xyz;
        let v2 = verts[face.z].xyz;
        let h  = ray_tri(ro, rd, v0, v1, v2);
        if (h.x > 0.0 && h.x < best.t) {
          best.t = h.x; best.face = i32(f);
          best.bu = h.y; best.bv = h.z;
        }
      }
    } else {
      if (sp < i32(STACK) - 2) {
        stack[sp] = u32(bm.x); sp = sp + 1;
        stack[sp] = u32(bm.y); sp = sp + 1;
      }
    }
  }
  return best;
}

fn fresnel(F0: vec3<f32>, vh: f32) -> vec3<f32> {
  return F0 + (vec3<f32>(1.0) - F0) * pow(1.0 - vh, 5.0);
}

fn D_ggx(nh: f32, a: f32) -> f32 {
  let a2 = a * a;
  let denom = nh * nh * (a2 - 1.0) + 1.0;
  return a2 / (PI * denom * denom);
}

fn G_smith(nv: f32, nl: f32, rough: f32) -> f32 {
  let k = (rough + 1.0) * (rough + 1.0) / 8.0;
  let gv = nv / (nv * (1.0 - k) + k);
  let gl = nl / (nl * (1.0 - k) + k);
  return gv * gl;
}

fn shade_direct(N: vec3<f32>, V: vec3<f32>, L: vec3<f32>,
                light_color: vec3<f32>, mat: Material) -> vec3<f32> {
  let H  = _norm(L + V);
  let nl = clamp(dot(N, L), 0.0, 1.0);
  let nv = clamp(dot(N, V), 0.0, 1.0) + 1e-5;
  let nh = clamp(dot(N, H), 0.0, 1.0);
  let vh = clamp(dot(V, H), 0.0, 1.0);
  let metallic  = mat.params.x;
  let roughness = mat.params.y;
  let specular  = mat.params.z;
  let a = max(roughness * roughness, 1e-3);
  let base = mat.base_color.rgb;
  let F0_d = vec3<f32>(0.04 * specular * 2.0);
  let F0   = mix(F0_d, base, metallic);
  let F    = fresnel(F0, vh);
  let D    = D_ggx(nh, a);
  let G    = G_smith(nv, nl, roughness);
  let spec = F * D * G / (4.0 * nl * nv + 1e-5);
  let kD   = (vec3<f32>(1.0) - F) * (1.0 - metallic);
  let diff = kD * base / PI;
  return (diff + spec) * light_color * nl;
}

fn aces(x: vec3<f32>) -> vec3<f32> {
  let a = 2.51; let b = 0.03; let c = 2.43; let d = 0.59; let e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e),
               vec3<f32>(0.0), vec3<f32>(1.0));
}

fn linear_to_srgb(c: vec3<f32>) -> vec3<f32> {
  let lo = c * 12.92;
  let hi = 1.055 * pow(max(c, vec3<f32>(0.0)), vec3<f32>(1.0 / 2.4)) - 0.055;
  return select(hi, lo, c <= vec3<f32>(0.0031308));
}

@compute @workgroup_size(8, 8, 1)
fn cs_render(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= u.size.x || gid.y >= u.size.y) { return; }
  let i = f32(gid.x);
  let j = f32(gid.y);
  let w = f32(u.size.x);
  let h = f32(u.size.y);
  let uu = ((i / (w - 1.0)) * 2.0 - 1.0) * u.aspect;
  let vv = -((j / (h - 1.0)) * 2.0 - 1.0);

  let rd = _norm(uu * u.cam_right.xyz + vv * u.cam_up.xyz
                 + u.fov_scale * u.cam_look.xyz);
  let ro = u.cam_pos.xyz;
  let hit = trace(ro, rd);

  var col = vec3<f32>(0.0);
  if (hit.face >= 0) {
    let f = u32(hit.face);
    var N = normals[f].xyz;
    let V = -rd;
    if (dot(N, V) < 0.0) { N = -N; }
    let mi = faces[f].w;
    let mat = materials[mi];
    let direct_k = shade_direct(N, V, u.sun_dir.xyz,  u.sun_color.xyz  * 0.5, mat);
    let direct_f = shade_direct(N, V, u.fill_dir.xyz, u.fill_color.xyz,        mat);
    col = direct_k + direct_f + mat.emissive.rgb;
  } else {
    // Tinted background; the renderer host can blit a real env later.
    col = vec3<f32>(0.05, 0.06, 0.08);
  }
  let outc = linear_to_srgb(aces(col));
  textureStore(out_image, vec2<i32>(i32(gid.x), i32(gid.y)),
               vec4<f32>(outc, 1.0));
}
