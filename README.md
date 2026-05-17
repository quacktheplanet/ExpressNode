# Coding Nodes

A Blender addon that compiles a **Python expression** into a clean,
group-wrapped **Geometry Nodes subtree**. The user types math; the
addon produces a readable algorithmic node graph.

Two shapes, one compiler:

- **Expression Modifier.** A modifier with a text field. Type an
  equation; see the result. Never open the GN editor unless you want
  to.
- **Expression Node Group.** A node group you drop into any existing
  GN tree. Same compiler. Embeddable in larger graphs.

## Quick example

```python
def ripple(P, t):
    return vec3(0, 0, sin(P.x * 6 + t) * 0.3)
```

Type that into the Expression Modifier. The mesh ripples. The
generated GN tree contains one `ripple` group node with the math
inside — not a wall of `Math (MULTIPLY)` nodes.

## Status

M1 (frontend: Python → EvalGraph), M2 (grouping pass), and M3's
headless layer (op emitters + emission plan + import-clean bpy
executor/modifier/addon) are built and tested — **115 passing tests,
no Blender required**. The M3 Blender verification is a planned,
checklisted step (see `TESTING.md`).

```bash
cd coding-nodes && python3 -m pytest tests/ -q
```

Read order:

1. `SCOPE.md` — vision, audience, success criteria.
2. `SPEC.md` — architecture: compiler pipeline, Python subset, GN
   emission strategy, the two user-facing shapes.
3. `PLAN.md` — milestones and current status.
4. `TESTING.md` — milestone-by-milestone path + the M3 Blender checklist.
5. `docs/grouping.md` — the M2 grouping-pass design.
6. `docs/emission.md` — the M3 backend design.
7. `docs/expression-reference.md` — the supported Python surface.
8. `docs/existing-alternatives.md` — Sverchok / Animation Nodes / OSL
   comparison.
6. `docs/examples/` — two worked examples.

## Relationship to the other projects in this repo

| Project | Role |
|---|---|
| `../annihilation-morph-script/` | Single Blender script — the visual target |
| `../sacred-geometry-engine/` | Procedural engine. Phase 1 MVP shipped. Provides the compiler IR and GN emitter Coding Nodes builds on. |
| `coding-nodes/` (this) | Adds a Python-expression frontend to that compiler, plus the user-facing modifier and node group. |

Coding Nodes is an addon that sits on top of `sacred_geometry`'s
compiler infrastructure. The IR and GN backend live there; the
frontend and UX shells live here.

## Target platform

Blender 4.x and 5.x. Python 3.11+.

## License

Unlicensed. To be decided before public release.
