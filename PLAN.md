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

> **Status:** M1 ✅ done. M2 ✅ done. Next up: M3.
> Run `python3 -m pytest tests/` (see `TESTING.md` for the
> milestone-by-milestone verification path).

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

### M3 — GN op emitters + Expression Modifier (Shape A) (≈1–1.5 weeks)

**Deliverables:**
- GN emitters for every op the frontend produces (`input.*`, `math.*`,
  `vec.*`, `texture.*`, `compare.*`, `bool.*`, `flow.if`, `attr.*`,
  `obj.*`, `constant.*`).
- A `GroupedGraph` → Blender node-tree emitter: each wrapped region
  becomes a GN node-group datablock; references become Group nodes.
- `coding_nodes.runtime.modifier` implements the Expression Modifier:
  text field, "Recompile", "View Graph", error display.
- On expression change: debounced recompile, in-place GN group rebuild.
- Parameter bindings survive recompiles when the signature is unchanged.

**Done =** In Blender, the user adds the modifier, types the ripple
example, scrubs the timeline, and the mesh responds. The curl-noise
example shows a `curl` group containing twelve `n` sub-groups.

### M4 — Expression Node Group (Shape B) (≈3–4 days)

**Deliverables:**
- `coding_nodes.runtime.node_group` registers a node group the user
  can drop into any GN tree.
- The node group's interior is managed by the same compiler.
- Inputs and outputs are auto-derived from the expression signature.

**Done =** In Blender, the user can drop the Expression Node Group
into an existing GN tree, type an expression, and the node group's
contents update.

### M5 — Polish, examples, ship (≈1 week)

**Deliverables:**
- The two examples are documented step-by-step in `docs/examples/`.
- The expression reference doc lists every supported construct.
- Error messages have been triaged: each unsupported Python feature
  gives a useful, specific error message.
- Installable `.zip` builds and loads on Blender 4.x and 5.x.
- README contains install + first-run instructions.

**Done =** A first user can install the zip, follow the README, and
have a working example in under 5 minutes.

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
