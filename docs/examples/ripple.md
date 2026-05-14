# Example: Ripple Displacement

A hello-world for Coding Nodes. The simplest useful expression: displace
mesh vertices along Z by a time-varying sine wave.

## The expression

```python
def ripple(P, t, freq=6.0, amp=0.3):
    return vec3(0, 0, sin(P.x * freq + t) * amp)
```

What this says:
- For every point `P` in the mesh, compute an offset vector.
- The Z component is `sin(P.x * freq + t) * amp`. X and Y stay 0.
- `freq` and `amp` are parameters with defaults; they'll show up as
  modifier inputs.
- `t` is implicit — the scene time in seconds. The wave drifts as the
  timeline plays.

## Using it via the Expression Modifier

1. Add an `Expression` modifier to a mesh (e.g. a subdivided plane).
2. Set Target = "Position Offset" so the return vector adds to position.
3. Paste the expression into the text field.
4. Click `Recompile` (or wait for auto-recompile).
5. Scrub the timeline. The plane ripples.

The modifier panel now shows `freq` and `amp` as adjustable inputs.

## What the compiler produces

A GN node group named `Expression_ripple`:

```
[ Group Input ]
       |
       |  P  (Position)
       |  t  (Scene Time / Seconds)
       |  freq  (Group Input: 6.0)
       |  amp   (Group Input: 0.3)
       |
       v
+-----------------------+
| ripple                |   <- a group node, contents below
+-----------------------+
       |
       v
[ Set Position (Offset) ]
       |
       v
[ Group Output ]
```

Inside the `ripple` group:

```
[ Input: P, t, freq, amp ]
       |
P.x * freq  ->  + t  ->  sin  ->  * amp  ->  vec3(0, 0, .)
       |
       v
[ Output: vec3 ]
```

One named group node containing the math, not 8 loose math nodes
scattered around the top-level graph.

## Using it via the Expression Node Group

1. Open an existing GN tree.
2. `Shift+A → Group → Expression`.
3. The Expression Node Group lands in the editor with default contents.
4. With the node selected, open the N-panel. Paste the same expression
   into the text field.
5. The node's interior rebuilds. Its outputs match the expression's
   return type (vec3).
6. Wire the output into your existing `Set Position` (or wherever).

Same compiler, different surface.

## Tweaking from here

- Bump `freq` to 12 for tighter waves.
- Swap `sin` for `cos` (or add both) for a phase-shifted version.
- Change `vec3(0, 0, ...)` to `vec3(..., ..., ...)` for 3D motion.
- Use `N` instead of a fixed axis: `return N * sin(P.x * freq + t) * amp`
  to displace along the surface normal.

Each edit recompiles the GN group in place.

## Next

The curl-noise example in `curl-noise.md` is a more substantial kernel
demonstrating function composition and the grouping behavior.
