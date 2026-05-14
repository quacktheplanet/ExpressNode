# Example: Curl-Noise Displacement

A divergence-free vector field that produces organic swirling motion.
Demonstrates the compiler's function-grouping behavior: a helper
function in Python becomes a named group node in the output graph.

## The expression

```python
def n(P, seed):
    # one scalar noise sample at P with a seed-based offset
    return noise(P + vec3(seed * 13.7, seed * 29.1, seed * 47.3))

def curl(P, t, scale=2.0, strength=0.4):
    eps = 1e-3
    # finite-difference partials of three independent noise channels
    nx_dy = n(P + vec3(0, eps, 0), 1) - n(P + vec3(0, -eps, 0), 1)
    nx_dz = n(P + vec3(0, 0, eps), 1) - n(P + vec3(0, 0, -eps), 1)
    ny_dx = n(P + vec3(eps, 0, 0), 2) - n(P + vec3(-eps, 0, 0), 2)
    ny_dz = n(P + vec3(0, 0, eps), 2) - n(P + vec3(0, 0, -eps), 2)
    nz_dx = n(P + vec3(eps, 0, 0), 3) - n(P + vec3(-eps, 0, 0), 3)
    nz_dy = n(P + vec3(0, eps, 0), 3) - n(P + vec3(0, -eps, 0), 3)
    return vec3(nz_dy - ny_dz, nx_dz - nz_dx, ny_dx - nx_dy) * strength
```

What it does:
- Helper function `n(P, seed)` samples a single scalar noise field with
  a seed-based offset (cheap way to get "independent" channels).
- `curl(P, t)` builds three independent noise scalars `nx, ny, nz` and
  approximates the curl via finite differences:
  `curl = (∂nz/∂y - ∂ny/∂z, ∂nx/∂z - ∂nz/∂x, ∂ny/∂x - ∂nx/∂y)`.
- The result is a divergence-free vector field — characteristic
  swirling motion when used as a displacement.

## What the compiler produces

A GN node group with **two named sub-groups**: `n` and `curl`. Each
captures one Python function. The top-level graph looks like:

```
[ Group Input: P, t, scale, strength ]
       |
       v
+-----------+
|  curl     |   <- one named group, contents wrap the curl computation
+-----------+
       |
       v
[ Set Position (Offset) ]
       |
       v
[ Group Output ]
```

Open the `curl` group and you find — among the math — references to a
sub-sub-group `n`. The graph mirrors the code's call structure.

Without the grouping pass: ~40 individual math nodes scattered across
the editor. With it: 2 named groups, readable at a glance, expandable
when you want to inspect.

## Using it

1. Add Expression Modifier to a subdivided sphere (icosphere subdivisions
   3 or 4 works well).
2. Paste the expression. Set Target = "Position Offset".
3. Scrub timeline. The sphere swirls.
4. Adjust `scale` for noise frequency, `strength` for displacement
   amplitude. Both appear as modifier inputs.

## Why the grouping matters

The same kernel, compiled without function-grouping, produces ~40 loose
math nodes. The user opens the modifier's node group and sees an
impenetrable mess. With grouping, the user sees the same structure
they wrote in Python — two named functions composing — and can dive in
where they want to.

This is the whole point of the project: code → readable algorithmic
node graph, not code → flat node soup.

## Variations to try

- Drop the `scale` parameter into individual `n` calls to get different
  noise frequencies per channel.
- Multiply by `t` to make `curl` time-varying explicitly (in addition
  to the implicit `t` inside `noise`).
- Add an output `set_attr("morph_mask", length(curl_output))` so a
  shader can read where displacement is intense.
