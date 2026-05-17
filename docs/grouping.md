# The Grouping Pass (M2)

How a flat EvalGraph becomes a readable hierarchy of named sub-groups.
This is the design behind `coding_nodes/grouping/`.

## The problem it solves

The M1 frontend inlines every user-function call. Compiling
`examples/curl_noise.py` (whose `curl` calls a helper `n` twelve times)
produces ~50 flat EvalGraph nodes. Emitted naively to Geometry Nodes,
that's a wall of `Math` and `Vector Math` nodes — exactly the mess this
project exists to avoid.

The grouping pass reconstructs the structure the user actually wrote, so
the eventual GN tree reads like the source: a `curl` group containing
`n` sub-groups, not loose arithmetic.

## How structure survives inlining

The frontend tags every emitted node with a **scope path**: a tuple of
frame ids recording which function call it came from.

```
("curl#0",)              # a node directly in the entry function
("curl#0", "n#3")        # a node inside the 3rd call to helper n()
```

Each function entry — the entry function and every inlined call — pushes
a uniquely-numbered frame (`name#counter`). So twelve calls to `n` get
twelve distinct frames (`n#1` … `n#12`), and the pass can tell call
instances apart even though their nodes are interleaved in the flat
graph.

These tags live on `EvalNode.params["__scope_path__"]` and, for
convenience, on `CompiledExpression.scope_paths` (`node_id -> path`).

## The pass

`group(compiled, inline_threshold=3) -> GroupedGraph`, three steps:

### 1. Build the region tree

Walk every node's scope path. For each path prefix, ensure a
`GroupRegion` exists; link it under the region of its parent prefix.
Assign each node to the region whose path equals the node's path
exactly. The single-element-path region is the **root** (the entry
function — the main tree, never wrapped).

Result: a tree of regions mirroring the call structure.

### 2. Compute boundary sockets

For a region `R` with member set `M` (R's direct nodes plus all
descendants), examine every edge:

- **Edge into R** (source outside `M`, target inside): becomes an
  **input** socket. The external producer feeds the sub-group.
- **Edge out of R** (source inside `M`, target outside): becomes an
  **output** socket.

Plus one subtlety: if a region produces the graph's final result, the
value leaves through `graph.outputs` rather than an edge to another
node. That still needs an output socket, so the pass also scans
`graph.outputs` and adds an output boundary (with `consumer_node = -1`
marking "graph output") for any result produced inside a non-root
region.

Boundaries are **deduplicated** by `(producer_node, producer_socket)`:
one external value used by three internal nodes is one input socket;
one internal result consumed by three external nodes is one output
socket.

### 3. Inline heuristic

A region with `node_count() <= inline_threshold` (default 3) is marked
`inlined`. Inlined regions stay flattened into their parent rather than
becoming their own sub-group — wrapping `x * 2.0` in its own box helps
nobody. The threshold is configurable; the root is never inlined.

## The output: `GroupedGraph`

Pure data, no `bpy`:

```python
GroupedGraph
├── graph: EvalGraph                 # the original flat graph (unmutated)
└── root: GroupRegion
    ├── function / instance / path
    ├── direct_node_ids              # nodes at this exact scope
    ├── children: [GroupRegion, …]   # nested calls
    ├── inputs / outputs: [BoundarySocket]
    ├── inlined: bool
    └── is_root: bool

GroupedGraph.wrapped_regions()  # non-root, non-inlined -> real sub-groups
GroupedGraph.inlined_regions()  # flattened into parent
GroupedGraph.describe()         # JSON-friendly summary
```

The grouping pass never mutates the underlying `EvalGraph` — it
describes a hierarchy *over* it. The graph stays acyclic and
backend-agnostic.

## What consumes this (M3)

The GN backend extension walks a `GroupedGraph`:

- Each `wrapped_region` → a new GN node-group datablock. Its
  `inputs`/`outputs` define the group's interface. Its `direct_node_ids`
  (and inlined descendants) emit inside it.
- Each region reference in a parent → a Group node instance, wired via
  the boundary sockets.
- The root → the top-level tree.

Structurally identical sibling regions (e.g. the twelve `n` calls) are a
natural place to share one node-group datablock referenced many times —
a follow-up optimization the data model already supports (compare
regions by op/edge shape).

## Worked example

`examples/curl_noise.py`:

```
curl(P, t, scale, strength)        -> root region "curl#0"
  n(P + …, 1.0)  (×12)             -> 12 child regions "n#1" … "n#12"
```

`group(compile(src), inline_threshold=2).describe()` shows a `curl` root
with twelve `n` children, each carrying its own input sockets (the
offset vector and seed) and one output socket (the noise scalar). The
root's *direct* node count is a fraction of the ~50 total — the rest
live inside the `n` regions. That is the "not a flat sea of nodes"
guarantee, verified by
`tests/m2_grouping/test_examples_grouped.py`.

## Related

- `../PLAN.md` — milestones
- `../TESTING.md` — how to verify each milestone
- `../SPEC.md` — the GN emission strategy that consumes this
