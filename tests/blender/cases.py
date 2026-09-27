"""Expression cases shared by the Blender and GPU parity checks.

Pure Python (no bpy, no numpy at import) so every harness can load it:
the in-Blender checks (bl_gn.py, bl_osl.py, bl_gui.py) and the WGSL
driver (tests/gpu/wgsl_parity.py).

Each case lists the backends it is compared on. Geometry Nodes can't
match the oracle for noise()/voronoi() (it uses Blender's own noise, by
design, see docs/evaluator.md), so noise cases are shader-only there.
Cases that read the index, frame, delta time, normals, attributes or
objects are Geometry Nodes only: in the shader harnesses those are
bindings the harness picks, not something the backend computes.
"""

from __future__ import annotations

import pathlib

_EXAMPLES = pathlib.Path(__file__).resolve().parents[2] / "examples"

ALL = ("gn", "osl", "glsl", "wgsl")
SHADERS = ("osl", "glsl", "wgsl")

CASES = [
    {
        "name": "ripple",
        "source": (_EXAMPLES / "ripple.py").read_text(encoding="utf-8"),
        "backends": ALL,
        "params": {"freq": 4.0, "amp": 0.5},
    },
    {
        "name": "arithmetic",
        "source": (
            "def arith(P, t, a=1.5, b=0.25):\n"
            "    return vec3(P.x * a - P.y / 2.0 + b,\n"
            "                (P.z + t) % 0.7,\n"
            "                P.y ** 2.0 - P.x // 0.3)\n"
        ),
        "backends": ALL,
        "params": {"a": -0.75},
    },
    {
        "name": "functions",
        "source": (
            "def funcs(P, t):\n"
            "    return vec3(sin(P.x) + cos(P.y) * tan(P.z * 0.4),\n"
            "                atan2(P.y, P.x) + sqrt(abs(P.z)),\n"
            "                exp(P.x * 0.5) - log(abs(P.y) + 1.0))\n"
        ),
        "backends": ALL,
    },
    {
        "name": "rounding",
        "source": (
            "def rounding(P, t):\n"
            "    return vec3(floor(P.x * 3.0) + ceil(P.y * 2.0) + round(P.z * 4.0),\n"
            "                sign(P.x) * min(P.y, P.z) + max(P.x, 0.1),\n"
            "                asin(clamp(P.y, -0.9, 0.9)) + acos(clamp(P.z, -0.9, 0.9))\n"
            "                + atan(P.x))\n"
        ),
        "backends": ALL,
    },
    {
        "name": "shaping",
        "source": (
            "def shaping(P, t, k=0.35):\n"
            "    return vec3(clamp(P.x, -0.5, 0.5) + mix(P.y, P.z, k) + mix(P.y, P.z, P.x),\n"
            "                smoothstep(-0.5, 0.8, P.x) + step(0.1, P.y),\n"
            "                fract(P.z * 2.3) + ping_pong(P.x, 0.4))\n"
        ),
        "backends": ALL,
    },
    {
        "name": "logic",
        "source": (
            "def logic(P, t):\n"
            "    a = P.x if P.y > 0.0 else P.z\n"
            "    b = 1.0 if (P.x < 0.2 and P.z >= -0.3) else 0.0\n"
            "    c = 2.0 if (P.y <= 0.1 or not (P.x > 0.5)) else -1.0\n"
            "    d = 1.0 if P.z != 0.25 else 0.0\n"
            "    e = 3.0 if P.x == P.x else 0.0\n"
            "    return vec3(a, b + d, c + e)\n"
        ),
        "backends": ALL,
    },
    {
        "name": "vectors",
        "source": (
            "def vectors(P, t):\n"
            "    q = vec3(0.3, -0.2, 0.9)\n"
            "    r = reflect(P, q) * 0.5 + cross(P, q)\n"
            "    s = normalize(P + vec3(0.0, 0.0, 2.0)) * length(P) - q * dot(P, q)\n"
            "    return r + s + vec3(distance(P, q), 0.0, 0.0) - P / vec3(2.0, 4.0, 8.0)\n"
        ),
        "backends": ALL,
    },
    {
        "name": "vector_ops",
        "source": (
            "def vector_ops(P, t):\n"
            "    a = P % vec3(0.5, 0.7, 0.3)\n"
            "    b = P // vec3(0.4, 0.4, 0.4)\n"
            "    c = (P * P + vec3(0.1, 0.1, 0.1)) ** vec3(0.5, 1.5, 2.0)\n"
            "    m = mix(P, P.zxy, 0.3) + mix(P, P.yzx, P.x)\n"
            "    return a + b * 0.1 + c - (-P) * 0.2 + m\n"
        ),
        "backends": ALL,
    },
    {
        "name": "swizzle",
        "source": (
            "def swz(P, t):\n"
            "    v = vec2(P.x, P.y)\n"
            "    return P.zyx + P.yxz * 0.5 + vec3(v.y, 1.0, 2.0) + vec3(P.z, 0.0, 0.0).xzy\n"
        ),
        "backends": ALL,
    },
    {
        "name": "helpers",
        "source": (
            "def wave(x, k):\n"
            "    return sin(x * k) * 0.5\n"
            "\n"
            "def bump(p, k):\n"
            "    return wave(p.x, k) + wave(p.y, k * 2.0) + wave(p.z, k * 3.0)\n"
            "\n"
            "def helpers(P, t, k=1.7):\n"
            "    return vec3(bump(P, k), bump(P.yzx, k + t), bump(P * 2.0, k) - wave(P.x, 3.0))\n"
        ),
        "backends": ALL,
        "inline_threshold": 0,     # force wave and bump into nested groups
    },
    {
        "name": "helpers_inlined",
        "source": None,            # same source as "helpers", default threshold
        "same_as": "helpers",
        "backends": ("gn",),
    },
    {
        "name": "builtins",
        "source": (
            "def builtins(P, t, frame, dt, i, N):\n"
            "    return vec3(t * 0.5 + frame * 0.01, dt * 10.0, i * 0.001) + N * 0.1\n"
        ),
        "backends": ("gn",),
    },
    {
        "name": "access",
        "source": (
            "def access(P, t):\n"
            "    set_attr(\"heat\", P.x * 2.0)\n"
            "    return (vec3(attr(\"seed_attr\"), 0.0, 0.0)\n"
            "            + obj(\"Target\", \"position\") * 0.1\n"
            "            + obj(\"Target\", \"scale\") * 0.01\n"
            "            + obj(\"Target\", \"rotation\") * 0.001)\n"
        ),
        "backends": ("gn",),
    },
    {
        "name": "curl_noise",
        "source": (_EXAMPLES / "curl_noise.py").read_text(encoding="utf-8"),
        "backends": SHADERS,
        # Central differences with eps = 0.001, scaled by 1/(2 eps): float32
        # rounding of the noise values is amplified ~200x, so a float32
        # backend can't get closer than ~1e-3 to the float64 oracle.
        "atol": 1e-2,
    },
    {
        "name": "cells",
        "source": (
            "def cells(P, t):\n"
            "    return vec3(voronoi(P, 2.0), noise(P, 1.5), voronoi(P * 0.5))\n"
        ),
        "backends": SHADERS,
    },
]

for _c in CASES:
    if _c.get("same_as"):
        _src = next(c for c in CASES if c["name"] == _c["same_as"])
        _c["source"] = _src["source"]

TIME = 0.5          # seconds; frame 12 at 24 fps
FRAME = 12
FPS = 24


def cases_for(backend: str) -> list[dict]:
    return [c for c in CASES if backend in c["backends"]]


def sample_points(n: int = 400, seed: int = 7):
    """Deterministic points in [-1.5, 1.5]^3 (a plain LCG, no numpy)."""
    state = seed
    out = []
    for _ in range(n):
        p = []
        for _ in range(3):
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            p.append(state / 0x7FFFFFFF * 3.0 - 1.5)
        out.append(p)
    return out


def tolerance_check(np, got, want, retry=None, atol=2e-4, rtol=2e-4):
    """Compare float32 backend output with the float64 oracle.

    A point that misses is forgiven only if the oracle itself jumps
    there (a floor/step/compare edge the float32 input sits on): `retry`
    re-evaluates the oracle with the inputs nudged by +-1e-5, and a match
    against any nudge counts. Returns (max_err, misses, forgiven).
    """
    got = np.asarray(got, dtype=np.float64).reshape(len(got), -1)
    want = np.asarray(want, dtype=np.float64).reshape(len(want), -1)
    k = min(got.shape[1], want.shape[1])
    got, want = got[:, :k], want[:, :k]
    err = np.abs(got - want)
    bad = np.any(err > atol + rtol * np.abs(want), axis=1)
    forgiven = 0
    if retry is not None and bad.any():
        for idx in np.nonzero(bad)[0]:
            for alt in retry(int(idx)):
                alt = np.asarray(alt, dtype=np.float64).reshape(-1)[:k]
                if np.all(np.abs(got[idx] - alt) <= atol + rtol * np.abs(alt)):
                    bad[idx] = False
                    forgiven += 1
                    break
    finite = np.isfinite(err)
    max_err = float(err[finite & ~bad[:, None]].max()) if (finite & ~bad[:, None]).any() else 0.0
    return max_err, int(bad.sum()), forgiven
