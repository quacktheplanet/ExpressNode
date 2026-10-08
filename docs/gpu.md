# The GPU Compute Backend (M9)

The same Python expression compiled to a **WGSL compute shader** — the
"fast at scale" target. The expression becomes a parallel
kernel: one GPU invocation per point, over flat `array<f32>` buffers.

## What it produces

`wgsl_source(source)` →

```wgsl
fn expr_ripple(P: vec3<f32>, N: vec3<f32>, Time: f32, ...,
               freq: f32, amp: f32) -> vec3<f32> {
    let v0: vec3<f32> = P;
    let v6: f32 = (v0).x;
    let v7: f32 = (v6 * freq);
    let v8: f32 = (v7 + v1);          // + Time
    let v9: f32 = sin(v8);
    let v10: f32 = (v9 * amp);
    let v11: vec3<f32> = vec3<f32>(v4, v5, v10);
    return v11;
}
struct Uniforms { Time: f32, ..., freq: f32, amp: f32, }
@group(0) @binding(0) var<storage, read>       in_P:  array<f32>;
@group(0) @binding(1) var<storage, read_write> out_R: array<f32>;
@group(0) @binding(2) var<uniform>             U:     Uniforms;
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    let n = arrayLength(&in_P) / 3u;
    if (i >= n) { return; }
    let P = vec3<f32>(in_P[3u*i+0u], in_P[3u*i+1u], in_P[3u*i+2u]);
    let r = expr_ripple(P, N, U.Time, ..., U.freq, U.amp);
    out_R[3u*i+0u] = r.x; out_R[3u*i+1u] = r.y; out_R[3u*i+2u] = r.z;
}
```

Design choices for robustness:
- **Flat `array<f32>` buffers** (positions `3*i..3*i+2`, results always
  3 floats — scalar results pad with zeros). Sidesteps WGSL's
  `vec3` storage-stride/alignment pitfalls entirely.
- **Uniform struct** for `Time/Frame/DeltaTime/Seed` + scalar params.
- One invocation per point, `@workgroup_size(64)`, bounds-checked
  against `arrayLength`.

## WGSL specifics handled

- No implicit scalar→vec promotion (like GLSL): scalar operands of
  vector arithmetic wrapped in `vec3<f32>(...)`.
- `select(false, true, cond)` for comparisons / `flow.if` / bool.
- `atan2(y,x)` native; `round` is round-half-to-even — **matches
  numpy `np.round`** (better than the GLSL `floor(x+0.5)` workaround).
- No float `mod` builtin → emit `a - b*floor(a/b)` (floored modulo,
  matching numpy / OSL / GLSL exactly).
- `u32` with defined wraparound == numpy `uint32`; signed→unsigned via
  `bitcast<u32>` (two's-complement reinterpret, same as
  `np.int64(...).astype(np.uint32)`). The reference noise is therefore
  **bit-exact** with the M6 oracle.

## Correctness model

Same split as every backend:

**Headless, proven (`tests/m9_gpu/`):**
- *Coverage* — every frontend op has a WGSL template.
- *Structural* — kernel function, storage/uniform bindings, `@compute`
  entry, bounds check, balanced braces/parens, **SSA verified**,
  scalar vs vector result writing, scalar→vec3 promotion, floored
  `mod`, uint32 noise lib only when used, faithful ripple chain.

**GPU-runtime checklist (when `naga`/`tint`/wgpu available):**
- `tests/m9_gpu/test_wgsl_compile.py` validates the WGSL (auto-runs
  when `naga` or `tint` is on PATH).
- Numeric parity vs the M6 oracle via a standalone wgpu dispatch over
  a grid of points — exact for noise-free, bit-exact for `noise()`/
  `voronoi()`. No Blender required for this check.

## Why this is the "fast at scale" tier

Each point is an independent GPU invocation. A million-point
displacement that the numpy oracle computes in ~tens of ms and the GN
graph evaluates per-frame on CPU runs here as a single dispatch — the
path to real-time on huge geometry. The kernel is portable WGSL
(WebGPU / wgpu / naga → SPIR-V / tint → SPIR-V/HLSL/MSL), so it targets
Vulkan/Metal/D3D/WebGPU from one source.

## M9 follow-up

- A bundled wgpu-python numeric harness (auto-skip when absent) that
  dispatches the kernel and diffs against `evaluate(...)`, closing
  parity headlessly wherever a GPU/driver exists.
- `attr.read`/`obj.read` currently neutral defaults; wiring to input
  buffers is the follow-up.

## Related

- `evaluator.md` — the oracle / reference noise this matches bit-exactly
- `glsl.md` / `osl.md` — the sibling shader backends
- `emission.md` — the GN backend
