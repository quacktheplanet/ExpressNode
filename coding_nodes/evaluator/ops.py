"""Numpy implementation of every EvalGraph op.

One function per op, mirroring `backend/op_emitters.py`. These define
the reference behaviour the other backends are validated against.

Calling convention: each op is `fn(args, node, ctx) -> ndarray`, where
`args` is the list of input values (already evaluated) in the order of
`node.input_sockets`, `node` is the EvalNode (for params), and `ctx`
carries the runtime inputs (P, t, parameters, attributes, ...).
"""

from __future__ import annotations

import numpy as np

from coding_nodes.evaluator.noise import value_noise, voronoi_f1


# --- broadcasting helpers ---

def _is_vec(a) -> bool:
    return np.ndim(a) >= 1 and np.shape(a)[-1] == 3


def _align(a, b):
    """Align a scalar with a vector for component-wise ops: if one side
    is a vec3 and the other is scalar/(N,), give the scalar a trailing
    axis so numpy broadcasts component-wise."""
    av, bv = _is_vec(a), _is_vec(b)
    if av and not bv:
        b = np.asarray(b)[..., None]
    elif bv and not av:
        a = np.asarray(a)[..., None]
    return a, b


def _bin(f):
    def op(args, node, ctx):
        a, b = _align(args[0], args[1])
        return f(a, b)
    return op


def _un(f):
    def op(args, node, ctx):
        return f(args[0])
    return op


# --- inputs ---

def _position(args, node, ctx):
    return ctx.P


def _normal(args, node, ctx):
    return ctx.normals


def _index(args, node, ctx):
    return ctx.index


def _scene_time(args, node, ctx):
    return np.asarray(ctx.t, dtype=np.float64)


def _frame(args, node, ctx):
    return np.asarray(ctx.frame, dtype=np.float64)


def _delta_time(args, node, ctx):
    return np.asarray(ctx.dt, dtype=np.float64)


def _parameter(args, node, ctx):
    name = node.params["name"]
    if name in ctx.params:
        return np.asarray(ctx.params[name], dtype=np.float64)
    return np.asarray(node.params.get("default", 0.0), dtype=np.float64)


def _const(args, node, ctx):
    v = node.params.get("value", 0.0)
    if v is True:
        v = 1.0
    elif v is False:
        v = 0.0
    return np.asarray(v, dtype=np.float64)


# --- vector construction / access ---

def _combine3(args, node, ctx):
    x, y, z = (np.broadcast_to(np.asarray(a, dtype=np.float64), ctx.shape)
               for a in args[:3])
    return np.stack([x, y, z], axis=-1)


def _combine2(args, node, ctx):
    x, y = (np.broadcast_to(np.asarray(a, dtype=np.float64), ctx.shape)
            for a in args[:2])
    z = np.zeros(ctx.shape, dtype=np.float64)
    return np.stack([x, y, z], axis=-1)


def _combine4(args, node, ctx):
    return _combine3(args, node, ctx)  # w dropped (vec4 surfaced as vec3)


def _component(idx):
    def op(args, node, ctx):
        v = np.asarray(args[0], dtype=np.float64)
        return v[..., idx]
    return op


def _swizzle(args, node, ctx):
    v = np.asarray(args[0], dtype=np.float64)
    pattern = node.params.get("pattern", "xyz")
    idx = {"x": 0, "y": 1, "z": 2, "w": 2}
    cols = [v[..., idx[c]] for c in pattern]
    return np.stack(cols, axis=-1)


# --- procedural ---

def _noise(args, node, ctx):
    P = np.asarray(args[0], dtype=np.float64)
    scale = float(np.asarray(args[1]).reshape(-1)[0]) if len(args) > 1 else 1.0
    return value_noise(P * scale, w=ctx.t, seed=ctx.seed)


def _voronoi(args, node, ctx):
    P = np.asarray(args[0], dtype=np.float64)
    scale = float(np.asarray(args[1]).reshape(-1)[0]) if len(args) > 1 else 1.0
    return voronoi_f1(P * scale, seed=ctx.seed)


# --- blender access ---

def _attr_read(args, node, ctx):
    name = node.params.get("name", "")
    dtype = node.params.get("dtype", "float")
    if name in ctx.attributes:
        return np.asarray(ctx.attributes[name], dtype=np.float64)
    if dtype in ("vec3", "vec2", "vec4", "color"):
        return np.zeros(ctx.shape + (3,), dtype=np.float64)
    return np.zeros(ctx.shape, dtype=np.float64)


def _attr_write(args, node, ctx):
    name = node.params.get("name", "")
    ctx.written[name] = np.asarray(args[0])
    return np.ones(ctx.shape, dtype=np.float64)


def _obj_read(args, node, ctx):
    obj = node.params.get("object", "")
    field = node.params.get("field", "position")
    vec = ctx.objects.get(obj, {}).get(field, (0.0, 0.0, 0.0))
    vec = np.asarray(vec, dtype=np.float64)
    return np.broadcast_to(vec, ctx.shape + (3,))


# --- flow / bool / compare ---

def _if(args, node, ctx):
    cond, t, f = args[0], args[1], args[2]
    c = np.asarray(cond) != 0
    if _is_vec(t) or _is_vec(f):
        c = c[..., None]
    return np.where(c, t, f)


def _smoothstep(args, node, ctx):
    lo, hi, x = (np.asarray(a, dtype=np.float64) for a in args[:3])
    tt = np.clip((x - lo) / np.where(hi - lo == 0, 1.0, hi - lo), 0.0, 1.0)
    return tt * tt * (3.0 - 2.0 * tt)


def _mix(args, node, ctx):
    a, b, t = args[0], args[1], args[2]
    if _is_vec(a) or _is_vec(b):
        t = np.asarray(t)
        if not _is_vec(t):
            t = t[..., None]
    return a + (b - a) * t


def _clamp(args, node, ctx):
    x, lo, hi = (np.asarray(a, dtype=np.float64) for a in args[:3])
    return np.clip(x, lo, hi)


def _ping_pong(a, b):
    a, b = np.broadcast_arrays(np.asarray(a, dtype=np.float64),
                               np.asarray(b, dtype=np.float64))
    safe = np.where(b == 0, 1.0, b)
    r = np.abs(np.mod(a - safe, 2.0 * safe) - safe)
    return np.where(b == 0, 0.0, r)


def _cross(args, node, ctx):
    return np.cross(np.asarray(args[0], dtype=np.float64),
                    np.asarray(args[1], dtype=np.float64))


def _normalize(args, node, ctx):
    v = np.asarray(args[0], dtype=np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


def _reflect(args, node, ctx):
    v = np.asarray(args[0], dtype=np.float64)
    n = np.asarray(args[1], dtype=np.float64)
    return v - 2.0 * np.sum(v * n, axis=-1, keepdims=True) * n


def _bool(f):
    def op(args, node, ctx):
        a = np.asarray(args[0]) != 0
        if len(args) > 1:
            b = np.asarray(args[1]) != 0
            return f(a, b).astype(np.float64)
        return f(a).astype(np.float64)
    return op


def _cmp(f):
    def op(args, node, ctx):
        a, b = _align(args[0], args[1])
        return f(a, b).astype(np.float64)
    return op


OPS = {
    # inputs
    "input.position": _position,
    "input.normal": _normal,
    "input.index": _index,
    "input.scene_time": _scene_time,
    "input.frame": _frame,
    "input.delta_time": _delta_time,
    "input.parameter": _parameter,
    # constants
    "constant.float": _const,
    "constant.int": _const,
    "constant.bool": _const,
    # scalar arithmetic
    "math.add": _bin(lambda a, b: a + b),
    "math.sub": _bin(lambda a, b: a - b),
    "math.mul": _bin(lambda a, b: a * b),
    "math.div": _bin(lambda a, b: a / b),
    "math.floordiv": _bin(lambda a, b: np.floor(a / b)),
    "math.mod": _bin(lambda a, b: np.mod(a, b)),
    "math.pow": _bin(lambda a, b: np.power(a, b)),
    "math.neg": _un(lambda a: -a),
    # scalar functions
    "math.sin": _un(np.sin), "math.cos": _un(np.cos), "math.tan": _un(np.tan),
    "math.asin": _un(np.arcsin), "math.acos": _un(np.arccos),
    "math.atan": _un(np.arctan),
    "math.atan2": _bin(lambda a, b: np.arctan2(a, b)),
    "math.sqrt": _un(np.sqrt), "math.exp": _un(np.exp),
    "math.log": _un(np.log), "math.abs": _un(np.abs),
    "math.floor": _un(np.floor), "math.ceil": _un(np.ceil),
    # round half up, like Blender's Round and GLSL floor(x + 0.5)
    "math.round": _un(lambda a: np.floor(a + 0.5)), "math.sign": _un(np.sign),
    "math.min": _bin(np.minimum), "math.max": _bin(np.maximum),
    "math.clamp": _clamp, "math.mix": _mix, "math.smoothstep": _smoothstep,
    "math.fract": _un(lambda a: a - np.floor(a)),
    # step(edge, x): 1 where x >= edge
    "math.step": _bin(lambda e, x: (x >= e).astype(np.float64)),
    # Blender's Ping-Pong: 0 at 0, rising to `scale` at `scale`, back to
    # 0 at 2*scale; 0 when scale is 0.
    "math.ping_pong": _bin(_ping_pong),
    # vector
    "vec.add": _bin(lambda a, b: a + b),
    "vec.sub": _bin(lambda a, b: a - b),
    "vec.mul": _bin(lambda a, b: a * b),
    "vec.div": _bin(lambda a, b: a / b),
    "vec.floordiv": _bin(lambda a, b: np.floor(a / b)),
    "vec.mod": _bin(lambda a, b: np.mod(a, b)),
    "vec.pow": _bin(lambda a, b: np.power(a, b)),
    "vec.neg": _un(lambda a: -a),
    "vec.length": _un(lambda v: np.linalg.norm(v, axis=-1)),
    "vec.dot": _bin(lambda a, b: np.sum(a * b, axis=-1)),
    "vec.cross": _cross,
    "vec.normalize": _normalize,
    "vec.reflect": _reflect,
    "vec.distance": _bin(lambda a, b: np.linalg.norm(a - b, axis=-1)),
    "vec.combine2": _combine2,
    "vec.combine3": _combine3,
    "vec.combine4": _combine4,
    "vec.component.x": _component(0),
    "vec.component.y": _component(1),
    "vec.component.z": _component(2),
    "vec.component.w": _component(2),
    "vec.swizzle": _swizzle,
    # comparisons
    "compare.lt": _cmp(lambda a, b: a < b),
    "compare.le": _cmp(lambda a, b: a <= b),
    "compare.gt": _cmp(lambda a, b: a > b),
    "compare.ge": _cmp(lambda a, b: a >= b),
    "compare.eq": _cmp(lambda a, b: a == b),
    "compare.ne": _cmp(lambda a, b: a != b),
    # boolean
    "bool.and": _bool(np.logical_and),
    "bool.or": _bool(np.logical_or),
    "bool.not": _bool(np.logical_not),
    # flow
    "flow.if": _if,
    # procedural
    "texture.noise": _noise,
    "texture.voronoi": _voronoi,
    # blender access
    "attr.read": _attr_read,
    "attr.write": _attr_write,
    "obj.read": _obj_read,
}
