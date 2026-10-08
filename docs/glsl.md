# The GLSL Backend (M8)

The same Python expression compiled to a **GLSL fragment shader** for
Eevee / real-time viewport shading. Second backend off the
multi-backend trajectory, same SSA approach as OSL.

## What it produces

`glsl_source(source)` → a complete `#version 330 core` fragment shader:
the expression as a function `Tret expr_<name>(vec3 P, vec3 N, float
Time, ..., <params>)`, plus a `main()` that calls it and writes
`_fragColor` (so the shader is non-trivial and validator-checkable).

```glsl
#version 330 core
vec3 expr_ripple(vec3 P, vec3 N, float Time, ..., float freq, float amp) {
    vec3  v0 = P;
    float v6 = (v0).x;
    float v7 = (v6 * freq);
    float v8 = (v7 + v1);     // + Time
    float v9 = sin(v8);
    float v10 = (v9 * amp);
    vec3  v11 = vec3(v4, v5, v10);
    return v11;
}
out vec4 _fragColor;
void main() { ... _fragColor = vec4(expr_ripple(...), 1.0); }
```

## GLSL vs OSL — two real differences

1. **No implicit float→vec promotion.** OSL auto-promotes; GLSL does
   not. The emitter wraps scalar operands of vector arithmetic
   (`vec.add/sub/mul/div/mod/pow/floordiv`) in `vec3(...)`, decided
   from the resolved operand types in the EvalGraph. (Tested:
   `P + k` emits `vN + vec3(k)`.)
2. **Better noise parity.** GLSL `uint` is 32-bit with defined
   wraparound — *identical to numpy `uint32`*. The reference
   `cn_hash`/`cn_value_noise`/`cn_voronoi_f1` are therefore
   **bit-exact** with the M6 oracle, which OSL's signed `int` could
   not guarantee. `uint(negativeInt)` in GLSL is the same two's-
   complement reinterpret as `np.int64(...).astype(np.uint32)`.

Minor mappings: `atan2(y,x)` → GLSL `atan(y,x)`; `round` →
`floor(x+0.5)` (GLSL `round` rounding mode is unspecified);
comparisons/bool/flow via `?:`; component access via `.x/.y/.z`.

## Correctness model

Same honest split as OSL/GN:

**Headless, proven (`tests/m8_glsl/`):**
- *Coverage* — every frontend op has a GLSL template (or is one of the
  two emitter-special-cased ops).
- *Structural* — `#version`, balanced braces/parens, **SSA verified**
  (every `vN` declared before use), function + `main()`, scalar vs
  vector return, float literals always have a decimal point,
  scalar→vec3 promotion present, noise lib (uint32) only when used,
  faithful ripple chain.

**GLSL-runtime checklist (when `glslangValidator` available):**
- `tests/m8_glsl/test_glsl_compile.py` compiles the generated `.frag`
  (auto-runs when on PATH, skips otherwise).
- Numeric parity vs the M6 oracle: exact for noise-free expressions
  (GLSL stdlib == numpy IEEE) and **bit-exact for `noise()`/
  `voronoi()`** thanks to uint32 parity — the strongest parity story
  of any backend so far.

## M8 follow-up

- `attr.read`/`obj.read` currently emit neutral defaults; wiring to
  shader inputs / textures is the follow-up.
- A standalone GL/`glslang`-SPIRV numeric harness comparing shader
  output to `evaluate(...)` on a grid where the toolchain exists.

## Related

- `evaluator.md` — the oracle / reference noise spec this matches
- `osl.md` — the sibling shader backend
- `emission.md` — the GN backend
