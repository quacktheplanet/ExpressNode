# 02 — Existing Alternatives

An honest comparison of tools that overlap with this project's intent. The
conclusion: each solves a related problem; none solves the specific gap
this project targets.

## Sverchok

**What it is.** A parametric node-based geometry system, philosophically
similar to Grasshopper for Rhino or Houdini's VEX. Around 600 nodes
covering CAD-style operations, math, lofting, CSG, recursion.

**Python in nodes?** Yes — Sverchok has Python script nodes where you can
write arbitrary Python that operates on Sverchok's data types.

**Why this isn't the same project:**

- **Parallel ecosystem.** Sverchok is its own node universe with its own
  data types (`SvVertices`, `SvEdges`, `SvFaces`, ...). It does not
  interoperate with Blender's native Geometry Nodes graphs.
- **Different mental model.** Sverchok is closer to Grasshopper's
  list-of-lists everything-is-vectors-and-loops paradigm. PyNodes (this
  project) targets a smaller, GN-adjacent surface for users who already
  live in GN.
- **Output to Blender.** Sverchok produces final Blender mesh datablocks
  at end-of-graph nodes; it doesn't write attributes mid-graph that a GN
  modifier on the same object can read.

**Relevant takeaways.** Sverchok's Python script node design is a useful
reference. Its long-running maintenance has produced good answers for
node-tree persistence, undo integration, and dependency handling.

## Animation Nodes

**What it is.** A motion-graphics-focused node system, separate from GN.
Predates GN by years. Last release supported up to Blender 4.2.

**Python in nodes?** Yes — supports scripting and procedural execution.

**Why this isn't the same project:**

- **Largely superseded.** GN absorbs most of Animation Nodes' motion-graphics
  use cases. Active development is minimal.
- **Standalone evaluation.** Like Sverchok, AN is its own system with its
  own data flow. It can drive Blender data, but doesn't interoperate
  inside a single object's GN modifier stack.
- **Aging codebase.** Built when Python 3.7 was current; modernization
  would be substantial.

**Relevant takeaways.** AN's "Expression Node" (a Python evaluator) is a
good UX reference: a small text field, autocomplete from input sockets,
output sockets dynamically updated.

## Open Shading Language (OSL)

**What it is.** A shading language supported by Cycles (CPU mode).
Programmable procedural shaders with custom math, custom noise, custom
patterns.

**Why this isn't the same project:**

- **Shaders only.** OSL affects rendering, not geometry. You cannot
  displace vertices with OSL, only fake displacement via bump/normal in
  the shader.
- **Cycles CPU only.** No Eevee support, no GPU.
- **Not Python.** OSL is its own language (C-like).

**Relevant takeaways.** OSL proves Blender users want programmable
shading and procedural control. PyNodes brings that to the geometry side.

## Comparison table

|  | Sverchok | Animation Nodes | OSL | **PyNodes (this)** |
|---|---|---|---|---|
| Custom node tree | yes | yes | (shader subgraph) | yes |
| Python in nodes | yes | yes | no (OSL only) | yes |
| Interops with native GN | no | no | n/a | **yes** (via named attributes) |
| Affects geometry | yes | yes | no | yes |
| Affects shading | indirectly | no | yes (Cycles only) | indirectly (via attrs) |
| Numpy first-class | partial | partial | n/a | **yes** |
| Active development | yes | minimal | yes (Cycles) | (spec only) |
| Learning curve | steep | moderate | steep | aims low |

## The gap

What does not exist today, and what this project would provide:

> A Blender addon that adds Python-executing nodes designed to
> interoperate cleanly with native Geometry Nodes through shared named
> attributes, with first-class numpy support, minimal mental overhead for
> a GN-fluent user, and a UX optimized for short snippets, not whole
> programs.

That gap is the project's reason for existing.

## Related docs

- Three levels of implementation: `03-three-levels.md`
- Overview: `01-overview.md`
