# ExpressNode — Executive Specification

**Version:** 0.2 (focused)
**Status:** Specification. Build queued.
**Target:** Blender 5.0+ (tested on 5.0.1 and 5.1.2; 4.x is not tested or declared).

> See also `SCOPE.md` (vision and audience) and `PLAN.md` (concrete
> build steps).

## What it is

A Blender addon that compiles a **Python expression** into a clean,
group-wrapped **Geometry Nodes subtree** and exposes it through:

- **Shape A — Expression Modifier.** A modifier with a text field. Type
  `sin(P.x * 6 + t) * 0.3`. The mesh responds.
- **Shape B — Expression Node Group.** A node group the user drops into
  any GN tree. Same text field, same compiler, embeddable in larger graphs.

Both shapes share one compiler. The user writes the expression; the addon
produces a readable algorithmic node tree — not a flat sea of math nodes.

## Architecture at a glance

```
+---------------------------+
| User-written expression   |   "sin(P.x * 6 + t) * 0.3"
+---------------------------+
              |
              v
+---------------------------+
|  Python AST parser        |   ast.parse(source)
+---------------------------+
              |
              v
+---------------------------+
|  AST -> EvalGraph         |   typed IR, shared with sacred_geometry
+---------------------------+
              |
              v
+---------------------------+
|  Group-wrapping pass      |   wraps functions as named GN sub-groups
+---------------------------+
              |
              v
+---------------------------+
|  GN tree emitter          |   sacred_geometry.compiler.gn_backend
+---------------------------+
              |
              v
+---------------------------+
|  Blender GN node group    |   attached as a modifier (Shape A)
|                           |   or dropped into a tree (Shape B)
+---------------------------+
```

## Reuse of existing infrastructure

The compiler reuses the IR and GN backend already built in
`sacred-geometry-engine/sacred_geometry/`:

- `sacred_geometry.ir.eval_graph.EvalGraph` — the typed IR.
- `sacred_geometry.compiler.gn_backend` — the EvalGraph → GN emitter
  (extended in this project with a group-wrapping pass).
- `sacred_geometry.compiler.optimize` — CSE + DCE passes.

The new code in this project:

- **Python AST → EvalGraph frontend.** A new module that parses a
  Python expression and emits the same EvalGraph the SacredEntity DSL
  emits.
- **Group-wrapping emitter pass.** An upgrade to the GN backend so it
  produces `Function → sub-group` mappings instead of flat math nodes.
- **Modifier UI / node-group wrapper.** The Blender-side surfaces.

## The Python subset

The compiler accepts a statically-shaped, statically-typed,
pure-expression subset of Python. The rule of thumb:

> If the function reads like math to someone who's never run Python, it
> probably compiles.

**Supported:**
- Numeric types: `float`, `int`, `bool`.
- Fixed vectors: `vec2`, `vec3`, `vec4`.
- Arithmetic, comparisons, boolean operators.
- Control flow: `if/else` expressions, function definitions, function
  calls.
- Built-in functions: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`,
  `atan2`, `sqrt`, `pow`, `exp`, `log`, `abs`, `min`, `max`, `clamp`,
  `mix`, `smoothstep`, `noise`, `voronoi`, `length`, `dot`, `cross`,
  `normalize`, `reflect`, `vec2`, `vec3`, `vec4`.
- Built-in variables: `P` (position), `N` (normal), `i` (index),
  `t` (scene time, seconds), `frame` (current frame).
- Blender access: `attr("name")` reads named attribute, `obj("name",
  "field")` reads another object's data, `set_attr("name", value)`
  writes a named attribute.

**Out of the subset (won't compile, with clear error messages):**
- I/O, network, file operations.
- Dynamic attribute access (`getattr` with runtime strings).
- Classes, metaclasses, decorators (other than the kernel decorator).
- `*args` / `**kwargs`.
- Mutable globals, exceptions as control flow.
- String formatting, regex.
- Variable-shape arrays, dicts, sets.

Full reference: `docs/expression-reference.md`.

## GN emission strategy: avoiding "a million math nodes"

The defining quality bar. A naive compiler dumps every Python operation
into an individual `Math` or `Vector Math` node, producing an
unreadable graph. The compiler this project ships does the opposite:

- **Each user-defined function becomes a GN group node.** A `def
  noise_layer(P, scale)` in Python is one box in the output graph,
  named `noise_layer`, with the math living inside.
- **Trivial one-liners inline.** `x * 2` doesn't get its own group.
- **Nested functions become nested groups.** The structure of the code
  is the structure of the graph.
- **Layout is automatic and readable.** Frame nodes group logically
  related ops. Lines don't cross unnecessarily. Group nodes are wide
  enough to read names.
- **Nodes are labeled** with the source-line snippet they came from.

The user opens the modifier panel, expands the node group, and sees:
`ripple → noise → set_position`. Not a wall of arithmetic.

## Shape A: Expression Modifier

A new modifier type registered by the addon. UI:

```
+-----------------------------------------------------+
| Geometry Nodes Modifier: Expression                 |
+-----------------------------------------------------+
| Target: Position (vec3) | Normal Offset | Custom    |
| Expression:                                         |
|   +-----------------------------------------+       |
|   | def ripple(P, t):                       |       |
|   |     return vec3(0, 0, sin(P.x*6+t)*.3)  |       |
|   +-----------------------------------------+       |
| [Recompile]  [View Graph]  [Errors: 0]              |
+-----------------------------------------------------+
```

- Edit the expression → addon recompiles (debounced) → modifier rebuilds
  its node group → viewport updates.
- "View Graph" opens the generated node group in the GN editor for
  inspection. Useful for learning and debugging.
- "Errors" surfaces compile failures with source-line markers.

## Shape B: Expression Node Group

A `coding_nodes_expression` node group the user drops into any existing
GN tree via `Shift+A → Group → Expression`. Its inputs are auto-derived
from the user's expression signature.

Inside the group: the same compiler output as Shape A. Outside: the
group looks and behaves like any other GN group node, fits inside
larger graphs.

Both shapes share the same compiler and produce the same output. The
choice is a UX preference: A for "I just want it to work," B for "I
want it inside my larger graph."

## Access to Blender features

The compiled group can hook into any GN input the user's expression
references:

| Expression form | What it becomes |
|---|---|
| `P` | `Input → Position` node |
| `N` | `Input → Normal` node |
| `i` | `Input → Index` node |
| `t` | `Input → Scene Time → Seconds` |
| `frame` | `Input → Scene Time → Frame` |
| `attr("disp")` | `Named Attribute("disp")` |
| `set_attr("col", v)` | `Store Named Attribute("col", v)` |
| `obj("Cube", "position")` | `Object Info("Cube") → Position` |

Shaders consume what the compiler writes via the `Attribute` node. The
compiler can't read shader output directly (shaders run after geometry
in Blender's pipeline) but can drive every input a shader needs.

## Live update

On expression edit:

1. The addon debounces (~250 ms) to coalesce keystrokes.
2. Parses the source. On parse error: red marker, no rebuild.
3. Compiles to EvalGraph. On compile error: marker on the offending
   line, no rebuild.
4. Diffs against the previous EvalGraph. If unchanged: no rebuild.
5. Rebuilds the GN group in place. Parameter bindings preserved when
   possible.

## Error reporting

Compile errors carry the AST node's source line and column. The UI
shows them inline:

```
  def ripple(P, t):
      return sin(getattr(math, "sin"))   <-- error here
                  ^
  Compile error: getattr() with a runtime string isn't supported.
                 Use a direct call to sin() instead.
```

Errors do not crash anything. The viewport keeps the last good version
of the node group; the user keeps typing.

## What this project deliberately reuses, builds, and skips

**Reuses (from `sacred-geometry-engine/sacred_geometry/`):**
- The `EvalGraph` IR.
- The optimizer passes (CSE, DCE).
- The GN backend emitter (extended for group wrapping).

**Builds (new in this project):**
- The Python AST → EvalGraph frontend.
- The group-wrapping pass.
- Two user-facing surfaces (Expression Modifier, Expression Node Group).
- Live-update plumbing.
- An expression reference doc and two worked examples.

**Open for later:**
- OSL backend (compile the same expression to a Cycles shader).
- GLSL backend (compile to Eevee shading).
- GPU compute backend (for very large point counts).
- Additional frontends (Halide-style array DSL, visual node authoring).

## Related docs

- `SCOPE.md` — vision, audience, success criteria.
- `PLAN.md` — concrete build steps and milestones.
- `docs/expression-reference.md` — full supported Python surface.
- `docs/existing-alternatives.md` — Sverchok / Animation Nodes / OSL comparison.
- `docs/examples/ripple.md` — hello-world walkthrough.
- `docs/examples/curl-noise.md` — multi-step example.
