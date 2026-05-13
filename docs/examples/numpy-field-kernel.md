# Example: Numpy Curl-Noise Field Kernel

A more substantial PyNodes example: compute a curl-noise vector field
across all vertices of a mesh in a single vectorized numpy pass, then use
it to advect particles or displace the mesh.

This is pseudocode against the proposed API (`../api/node-reference.md`).

## Goal

Compute, per vertex:

```
curl(P, t) ≈ (∂Nz/∂y - ∂Ny/∂z,
              ∂Nx/∂z - ∂Nz/∂x,
              ∂Ny/∂x - ∂Nx/∂y)
```

where `Nx, Ny, Nz` are three independent noise scalars sampled at the
vertex position with time `t` advancing through their W axis. The result
is a divergence-free vector field — characteristic swirling motion.

## PyNodes graph

```
+--------------+    +--------------+    +-------------------+    +---------------------+
| Mesh In      |    | Positions    |    | NumpyKernel       |    | Attribute Bridge    |
| object=Sphere| -> | (extracts P) | -> | "curl noise"      | -> | name="curl_velocity"|
+--------------+    +--------------+    +-------------------+    | type=FLOAT_VECTOR   |
                                                                 | domain=POINT        |
                                                                 +---------------------+
```

The `NumpyKernel` code:

```python
import numpy as np

# Inputs:
P = inputs['positions']          # (N, 3) float32
scale = params.get('scale', 1.5)
strength = params.get('strength', 0.4)
seed = int(params.get('seed', 0))

eps = 1e-3

# Three independent perlin-like noise scalars at P, parameterized by t (time).
# Replace with your favorite noise; this stub uses a periodic sin product
# that is deterministic and good enough to demonstrate the kernel shape.
def n(p, offset_seed):
    return (
        np.sin(scale * p[..., 0] + t * 0.7 + offset_seed * 13.0) *
        np.cos(scale * p[..., 1] + t * 1.1 + offset_seed * 29.0) *
        np.sin(scale * p[..., 2] + t * 0.9 + offset_seed * 47.0)
    )

# Sample at offsets to approximate partial derivatives via finite differences.
def grad(p, offset_seed):
    dx = (n(p + np.array([eps, 0, 0]), offset_seed)
          - n(p - np.array([eps, 0, 0]), offset_seed)) / (2 * eps)
    dy = (n(p + np.array([0, eps, 0]), offset_seed)
          - n(p - np.array([0, eps, 0]), offset_seed)) / (2 * eps)
    dz = (n(p + np.array([0, 0, eps]), offset_seed)
          - n(p - np.array([0, 0, eps]), offset_seed)) / (2 * eps)
    return dx, dy, dz

# Three independent fields: Nx, Ny, Nz
nx_dy, nx_dy_, nx_dz = grad(P, seed + 1)   # we only need a couple of partials
ny_dx, ny_dy_, ny_dz = grad(P, seed + 2)
nz_dx, nz_dy, nz_dz_ = grad(P, seed + 3)

curl_x = nz_dy - ny_dz
curl_y = nx_dz - nz_dx
curl_z = ny_dx - nx_dy_

velocity = np.stack([curl_x, curl_y, curl_z], axis=-1) * strength

outputs['velocity'] = velocity.astype(np.float32)
```

## What the GN side does

A GN modifier on the same object reads the `curl_velocity` named
attribute and uses it as the Offset for a `Set Position` node:

```
Named Attribute "curl_velocity" → Set Position (Offset)
```

The mesh ripples as if blown by an invisible swirling wind.

## Per-frame cost

On a 10k-vertex sphere:

- `MeshIn` (foreach_get): ~1 ms
- `NumpyKernel` (numpy ops above): ~8-15 ms
- `AttributeBridge` (foreach_set): ~1 ms
- GN evaluation: ~3 ms

Total: ~15-20 ms per frame. Live tweakable.

On a 100k-vertex mesh: ~80-150 ms per frame. Just below comfortable;
worth porting to `numba.njit` (see below).

## With numba

If the user has numba enabled in addon prefs:

```python
from numba import njit

@njit(cache=True)
def curl_kernel(P, t, scale, strength, seed):
    # numba-compatible version — pure numpy, no kwargs in inner calls
    ...
    return velocity

outputs['velocity'] = curl_kernel(P, t, scale, strength, seed)
```

First call compiles (~2s). Subsequent calls: ~3-5× faster than pure
numpy on 100k+ data.

## With the AttributeBridge or directly

Two ways to write the result:

**A. `AttributeBridge` node** — separate write step. The PyNodes graph
remains a pure DAG; the bridge is the only side-effectful node.

**B. The `MeshOutNode`** — combine "compute velocity" with "displace
mesh" in one node by adding `velocity` to positions and writing the
result. Faster for simple cases but more entangled.

Recommended: A for graphs with multiple downstream consumers; B for
single-target displacement.

## Editing iteration

The user can tweak:

- `scale`, `strength`, `seed` parameters via the node UI sliders.
- The kernel code itself — change the noise function, the partial
  derivative formula, the post-processing.

Parameter changes invalidate the cache instantly; viewport updates within
a frame.

Code changes commit on focus loss or explicit `Recompile`. The new code
object is compiled (~50µs) and the cache is busted for that node.

## Promoting to GN (phase 3)

The hybrid compiler could translate this kernel to GN, but only
partially: the finite-difference structure with three offset samples is
expressible (three `Noise Texture` nodes, three Vector Math subtracts).
The compiler would emit roughly:

```
Position ─┬→ Noise(seed1, offset XYZ ±eps) → 3 samples → Vector Math
          ├→ Noise(seed2, offset XYZ ±eps) → 3 samples → Vector Math
          └→ Noise(seed3, offset XYZ ±eps) → 3 samples → Vector Math
       → Combine XYZ → scale by strength → Named Attribute
```

Roughly 20 GN nodes vs 1 Python kernel. The compiler would handle the
expansion automatically.

## What this example shows

- Numpy makes per-vertex math expressive without sacrificing speed.
- Curl-noise is a one-page kernel in PyNodes, vs dozens of nodes in GN.
- Interop via named attribute keeps PyNodes decoupled from how the
  output is used.
- Performance is acceptable for medium-sized meshes; numba and GN
  promotion offer escape hatches at scale.

## Related

- Displace example: `displace-with-python.md`
- Performance: `../architecture/10-performance.md`
- Node reference: `../api/node-reference.md`
