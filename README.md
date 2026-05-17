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

The full **M1–M7 headless build is complete** — frontend, grouping,
backend (op emitters + emission plan + executor), both user-facing
shapes (modifier + node group), apply modes, parameter reconciliation,
error triage, doc guard, addon packaging, the **numpy reference
evaluator (M6)** that *proves the math is correct* (ripple matches
hand-written numpy to 0.0 error) and is the oracle, and the **OSL
backend (M7)**, the **GLSL/Eevee backend (M8)**, and the **WGSL GPU
compute backend (M9)** — the same expression compiled to a Cycles
shader, a real-time GLSL shader, and a parallel GPU kernel, all
validated structurally against the oracle (GLSL/WGSL `uint` noise is
bit-exact with it). **275 passing tests (6 toolchain-skipped), no
Blender required.** The M3/M4/M5 Blender verification and the
M7/M8/M9 runtime parity checks are planned, checklisted steps (see
`TESTING.md`); M6 has no runtime step. The whole arc is mapped in
[`../ROADMAP.md`](../ROADMAP.md).

One expression now targets **geometry (GN), correctness (numpy oracle),
Cycles shading (OSL), real-time shading (GLSL), and GPU compute
(WGSL)** — all from one IR.

```bash
cd coding-nodes && python3 -m pytest tests/ -q          # 275 tests
python3 tools/package_addon.py dist                     # build the zip
```

## Install (Blender)

1. `python3 tools/package_addon.py dist` → `dist/coding_nodes_addon.zip`
   (bundles both packages; no manual `sys.path` setup needed).
2. Blender › Preferences › Add-ons › **Install from Disk** → pick the
   zip → enable **"Coding Nodes — Expression"**.
3. **Shape A (modifier):** select a mesh → Properties › Modifiers ›
   *Coding Nodes Expression* panel → paste an expression → *Recompile*.
4. **Shape B (node group):** open a Geometry Nodes editor → N-panel ›
   *Coding Nodes* tab → *Add Expression Node Group*.

First expression to try (`examples/ripple.py`):

```python
def ripple(P, t, freq=6.0, amp=0.3):
    return vec3(0.0, 0.0, sin(P.x * freq + t) * amp)
```

Add it as a modifier on a subdivided plane, scrub the timeline — the
plane ripples. Full verification steps: `TESTING.md`.

Read order:

1. `SCOPE.md` — vision, audience, success criteria.
2. `SPEC.md` — architecture: compiler pipeline, Python subset, GN
   emission strategy, the two user-facing shapes.
3. `PLAN.md` — milestones and current status.
4. `TESTING.md` — milestone-by-milestone path + the M3 Blender checklist.
5. `docs/grouping.md` — the M2 grouping-pass design.
6. `docs/emission.md` — the M3 backend design.
7. `docs/evaluator.md` — the M6 numpy oracle + reference noise spec.
8. `docs/osl.md` — the M7 OSL backend.
9. `docs/glsl.md` — the M8 GLSL/Eevee backend.
10. `docs/gpu.md` — the M9 WGSL GPU compute backend.
11. `docs/expression-reference.md` — the supported Python surface.
12. `docs/existing-alternatives.md` — Sverchok / Animation Nodes / OSL
    comparison.
13. `docs/examples/` — two worked examples.

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
