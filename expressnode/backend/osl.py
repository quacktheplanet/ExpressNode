"""OSL backend: compile a CompiledExpression to Open Shading Language.

The same expression that drives geometry (GN backend) becomes a Cycles
shader. OSL is a clean expression language, so emission is a direct SSA
translation of the EvalGraph: one `type vN = expr;` per node, in
topological order.

Correctness model (mirrors how every backend boundary in this project
is handled):
- **Headless, proven here:** every frontend op has an OSL template
  (coverage); emitted source is structurally valid (shader signature,
  balanced braces, SSA — every var declared before use, params
  surfaced); golden programs are pinned.
- **OSL-runtime checklist (when oslc/testshade/Blender is available):**
  numeric parity with the M6 numpy oracle. For noise-free expressions
  OSL's stdlib (`sin`, `mix`, `dot`, ...) is IEEE-identical to numpy,
  so the SSA translation is the only thing under test. `noise()` /
  `voronoi()` use reference helpers authored to mirror
  `evaluator/noise.py`; bit-exact lattice-hash parity across languages
  is the runtime-checklist item (see docs/osl.md).

No `bpy`; pure text generation; fully importable headlessly.
"""

from __future__ import annotations

from .._ir.eval_graph import SocketType

from ..backend.op_emitters import get_emitter
from ..frontend.parser import CompiledExpression

# ---------------------------------------------------------------------------
# Reference noise/voronoi in OSL — mirrors expressnode/evaluator/noise.py
# ---------------------------------------------------------------------------

OSL_NOISE_LIB = r'''
/* Reference value noise / voronoi: mirrors the numpy oracle
   (expressnode/evaluator/noise.py), hash included. */

/* OSL has only signed 32-bit ints. Multiply and xor give the same bits
   as uint32; right shifts are emulated as logical shifts, and the final
   value is read as unsigned, so the hash matches the oracle's uint32. */
int cn_srl(int h, int s) { return (h >> s) & ((1 << (32 - s)) - 1); }
int cn_step(int h, int p)
{
    h = (h ^ p) * 0x85EBCA77;
    return h ^ cn_srl(h, 13);
}
int cn_final(int h)
{
    h = (h ^ cn_srl(h, 15)) * 0xC2B2AE3D;
    return h ^ cn_srl(h, 13);
}
float cn_u01(int h)
{
    float f = (float)(h & 0x7FFFFFFF);
    if (h < 0) f += 2147483648.0;
    return f / 4294967296.0;
}
float cn_h01(int a, int b, int c, int d, int e)
{
    int h = 0x9E3779B1;
    h = cn_step(h, a); h = cn_step(h, b); h = cn_step(h, c);
    h = cn_step(h, d); h = cn_step(h, e);
    return cn_u01(cn_final(h));
}
float cn_h01_4(int a, int b, int c, int d)
{
    int h = 0x9E3779B1;
    h = cn_step(h, a); h = cn_step(h, b); h = cn_step(h, c);
    h = cn_step(h, d);
    return cn_u01(cn_final(h));
}

float cn_fade(float t) { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }

float cn_slice(float x, float y, float z, int iw, int seed)
{
    int ix = (int)floor(x), iy = (int)floor(y), iz = (int)floor(z);
    float ux = cn_fade(x - ix), uy = cn_fade(y - iy), uz = cn_fade(z - iz);
    float c000 = cn_h01(ix,   iy,   iz,   seed, iw);
    float c100 = cn_h01(ix+1, iy,   iz,   seed, iw);
    float c010 = cn_h01(ix,   iy+1, iz,   seed, iw);
    float c110 = cn_h01(ix+1, iy+1, iz,   seed, iw);
    float c001 = cn_h01(ix,   iy,   iz+1, seed, iw);
    float c101 = cn_h01(ix+1, iy,   iz+1, seed, iw);
    float c011 = cn_h01(ix,   iy+1, iz+1, seed, iw);
    float c111 = cn_h01(ix+1, iy+1, iz+1, seed, iw);
    float x00 = mix(c000, c100, ux), x10 = mix(c010, c110, ux);
    float x01 = mix(c001, c101, ux), x11 = mix(c011, c111, ux);
    return mix(mix(x00, x10, uy), mix(x01, x11, uy), uz);
}

float cn_value_noise(point p, float w, int seed)
{
    int iw = (int)floor(w);
    float fw = cn_fade(w - iw);
    float a = cn_slice(p[0], p[1], p[2], iw,     seed);
    float b = cn_slice(p[0], p[1], p[2], iw + 1, seed);
    return mix(a, b, fw);
}

float cn_voronoi_f1(point p, int seed)
{
    int bx = (int)floor(p[0]), by = (int)floor(p[1]), bz = (int)floor(p[2]);
    float best = 1.0e30;
    for (int dx = -1; dx <= 1; dx = dx + 1)
    for (int dy = -1; dy <= 1; dy = dy + 1)
    for (int dz = -1; dz <= 1; dz = dz + 1) {
        int cx = bx + dx, cy = by + dy, cz = bz + dz;
        float fx = cn_h01_4(cx, cy, cz, seed);
        float fy = cn_h01_4(cy, cz, cx, seed);
        float fz = cn_h01_4(cz, cx, cy, seed);
        point f = point(cx + fx, cy + fy, cz + fz);
        float d = distance(p, f);
        if (d < best) best = d;
    }
    return best;
}
'''


# ---------------------------------------------------------------------------
# Op -> OSL expression templates
# ---------------------------------------------------------------------------

def _osl_type(t: SocketType) -> str:
    if t == SocketType.VECTOR:
        return "vector"
    return "float"  # FLOAT / INT / others surfaced as float in the shader


def _bin(symbol):
    return lambda a, n: f"({a[0]} {symbol} {a[1]})"


def _fn(name):
    return lambda a, n: f"{name}({', '.join(a)})"


def _cmp(symbol):
    return lambda a, n: f"(({a[0]} {symbol} {a[1]}) ? 1.0 : 0.0)"


_TEMPLATES = {
    # inputs
    "input.position": lambda a, n: "P",
    "input.normal": lambda a, n: "N",
    "input.index": lambda a, n: "0.0",
    "input.scene_time": lambda a, n: "Time",
    "input.frame": lambda a, n: "Frame",
    "input.delta_time": lambda a, n: "DeltaTime",
    # constants
    "constant.float": lambda a, n: repr(float(n.params.get("value", 0.0))),
    "constant.int": lambda a, n: repr(float(n.params.get("value", 0.0))),
    "constant.bool": lambda a, n: "1.0" if n.params.get("value") else "0.0",
    # scalar arithmetic
    "math.add": _bin("+"), "math.sub": _bin("-"),
    "math.mul": _bin("*"), "math.div": _bin("/"),
    "math.mod": lambda a, n: f"mod({a[0]}, {a[1]})",
    "math.pow": lambda a, n: f"pow({a[0]}, {a[1]})",
    "math.floordiv": lambda a, n: f"floor({a[0]} / {a[1]})",
    "math.neg": lambda a, n: f"(-{a[0]})",
    "math.sin": _fn("sin"), "math.cos": _fn("cos"), "math.tan": _fn("tan"),
    "math.asin": _fn("asin"), "math.acos": _fn("acos"),
    "math.atan": _fn("atan"),
    "math.atan2": lambda a, n: f"atan2({a[0]}, {a[1]})",
    "math.sqrt": _fn("sqrt"), "math.exp": _fn("exp"), "math.log": _fn("log"),
    "math.abs": _fn("abs"), "math.floor": _fn("floor"),
    "math.ceil": _fn("ceil"), "math.round": lambda a, n: f"floor({a[0]} + 0.5)",
    "math.sign": _fn("sign"),
    "math.min": lambda a, n: f"min({a[0]}, {a[1]})",
    "math.max": lambda a, n: f"max({a[0]}, {a[1]})",
    "math.clamp": lambda a, n: f"clamp({a[0]}, {a[1]}, {a[2]})",
    "math.mix": lambda a, n: f"mix({a[0]}, {a[1]}, {a[2]})",
    "math.smoothstep": lambda a, n: f"smoothstep({a[0]}, {a[1]}, {a[2]})",
    "math.fract": lambda a, n: f"({a[0]} - floor({a[0]}))",
    "math.step": lambda a, n: f"(({a[1]}) >= ({a[0]}) ? 1.0 : 0.0)",
    "math.ping_pong": lambda a, n: f"fabs(mod(({a[0]}) - ({a[1]}), 2.0 * ({a[1]})) - ({a[1]}))",
    # vector
    "vec.add": _bin("+"), "vec.sub": _bin("-"),
    "vec.mul": _bin("*"), "vec.div": _bin("/"),
    "vec.mod": lambda a, n: f"mod({a[0]}, {a[1]})",
    "vec.pow": lambda a, n: f"pow({a[0]}, {a[1]})",
    "vec.floordiv": lambda a, n: f"floor({a[0]} / {a[1]})",
    "vec.neg": lambda a, n: f"(-{a[0]})",
    "vec.length": _fn("length"),
    "vec.dot": lambda a, n: f"dot({a[0]}, {a[1]})",
    "vec.cross": lambda a, n: f"cross({a[0]}, {a[1]})",
    "vec.normalize": _fn("normalize"),
    "vec.reflect": lambda a, n: f"reflect({a[0]}, {a[1]})",
    "vec.distance": lambda a, n: f"distance({a[0]}, {a[1]})",
    "vec.combine2": lambda a, n: f"vector({a[0]}, {a[1]}, 0.0)",
    "vec.combine3": lambda a, n: f"vector({a[0]}, {a[1]}, {a[2]})",
    "vec.combine4": lambda a, n: f"vector({a[0]}, {a[1]}, {a[2]})",
    "vec.component.x": lambda a, n: f"{a[0]}[0]",
    "vec.component.y": lambda a, n: f"{a[0]}[1]",
    "vec.component.z": lambda a, n: f"{a[0]}[2]",
    "vec.component.w": lambda a, n: f"{a[0]}[2]",
    # comparisons
    "compare.lt": _cmp("<"), "compare.le": _cmp("<="),
    "compare.gt": _cmp(">"), "compare.ge": _cmp(">="),
    "compare.eq": _cmp("=="), "compare.ne": _cmp("!="),
    # boolean
    "bool.and": lambda a, n: f"((({a[0]} != 0.0) && ({a[1]} != 0.0)) ? 1.0 : 0.0)",
    "bool.or": lambda a, n: f"((({a[0]} != 0.0) || ({a[1]} != 0.0)) ? 1.0 : 0.0)",
    "bool.not": lambda a, n: f"(({a[0]} != 0.0) ? 0.0 : 1.0)",
    # flow
    "flow.if": lambda a, n: f"(({a[0]} != 0.0) ? {a[1]} : {a[2]})",
    # procedural (reference helpers)
    "texture.noise": lambda a, n: (
        f"cn_value_noise(point({a[0]})"
        f"{(' * ' + a[1]) if len(a) > 1 else ''}, Time, Seed)"
    ),
    "texture.voronoi": lambda a, n: (
        f"cn_voronoi_f1(point({a[0]})"
        f"{(' * ' + a[1]) if len(a) > 1 else ''}, Seed)"
    ),
    # blender access
    # In a shader, geometry attributes / object data come from the
    # material graph, not the kernel; emit compilable neutral defaults.
    # (Wiring these to OSL getattribute() is the M7 follow-up.)
    "attr.read": lambda a, n: "0.0",
    "attr.write": lambda a, n: (a[0] if a else "0.0"),
    "obj.read": lambda a, n: "vector(0.0, 0.0, 0.0)",
}


def _swizzle(a, n):
    # OSL only indexes names (`v0[1]`, not `(v0)[1]`) and has no vec2 or
    # vec4: two components pad with 0, a fourth is dropped.
    pat = n.params.get("pattern", "xyz")
    idx = {"x": 0, "y": 1, "z": 2, "w": 2}
    comps = [f"{a[0]}[{idx[c]}]" for c in pat[:3]]
    if len(comps) == 1:
        return comps[0]
    while len(comps) < 3:
        comps.append("0.0")
    return f"vector({', '.join(comps)})"


_TEMPLATES["vec.swizzle"] = _swizzle


def osl_template_ops() -> set[str]:
    return set(_TEMPLATES)


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def emit_osl(compiled: CompiledExpression, shader_name: str = "") -> str:
    """Return a complete OSL shader string for the compiled expression."""
    graph = compiled.graph
    name = shader_name or f"expr_{compiled.entry_function}"

    # Shader parameters. Position/Normal use OSL globals P/N inside the
    # body; Time/Frame/Seed are exposed parameters.
    param_lines = ["    float Time = 0.0,",
                   "    float Frame = 1.0,",
                   "    float DeltaTime = 0.0416667,",
                   "    int   Seed = 0,"]
    for pname, ptype, default in [
        (p.name, p.type.to_socket_type(), p.default)
        for p in compiled.parameters
    ]:
        if ptype == SocketType.VECTOR:
            param_lines.append(f"    vector {pname} = vector(0.0),")
        else:
            param_lines.append(f"    float {pname} = {float(default or 0.0)!r},")

    nid, rsock = graph.outputs["result"]
    rtype = graph.nodes[nid].output_type(rsock)
    out_decl = ("output vector Result = vector(0.0)"
                if rtype == SocketType.VECTOR
                else "output float Result = 0.0")

    body: list[str] = []
    var: dict[int, str] = {}
    used_noise = False

    def in_expr(node, socket_name) -> str:
        for e in graph.in_edges(node):
            if e.target_socket == socket_name:
                return var[e.source_node]
        return "0.0"

    for node in graph.topological_order():
        em = get_emitter(node.op)
        if em is not None and em.kind == "param_only":
            var[node.id] = "0.0"
            continue
        if node.op == "input.parameter":
            var[node.id] = node.params["name"]
            continue
        tmpl = _TEMPLATES.get(node.op)
        if tmpl is None:
            raise KeyError(
                f"no OSL template for op {node.op!r} "
                f"(add it to backend/osl.py)"
            )
        if node.op in ("texture.noise", "texture.voronoi"):
            used_noise = True
        args = [in_expr(node, s) for s, _ in node.input_sockets]
        expr = tmpl(args, node)
        vname = f"v{node.id}"
        otype = _osl_type(node.output_type(node.output_sockets[0][0]))
        body.append(f"    {otype} {vname} = {expr};")
        var[node.id] = vname

    result_var = var[nid]
    body.append(f"    Result = {result_var};")

    lib = OSL_NOISE_LIB if used_noise else ""
    params = "\n".join(param_lines) + f"\n    {out_decl}"
    return (
        f"// generated by expressnode — OSL backend\n"
        f"{lib}\n"
        f"shader {name} (\n{params}\n)\n"
        f"{{\n" + "\n".join(body) + "\n}\n"
    )
