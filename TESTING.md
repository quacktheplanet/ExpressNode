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

## Continuous checks

Run before every commit:

```bash
cd coding-nodes && python3 -m pytest tests/ -q
```

Add a test alongside any new behavior, in the milestone directory it
belongs to. Keep new tests headless unless the behavior genuinely needs
Blender — in which case document the manual steps in this file under the
relevant milestone.
