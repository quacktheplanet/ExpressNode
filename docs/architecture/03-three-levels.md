# 03 — Three Implementation Levels

There are three ways to implement "Python in Blender nodes." They are not
mutually exclusive — Level 2 sits on top of Level 1; Level 3 is a long-term
core change. The recommendation is to start at Level 1, build to Level 2,
and treat Level 3 as a research direction.

## Level 1 — Addon (the recommended start)

Build a Blender addon that registers a custom `NodeTree` subclass and a
library of nodes that execute Python.

**Mechanism.** When the user changes an input, an evaluator walks the
node graph in topological order, calls `node.evaluate()` for each node,
and Python runs.

**Pros:**
- Achievable in 2–6 months with a small team (1 Python dev + 1 technical
  artist). Faster with AI-assisted coding.
- 100% Python — no C++ build chain, no Blender source patches.
- Familiar to Blender users (custom node trees are an established API).
- Can ship as a standard `.zip` addon.

**Cons:**
- Not parallel. Python's GIL means per-node evaluation is single-threaded.
  Numpy releases the GIL internally for some ops, which helps, but the
  evaluator orchestration is Python.
- No GPU. Heavy work must vectorize through numpy/numba/scipy.
- Latency: every parameter change re-runs Python; caching is critical.

**Scope.** This is what `04` through `11` specify.

## Level 2 — Hybrid Compiler (the medium-term enhancement)

Add a compiler that parses simple Python expressions and emits equivalent
Geometry Nodes graphs.

**Mechanism.** The user writes:

```python
offset = sin(P.x * freq + t) * amp
```

The compiler turns that AST into:

```
Separate XYZ -> Math MULTIPLY (freq) -> Math ADD (t) ->
  Math SINE -> Math MULTIPLY (amp) -> output
```

When parameters change, only the GN tree's input sockets are bumped; no
Python re-runs.

**Pros:**
- GN performance: parallel, eventually GPU.
- Stays inside Blender's depsgraph.
- The user *writes* Python but *runs* GN — best of both worlds for the
  subset of expressions that map cleanly.

**Cons:**
- Only a subset of Python is expressible in GN. Loops, conditionals
  beyond `where`, recursion, and most stdlib are out.
- AST → GN translation is non-trivial. Edge cases multiply.
- The user can write expressions the compiler rejects, with confusing
  error messages.

**When to add this.** After Level 1 is solid and the addon has shipping
users. Level 2 is an optimization, not a replacement.

## Level 3 — Native Integration (the speculative long-term)

Modify Blender itself to allow Python execution inside native Geometry
Nodes, with proper sandboxing, threading boundaries, and depsgraph
support.

**Mechanism.** Add a `Geometry Node Python` node type whose evaluation
calls into a sandboxed interpreter, with the dependency graph aware of
the inputs and outputs of the script.

**Pros:**
- Lives inside GN. No separate editor space.
- Could be made to play nicely with future GPU evaluation (e.g. Python
  defines an algorithm; the engine offloads compatible subsets to GPU).
- "First-class" feel.

**Cons:**
- Multi-year engineering effort with Blender core developers.
- The architectural objections (GIL, parallelism, determinism, security)
  must each be solved.
- Upstream acceptance is uncertain.

## Decision

Start at **Level 1**. Ship a usable addon. Take on Level 2 once
Level 1 has real users with real performance complaints that Level 2
would solve. Contribute lessons learned to upstream discussions
if and when the Blender core team explores Python-in-GN.

## What "starting at Level 1" means in practice

- Custom `PyNodeTree` registered.
- Custom editor space.
- Core nodes: `PyExpr`, `NumpyKernel`, `ReadAttribute`, `WriteAttribute`,
  `MeshIn`, `MeshOut`.
- Pull-based evaluator with `(node_id, input_hash)` caching.
- Depsgraph handlers for live update.
- Shared-attribute interop with GN modifiers.
- Documentation + 2 worked examples.

That ships. Then we iterate.

## Related docs

- Node tree design: `04-node-tree-design.md`
- Python execution: `05-python-execution.md`
- Roadmap: `11-roadmap-risks.md`
