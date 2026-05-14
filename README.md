# Coding Nodes for Blender

A specification for a Blender addon that introduces **Python-executing nodes**
in a custom node tree, addressing the gap that native Geometry Nodes does not
allow arbitrary Python execution.

**Status: specification only. No implementation code in this repo.**

## Why this project exists

Blender's Geometry Nodes is intentionally not a Python execution environment.
That decision is correct for GN's architecture (parallel, GPU-friendly,
deterministic), but it leaves a real authoring gap: motion graphics,
mathematical experimentation, numpy-vectorized algorithms, and rapid
prototyping benefit from Python in-graph.

Existing tools in the space:

| Tool | What it offers |
|---|---|
| **Sverchok** | A whole parallel node universe with Python script nodes |
| **Animation Nodes** | Motion-graphics scripting in nodes |
| **OSL** | Programmable shader logic in Cycles |

This project specifies a Blender addon for Python-executing nodes
that interoperate with native Geometry Nodes through shared named
attributes.

## Vision in one sentence

A custom node tree where each node may run a small Python (or numpy) snippet,
interoperating with neighboring Geometry Nodes modifiers through shared named
attributes, with caching, error reporting, and a usable editor UX.

## Status of this repo

Spec only. Files describe:
- the design space and existing alternatives,
- three implementation levels (addon / hybrid compiler / native) with tradeoffs,
- the proposed node tree, socket types, evaluation model, execution semantics,
- the Blender integration surface,
- performance and roadmap.

Read order:

1. `SCOPE.md` — **start here.** Vision, audience, phased execution,
   use-case brainstorm, decision triggers.
2. `SPEC.md` — executive overview of the architecture.
3. `docs/architecture/01-overview.md` through `11-roadmap-risks.md`.
4. `docs/api/node-reference.md` — proposed node types.
5. `docs/examples/` — two worked examples.

## Relationship to other projects in this repo

| Project | Role |
|---|---|
| `../annihilation-morph-script/` | Runnable demo of sacred-geometry forms |
| `../sacred-geometry-engine/` | Framework spec for the same vision at scale |
| `coding-nodes/` (this) | Infrastructure that would unlock both — Python nodes can host the sacred-geometry DSL or the morph script's math directly |

Coding Nodes is independent of the other two projects — it stands on its own
as a Blender capability. But if it exists, the Sacred Geometry Engine becomes
much easier to implement, because the DSL can be hosted as a single
NumpyKernel node rather than emitted as a sprawling GN graph.

## Target platform

Blender 4.x and 5.x. Python 3.11+. Numpy. Optionally scipy/numba.

## License

Unlicensed. Treat as private specification until decided.
