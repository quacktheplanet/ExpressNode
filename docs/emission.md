# The Backend: Emitters, Plan, Executor (M3)

How a `GroupedGraph` becomes a Blender node tree. Design behind
`expressnode/backend/`.

## Three layers, one Blender boundary

```
GroupedGraph (M2, pure)
      |
      v
op_emitters.py    op  ->  Blender node descriptor      [pure data]
      |
      v
plan.py           build_plan -> EmissionPlan           [pure data]
      |
      v   ------------------ Blender boundary ------------------
      v
gn_executor.py    execute(plan) -> bpy NodeTree         [lazy bpy]
modifier.py       Expression Modifier operator/panel    [lazy bpy]
```

Everything above the boundary is headlessly tested. Everything below
imports cleanly without Blender (lazy `import bpy` inside functions)
and is verified in Blender per the M3 checklist in `TESTING.md`.

## op_emitters.py — the registry

A pure-data table: each EvalGraph op the frontend can produce maps to an
`OpEmitter(bl_idname, settings, output, kind, note)`.

`kind`:

- **simple** — 1:1 Blender node. The executor instantiates `bl_idname`,
  applies `settings`, wires inputs in declared order, reads `output`.
  (`math.add` → `ShaderNodeMath` op `ADD`; `input.position` →
  `GeometryNodeInputPosition`; …)
- **complex** — needs a hand-written executor handler: multi-node
  expansion or dynamic settings (`vec.swizzle`, `flow.if`,
  `math.clamp/mix/smoothstep`, `texture.noise`, `attr.read/write`,
  constants, `*.floordiv`, …).
- **interface** — not a node: `input.parameter` becomes a Group Input
  socket on the root tree.
- **param_only** — never wired: `constant.string` is consumed via
  params (the literal inside `attr()`/`obj()`).

`frontend_op_universe()` derives the complete set of ops the frontend
can emit (from the builtin registry plus the structural ops the parser
emits). The coverage test asserts every one has an emitter — so "the
backend can't handle this op" is impossible to ship undetected.

## plan.py — the EmissionPlan

`build_plan(compiled)` walks the `GroupedGraph` and produces a fully
serializable `EmissionPlan`:

```
EmissionPlan
├── root_name
├── parameters: [(name, socket_type, default)]   # modifier inputs
└── groups: { name -> GroupDef }
        GroupDef
        ├── is_root
        ├── inputs / outputs: [(name, socket_type)]   # group interface
        ├── nodes: [PlannedNode]      # one per emitted EvalGraph node
        ├── instances: [GroupInstance]  # references to child GroupDefs
        └── links: [PlannedLink]      # Endpoint -> Endpoint
```

`Endpoint` is uniform: `node` / `instance` / `group_input` /
`group_output`. That uniformity is what makes the executor a dumb,
trustworthy walk.

### How the plan is built

1. **Name the groups.** Root → `Expr_<entry>`; each wrapped region →
   its sanitized frame id (`n#3` → `n_3`).
2. **Home resolution.** Each EvalGraph node belongs to the nearest
   enclosing region that owns a GroupDef (root or a non-inlined wrapped
   region). Inlined regions fold into their parent.
3. **Place nodes.** One `PlannedNode` per node (skipping interface /
   param-only ops).
4. **Place instances.** Each wrapped region becomes a `GroupInstance`
   in its parent's GroupDef.
5. **Interfaces.** Root exposes the user parameters in and a `Result`
   out. Each wrapped region's interface comes straight from the M2
   `BoundarySocket`s.
6. **Links.** Intra-group edges become `node → node`. Region
   boundaries thread `producer → instance → consumer` through the
   interface (one nesting level — exactly what `ripple` and
   `curl_noise` need).

The underlying `EvalGraph` is never mutated.

### Worked numbers (`curl_noise.py`, inline threshold 2)

- 13 groups: `Expr_curl` + `n_1` … `n_12`.
- Root: ~79 nodes, 12 instances, ~112 links.
- Each `n_*`: 2 inputs (`in_0` float seed, `in_1` vector offset), 1
  float output, ~9 nodes.

Flattened, that's ~190 loose nodes. Grouped, the user sees a `curl`
graph with twelve labeled `n` boxes.

## gn_executor.py — the Blender walk

Two passes:

1. For every GroupDef: create the `NodeTree`, add its interface, add a
   Group Input/Output node, then create its nodes (simple = generic;
   complex = hand-written handler) and its group instances.
2. For every GroupDef: resolve each `PlannedLink`'s endpoints to
   concrete sockets and connect.

Lazy `import bpy`. The headless tests import this module (proving no
top-level bpy) but never call `execute()`.

## modifier.py — Expression Modifier

An `Object` string property (the expression), a *Recompile* operator
(compile → plan → execute → attach a `NODES` modifier), and a panel
that shows compile errors inline instead of crashing. Classes are built
at `register()` time so the module imports without bpy.

## What's proven where

| Property | Proven by |
|---|---|
| Every op has an emitter | `tests/m3_emit/test_op_coverage.py` |
| Plan shape for the examples | `tests/m3_emit/test_emission_plan.py`, `test_plan_groups.py` |
| bpy modules import headlessly | `tests/m3_emit/test_import_safety.py` |
| Nodes actually build & connect | Blender checklist 3.1–3.4 (`TESTING.md`) |
| Mesh visibly responds | Blender checklist 3.2 / 3.4 |

## Related

- `design/PLAN.md` — milestones and status
- `../TESTING.md` / `design/TESTING-CHECKLIST.md` — the Blender verification checklist
- `grouping.md` — the M2 region tree this consumes
- `design/SPEC.md` — the overall architecture
