# Coding Nodes — Scope & Vision

This doc defines what Coding Nodes is *trying to be*, who it's for, what
evidence we'd need before scaling up. It complements `SPEC.md` (which
describes architecture). Read this first when deciding what to build
and when to ship.

## Vision

> Python-in-Blender that **compiles to real Geometry Nodes graphs**,
> opening up vectorized math, recursive algorithms, and external data
> ingestion without leaving the node-based authoring paradigm.
> Open source. Built for technical artists, generative designers,
> computational tinkerers. A Grasshopper-shaped tool for Blender.

We are filling the gap between "vanilla Geometry Nodes is too
limited" and "I need a separate DCC for this."

## Audience

The bullseye: people who already use Blender and have hit GN's ceiling.
Concretely:

- **Technical artists** building procedural rigs, motion graphics, or
  generative systems that outgrow GN's primitive math nodes.
- **Generative / computational artists** doing L-systems, IFS fractals,
  phyllotaxis, reaction-diffusion — algorithms that are unnatural in GN.
- **Computational designers** (architecture, product, parametric design)
  looking for an open-source Grasshopper alternative.
- **Researchers** using Blender for scientific visualization who need to
  read external data into geometry.
- **Students** learning procedural / algorithmic design.

## Why this needs to exist

What exists today and what's missing:

| Tool | What it does | Why it doesn't close the gap |
|---|---|---|
| **Sverchok** | Parametric node-based system with Python script nodes | Its own parallel node universe; doesn't interop with native GN |
| **Animation Nodes** | Motion-graphics scripting in nodes | Aging, mostly superseded; separate evaluation system |
| **OSL** | Programmable Cycles shaders | Shading only, no geometry effect; CPU only |
| **`bpy` scripting** | Generate GN trees programmatically from Python | Tedious — you author each node by hand; worse than the GUI for most cases |
| **Houdini** | The mature reference for code-in-graph (VEX) | Not open source; not Blender |

Coding Nodes' specific addition: **a compiler that takes Python
expressions and emits actual Blender Geometry Nodes trees.** The user
writes code; Blender runs node graphs. The user gets expressiveness;
Blender keeps its evaluation model. Everyone wins on the cases that map
cleanly.

For cases that don't map (loops, recursion, external IO, scipy), we have
Level 1: Python runs adjacent to GN as an addon, communicating through
shared named attributes.

## Why Blender core hasn't done this themselves

Stated reasons from public devtalk threads and Blender Conference talks
(primarily from Jacques Lucke, who leads Geometry Nodes):

1. **GIL.** Python is single-threaded. GN evaluates in parallel across
   points on many cores. Python in the evaluator = serialization.
2. **GPU.** Long-term GN moves to GPU compute. Python doesn't run on
   GPUs; any node containing Python would force CPU fallback.
3. **Determinism.** GN nodes are pure functions. Python has side effects
   (IO, time, random state, mutable globals).
4. **Caching.** Caching opaque Python (with its closures and imported
   modules) is much harder than caching pure primitive ops.
5. **Stability / sandboxing.** Arbitrary code in the hot evaluation path
   is a crash and security risk.
6. **Maintenance philosophy.** Small set of well-typed primitives +
   composition > escape hatch committing them to support arbitrary
   code forever.

These reasons are **correct for Blender's GN architecture**. They are
not blockers for us, because:

- **Level 1 (addon)** doesn't run Python *inside* GN evaluation. Python
  runs *adjacent* to GN, writes named attributes, and GN reads them.
  The GIL is the addon's problem, not Blender's. Determinism is on the
  user — if they write side-effectful code, that's their choice.
- **Level 2 (hybrid compiler)** doesn't run Python at evaluation time
  at all. Python is parsed at *edit time* and compiled to a GN graph.
  At runtime, only GN executes. The GIL never sees the inside of an
  evaluation. GPU compatibility is preserved for the compiled subset.

We don't fight the core team's reasoning. We route around it.

## Use cases (brainstorm)

The point of this section: when we make scope decisions, we ask "does
this feature serve any use case below?" If no, defer. If yes, prioritize
by how many cases it serves and how loud those users would be.

### Math & motion graphics
- Custom math expressions as single nodes (sin, atan2, complex curves)
- Animated parameter curves driven by stateful evaluation
- Sound-reactive geometry (read FFT from a file, animate vertices)
- Beat-locked or music-locked animation
- Easing libraries, custom interpolators

### Generative / algorithmic art
- L-systems and turtle-graphics
- Iterated Function Systems (Mandelbrot, Mandelbulb, Menger sponge)
- Phyllotaxis / golden-angle distributions
- Reaction-diffusion patterns (Turing, Gray-Scott)
- Cellular automata on mesh attributes (Game of Life on a sphere)
- Procedural plants beyond what Sapling does
- Recursive grammar-based architecture (rule-based facade generation)

### Computational design / architecture
- Form-finding (catenary networks, tension structures, minimal surfaces)
- Stress-driven topology optimization (read FEA result, color/displace)
- Parametric building generation from CSV (lot dimensions → massing)
- Sun-path analysis driving louver geometry
- Daylighting metric visualization
- Acoustic ray-tracing visualization
- Truss/lattice optimization

### Data viz / scientific
- CSV → bar chart geometry (with bonus: customizable, procedural)
- GeoJSON → terrain mesh
- Time-series geometry animations (climate data, stock data)
- Molecular structure visualization (PDB files → meshes)
- Network graphs (Force-directed layouts as geometry)
- Statistical distribution previews (histogram volumes, etc.)

### ML / AI integration
- Pose-estimation output → rig animation
- Text-to-3D model output → mesh import + post-processing
- Stable Diffusion / depth map → relief geometry
- Vertex-attribute classification (run a small numpy classifier inline)

### Pipeline / tooling
- Read JSON config from upstream tools
- Export procedural variants for game asset pipelines
- Drive Blender from external simulation tools without leaving the node graph
- Live-link from custom DCC tools via attribute round-trips

### Education
- Teach algorithms (recursion, fractals, optimization) with immediate
  visual output
- "View Generated GN Tree" — debugging compiled output is a teachable
  artifact
- Step-through debugging of generated graphs
- Side-by-side: native GN node-soup vs. compiled-from-Python version

## Phased execution

Each phase has a stated **Goal**, **Deliverable**, **Done = ** criterion,
and **Evidence we'd need before moving to the next phase.** If the
evidence isn't there, we stay where we are. Staying is a valid outcome.

### Phase 1 — Python adjacent to GN (Level 1 addon)

**Goal:** Ship a usable Blender addon. Custom node tree, Python-executing
nodes, named-attribute interop with GN.

**Deliverable:**
- Installable `.zip` addon for Blender 4.x / 5.x.
- Custom `PyNodeTree` with its own editor space.
- Core nodes: `PyExpr`, `NumpyKernel`, `MeshIn`, `MeshOut`,
  `ReadAttribute`, `WriteAttribute`, `AttributeBridge`, `Time`,
  `Constant`.
- Pull-based evaluator with `(node_id, input_hash)` caching.
- Depsgraph + frame-change handlers.
- Restricted execution by default; opt-in unrestricted mode.
- Two shipped examples: PyExpr displace, NumpyKernel curl-noise.

**Done =** A user installs the addon, opens the example file, scrubs
the timeline, sees the mesh animate. Edits the kernel code, sees the
viewport update.

**Time estimate:** 3–4 months, 1–2 developers.

**Evidence we'd need before Phase 2:**
- ≥ 50 users actively using the addon (not just installs).
- Specific performance complaints attributable to Phase 1 limits
  (GIL ceiling on > 100k-point graphs, attribute round-trip cost).
- Concrete feature requests that ONLY Phase 2 can serve (i.e. requests
  for parallel/GPU-speed execution of code the user wrote).

### Phase 2 — Python compiled to GN (Level 2 hybrid compiler)

**Goal:** Parse a subset of Python and emit equivalent Geometry Nodes
graphs. The user *writes* Python; at runtime, Blender *runs* native GN.
Parallel-friendly, GPU-ready.

**Deliverable:**
- Python AST parser restricted to expressions + assignments + `return`.
- AST → GN-tree compiler covering arithmetic, vector math, sin/cos/atan2,
  conditional via `where()`, named-attribute reads/writes, basic
  numpy-like ops on per-point arrays.
- Per-node toggle: "Run as Python" vs. "Compile to GN".
- Clear error messages when an expression isn't compilable, with the
  reason (e.g. "scipy.fft is not available in compiled mode").
- A "View Generated GN Tree" preview for the compiled subgraph.

**Done =** The two Phase 1 examples can be toggled to GN mode. Output
is visually identical. Performance is at least 10× faster on N=1M points.

**Time estimate:** 6–9 months on top of Phase 1.

**Evidence we'd need before Phase 3:**
- Real users running 1M+ point graphs.
- Specific capabilities they need that *neither* Phase 1's adjacency
  nor Phase 2's compiler can deliver. Examples might include:
  - True single-tree coexistence of Python and GN nodes (without
    attribute round-trips between two stacks).
  - GPU execution of user-written code (not just compiled-to-GN code).
  - Native install with no `pip install numpy` step.

### Phase 3 — Open

Held open. Possible directions, to be evaluated when we get there:

1. **Polish.** Documentation, cookbook, example library (50+ kernels),
   integration tutorials. The most likely default.
2. **Upstream contribution.** Push features into mainline Blender via
   the contributor pipeline. Demonstrates the architectural objections
   don't apply to our approach. Free distribution if it lands.
3. **Standalone compute engine.** Build a separate process that runs
   compute, exports geometry to Blender via a thin bridge (Houdini
   Engine-style). Trade: adds maintenance load; gains independence
   from Blender's evaluation model.
4. **Blender fork.** A downstream Blender with native Python-in-GN
   integration. Trade: full control; ongoing rebase work and a parallel
   community to maintain.

The Phase 3 choice will be evidence-driven and made at the time, not
pre-committed.

## Decision triggers

Before escalating between phases, we want to see:

1. **Real user base.** Not installs, not stars, but people who have
   actually built something with the current phase's deliverable. If
   the count is in single digits after 6 months of public availability,
   the gap we think we're closing may not actually motivate enough
   people.

2. **Specific feature requests.** "It's slow" is not enough. "It's slow
   when I do X" is. The specific X must map to a capability the next
   phase delivers.

3. **Maintainer capacity.** Each phase ratchets up maintenance load.
   We need confidence we can keep the current phase shipping (bug
   fixes, Blender-version updates, addon-API churn) while we build
   the next.

4. **Community contributions.** Are people sending PRs? Have outside
   maintainers shown up? Open-source projects that never attract
   contributors are vulnerable to bus factor 1; that's a real
   constraint on what scope is sustainable.

Phase 1 and Phase 2 are each complete products on their own.
HardOps, MachinTools, NodeWrangler, and BoxCutter show what a
focused Blender addon can be without ever growing beyond its niche.

## What success looks like

A two-year horizon:

- Coding Nodes is an installable Blender addon used by generative
  artists, technical artists, researchers, and computational designers.
- It's the canonical answer when someone asks "how do I do FFT in
  Geometry Nodes?" or "how do I read CSV into a mesh?"
- It coexists with vanilla GN as a complement.
- Phase 2 (hybrid compiler) has shipped and proven useful for
  performance-sensitive cases.
- A community of contributors maintains it.
- Educational programs in computational design and generative art use
  it. Studios use it in pipelines.
- It is the de facto open-source Grasshopper-shaped
  procedural-with-code system for Blender.

## How to use this doc

When proposing a feature, ask:

1. Does it serve a use case in the brainstorm above? Which one(s)?
2. Does it belong in the current phase, or is it a Phase 2 (or later)
   feature in disguise?
3. Does it advance us toward "modest success"? Does it bring us closer
   to any of the decision-trigger conditions for the next phase?
4. Is there a smaller version of it that ships sooner?

When something fails the use-case test, write it down as a deferred
idea and move on. Don't expand the spec to accommodate every "would be
nice" — that's how scope dies.

## Related docs

- `SPEC.md` — what we're building (architecture)
- `docs/architecture/01-overview.md` — system design
- `docs/architecture/03-three-levels.md` — implementation-level analysis
- `docs/architecture/11-roadmap-risks.md` — phase risks
