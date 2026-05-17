# Testing Guide

How to verify Coding Nodes, milestone by milestone. Every step here is
**headless** (no Blender) unless explicitly marked **[Blender]**.

## Prerequisites

```bash
pip install pytest
```

The test suite imports both `coding_nodes` (this project) and
`sacred_geometry` (the sibling engine that provides the IR). The path
wiring is handled by `tests/conftest.py` — no install step needed.

## Run everything

```bash
cd coding-nodes
python3 -m pytest tests/ -q
```

Expected: all tests pass.

## Run one milestone at a time

The test tree mirrors the build milestones in `PLAN.md`:

```
tests/
├── conftest.py            # path wiring (applies to all subdirs)
├── m1_frontend/           # M1 — Python AST -> EvalGraph
│   ├── test_basic.py
│   ├── test_arithmetic.py
│   ├── test_vectors.py
│   ├── test_builtins.py
│   ├── test_user_functions.py
│   ├── test_errors.py
│   └── test_examples.py
└── m2_grouping/           # M2 — flat graph -> region tree
    ├── test_region_extraction.py
    ├── test_boundaries.py
    ├── test_inline_heuristic.py
    └── test_examples_grouped.py
```

Verify a milestone in isolation:

```bash
python3 -m pytest tests/m1_frontend/ -q     # M1
python3 -m pytest tests/m2_grouping/ -q     # M2
```

Verify a single concern:

```bash
python3 -m pytest tests/m2_grouping/test_inline_heuristic.py -v
```

## Milestone 1 — Frontend (`tests/m1_frontend/`)

**What it proves:** a Python expression parses into a typed EvalGraph,
built-ins resolve, user functions inline, and unsupported syntax raises
a located `CompileError`.

| Test file | Verifies |
|---|---|
| `test_basic.py` | Entry-function selection, bare-expression wrapping, syntax errors carry a line number |
| `test_arithmetic.py` | Scalar vs vector op dispatch, numeric type promotion |
| `test_vectors.py` | `vec2/3/4`, component access, swizzles, subscripts, range checks |
| `test_builtins.py` | Every built-in function returns the right type; `attr`/`set_attr`/`obj` specials |
| `test_user_functions.py` | Inlining, vector args, defaults, scope tracking, arity errors |
| `test_errors.py` | Every unsupported construct gives a clear, located error |
| `test_examples.py` | `examples/ripple.py` and `examples/curl_noise.py` compile to acyclic graphs |

**M1 done-criterion:** `tests/m1_frontend/test_examples.py` is green.

## Milestone 2 — Grouping (`tests/m2_grouping/`)

**What it proves:** the flat scope-annotated EvalGraph reconstructs into
a call tree, boundary sockets are computed, small regions inline, and
the curl-noise example becomes a readable tree instead of a flat sea of
nodes.

| Test file | Verifies |
|---|---|
| `test_region_extraction.py` | Call tree shape; every node assigned to exactly one region |
| `test_boundaries.py` | Crossing edges + graph outputs become input/output sockets, deduplicated |
| `test_inline_heuristic.py` | Small regions inline; threshold is configurable; root never inlines |
| `test_examples_grouped.py` | `curl_noise.py` yields a `curl` root with 12 `n` sub-regions |

**M2 done-criterion:**
`tests/m2_grouping/test_examples_grouped.py::test_curl_noise_produces_n_subregions`
is green — proving the "no flat sea of nodes" requirement.

Quick manual look at the grouped structure:

```bash
python3 - <<'PY'
import sys; sys.path[:0] = ["coding-nodes", "sacred-geometry-engine"]
from coding_nodes import compile, group
import json, pathlib
src = pathlib.Path("coding-nodes/examples/curl_noise.py").read_text()
print(json.dumps(group(compile(src)).describe(), indent=2, default=str))
PY
```

You'll see the `curl` root with twelve `n#…` child regions and their
input/output socket lists.

## Milestone 3 — Backend: emitters + plan (`tests/m3_emit/`)

**What it proves headlessly:** every op the frontend can emit maps to a
Blender node descriptor; the emission plan for the examples has the
right groups, sub-groups, instances, interfaces, and links; the
bpy-using modules import cleanly without Blender.

| Test file | Verifies |
|---|---|
| `test_op_coverage.py` | Every frontend op (and every op the examples use) has a registered emitter; emitter kinds/bl_idnames are well-formed |
| `test_emission_plan.py` | `ripple` plans to one root group; parameters surface; result is linked to the group output; every eval node is placed or intentionally interface/param-only |
| `test_plan_groups.py` | `curl_noise` plans to a root + 12 `n` sub-groups, instantiated and wired through interfaces; inline threshold collapses helpers |
| `test_import_safety.py` | `gn_executor`, `modifier`, the addon shell, and `pipeline` import with no `bpy` present |

**M3 headless done-criterion:** `tests/m3_emit/` is green — proving the
plan that the Blender executor will consume is complete and correctly
shaped.

Inspect the plan for an example:

```bash
python3 - <<'PY'
import sys; sys.path[:0] = ["coding-nodes", "sacred-geometry-engine"]
from coding_nodes import plan_source
import json, pathlib
src = pathlib.Path("coding-nodes/examples/curl_noise.py").read_text()
print(json.dumps(plan_source(src, inline_threshold=2).describe(),
                  indent=2, default=str))
PY
```

## Milestone 3 — Blender verification **[Blender]** (the planned test)

Everything above is headless. The remaining step runs the executor in
Blender. Do these in order; each builds on the previous.

### Setup

1. Copy or symlink `coding-nodes/blender_addon/` into Blender's addons
   folder (or "Install from Disk" pointing at it). It puts both
   `coding_nodes` and `sacred_geometry` on `sys.path` automatically.
2. Enable **"Coding Nodes — Expression Modifier"** in Preferences.

### Test 3.1 — addon registers

- Expected: no errors on enable. A **Coding Nodes Expression** panel
  appears under Properties › Modifiers with a text field and a
  *Recompile Expression* button.

### Test 3.2 — ripple (no sub-groups, the golden path)

1. Add a subdivided plane; keep it active.
2. Paste `examples/ripple.py` into the panel text field.
3. Click *Recompile Expression*.
- Expected: a `CodingNodesExpression` Nodes modifier appears, its node
  group is `Expr_ripple`, with `freq` and `amp` as modifier inputs.
- Scrub the timeline → the plane ripples; the wave drifts with `t`.
- Change `freq` to 12 → tighter waves on next recompile.
- Open `Expr_ripple` in the Geometry Nodes editor → confirm a small
  readable graph (Position → math chain → Combine XYZ → output), **not**
  a wall of loose `Math` nodes.

### Test 3.3 — compile errors surface, don't crash

1. Type `def f(): return getattr(math,"sin")(P.x)`.
2. Recompile.
- Expected: the panel shows a red error box with the line, no crash,
  the previous good modifier still intact.

### Test 3.4 — curl-noise (sub-groups, the M2/M3 payoff)

1. New subdivided icosphere (subdivisions ≈ 3).
2. Paste `examples/curl_noise.py`; recompile.
- Expected: node group `Expr_curl` containing **twelve `n_*` group
  instances**, not ~180 loose math nodes.
- Open one `n_1` group → confirm it has the `n` body (offset add →
  Noise) with `in_0`/`in_1` inputs and one float output.
- Scrub the timeline → the icosphere swirls organically.
- Adjust `scale` / `strength` modifier inputs → visible change on
  recompile.

### What to watch for (known soft spots to record findings on)

These are the parts the headless plan can't fully prove; note results
in the PR/notes so we iterate:

- **Complex emitters** (`flow.if`, `math.clamp/mix/smoothstep`,
  `compare.eq/ne/le/ge`, `texture.noise` W-wiring, `attr.write`
  geometry threading, `vec.swizzle` expansion, `*.floordiv`,
  `vec.pow`). The descriptors are registered; the in-Blender wiring is
  what 3.2–3.4 exercise. Note any that misbehave.
- **Socket-name resolution** in the executor (`outputs.get(name)` vs
  index). If a link silently drops, it's almost always a socket-name
  mismatch for one bl_idname.
- **Boundary threading** for nested helpers deeper than one level
  (curl→n is one level and is covered; deeper nesting is plan-only
  until a test case needs it).
- **Modifier output application.** The root group currently outputs the
  raw expression result. If the modifier should apply it as a position
  offset / normal offset, that wrapping is the first follow-up after
  3.4 passes.

### Outcome

When 3.1–3.4 pass, M3's done-criterion is met: *the user types an
expression and sees the mesh respond, with a readable grouped node
tree.* Record any soft-spot findings; they become the M3 follow-up /
M5 polish list.

## Milestone 4 — Expression Node Group, Shape B (`tests/m4_nodegroup/`)

**What it proves headlessly:** Shape B reuses the M3 pipeline exactly,
and the plan's root group is a clean, droppable group — interface is
exactly the user parameters in plus a `Result` out, with no
interface/param-only ops leaking inside. Same plan as Shape A, so the
node tree is identical; the only difference is where it lands.

| Test file | Verifies |
|---|---|
| `test_shape_b_contract.py` | Root group interface == params-in + Result-out; nothing interface/param-only emitted as a node; result wired; Shape A and Shape B share one plan; result type preserved |
| `test_import_safety.py` | `node_group` and the two-shape addon import with no `bpy` |

**M4 headless done-criterion:** `tests/m4_nodegroup/` is green.

### Milestone 4 — Blender verification **[Blender]** (the planned test)

Do these after the M3 checklist; Shape B sits on the same executor.

#### Test 4.1 — operator + panel appear

- In a Geometry Nodes editor, open the N-panel.
- Expected: a **Coding Nodes** tab with a "Coding Nodes Expression
  Group" panel: an expression text field and an *Add Expression Node
  Group* button.

#### Test 4.2 — drop a group into an existing tree

1. Add a Geometry Nodes modifier to a mesh; open its tree.
2. In the Coding Nodes panel, keep the default `offset` expression.
3. Click *Add Expression Node Group*.
- Expected: a Group node appears in the tree, labeled with the
  generated group name, referencing the compiled `Expr_offset` tree
  with `amp` as an input and a `Result` output.
- Wire its `Result` into a Set Position offset; confirm the mesh
  deforms and animates with the timeline.

#### Test 4.3 — same compiler as Shape A

1. Apply the same expression via the Expression *Modifier* (Shape A)
   on another object.
- Expected: visually identical result. (Same plan, same tree shape —
  asserted headlessly by `test_shape_a_and_shape_b_share_one_plan`.)

#### Test 4.4 — compile error in the panel

1. Type a bad expression; click the button.
- Expected: red error box in the panel, no node added, no crash.

#### Soft spots to record

- **In-place re-edit of a dropped group.** First cut creates a fresh
  group datablock per add. Re-pointing every existing instance of a
  group when its expression changes is the M4 follow-up; note the
  desired UX after 4.2 works.
- **2D-cursor placement.** The new node currently lands at origin;
  placement polish is M5.

### Outcome

When 4.1–4.4 pass, M4's done-criterion is met: *the user drops an
expression into any GN tree as a group node, edits it, and it works* —
the same compiler as the modifier, a different delivery surface.

## Milestone 5 — Polish (`tests/m5_polish/`)

**What it proves headlessly:** the expression group can be wrapped for
real modifier use (Geometry in/out apply modes); tuned parameter values
survive a recompile; every unsupported construct fails with a clear,
located, hinted message; the docs cannot drift from the implementation;
the addon packages into a structurally valid, self-contained zip.

| Test file | Verifies |
|---|---|
| `test_apply_modes.py` | `raw` / `offset` / `absolute`; the wrapper is a Geometry-in/out group instantiating the expression group; params still exposed |
| `test_param_reconcile.py` | Values kept on stable signature; new→default; removed→dropped; type-change→reset; signature-change detection |
| `test_error_quality.py` | A 22-case matrix: each unsupported construct → expected message; errors are located; `str()` renders line+caret; unknown-name hints builtins |
| `test_doc_accuracy.py` | Every built-in is in `expression-reference.md`; emitter registry covers the frontend universe; backend-only ops excluded; key docs exist |
| `test_packaging.py` | `tools/package_addon.py` builds a zip bundling both packages + a register shim, no `__pycache__`, idempotent |

**M5 headless done-criterion:** `tests/m5_polish/` is green (71 tests).

Build the installable addon:

```bash
cd coding-nodes && python3 tools/package_addon.py dist
# -> dist/coding_nodes_addon.zip
```

### Milestone 5 — Blender verification **[Blender]** (the planned test)

Run after the M3/M4 checklists.

#### Test 5.1 — install the packaged zip

1. `python3 tools/package_addon.py dist`.
2. Blender › Preferences › Add-ons › Install from Disk →
   `dist/coding_nodes_addon.zip`; enable it.
- Expected: enables with no errors; both the Modifier panel (Shape A)
  and the Node Editor "Coding Nodes" tab (Shape B) appear. No external
  `sys.path` setup needed — the libs are bundled.

#### Test 5.2 — apply modes (Shape A)

1. Expression Modifier on a plane, `examples/ripple.py`.
- Expected (mode `offset`, the modifier default): the modifier tree has
  **Geometry in → Set Position → Geometry out**, the expression group
  instanced between, `freq`/`amp` as modifier inputs; the plane ripples.
- Switch to `absolute` (when the mode selector lands in the M5
  follow-up): the Result drives absolute position instead of an offset.

#### Test 5.3 — parameter values survive a recompile

1. Set `freq` to 12 on the modifier.
2. Edit the body (keep `freq`/`amp`); Recompile.
- Expected: `freq` stays 12 (reconcile kept it — the signature was
  unchanged). Rename `freq`→`f` and recompile → `f` appears at its
  default (renamed = new parameter).

#### Test 5.4 — error messages read well in-panel

- Trigger several cases from the `test_error_quality.py` matrix; confirm
  the panel shows the message + the offending line, no crash.

#### Soft spots to record

- **`absolute` mode UI.** The plan supports `raw`/`offset`/`absolute`;
  the modifier currently hardcodes `offset`. A mode dropdown is the M5
  follow-up.
- **`normal` mode.** Scalar-Result-along-normal is intentionally not in
  `APPLY_MODES` yet (type handling); add when a case needs it.
- **Reconcile wiring.** `reconcile()` is unit-proven; confirm the
  modifier actually calls it across a rebuild and re-applies values.

### Outcome

When 5.1–5.4 pass, the product is shippable: installable in one zip,
two working shapes, values that survive edits, and errors that explain
themselves. Remaining items become the M5 follow-up list.

## Milestone 6 — Reference Evaluator / oracle (`tests/m6_evaluator/`)

**Fully headless — no Blender, ever.** The numpy evaluator runs the
expression graph directly and proves the *numbers* are right, not just
that the plan is shaped right. It is the oracle every future backend
(OSL/GLSL/GPU) gets validated against.

| Test file | Verifies |
|---|---|
| `test_correctness.py` | Arithmetic, vectors, built-ins, user-function inlining compute exactly; **ripple == hand-written numpy, 0.0 error**; `set_attr` records correctly |
| `test_curl_noise_eval.py` | curl-noise: (N,3), finite, deterministic, time/seed/strength sensitive |
| `test_noise_spec.py` | Reference value-noise/voronoi properties pinned (range, determinism, spatial+temporal continuity) |
| `test_oracle_api.py` | `evaluate()` defaults, shapes, normals fallback, attribute/object injection, EvalResult is array-like |

**M6 done-criterion:** `tests/m6_evaluator/` green (32 tests). There is
**no M6 Blender step** — correctness is proven entirely headlessly.
This is the deliverable that converts "we think it's right" into "we
proved it's right" for the whole M1→M5 path.

Try it:

```bash
python3 - <<'PY'
import sys; sys.path[:0] = ["coding-nodes", "sacred-geometry-engine"]
import numpy as np
from coding_nodes import compile, evaluate
c = compile(open("coding-nodes/examples/ripple.py").read())
P = np.random.uniform(-2, 2, (5, 3))
print(evaluate(c, P=P, t=0.3).values)
PY
```

See `docs/evaluator.md` for the reference noise/voronoi spec and the
Blender-noise caveat (GN delegates to Blender's noise nodes, so
noise-containing expressions match OSL/GLSL but not GN — by design).

## Milestone 7 — OSL backend (`tests/m7_osl/`)

**Headless:** the same expression compiled to an Open Shading Language
shader (`osl_source(...)`). First backend off the multi-backend
trajectory; validated against the M6 oracle.

| Test file | Verifies |
|---|---|
| `test_osl_coverage.py` | Every frontend op has an OSL template (or is one of the two emitter-special-cased ops) |
| `test_osl_structure.py` | Shader signature; balanced braces/parens; **SSA — every `vN` declared before use**; params surfaced; noise lib only when used; ripple chain faithful; scalar/vector output; name override |
| `test_osl_compile.py` | Runs `oslc` on the generated shaders **if oslc is on PATH**; skips cleanly otherwise (auto-runs in any toolchain'd env) |

**M7 headless done-criterion:** `tests/m7_osl/` green (15 tests; the 2
oslc tests skip without the toolchain).

Inspect a generated shader:

```bash
python3 - <<'PY'
import sys; sys.path[:0] = ["coding-nodes", "sacred-geometry-engine"]
from coding_nodes import osl_source
print(osl_source(open("coding-nodes/examples/ripple.py").read()))
PY
```

### Milestone 7 — OSL-runtime checklist **[oslc / testshade / Blender]**

Run where the OSL toolchain exists (no Blender GUI needed for the first
two):

1. **Compile.** `oslc shader.osl` succeeds for both examples. (The
   pytest in `test_osl_compile.py` does this automatically when `oslc`
   is on PATH.)
2. **Numeric parity, noise-free.** For a noise-free expression (e.g.
   ripple), `testshade` output over a grid equals
   `evaluate(compiled, P=grid, t=...)` to float epsilon — expected
   exact, since OSL stdlib is IEEE-identical to numpy.
3. **Numeric parity, noise.** For curl-noise, compare to the oracle;
   record any lattice-hash mismatch (Python uint32 vs OSL `int`
   overflow/shift) — that's the known parity item to reconcile in the
   M7 follow-up.
4. **In Cycles (Blender).** Assign the shader in a Cycles material;
   confirm it drives the expected channel and animates with `Time`.

#### Soft spots to record

- **Lattice-hash bit-parity** across Python/OSL for `noise()`/
  `voronoi()` (item 3).
- **`attr.read`/`obj.read`** currently emit neutral defaults; wiring to
  OSL `getattribute()` is the M7 follow-up.

### Outcome

When `tests/m7_osl/` is green and the runtime checklist confirms
compile + noise-free parity, M7 is done: the same expression is a
correct Cycles shader, validated against the oracle.

## Continuous checks

Run before every commit:

```bash
cd coding-nodes && python3 -m pytest tests/ -q
```

Add a test alongside any new behavior, in the milestone directory it
belongs to. Keep new tests headless unless the behavior genuinely needs
Blender — in which case document the manual steps in this file under the
relevant milestone.
