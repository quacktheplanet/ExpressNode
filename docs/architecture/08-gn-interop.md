# 08 — Geometry Nodes Interop

## Purpose

Define the bridge between PyNodes and native Geometry Nodes. This bridge is
the heart of the project: PyNodes and GN collaborate, each handling the
work it does best.

## Interop model

The two systems run on the same object's evaluation chain, communicating
via **named attributes** on the object's geometry.

```
+------------------+   writes "displacement" attr   +------------------+
|  PyNodes tree    | -----------------------------> |  Object's mesh   |
+------------------+                                +------------------+
                                                              |
                                                              | reads
                                                              v
                                                    +------------------+
                                                    |  GN modifier on  |
                                                    |  same object     |
                                                    | "Named Attribute"|
                                                    |   -> Set Position|
                                                    +------------------+
```

PyNodes computes; GN deforms. Or the other way around: GN computes a
field, PyNodes reads it via `ReadAttribute`, applies a fancier numpy op,
writes it back, GN consumes the result.

## Evaluation order

PyNodes evaluates **before** GN modifiers in the modifier stack. That is
the contract.

- The PyNodes "modifier" (technically: a hidden modifier-like construct
  the addon registers) runs first.
- It writes any output attributes to the mesh.
- Subsequent GN modifiers see those attributes via their
  `Named Attribute` node.

If a user wants the reverse order (GN computes first, then PyNodes reads
the GN output), they put a GN modifier above and a second PyNodes
"modifier" below.

## Named attribute conventions

The addon does not impose a namespace on attribute names. The user
chooses. But the addon ships defaults for common cases:

| PyNodes node | Default attribute |
|---|---|
| `Displacement Kernel` | `displacement` (FLOAT_VECTOR, POINT) |
| `Density Kernel` | `density` (FLOAT, POINT) |
| `Color Kernel` | `color` (FLOAT_COLOR, POINT) |
| `Selection Kernel` | `selection` (BOOLEAN, POINT) |

Users can override the name on the node. The GN side reads the same name
via a `Named Attribute` node.

## The `AttributeBridge` node

A dedicated node that wraps attribute writing:

```
inputs:
  Object: target object
  Name:   string (attribute name)
  Type:   FLOAT | INT | VECTOR | COLOR | BOOL
  Domain: POINT | EDGE | FACE | CORNER
  Data:   numpy array

side effect:
  Writes (or creates) the named attribute on the object.
output:
  Object: passthrough (allows chaining)
```

The bridge node is the only node that mutates Blender data. Every other
PyNode is pure. This contains side effects to one obvious node type.

## The `ReadAttribute` node

The inverse: reads a named attribute from an object into a numpy array.

```
inputs:
  Object: source object
  Name:   string
outputs:
  Data:   numpy array, shape inferred from domain + type
```

Reading is non-destructive. Use it to bootstrap a PyNodes graph from an
object's positions, GN-computed scratch attribute, etc.

## Evaluation ordering caveats

- PyNodes evaluation triggers a depsgraph update.
- The user's GN modifier will then see the new attribute on the next
  evaluation.
- There is a one-frame lag if PyNodes and GN are configured naively in a
  cyclic dependency (PyNodes reads GN output of the *same* modifier).
- To break cycles, separate "read" and "write" phases or use two GN
  modifiers (one above PyNodes, one below).

## Cycle detection

The addon detects when PyNodes reads an attribute that the same object's
GN modifier (below it in the stack) also writes. In that case it warns:
"This creates a one-frame feedback loop. Consider reordering modifiers
or using a separate object."

## Performance

Attribute round-trip is two `foreach_get`/`foreach_set` calls per
interop point. For `(N, 3)` data on a 100k-vertex mesh this is ~5ms
total, dwarfed by the actual computation. Not a bottleneck.

## Open questions

- Should the addon offer a "GN Tree Reference" node that compiles to a
  GN node group and runs it as part of the PyNodes graph? **Possibly** in
  phase 2 — would let PyNodes orchestrate small GN snippets.
- Per-frame consistency: if a PyNodes write changes mid-frame (e.g. a
  modal operator dragging a slider), how do we guarantee Cycles render
  sees the final value? Document the workflow; recommend final-render
  bake before output.

## Related docs

- Geometry bridge: `06-geometry-bridge.md`
- Live update: `07-live-update.md`
- Node reference: `../api/node-reference.md`
