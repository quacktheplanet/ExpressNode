# Coding Nodes — Build Plan

Concrete steps to ship the first version. Ordered so each step leaves
a working artifact.

## Where the code goes

```
coding-nodes/
├── coding_nodes/                    # the Python package
│   ├── __init__.py
│   ├── frontend/                    # Python AST -> EvalGraph
│   │   ├── parser.py                # AST traversal
│   │   ├── builtins.py              # sin, cos, noise, vec3, etc.
│   │   └── errors.py                # CompileError with source spans
│   ├── grouping/
│   │   └── group_pass.py            # wraps user functions as GN sub-groups
│   ├── runtime/
│   │   ├── modifier.py              # Expression Modifier (Shape A)
│   │   └── node_group.py            # Expression Node Group (Shape B)
│   └── ui/
│       ├── modifier_panel.py
│       └── node_panel.py
├── blender_addon/
│   └── __init__.py                  # bl_info, register/unregister
├── tests/
└── examples/
    ├── ripple.py
    └── curl_noise.py
```

The compiler IR (`EvalGraph`, optimizer) and base GN emitter come from
`sacred-geometry-engine/sacred_geometry/`. This package adds the
frontend, the grouping pass, and the user-facing shapes.

## Milestones

Each milestone leaves a working, tested artifact.

> **Status:** M1–M5 headless ✅ · **M6 ✅ (oracle)** ·
> **M7 ✅ (OSL)** · **M8 ✅ (GLSL/Eevee)** ·
> **M9 ✅ (WGSL GPU compute)** — all headless.
> Blender/runtime parity checklists pending (`TESTING.md`); M6 has no
> runtime step.
> Run `python3 -m pytest tests/` (275 headless, 6 toolchain-skipped;
> see `TESTING.md`). Whole arc: `../ROADMAP.md`.

### M1 — Frontend parses the supported subset (≈1 week) ✅

**Deliverables:**
- `coding_nodes.frontend.parser` accepts a Python expression and returns
  an EvalGraph for the supported subset.
- Built-in functions (sin, cos, noise, vec3, attr, etc.) lower to
  EvalGraph ops.
- Built-in variables (P, N, t, frame, i) lower to the right input ops.
- `CompileError` carries source-line and column information.
- Headless tests cover every supported construct and several
  unsupported ones (with expected error messages).

**Done =** Given the example expressions in `examples/ripple.py` and
`examples/curl_noise.py`, the parser produces a valid EvalGraph and
the unit tests pass.

### M2 — Group-wrapping pass (≈1 week) ✅

**Deliverables:**
- `coding_nodes.grouping.group_pass` reconstructs the call tree from
  per-node scope paths and produces a `GroupedGraph`: a hierarchy of
  named regions over the flat EvalGraph.
- Boundary computation: edges (and graph outputs) crossing a region
  become deduplicated input/output sockets.
- Inline heuristic: small regions stay flattened; threshold configurable.
- Headless tests verify the region tree, boundaries, and the
  inline heuristic.

**Done =** Compiling `examples/curl_noise.py` groups into a `curl` root
with twelve `n` sub-regions — not a flat sea of nodes. Verified by
`tests/m2_grouping/test_examples_grouped.py`.

Scope note: M2 delivers and headlessly tests the **grouping plan** (the
`GroupedGraph` the backend will consume). Turning that plan into an
actual Blender node tree needs per-op GN emitters (`math.sin` → a Math
node, `vec.combine3` → a Combine XYZ node, …) plus the sub-group
wrapping, all of which require `bpy`. That emission work moves into M3,
where it is verified in Blender. This keeps M1/M2 fully headless and
CI-friendly; see `TESTING.md`.

### M3 — GN op emitters + Expression Modifier (Shape A)

**Headless layer ✅ (built + tested, no Blender):**
- `backend/op_emitters.py`: emitter descriptor for every op the
  frontend produces; coverage proven by `frontend_op_universe()` vs the
  registry.
- `backend/plan.py`: `build_plan` → `EmissionPlan` (groups, nodes,
  instances, interfaces, links) — pure data, fully testable.
- `backend/gn_executor.py`, `backend/modifier.py`, `blender_addon/`:
  written with lazy `bpy`, import-clean, verified headlessly to import.
- 22 M3 tests in `tests/m3_emit/`.

**Blender layer (built, pending verification):**
- `execute(plan)` builds the datablocks; the Expression Modifier
  (text field, Recompile, inline errors) attaches it.
- Verified via the **M3 Blender checklist** in `TESTING.md`
  (3.1 register · 3.2 ripple · 3.3 errors · 3.4 curl-noise).

**Done =** M3 Blender checklist 3.1–3.4 pass: the user types the
ripple example, scrubs the timeline, the mesh responds; curl-noise
shows a `curl` group containing twelve `n` sub-groups; soft-spot
findings recorded for follow-up.

Deferred to the M3 follow-up (after the checklist run): modifier
output application mode (position offset / normal offset / custom),
debounced auto-recompile, "View Graph" button, parameter-binding
preservation across recompiles. These are polish on a working path.

### M4 — Expression Node Group (Shape B)

**Headless layer ✅ (built + tested):**
- `backend/node_group.py`: an operator that compiles via the **same M3
  pipeline** and inserts a `GeometryNodeGroup` into the active node
  editor, plus a Coding Nodes N-panel. Lazy `bpy`, import-clean.
- Addon shell wires both shapes (modifier + node group).
- 9 M4 tests in `tests/m4_nodegroup/`: the Shape-B contract (root
  group interface == params-in + Result-out, nothing interface/
  param-only emitted, result wired, identical plan to Shape A), and
  import safety.

**Blender layer (built, pending verification):**
- Verified via the **M4 Blender checklist** in `TESTING.md`
  (4.1 panel · 4.2 drop into a tree · 4.3 same as Shape A · 4.4 errors).

**Done =** M4 Blender checklist 4.1–4.4 pass: the user drops an
expression into a GN tree as a group node, wires its `Result`, and it
works — same compiler as the modifier, different delivery surface.

Deferred to the M4 follow-up: in-place re-edit of a dropped group
(re-point existing instances on recompile), 2D-cursor placement of the
new node.

### M5 — Polish, ship

**Headless layer ✅ (built + tested, 71 M5 tests):**
- **Apply modes** (`backend/plan.py`): `raw` / `offset` / `absolute`.
  The expression group is wrapped in a Geometry-in/out modifier group
  so Shape A is a valid GN modifier — removes the biggest M3 soft spot.
- **Parameter reconciliation** (`backend/params.py`): a pure function
  that carries tuned values across a recompile when the signature is
  stable; `changed_signature()` decides rebuild-vs-revalue.
- **Error triage** (`tests/m5_polish/test_error_quality.py`): a
  22-case matrix asserting every unsupported construct gives a clear,
  located, hinted message.
- **Doc-accuracy guard** (`test_doc_accuracy.py`): docs cannot drift —
  every built-in must be documented; emitter coverage re-asserted.
- **Addon packaging** (`tools/package_addon.py`): builds a
  self-contained `coding_nodes_addon.zip` bundling both packages plus a
  register shim; structure verified headlessly.

**Blender layer (built, pending verification):**
- Verified via the **M5 Blender checklist** in `TESTING.md`
  (5.1 install zip · 5.2 apply modes · 5.3 param survival · 5.4 errors).

**Done =** M5 checklist 5.1–5.4 pass: a first user installs the zip,
follows the README, and has a working example fast.

**M5 follow-up (after the checklist):** apply-mode dropdown in the
modifier UI, `normal` mode, debounced auto-recompile, "View Graph"
button, dropped-group in-place re-edit, step-by-step example docs
refresh.

### M6 — Reference Evaluator / correctness oracle ✅

**Fully headless — built + tested, no Blender step:**
- `coding_nodes/evaluator/`: a numpy interpreter of the EvalGraph.
  `evaluate(compiled, P=..., t=..., params=...)` → `EvalResult`.
- `evaluator/noise.py`: the canonical reference value-noise / voronoi
  (the spec OSL/GLSL/GPU must reproduce).
- `evaluator/ops.py`: a numpy implementation of every op, mirroring
  `backend/op_emitters.py`.
- 32 M6 tests: ripple matches hand-written numpy to 0.0 error;
  user-function inlining numerically correct; curl-noise deterministic
  & parameter-sensitive; noise spec pinned; API contract.
- Fixed `examples/curl_noise.py` so `scale`/`strength` are actually
  used (the evaluator surfaced that they were dead — a real find).

**Done =** `tests/m6_evaluator/` green. This converts the structural
confidence of M1–M5 into proven numerical correctness, headlessly, and
becomes the oracle for validating the OSL/GLSL/GPU backends.

### M7 — OSL backend ✅ headless

First backend off the multi-backend trajectory (ROADMAP §4b): the same
expression compiled to an Open Shading Language shader for Cycles.

**Headless — built + tested:**
- `backend/osl.py`: SSA emitter (`emit_osl` / `osl_source`), per-op OSL
  template table, reference `cn_value_noise`/`cn_voronoi_f1` mirroring
  the M6 oracle, included only when used.
- 15 M7 tests: op-template coverage; structural validity (shader
  signature, balanced braces/parens, **SSA declared-before-use**,
  params surfaced, faithful ripple chain, scalar vs vector output);
  + 2 `oslc`-compile tests that auto-run when the toolchain is present,
  skip otherwise.

**OSL-runtime checklist (when oslc/testshade/Blender available):**
- generated shaders compile (auto-runs in any env with `oslc`);
- numeric parity vs the M6 oracle — exact for noise-free expressions
  (OSL stdlib == numpy IEEE); bit-exact lattice-hash parity for
  `noise()`/`voronoi()` is the explicit runtime item.

**Done =** `tests/m7_osl/` green; the OSL-runtime checklist confirms
compile + oracle parity where the toolchain exists. See `docs/osl.md`.

### M8 — GLSL / Eevee backend ✅ headless

Second backend off ROADMAP §4b: the same expression as a GLSL fragment
shader for real-time / Eevee shading.

**Headless — built + tested:**
- `backend/glsl.py`: SSA emitter (`emit_glsl`/`glsl_source`), per-op
  GLSL template table, scalar→`vec3` promotion for vector arithmetic
  (GLSL has no implicit promotion), uint32 reference noise that is
  **bit-exact** with the M6 oracle.
- 16 M8 tests: template coverage; structural validity (`#version`,
  balanced braces/parens, SSA declared-before-use, scalar/vector
  return, float-literal correctness, promotion, faithful ripple);
  + 2 `glslangValidator` compile tests (auto-run when present).

**GLSL-runtime checklist:** generated `.frag` compiles; numeric parity
vs the oracle — exact for noise-free, **bit-exact for `noise()`/
`voronoi()`** (uint32 parity, the strongest of any backend).

**Done =** `tests/m8_glsl/` green; runtime checklist confirms compile +
parity where the toolchain exists. See `docs/glsl.md`.

### M9 — WGSL GPU compute backend ✅ headless

Third backend off ROADMAP §4b and the "fast at scale" tier: the same
expression as a WGSL compute kernel — one GPU invocation per point over
flat `array<f32>` buffers.

**Headless — built + tested:**
- `backend/wgsl.py`: SSA kernel emitter (`emit_wgsl`/`wgsl_source`),
  per-op WGSL templates, scalar→`vec3<f32>` promotion, flat-buffer
  layout (sidesteps vec3 stride), Uniforms struct, `@compute` entry
  with bounds check. `round` matches numpy round-half-to-even; floored
  `mod`; `bitcast<u32>` for bit-exact uint32 noise vs the oracle.
- 17 M9 tests: template coverage; structural validity (kernel +
  bindings + `@compute`, balanced, SSA, scalar/vector write,
  promotion, floored mod, faithful ripple); + 2 `naga`/`tint`
  validate tests (auto-run when present).

**GPU-runtime checklist:** WGSL validates (`naga`/`tint`); standalone
wgpu dispatch over a grid equals the oracle — exact for noise-free,
bit-exact for noise. No Blender required.

**Done =** `tests/m9_gpu/` green; runtime checklist confirms validate +
parity where the toolchain exists. See `docs/gpu.md`.

## Total estimated effort

**4–5 weeks of focused work**, single developer. The first three
milestones are the load-bearing ones; M4 and M5 are largely UI and
polish on top of the same compiler.

## What gets built after M5

- More built-ins (voronoi variants, easing curves, common patterns).
- Better visual layout (frame nodes around logical sections).
- Performance polish (faster recompile on large kernels).
- Optional: OSL backend, GLSL backend, GPU compute backend.
- Optional: visual / graphical frontend.

Each of these is a separate, optional milestone added after the first
ship ships.

## Risks

| Risk | Mitigation |
|---|---|
| Blender 4.x/5.x API churn (modifier registration changed in 4.0) | Pin to specific Blender versions; test on each before tagging a release. |
| Group-wrapping produces awkward layouts | Iterate on layout heuristics during M2; ship "good enough" and improve based on feedback. |
| Live recompile causes viewport stutter | Debounce aggressively; cache parse results; rebuild only the changed sub-groups. |
| Error messages are obscure | Triage during M5 — each unsupported feature gets a specific message before ship. |
| User-written expressions are slow at runtime | The compiled output is native GN; performance is GN-native. The compile step is one-time per edit. |
