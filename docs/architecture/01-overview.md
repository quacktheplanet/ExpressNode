# 01 — Overview

## Why this project exists

Blender's Geometry Nodes (GN) does not allow arbitrary Python execution
inside node graphs. That is intentional:

- **GIL.** Python is single-threaded under the GIL; GN aims to evaluate
  parallel across millions of points.
- **GPU.** GN is moving toward GPU execution; Python doesn't translate.
- **Determinism.** Side-effectful Python code breaks reproducibility.
- **Sandboxing.** Arbitrary Python is a security/stability liability inside
  the dependency graph.
- **Caching.** Caching opaque Python is much harder than caching pure ops.

These constraints are correct for GN's architecture. They are not correct
for a separate authoring surface designed for prototyping, math
experiments, and motion-graphics-style work, where Python's
expressiveness outweighs the loss of parallelism.

## What this project adds

A separate, parallel node tree — `PyNodeTree` — registered as its own
Blender editor space. Inside it, nodes can execute Python (and numpy)
code, with:

- A pull-based evaluator that runs only nodes affected by changes.
- A per-node code cache (compile-once, exec-many).
- Restricted globals by default (no `os`, `sys`, `subprocess`).
- Caching by `(node_id, input_hash)`.
- A geometry bridge to Blender mesh/point-cloud/curves datablocks via
  numpy.
- A clean round-trip to/from neighboring GN modifiers through named
  attributes.

The result is a "Python sidecar" that complements GN rather than replacing
it.

## Use cases that motivate the project

- A motion designer wants to displace a mesh with a custom mathematical
  function that doesn't map cleanly to GN's math nodes. Today they string
  together a dozen math nodes; with PyNodes they write three lines.
- A technical artist wants to prototype a new SDF blend rule. PyNodes lets
  them script it in numpy first, validate visually, then port to GN if
  performance demands it.
- A researcher wants to use scipy in-graph (sparse matrices,
  optimization, statistics). PyNodes makes scipy available; GN doesn't.
- A pipeline TD wants to read external data (CSV, JSON, custom binary)
  into geometry. PyNodes can call standard Python IO; GN cannot.

## Non-goals

- **General programming environment.** Not a notebook, not a REPL, not a
  Python IDE. The nodes are short snippets, not modules.
- **Replacement for GN.** PyNodes interoperates with GN; doesn't replace
  it. Heavy parallel work belongs in GN.
- **Pure-Python rendering.** No attempt to render with Python; visualize
  via Blender's renderers.

## What "done" looks like (phase 1 only)

A user installs the addon. They open the new editor space. They drop a
`NumpyKernel` node, paste a numpy snippet that computes a displacement
field from a Position attribute, connect it to a `Write Attribute` node,
point that at a mesh, and add a GN modifier on the same mesh that reads
the named attribute and applies a `Set Position`. They see the mesh
displace. Scrubbing the timeline updates the displacement.

That single end-to-end loop is the phase-1 success criterion.

## Related docs

- Existing alternatives: `02-existing-alternatives.md`
- Three implementation levels: `03-three-levels.md`
- Node tree design: `04-node-tree-design.md`
