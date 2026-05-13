# Coding Nodes — Executive Specification

**Version:** 0.1 (draft)
**Status:** Specification. No implementation.
**Target:** Blender 4.x / 5.x.

## Premise

Blender's Geometry Nodes evaluates as a compiled data-flow graph: parallel,
GPU-friendly, deterministic, with the GIL kept out. Those constraints make
arbitrary Python execution inside GN architecturally incorrect.

But there is real demand for Python-in-nodes: vectorized numpy algorithms,
mathematical experiments, custom L-systems, SDF prototyping, rapid
iteration. The right answer is **a separate node tree that runs Python**,
designed to interoperate with GN at attribute boundaries rather than fight
GN's evaluation model.

## What this project specifies

An addon that registers:

- A new `NodeTree` subclass `PyNodeTree` with its own editor space.
- A library of nodes that execute Python: `PyExpr`, `NumpyKernel`,
  `SDFFunction`, and friends.
- An evaluation model: pull-based DAG, cached per node, recomputed on input
  change.
- Bridges to Blender geometry: `bmesh`, `Mesh.attributes`,
  `foreach_get`/`foreach_set`, and named-attribute round-trip with GN.
- A live-update story: depsgraph hooks + cache invalidation.
- A UI: code editor widget per node, error display, print viewer.

## What it does NOT specify

- A Python implementation living *inside* native GN. That requires Blender
  core changes (C++). See `docs/architecture/03-three-levels.md` for why
  we recommend the addon path first.
- A general programming environment. The scope is data-flow nodes that
  execute Python; not a notebook, not a REPL, not a debugger.

## Architecture at a glance

```
+---------------------------------------+
|  PyNodeTree editor (custom space)     |
|  user authors a graph of Python nodes |
+---------------------------------------+
                  |
                  v
+---------------------------------------+
|  Pull-based evaluator                 |
|  - topological sort                   |
|  - per-node code object cache         |
|  - per-node (id, input-hash) cache    |
+---------------------------------------+
                  |
                  v
+---------------------------------------+
|  Geometry / attribute bridge          |
|  - bpy.types.Mesh <-> numpy           |
|  - named attributes <-> GN modifier   |
+---------------------------------------+
                  |
                  v
+---------------------------------------+
|  Blender scene                        |
+---------------------------------------+
```

## Layered spec

| Doc | Purpose |
|---|---|
| `docs/architecture/01-overview.md` | Problem statement, vision |
| `docs/architecture/02-existing-alternatives.md` | Sverchok / AN / OSL comparison |
| `docs/architecture/03-three-levels.md` | Addon vs Hybrid Compiler vs Native — tradeoffs |
| `docs/architecture/04-node-tree-design.md` | NodeTree, sockets, evaluation model |
| `docs/architecture/05-python-execution.md` | Code caching, sandboxing, error reporting |
| `docs/architecture/06-geometry-bridge.md` | Mesh / points / curves ↔ numpy |
| `docs/architecture/07-live-update.md` | Depsgraph hooks, dependency tracking, caching |
| `docs/architecture/08-gn-interop.md` | Reading from / writing to a GN modifier |
| `docs/architecture/09-ui-and-editor.md` | Editor space, code widget, error display |
| `docs/architecture/10-performance.md` | Vectorization, GIL boundaries, when to bail |
| `docs/architecture/11-roadmap-risks.md` | Phased delivery, risks |
| `docs/api/node-reference.md` | Proposed node types with pseudocode |
| `docs/examples/displace-with-python.md` | End-to-end example: PyExpr displacement |
| `docs/examples/numpy-field-kernel.md` | Vectorized curl-noise as a NumpyKernel node |

## Implementation levels (summary; details in `03-three-levels.md`)

| Level | What | Effort | Outcome |
|---|---|---|---|
| **1. Addon** | Custom node tree + Python-executing nodes | 2–6 months, 1–2 devs | Real, shippable. Recommended start. |
| **2. Hybrid Compiler** | Parse Python expressions, emit GN graphs ("VEX for Blender") | Add 6–12 months on top of L1 | Mainstream GN parity, much faster execution |
| **3. Native** | Modify Blender C++ to allow Python in GN | Multi-year, core dev | Speculative; not pursued first |

We recommend starting at Level 1 and treating Level 2 as a future enhancement
that **wraps** Level 1, not replaces it.

## Authoring example (Level 1)

A `NumpyKernel` node that takes an input geometry's positions, computes a
curl-noise displacement vectorized in numpy, writes a `displacement`
attribute back:

```python
# Inside the NumpyKernel node's code field:
import numpy as np

P = inputs["positions"]            # (N, 3) float32
t = inputs["time"]
freq = inputs["freq"]

eps = 1e-3
def n(p, t):
    return np.sin(freq * p[..., 0] + t) * \
           np.cos(freq * p[..., 1] + t * 1.3) * \
           np.sin(freq * p[..., 2] + t * 0.7)

nx = n(P + np.array([0, eps, 0]), t) - n(P + np.array([0, -eps, 0]), t)
ny = n(P + np.array([0, 0, eps]), t) - n(P + np.array([0, 0, -eps]), t)
nz = n(P + np.array([eps, 0, 0]), t) - n(P + np.array([-eps, 0, 0]), t)

outputs["displacement"] = np.stack([nx, ny, nz], axis=-1) * 0.2
```

A neighboring GN modifier reads the `displacement` named attribute and
plugs it into a Set Position node. The Coding Nodes addon writes the
attribute on the same object between the two evaluations.

## Out of scope (v0.1)

- Multi-threading inside Python nodes (the GIL is a hard reality).
- Persistent state across frames at the node level (use Blender's
  Simulation Zones for that; PyNodes can call into them).
- Multi-DCC support.

## Open architectural questions

These are flagged in the relevant sub-docs:

- Restricted exec vs full Python? (`05-python-execution.md`)
- Editor as separate space or sub-tree of GN editor? (`09-ui-and-editor.md`)
- Cache key: input hash, or input id + version counter?
  (`07-live-update.md`)
- GN attribute round-trip: shared attribute names with the user choosing
  the convention, or addon-managed namespace? (`08-gn-interop.md`)
