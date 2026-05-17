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

## Milestone 3+ — GN op emitters & Expression Modifier **[Blender]**

M1 and M2 are fully headless. The step that turns the grouped graph
into actual Geometry Nodes — per-op emitters (`math.sin` → a Math node,
`vec.combine3` → a Combine XYZ node, …) and the sub-group wrapping —
requires Blender and is verified there:

1. Install the addon (instructions land with M3).
2. Add the Expression modifier to a mesh.
3. Paste `examples/ripple.py`; scrub the timeline; confirm the mesh
   responds.
4. Paste `examples/curl_noise.py`; open the generated node group;
   confirm one `curl` group containing twelve `n` sub-groups, not a
   wall of math nodes.

Until M3, the headless suite is the source of truth for correctness;
the Blender step is the source of truth for the visual result.

## Continuous checks

Run before every commit:

```bash
cd coding-nodes && python3 -m pytest tests/ -q
```

Add a test alongside any new behavior, in the milestone directory it
belongs to. Keep new tests headless unless the behavior genuinely needs
Blender — in which case document the manual steps in this file under the
relevant milestone.
