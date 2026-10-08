# ExpressNode

*Formerly Coding Nodes / Expression Nodes. The name you see changed; the Python package
(`coding_nodes`), the add-on module and the operator ids did not, so existing files keep working.*

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
validated against the oracle. **290 passing headless tests (6
toolchain-skipped), no Blender required.**

**Blender 5.2 (2026-10-07, branch `blender-5.2`):** modifier inputs moved from ID properties to RNA in 5.2;
`backend/modifier.py` reads and writes them either way. On Linux (RTX 5090, Vulkan) the whole runner passes
on 5.0.1, 5.1.2 and 5.2.2: 411 of 411 checks, WGSL included (Chrome in a window; headless Chrome on Linux
only has a software WebGPU adapter).

**Verified in Blender 5.0.1 and 5.1.2 (2026-09-27):** the M3/M4/M5
checklists and the M7/M8/M9 runtime checks are automated in
`tests/blender/` and `tests/gpu/` and all pass (275 checks). Every case
is run for real: the Geometry Nodes modifier evaluated on a point cloud,
OSL rendered in Cycles, GLSL run by Blender's gpu module, WGSL
dispatched by WebGPU, and each result compared with the oracle. The
first run found and fixed a long list of bugs (the Geometry Nodes
executor wired sockets wrongly, most OSL didn't compile, noise didn't
match); see "Blender and GPU checks" in `TESTING.md`. The whole arc is
mapped in [`../ROADMAP.md`](../ROADMAP.md).

One expression now targets **geometry (GN), correctness (numpy oracle),
Cycles shading (OSL), real-time shading (GLSL), and GPU compute
(WGSL)** — all from one IR.

```bash
python3 -m pytest tests/ -q                             # 290 tests
python3 tools/package_addon.py dist                     # build the zip
python3 tests/blender/run_all.py --blender <blender.exe> [--blender ...] \
    [--puppeteer <dir with node_modules/puppeteer-core>]  # Blender + GPU
```

## Install (Blender)

1. `python3 tools/package_addon.py dist` → `dist/coding_nodes_addon.zip`
   (bundles the package; no manual `sys.path` setup needed). It's a
   legacy add-on zip (bl_info), which Blender 5 still installs; tested
   on 5.0.1 and 5.1.2.
2. Blender › Preferences › Add-ons › **Install from Disk** → pick the
   zip → enable **"ExpressNode"**.
3. **Shape A (modifier):** select a mesh → Properties › Modifiers ›
   *ExpressNode* panel → paste an expression → *Recompile*.
4. **Shape B (node group):** open a Geometry Nodes editor → N-panel ›
   *ExpressNode* tab → *Add Expression Node Group*. To change a
   dropped group later, select it, edit the text and click *Update
   Selected Group*; every node using that group updates.

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

## Where the compiler came from

The intermediate representation (EvalGraph IR) started life in an
earlier procedural-geometry engine and is now vendored in
`coding_nodes/_ir`, so ExpressNode is self-contained: nothing else
needs to be installed. ExpressNode adds the Python-expression frontend,
the group-wrapping pass and the user-facing modifier and node group.

## Target platform

Blender 5.0 or newer (tested on 5.0.1, 5.1.2 and 5.2.2). Python 3.11+.

## Licence

GPL-3.0-or-later, like Blender itself: see [LICENSE](LICENSE).
