# 11 — Roadmap & Risks

## Phase 1 — Minimum Useful Addon (3–4 months)

**Goal:** End-to-end loop: PyNodes graph → named attribute → GN modifier
reads it → mesh deforms → timeline animates.

**Deliverables:**
- `PyNodeTree` custom node tree + editor space.
- Socket types: Float, Int, Vector, Array, String, Attribute, Geometry.
- Nodes: `MeshIn`, `MeshOut`, `PyExpr`, `NumpyKernel`, `ReadAttribute`,
  `WriteAttribute`, `AttributeBridge`, `Time`, `Constant`.
- Pull-based evaluator with `(node_id, input_hash)` caching.
- Depsgraph + frame-change handlers.
- Code editor docked to Blender's Text Editor.
- Per-node error display + print log viewer.
- Restricted execution by default + "Unrestricted" toggle.
- Two shipped examples (PyExpr displace, NumpyKernel curl-noise).
- Installable as a standard `.zip` addon.

**Done =** A user installs the addon, opens the example file, scrubs the
timeline, sees the mesh animate. Then edits the kernel code, sees the
viewport update.

## Phase 2 — Quality of Life (3–6 months)

**Goal:** Make it pleasant for sustained use.

**Deliverables:**
- Async evaluation (worker thread).
- Group nodes (sub-trees as reusable nodes).
- Inline code editor with basic syntax highlighting (custom widget).
- Curve and PointCloud bridge nodes.
- `SDFFunction` node type with analytical gradient option.
- Numba auto-integration (optional dep): decorator helper, install
  detection, fall-back path.
- Per-node profiling badges, "Profile Graph" operator.
- Preset library: ~10 useful kernels (curl-noise, voronoi cells,
  metaballs, basic L-system, fibonacci spiral, etc.).

**Done =** A motion designer can build a 20-node graph and iterate
without performance frustrations on a 100k-point mesh.

## Phase 3 — Hybrid Compiler (6–9 months)

**Goal:** Compile Python expressions to GN graphs for performance.

**Deliverables:**
- Python AST parser limited to expressions (no statements except
  assignments and `return`).
- AST → GN-tree compiler for the supported subset.
- Per-node toggle: "Run as Python" vs "Compile to GN".
- Clear error messages when expressions can't compile, with explanation.
- Coverage: arithmetic, sin/cos/atan2, vector math, where/select,
  named-attribute reads/writes, basic conditional via `where`.

**Done =** The shipped examples can be toggled between Python execution
and GN execution; both produce the same result; GN is at least 10×
faster on N=1M points.

## Phase 4 — Polish & Ecosystem (open-ended)

- Documentation site with cookbook recipes.
- Example library (50+ kernels).
- Integration with sister projects (Sacred Geometry Engine).
- Possibly contribute upstream ideas to Blender core (Python-in-GN
  discussions).

## Technology choices

| Layer | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Language | Python 3.11 | + optional numba | + AST parsing |
| Math | numpy | + optional numba/scipy | + AST → GN emit |
| UI | bpy panels + Text Editor docking | + custom widgets | + compiler diagnostics UI |
| Persistence | inline strings on nodes | + optional Text datablock per node | (same) |

## Risks

### Blender API churn
GN and the node API have moved fast (4.0 interface change, etc.).
Mitigation: pin to one or two Blender versions per release. Maintain a
small compatibility shim at the boundary.

### GIL & Python performance
Some users will want truly parallel execution and discover the GIL the
hard way. Mitigation: explicit performance docs (`10-performance.md`),
clear messaging that PyNodes is the CPU/Python tier, with GN as the
parallel tier.

### Sandboxing trust
Restricted execution is defense in depth, not airtight. Sharing
`.blend` files with PyNodes graphs is no riskier than sharing any
Python-using `.blend`, but users may misperceive the security boundary.
Mitigation: clear messaging, restricted-by-default, escalation requires
explicit user action.

### Depsgraph dragons
Live update via depsgraph hooks is delicate. Edge cases: recursion (a
PyNode evaluation that triggers another depsgraph update), undo/redo
interaction, file load. Mitigation: guarded handlers, careful testing
across Blender versions, an emergency "disable handlers" preference.

### Addon UI consistency
Blender users have strong UI expectations. Mitigation: match existing
patterns (editor space, add menu, panels). Don't invent UI; copy from
Geometry Nodes.

### Scope creep
PyNodes could become a general programming environment, which it
shouldn't. Mitigation: phase gates with explicit Done criteria. Reject
features that don't help the core "Python-in-graph alongside GN" mission.

### Maintenance burden
Custom node trees are subtle. Bugs around saving/loading, undo, and
linked libraries are time sinks. Mitigation: test coverage from day one,
specifically for save/load round-trips and undo behavior.

## What we deliberately defer

- Per-frame state at the node level (use Blender's Simulation Zones).
- Multi-DCC support (Blender only).
- Cloud / remote evaluation.
- AI-generated code suggestions inside nodes (separate project, opt-in).

## Related docs

- Three levels: `03-three-levels.md`
- Performance: `10-performance.md`
- Overview: `01-overview.md`
