# Existing Alternatives

A comparison of tools in adjacent spaces, to clarify where ExpressNode
sits relative to the existing landscape.

## Sverchok

**What it is.** A parametric node-based geometry system, philosophically
similar to Grasshopper for Rhino or Houdini's VEX. Around 600 nodes
covering CAD-style operations, math, lofting, CSG, recursion.

**Python in nodes?** Yes — Sverchok has Python script nodes where you
can write arbitrary Python that operates on Sverchok's data types.

**How ExpressNode differs:**

- **Output target.** ExpressNode produces native Blender Geometry
  Nodes trees that drop into a standard modifier stack. Sverchok
  produces final Blender mesh datablocks from its own node universe.
- **Authoring surface.** ExpressNode is a single expression compiler —
  type math, get a GN subtree. Sverchok is a full alternative node
  ecosystem with 600+ node types.
- **Mental model.** ExpressNode targets users already fluent in GN
  who want one more way to express algorithms. Sverchok asks users to
  learn a new node ecosystem.

**Useful reference points from Sverchok:** Their Python script node
design, their long history with node-tree persistence and undo
integration, their dependency-handling patterns.

## Animation Nodes

**What it is.** A motion-graphics-focused node system, separate from
GN. Predates GN by years. Last release supported up to Blender 4.2.

**Python in nodes?** Yes — supports scripting and procedural execution.

**How ExpressNode differs:**

- **Integration with GN.** ExpressNode outputs go inside GN trees
  directly. Animation Nodes runs as its own evaluation system.
- **Active focus.** ExpressNode targets a small, sharp problem
  (Python expression → GN subtree). Animation Nodes was broader; its
  motion-graphics ground has largely been absorbed by native GN.

**Useful reference point from Animation Nodes:** their "Expression
Node" (a Python evaluator) — small text field, autocomplete from input
sockets, output sockets dynamically updated. Good UX template.

## Open Shading Language (OSL)

**What it is.** A shading language supported by Cycles (CPU mode).
Programmable procedural shaders with custom math, custom noise, custom
patterns.

**How ExpressNode differs:**

- **Domain.** OSL affects rendering. ExpressNode affects geometry.
  They occupy different stages of Blender's pipeline.
- **Language.** OSL is a C-like language. ExpressNode uses a Python
  subset.

**Useful reference point from OSL:** OSL is the second backend we'd
likely add (compile the same Python expression to an OSL shader),
making "shading equivalents" of ExpressNode kernels trivial. Blender
already ships OSL for Cycles, so the dependency is already there.

## bpy scripting — "Python that builds a GN tree by hand"

**What it is.** Standard Blender Python — `bpy.data.node_groups.new(...)`,
`tree.nodes.new(...)`, `tree.links.new(...)`. Lets you build any GN
tree programmatically.

**How ExpressNode differs:**

- **Expressiveness.** bpy scripting authors each node by hand. Coding
  Nodes authors the math; the compiler generates the nodes.
- **Output quality.** bpy scripts often produce flat trees. Coding
  Nodes wraps user-defined functions as named group nodes.
- **Iteration loop.** bpy scripts are typically write-once; rerunning
  rebuilds from scratch. ExpressNode lives behind a text field that
  recompiles on edit, with stable parameter bindings across rebuilds.

## Comparison table

| Property | Sverchok | Animation Nodes | OSL | bpy scripts | **ExpressNode** |
|---|---|---|---|---|---|
| Output target | Sverchok mesh | AN data | Cycles shader | Native GN | **Native GN** |
| Authoring surface | 600+ nodes | 200+ nodes | C-like language | bpy code | **Python expression** |
| Affects geometry | yes | yes | no (shading) | yes | **yes** |
| Affects shading | indirectly | no | yes (Cycles) | indirectly | indirectly (via attrs) |
| Live edit | yes | yes | recompile | rerun script | **yes** |
| Output is readable | sometimes | sometimes | n/a | depends on author | **yes (group-wrapped)** |
| Learning curve | steep | moderate | steep | moderate | **low (looks like math)** |

## Where ExpressNode sits

> Type a Python expression. Get a clean, group-wrapped Geometry Nodes
> subtree. Use it as a modifier, or drop it into an existing GN tree.

The specific gap: there's no addon that takes a math expression and
produces a polished native GN graph designed to be read, edited, and
shipped. ExpressNode is the polished version of "Python that builds
GN trees."

## Related docs

- `design/SPEC.md` — architecture
- `design/SCOPE.md` — vision and audience
- `design/PLAN.md` — build milestones
