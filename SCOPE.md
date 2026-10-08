# ExpressNode — Scope & Vision

## Vision

> **Type an equation, get a clean Geometry Nodes subtree.**
> One Blender addon that compiles a Python expression into a readable,
> group-wrapped GN node group — usable either as a modifier or as a node
> group dropped into an existing tree.

We are filling the space between "vanilla Geometry Nodes is hard to
express algorithms in" and "I have to write a Python script that
builds a node tree by hand."

## Audience

The bullseye: Blender users who already use Geometry Nodes and want a
faster way to express mathematical ideas.

- **Technical artists** who currently build math-heavy GN setups out of
  dozens of `Math` and `Vector Math` nodes.
- **Generative / computational artists** who think in equations and
  want their thinking to land directly in the graph.
- **Educators** who want to teach procedural ideas with code that
  produces visible, navigable node graphs.
- **People who've tried existing Python-to-GN scripts** and found them
  awkward (you had to specify each node by hand) — this is the polished
  version of that idea.

## Success criteria

A user installs the addon, adds a modifier, types:

```python
def ripple(P, t):
    return vec3(0, 0, sin(P.x * 6 + t) * 0.3)
```

…and sees the mesh ripple. Then they open the generated node group and
see a readable subtree — one `ripple` group node containing the math,
not a wall of arithmetic.

If that works, we've shipped what matters.

## The two shapes

One compiler, two user-facing surfaces:

- **Expression Modifier (Shape A).** A modifier with a text field. The
  user never needs to open the GN editor unless they want to.
- **Expression Node Group (Shape B).** A node group the user drops into
  an existing GN tree. Same compiler. Embeddable in larger graphs.

The compiler is shared. The user picks whichever shape fits their
workflow.

## Where this came from

ExpressNode grew out of an earlier procedural-geometry engine whose
compiler (DSL → SymbolGraph → EvalGraph → GN tree) it builds on. That
IR is now vendored in `expressnode/_ir`; ExpressNode adds one more
frontend (the Python AST parser) and one polish pass (group-wrapping)
on top, and needs nothing else installed.

## What "done" looks like (first ship)

- The addon installs cleanly in Blender 5.0+ (tested on 5.0.1 and 5.1.2).
- The Expression Modifier works: edit, compile, see the result.
- The Expression Node Group works: drop it in, edit, see the result.
- Output node groups are readable: functions become groups, layout is
  clean.
- Live edit feels responsive (sub-second on small kernels).
- Error messages point at the right source line and say something
  useful.
- Two examples ship: ripple displacement, curl-noise field.

## Roadmap beyond first ship

In order of likely demand, each optional:

1. **More built-ins.** Voronoi, fractal noise variants, easing functions,
   common shading primitives.
2. **OSL backend.** Same expression, compile to a Cycles shader rather
   than a GN tree. Unlocks shading kernels.
3. **GLSL / Eevee backend.** Real-time shading.
4. **GPU compute backend.** For very large point counts where GN
   evaluation can't keep up.
5. **Visual / graphical frontend.** A custom node editor whose
   nodes emit the same EvalGraph — useful for non-coders.

All of these are speculative. The compiler IR is designed so any one of
them can be added later without rewriting the core.

## Related docs

- `SPEC.md` — architecture.
- `PLAN.md` — concrete build steps.
- `docs/expression-reference.md` — Python surface.
- `docs/existing-alternatives.md` — comparison with related tools.
