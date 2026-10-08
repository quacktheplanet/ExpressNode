# The OSL Backend (M7)

The same Python expression that drives geometry (the GN backend)
compiled to an **Open Shading Language** shader for Cycles. First step
of the multi-backend trajectory (ROADMAP §4b).

## What it produces

`osl_source(source)` → a complete `.osl` shader string. Emission is a
direct **SSA** translation of the EvalGraph: one `type vN = expr;` per
node in topological order. Example — `examples/ripple.py`:

```c
shader expr_ripple (
    float Time = 0.0,
    float Frame = 1.0,
    float DeltaTime = 0.0416667,
    int   Seed = 0,
    float freq = 6.0,
    float amp = 0.3,
    output vector Result = vector(0.0)
)
{
    vector v0 = P;
    float  v1 = Time;
    float  v6 = (v0)[0];
    float  v7 = (v6 * freq);
    float  v8 = (v7 + v1);
    float  v9 = sin(v8);
    float  v10 = (v9 * amp);
    vector v11 = vector(0.0, 0.0, v10);
    Result = v11;
}
```

That is exactly the oracle's semantics: `sin(P.x*freq+t)*amp` on Z.

- Position/Normal use OSL globals `P`/`N`.
- Exposed parameters become shader parameters (`freq`, `amp`, …).
- `Time`/`Frame`/`Seed` are shader parameters.
- User-function calls are already inlined in the EvalGraph, so the
  shader body is flat SSA (idiomatic for OSL).
- Scalar result → `output float Result`; vec result → `output vector`.

## Reference noise/voronoi

When an expression uses `noise()`/`voronoi()`, the shader prepends
`cn_value_noise` / `cn_voronoi_f1` — authored to mirror
`expressnode/evaluator/noise.py` (the oracle) algorithm-for-algorithm.
The library is included only when used.

## Correctness model

Consistent with every backend boundary in this project:

**Headless, proven here (`tests/m7_osl/`):**
- *Coverage* — every frontend op has an OSL template (or is one of the
  two emitter-special-cased ops). Mirrors the GN op-coverage guarantee.
- *Structural validity* — shader signature present, braces/parens
  balanced, **SSA verified** (every `vN` declared before use, single
  pass), parameters surfaced, `Result` assigned, noise lib only when
  used, ripple translation is faithful (the P.x·freq+t→sin→·amp chain).
- *Golden behaviour* — scalar vs vector output, shader-name override.

**OSL-runtime checklist (when `oslc`/`testshade`/Blender is available):**
- `tests/m7_osl/test_osl_compile.py` auto-runs `oslc` if it's on PATH
  (skips cleanly otherwise) — so any environment with the toolchain
  compiles the generated shaders in CI with zero extra setup.
- *Numeric parity vs the M6 oracle.* For noise-free expressions OSL's
  stdlib (`sin`, `mix`, `dot`, `clamp`, …) is IEEE-identical to numpy,
  so the SSA translation is the only thing under test and parity is
  expected exactly. For `noise()`/`voronoi()`, the algorithm matches
  the oracle; bit-exact cross-language lattice-hash parity (int
  overflow/shift semantics differ subtly between Python uint32 and OSL
  `int`) is the explicit runtime-checklist item.

This is the same honest split used for the GN/Blender checklists: the
generator and its structure are proven without the runtime; numeric
parity is confirmed when the runtime is present.

## M7 follow-up

- Wire `attr.read`/`obj.read` to OSL `getattribute()` / a coordinate
  system input (currently neutral compilable defaults).
- A standalone `testshade` numeric harness comparing shader output to
  `evaluate(...)` on a grid (auto-skip when absent), closing noise
  parity headlessly wherever the OSL tools exist.

## Related

- `evaluator.md` — the oracle and the reference noise spec this matches
- `emission.md` — the GN backend (the other target of the same IR)
- `../../ROADMAP.md` §4b — the multi-backend trajectory
- `../PLAN.md` / `../TESTING.md` — milestone status & test map
