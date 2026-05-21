# Expression Reference

The full Python surface the compiler accepts. Everything here compiles
to clean Geometry Nodes output.

## Rule of thumb

If the function reads like math to someone who's never run Python,
it compiles. If it depends on Python's runtime introspection, opens
files, or has variable-length arguments, it doesn't.

## Function definitions

```python
def name(arg1, arg2=default, ...):
    return expression
```

- One or more parameters, each typed-inferred from default values or
  use site.
- Keyword arguments with literal defaults supported.
- Single `return` expression. Multiple-statement bodies allowed when
  the statements are assignments, `if/else`, or nested `def`.
- Nested `def` becomes a nested group node in the output.

## Built-in variables

These are the inputs every expression has implicit access to:

| Name | Type | Source |
|---|---|---|
| `P` | vec3 | Position input |
| `N` | vec3 | Normal input |
| `i` | int | Index input |
| `t` | float | Scene time, seconds |
| `frame` | int | Current frame number |
| `dt` | float | Delta time between frames |

Reference them anywhere in the expression. The compiler wires them up
as the corresponding GN input node.

## Numeric types

- `int` — integer
- `float` — single-precision float
- `bool` — boolean

## Vector types

- `vec2(x, y)`
- `vec3(x, y, z)`
- `vec4(x, y, z, w)`

Components accessed by `.x`, `.y`, `.z`, `.w`, or by index `v[0]`,
`v[1]`, etc. Swizzles like `v.xy`, `v.zyx`, `v.xxxx` are supported.

## Arithmetic operators

Standard Python arithmetic: `+`, `-`, `*`, `/`, `//`, `%`, `**`.
- Component-wise on vectors.
- Mixed scalar/vector broadcasts the scalar.

## Comparison and boolean operators

`<`, `<=`, `>`, `>=`, `==`, `!=`, `and`, `or`, `not`.

Return `bool`. Used in conditional expressions.

## Conditional expressions

```python
result = a if condition else b
```

Compiles to a `Switch` node. Both branches are evaluated (typical GN
behavior); side effects in either branch aren't allowed anyway because
the language is pure-functional.

## Built-in functions

### Math

| Name | Description |
|---|---|
| `sin(x)`, `cos(x)`, `tan(x)` | Trig |
| `asin(x)`, `acos(x)`, `atan(x)` | Inverse trig |
| `atan2(y, x)` | Two-argument atan |
| `sqrt(x)` | Square root |
| `pow(x, n)` | Power |
| `exp(x)`, `log(x)` | Natural exp / log |
| `abs(x)` | Absolute value |
| `floor(x)`, `ceil(x)`, `round(x)` | Rounding |
| `mod(x, m)` | Modulo |
| `sign(x)` | Sign (-1/0/+1) |
| `min(a, b)`, `max(a, b)` | Min / max |
| `clamp(x, lo, hi)` | Clamp |
| `mix(a, b, t)` | Linear interpolation |
| `smoothstep(lo, hi, x)` | Smooth step |
| `fract(x)` | Fractional part (`x - floor(x)`) |
| `step(edge, x)` | 0.0 if x < edge, else 1.0 |
| `ping_pong(x, scale)` | Triangle wave, range [0, scale] |

### Procedural

| Name | Description |
|---|---|
| `noise(P)` | Scalar 4D perlin noise at P (uses `t` automatically) |
| `noise(P, scale=s, detail=d, roughness=r)` | Tunable noise |
| `voronoi(P)` | Scalar voronoi distance |
| `voronoi(P, scale=s)` | Tunable voronoi |

### Vector

| Name | Description |
|---|---|
| `length(v)` | Vector length |
| `dot(a, b)` | Dot product |
| `cross(a, b)` | Cross product |
| `normalize(v)` | Unit vector |
| `reflect(v, n)` | Reflection |

### Blender access

| Name | Description |
|---|---|
| `attr("name")` | Read a named attribute (auto-typed) |
| `attr("name", dtype)` | Read with explicit dtype (`"float"`, `"vec3"`, `"color"`) |
| `set_attr("name", value)` | Write a named attribute |
| `obj("name", "field")` | Read another object's property — `"position"`, `"rotation"`, `"scale"` |

## Compile-time errors

The compiler refuses to compile certain Python constructs. Each gives a
specific error message pointing at the offending source line.

| Construct | Error |
|---|---|
| `getattr(obj, dynamic_name)` | "Dynamic attribute access isn't compileable. Use a direct call instead." |
| `open(...)` / file I/O | "File I/O isn't available inside an expression." |
| `*args` / `**kwargs` | "Variadic arguments aren't compileable. Declare each argument explicitly." |
| `class Foo: ...` | "Class definitions aren't compileable. Use functions and vectors." |
| `import x` | "Imports aren't allowed inside an expression. The built-ins listed in `expression-reference.md` are available." |
| `try/except` | "Exception handling isn't compileable. Use `if/else` for fallback logic." |
| `list[i]` with dynamic `i` | "Variable-length array indexing isn't compileable. Use fixed vectors." |
| Mutating a global | "Mutating module-level state isn't compileable. Pure functions only." |

## Examples of the rule of thumb

These compile:

```python
def ripple(P, t):
    return vec3(0, 0, sin(P.x * 6 + t) * 0.3)

def banded(P):
    return mix(0.0, 1.0, smoothstep(0.0, 0.5, abs(sin(P.z * 8))))

def curl(P, t, scale=2.0):
    eps = 1e-3
    nx = noise(P + vec3(eps, 0, 0)) - noise(P - vec3(eps, 0, 0))
    ny = noise(P + vec3(0, eps, 0)) - noise(P - vec3(0, eps, 0))
    nz = noise(P + vec3(0, 0, eps)) - noise(P - vec3(0, 0, eps))
    return vec3(ny - nz, nz - nx, nx - ny) * scale
```

These don't:

```python
def dynamic(P, t):
    fn_name = "sin" if t > 0 else "cos"
    return getattr(math, fn_name)(P.x)         # dynamic dispatch

def with_io(P):
    with open("config.json") as f:              # I/O
        cfg = json.load(f)
    return P * cfg["scale"]

def variadic(*args):                            # variadic
    return sum(args)
```
