# 10 — Performance

## Purpose

Lay out the performance model honestly, set user expectations, document
known cliffs, and prescribe practices that keep PyNodes usable on large
data.

## The performance budget

Single-threaded Python with the GIL is a hard ceiling. Numpy releases the
GIL inside its C kernels, which helps inside a single node, but the
evaluator orchestration runs in Python.

Rough numbers on a modern desktop (Python 3.11, numpy 1.26):

| Operation | Cost on N=1M points |
|---|---|
| `foreach_get('co', ...)` | ~10 ms |
| Numpy elementwise `(N,3) + (N,3)` | ~3 ms |
| Numpy `sin`, `cos`, `exp` | ~10 ms |
| Numpy `linalg.norm` along axis | ~5 ms |
| 4D Perlin noise (pure numpy reference) | ~200–500 ms |
| 4D Perlin via numba | ~30 ms |
| Marching cubes on 128³ grid (skimage) | ~200 ms |
| `foreach_set('co', ...)` + `mesh.update()` | ~15 ms |

A graph evaluating in ~50ms feels live. 200ms feels sluggish. 1s feels
broken.

## The golden rules

1. **Vectorize everything.** No `for v in vertices` Python loops.
2. **One copy.** Pass `GeometryHandle` by reference; don't allocate fresh
   arrays per node when in-place works.
3. **Cache.** The evaluator caches per node. Don't fight it by including
   `time.time()` in your code (it busts the cache every frame).
4. **Profile.** Use the addon's per-node timing display. Don't optimize
   blind.
5. **Bail to GN.** If a kernel is hot and pure-math, port it to GN. The
   addon ships a "Suggest GN equivalent" button that prints the GN
   subgraph shape.

## Numba

Numba is an optional dependency. When enabled in addon prefs, users can
decorate their kernels:

```python
from numba import njit

@njit(cache=True)
def curl(P, t, eps):
    ...
```

Numba caches compiled functions on disk by code hash. First call
compiles (~1-3s). Subsequent calls run at near-C speed.

The addon documents numba clearly: it's not bundled (license / install
issues), users opt in by `pip install numba` in their Blender Python.

## Multi-threading

Inside a single numpy op, numpy releases the GIL for many operations
(linalg, FFT, large elementwise). Outside, Python is serial.

Phase 2 may add a worker-thread evaluator: heavy nodes evaluate in a
background thread, posting results back via a modal operator. Numpy
fluffies up, the UI stays responsive.

Phase 3 may add `multiprocessing` workers for truly parallel evaluation,
but the IPC cost (serializing numpy arrays) means it only pays off for
*very* large kernels.

## GPU

Out of scope for PyNodes the addon. If the user needs GPU performance,
the answer is GN (which targets GPU in its long-term roadmap). PyNodes is
the CPU/Python tier.

## Common performance traps

- **Implicit allocation:** `pos = pos + offset` allocates a new array each
  call. `pos += offset` does not. The latter is 2× faster on big arrays.
- **Mixed dtypes:** mixing `float64` and `float32` triggers conversions.
  Pick one and stick to it (`float32` is the Blender convention).
- **Wrong axis:** `np.linalg.norm(P)` on `(N, 3)` returns a scalar; you
  meant `np.linalg.norm(P, axis=-1)`. Easy to miss; expensive when wrong.
- **List comprehensions over numpy:** `[do(v) for v in P]` reverts to
  Python speed. Vectorize.
- **Forgetting `.ravel()` for `foreach_set`:** `foreach_set` expects a 1D
  array; passing `(N, 3)` shapes silently fails or errors weirdly.

## Profiling support

The addon ships a per-node timing badge: hover over a node's header to
see its last evaluation time. Long-running nodes (> 50ms) get an orange
badge; pathological ones (> 500ms) get red.

A "Profile Graph" operator runs the whole graph 10× and reports the top 5
slowest nodes in the print log.

## Performance contract for shipped node library

| Node | Target on N=100k points |
|---|---|
| `MeshIn` / `MeshOut` | < 5 ms |
| `PyExpr` (single line) | < 10 ms |
| `NumpyKernel` (typical 10-line math) | < 20 ms |
| `ReadAttribute` / `WriteAttribute` | < 5 ms |
| `AttributeBridge` | < 10 ms |

User-authored kernels are user-authored; we don't guarantee anything.

## Open questions

- Should the addon ship a noise library written in numba (always opt-in
  via prefs) for users who don't want to install it themselves? **Maybe**
  — license and packaging tax.
- Async/background evaluation: hard problem, real win. Schedule for phase
  2 with explicit research time.

## Related docs

- Python execution: `05-python-execution.md`
- Live update: `07-live-update.md`
- Roadmap: `11-roadmap-risks.md`
