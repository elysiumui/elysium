// Frosted-glass backdrop blur — separable Gaussian + tint + grain.
// Per Elysium deep-dive §2. Validated at load time with naga.

struct FrostedGlassUniforms {
    radius:          f32,
    _pad0:           vec3<f32>,
    tint:            vec4<f32>,
    noise_intensity: f32,
    _pad1:           vec3<f32>,
};

@group(0) @binding(0) var backdrop:        texture_2d<f32>;
@group(0) @binding(1) var backdrop_sampler: sampler;
@group(0) @binding(2) var<uniform> u:      FrostedGlassUniforms;

struct VsOut {
    @builtin(position) pos: vec4<f32>,
    @location(0)       uv:  vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vid: u32) -> VsOut {
    // Fullscreen triangle.
    let x = f32((vid << 1u) & 2u);
    let y = f32(vid & 2u);
    var out: VsOut;
    out.pos = vec4<f32>(x * 2.0 - 1.0, 1.0 - y * 2.0, 0.0, 1.0);
    out.uv  = vec2<f32>(x, y);
    return out;
}

// Approximate Gaussian weights for radius up to ~32 px. Compositor selects
// kernel size from `u.radius`; sampling steps span ±radius in UV space.
fn gaussian(d: f32, sigma: f32) -> f32 {
    let s2 = sigma * sigma;
    return exp(-0.5 * d * d / s2) / (sqrt(6.28318530718) * sigma);
}

fn hash12(p: vec2<f32>) -> f32 {
    var q = fract(p * vec2<f32>(123.34, 456.21));
    q = q + dot(q, q + 45.32);
    return fract(q.x * q.y);
}

@fragment
fn fs_main(in: VsOut) -> @location(0) vec4<f32> {
    let tex_size = vec2<f32>(textureDimensions(backdrop, 0));
    let texel    = vec2<f32>(1.0) / tex_size;
    let sigma    = max(u.radius * 0.5, 1.0);
    let kernel   = i32(ceil(u.radius));

    var color = vec4<f32>(0.0);
    var weight_sum = 0.0;
    // Two-pass Gaussian collapsed into one fragment for simplicity in v0;
    // production version (Phase 0.2) ships separable H/V passes.
    for (var dy = -kernel; dy <= kernel; dy = dy + 1) {
        for (var dx = -kernel; dx <= kernel; dx = dx + 1) {
            let off = vec2<f32>(f32(dx), f32(dy));
            let w   = gaussian(length(off), sigma);
            let s   = textureSample(backdrop, backdrop_sampler, in.uv + off * texel);
            color = color + s * w;
            weight_sum = weight_sum + w;
        }
    }
    color = color / weight_sum;

    // Tint mix in linear sRGB.
    color = mix(color, u.tint, u.tint.a * 0.5);

    // Subtle grain to read as "frosted."
    let n = hash12(in.uv * tex_size) - 0.5;
    color = vec4<f32>(color.rgb + vec3<f32>(n) * u.noise_intensity, color.a);

    return color;
}
