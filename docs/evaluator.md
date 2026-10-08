# The Reference Evaluator (M6)

The numpy evaluator runs a compiled expression's `EvalGraph` directly,
with no Blender. It is the project's **correctness oracle**.

## Why it exists

The M1–M5 headless tests prove the pipeline is *shaped* right (the plan
has the right groups, nodes, links, interfaces). They do not prove the
expression *computes the right numbers*. The evaluator closes that gap:

```python
from expressnode import compile, evaluate
import numpy as np

c = compile(open("examples/ripple.py").read())
P = np.random.uniform(-2, 2, (100, 3))
r = evaluate(c, P=P, t=0.37).values        # (100, 3)
# proven equal to sin(P.x*6+0.37)*0.3 on Z, exactly (0.0 error)
```

It is also the oracle every other backend is validated against: emit
OSL / GLSL / GPU → run it → compare to `evaluate(...)` within epsilon.

## API

```python
evaluate(compiled,
         P=None,            # (N,3) positions; default one point at origin
         t=0.0, frame=1.0, dt=1/24,
         normals=None,      # default: normalized P (origin -> +Z)
         params=None,       # override exposed parameters; else defaults
         attributes=None,   # {name: array} for attr()
         objects=None,      # {name: {field: vec}} for obj()
         seed=0) -> EvalResult
```

`EvalResult.values` is `(N,3)` for a vec result, `(N,)` for a scalar;
`EvalResult.written_attributes` holds anything `set_attr()` produced.
`EvalResult` is array-like (`np.asarray(result)` works).

numpy is the evaluator's only dependency — and the only part of the
package that needs it. The core (frontend, grouping, backend plan)
imports without numpy; `expressnode.evaluate` is exposed when numpy is
present and skipped otherwise.

## What it proves (headless, no Blender)

| Property | Where |
|---|---|
| Arithmetic / vectors / built-ins compute exactly | `tests/m6_evaluator/test_correctness.py` |
| Ripple == hand-written numpy reference (0.0 error) | same |
| User-function inlining is numerically correct | same |
| `set_attr` records the right values | same |
| curl-noise: finite, deterministic, time/seed/strength sensitive | `test_curl_noise_eval.py` |
| Reference noise/voronoi properties pinned | `test_noise_spec.py` |
| API defaults, shapes, attribute/object injection | `test_oracle_api.py` |

## Reference noise/voronoi — this is a spec, not an approximation

The evaluator is the oracle, so its procedural functions are the
**canonical definition** that OSL/GLSL/GPU backends must reproduce
exactly:

- **value noise** — integer-lattice value noise, quintic fade
  `6t⁵−15t⁴+10t³`, trilinear interpolation. 4D = two independent 3D
  lattice slices at `floor(w)` and `floor(w)+1`, blended by the faded
  `frac(w)`. Range `[0, 1]`. Deterministic uint32 hash of lattice
  coords + seed.
- **voronoi F1** — one feature point per integer cell at
  `cell + hash3(cell)`; returns the Euclidean distance to the nearest
  feature point over the 3×3×3 neighbourhood.

### Important caveat

Blender's own *Noise Texture* / *Voronoi Texture* nodes use different
algorithms. Therefore:

- Expressions **without** `noise()`/`voronoi()` match every backend
  exactly, including the **GN backend** (Blender math nodes are exact).
- Expressions **with** `noise()`/`voronoi()` match the **OSL/GLSL/GPU**
  backends (we implement the reference function there) but **not** the
  GN backend, which delegates to Blender's built-in noise nodes.

This is a deliberate, documented boundary: the oracle defines *our*
semantics; the GN backend trades exactness for using Blender's native,
GPU-accelerated noise. When numeric parity with GN matters, avoid
`noise()`/`voronoi()` or bake against the oracle.

## How backends will be validated against it

The pattern for OSL/GLSL/GPU (the next backends, see `../../ROADMAP.md`
§4b):

1. Compile an expression once.
2. `ref = evaluate(compiled, P=grid, t=...)`.
3. Emit the target source; run it (oslc / glslangValidator+runner /
   wgpu) over the same `grid`.
4. Assert `max|target − ref| < epsilon`.

That makes new backends headlessly verifiable for *correctness* — only
the in-Blender *visual/UX* check needs Blender.

## Related

- `../PLAN.md` — milestones (M6)
- `../TESTING.md` — the M6 test map
- `../../ROADMAP.md` — where the oracle sits in the trajectory
- `emission.md` — the GN backend it complements
