# Example: Displace with Python

A simple end-to-end PyNodes example: write a Python expression that
computes a per-point displacement, plug it into a sibling Geometry Nodes
modifier on the same object.

This is pseudocode against the proposed API (`../api/node-reference.md`).
PyNodes does not yet exist; this is the visual target the implementation
must reproduce.

## Goal

A subdivided plane that ripples like:

```
z = sin(freq * x + t) * amp
```

We'll author this in PyNodes (one `PyExpr` node + an `AttributeBridge`),
then read the named attribute in a GN modifier that sets position.

## Setup

1. Add a subdivided plane (`Plane`, then enter edit mode, subdivide a few
   times).
2. Add a Geometry Nodes modifier (we'll wire it up after PyNodes).
3. Open the new PyNodes editor space.

## PyNodes graph

```
+--------------+    +--------------+    +----------+    +---------------------+
| Mesh In      |    | Positions    |    | PyExpr   |    | Attribute Bridge    |
| object=Plane | -> | (extracts P) | -> | code =   | -> | object=Plane        |
+--------------+    +--------------+    | sin(...) |    | name="displacement" |
                                        +----------+    | type=FLOAT_VECTOR   |
                                                        | domain=POINT        |
                                                        +---------------------+
```

The `PyExpr` node's code:

```python
P = inputs['positions']            # (N, 3) float32
freq = 6.0
amp = 0.3
# displacement = (0, 0, sin(freq * x + t) * amp)
z = np.sin(freq * P[..., 0] + t) * amp
out = np.zeros_like(P)
out[..., 2] = z
```

Output: `out` — a vector array, same shape as positions, with only the Z
column populated.

The `AttributeBridge` writes this to a named attribute called
`displacement` on the Plane object, on the POINT domain.

## Geometry Nodes modifier

On the same Plane:

```
Group Input ──┐
              v
Named Attribute "displacement" ─────────┐
                                         v
                                       Set Position
                                         │
                                         v
                                       Group Output
```

The `Named Attribute` node reads the attribute PyNodes just wrote;
`Set Position` uses it as the Offset.

## Evaluation order

The modifier-like construct PyNodes registers runs before the GN
modifier. So the timeline of one frame is:

1. PyNodes evaluates → writes `displacement` attribute on the Plane mesh.
2. GN modifier evaluates → reads `displacement`, applies it.
3. Viewport updates.

## Animating

The `t` variable in the PyExpr code is automatically bound to scene
time in seconds. Scrubbing the timeline:

- Triggers a frame change.
- PyNodes' frame-change handler invalidates time-dependent nodes.
- On next pull, PyExpr re-evaluates with the new `t`.
- The new `displacement` attribute reaches the GN modifier.
- The mesh ripples.

The whole loop costs ~10ms on a 10k-vertex plane: PyExpr ~3ms, attribute
write ~2ms, GN evaluation ~3ms, viewport refresh ~2ms.

## Editing the kernel

The user can change `freq`, `amp`, or rewrite the expression entirely
without leaving the editor. On commit (focus loss or `Recompile`
button), the cache key for the PyExpr node changes and the next
evaluation picks up the new code.

## Promoting to GN later (phase 3)

In phase 3 the user could toggle the PyExpr node to "Compile to GN".
The compiler would translate `np.sin(freq * P[..., 0] + t) * amp` into
the GN equivalent:

```
Separate XYZ (Position) ─ X ─→ Math MULTIPLY (freq) → Math ADD (t) → Math SINE → Math MULTIPLY (amp) → Combine XYZ (0, 0, z) → output
```

Same result, parallel evaluation, no Python execution cost. Same
viewport ripple.

## What this example shows

- PyNodes graphs are small and readable for math-heavy kernels.
- Interop with GN is via named attributes, decoupled and clean.
- Live editing is the headline UX — change code, see results.

## Related

- `numpy-field-kernel.md` — more complex example (curl noise).
- Node reference: `../api/node-reference.md`.
- GN interop: `../architecture/08-gn-interop.md`.
