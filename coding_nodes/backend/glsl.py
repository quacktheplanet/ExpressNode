"""GLSL backend: compile a CompiledExpression to a GLSL fragment shader.

The same expression that drives geometry (GN) and Cycles shading (OSL)
compiled to GLSL for Eevee / real-time viewport shading. SSA emission,
exactly like the OSL backend.

GLSL is stricter than OSL — no implicit float<->vec promotion — so the
emitter wraps scalar operands of vector arithmetic in `vec3(...)`. In
return, GLSL `uint` is 32-bit with defined wraparound, identical to
numpy `uint32`, so the reference noise hash is **bit-parity-capable**
with the M6 oracle (stronger than OSL's signed `int`).

Correctness model (same split as OSL/GN):
- Headless, proven here: op-template coverage; structural validity
  (`#version`, balanced braces/parens, SSA declared-before-use,
  parameters surfaced, faithful ripple chain, scalar/vector return).
- GLSL-runtime checklist: `glslangValidator` compiles the generated
  `.frag` (auto-runs when on PATH); numeric parity vs the M6 oracle
  (exact for noise-free; bit-exact for noise via uint32 parity).
"""

from __future__ import annotations

from sacred_geometry.ir.eval_graph import SocketType

from coding_nodes.backend.op_emitters import get_emitter
from coding_nodes.frontend.parser import CompiledExpression

# ---------------------------------------------------------------------------
# Reference noise/voronoi in GLSL — mirrors evaluator/noise.py exactly.
# GLSL uint is 32-bit with wraparound == numpy uint32 -> bit parity.
# ---------------------------------------------------------------------------

GLSL_NOISE_LIB = r'''
// Reference value noise / voronoi — mirrors the numpy oracle
// (coding_nodes/evaluator/noise.py). GLSL uint == numpy uint32, so this
// is bit-exact with the oracle.

uint cn_hash(uint a, uint b, uint c, uint d, uint e) {
    uint h = 0x9E3779B1u;
    uint p[5] = uint[5](a, b, c, d, e);
    for (int i = 0; i < 5; i++) {
        h = (h ^ p[i]) * 0x85EBCA77u;
        h = h ^ (h >> 13);
    }
    h = (h ^ (h >> 15)) * 0xC2B2AE3Du;
    h = h ^ (h >> 13);
    return h;
}

float cn_h01(uint a, uint b, uint c, uint d, uint e) {
    return float(cn_hash(a, b, c, d, e)) / 4294967296.0;
}

float cn_fade(float t) { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }

float cn_slice(float x, float y, float z, int iw, int seed) {
    int ix = int(floor(x)), iy = int(floor(y)), iz = int(floor(z));
    float ux = cn_fade(x - float(ix));
    float uy = cn_fade(y - float(iy));
    float uz = cn_fade(z - float(iz));
    uint S = uint(seed), W = uint(iw);
    float c000 = cn_h01(uint(ix),   uint(iy),   uint(iz),   S, W);
    float c100 = cn_h01(uint(ix+1), uint(iy),   uint(iz),   S, W);
    float c010 = cn_h01(uint(ix),   uint(iy+1), uint(iz),   S, W);
    float c110 = cn_h01(uint(ix+1), uint(iy+1), uint(iz),   S, W);
    float c001 = cn_h01(uint(ix),   uint(iy),   uint(iz+1), S, W);
    float c101 = cn_h01(uint(ix+1), uint(iy),   uint(iz+1), S, W);
    float c011 = cn_h01(uint(ix),   uint(iy+1), uint(iz+1), S, W);
    float c111 = cn_h01(uint(ix+1), uint(iy+1), uint(iz+1), S, W);
    float x00 = mix(c000, c100, ux), x10 = mix(c010, c110, ux);
    float x01 = mix(c001, c101, ux), x11 = mix(c011, c111, ux);
    return mix(mix(x00, x10, uy), mix(x01, x11, uy), uz);
}

float cn_value_noise(vec3 p, float w, int seed) {
    int iw = int(floor(w));
    float fw = cn_fade(w - float(iw));
    float a = cn_slice(p.x, p.y, p.z, iw,     seed);
    float b = cn_slice(p.x, p.y, p.z, iw + 1, seed);
    return mix(a, b, fw);
}

float cn_voronoi_f1(vec3 p, int seed) {
    int bx = int(floor(p.x)), by = int(floor(p.y)), bz = int(floor(p.z));
    float best = 1.0e30;
    uint S = uint(seed);
    for (int dx = -1; dx <= 1; dx++)
    for (int dy = -1; dy <= 1; dy++)
    for (int dz = -1; dz <= 1; dz++) {
        int cx = bx + dx, cy = by + dy, cz = bz + dz;
        float fx = cn_h01(uint(cx), uint(cy), uint(cz), S, 0u);
        float fy = cn_h01(uint(cy), uint(cz), uint(cx), S, 0u);
        float fz = cn_h01(uint(cz), uint(cx), uint(cy), S, 0u);
        vec3 f = vec3(float(cx) + fx, float(cy) + fy, float(cz) + fz);
        best = min(best, distance(p, f));
    }
    return best;
}
'''


# ---------------------------------------------------------------------------
# Op -> GLSL expression templates
# ---------------------------------------------------------------------------

def _glsl_type(t: SocketType) -> str:
    return "vec3" if t == SocketType.VECTOR else "float"


def _bin(sym):
    return lambda a, n: f"({a[0]} {sym} {a[1]})"


def _fn(name):
    return lambda a, n: f"{name}({', '.join(a)})"


def _cmp(sym):
    return lambda a, n: f"(({a[0]} {sym} {a[1]}) ? 1.0 : 0.0)"


_TEMPLATES = {
    "input.position": lambda a, n: "P",
    "input.normal": lambda a, n: "N",
    "input.index": lambda a, n: "0.0",
    "input.scene_time": lambda a, n: "Time",
    "input.frame": lambda a, n: "Frame",
    "input.delta_time": lambda a, n: "DeltaTime",
    "constant.float": lambda a, n: _flit(n.params.get("value", 0.0)),
    "constant.int": lambda a, n: _flit(n.params.get("value", 0.0)),
    "constant.bool": lambda a, n: "1.0" if n.params.get("value") else "0.0",
    "math.add": _bin("+"), "math.sub": _bin("-"),
    "math.mul": _bin("*"), "math.div": _bin("/"),
    "math.mod": lambda a, n: f"mod({a[0]}, {a[1]})",
    "math.pow": lambda a, n: f"pow({a[0]}, {a[1]})",
    "math.floordiv": lambda a, n: f"floor({a[0]} / {a[1]})",
    "math.neg": lambda a, n: f"(-{a[0]})",
    "math.sin": _fn("sin"), "math.cos": _fn("cos"), "math.tan": _fn("tan"),
    "math.asin": _fn("asin"), "math.acos": _fn("acos"),
    "math.atan": _fn("atan"),
    "math.atan2": lambda a, n: f"atan({a[0]}, {a[1]})",
    "math.sqrt": _fn("sqrt"), "math.exp": _fn("exp"), "math.log": _fn("log"),
    "math.abs": _fn("abs"), "math.floor": _fn("floor"),
    "math.ceil": _fn("ceil"), "math.round": lambda a, n: f"floor({a[0]} + 0.5)",
    "math.sign": _fn("sign"),
    "math.min": lambda a, n: f"min({a[0]}, {a[1]})",
    "math.max": lambda a, n: f"max({a[0]}, {a[1]})",
    "math.clamp": lambda a, n: f"clamp({a[0]}, {a[1]}, {a[2]})",
    "math.mix": lambda a, n: f"mix({a[0]}, {a[1]}, {a[2]})",
    "math.smoothstep": lambda a, n: f"smoothstep({a[0]}, {a[1]}, {a[2]})",
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
    "vec.combine2": lambda a, n: f"vec3({a[0]}, {a[1]}, 0.0)",
    "vec.combine3": lambda a, n: f"vec3({a[0]}, {a[1]}, {a[2]})",
    "vec.combine4": lambda a, n: f"vec3({a[0]}, {a[1]}, {a[2]})",
    "vec.component.x": lambda a, n: f"({a[0]}).x",
    "vec.component.y": lambda a, n: f"({a[0]}).y",
    "vec.component.z": lambda a, n: f"({a[0]}).z",
    "vec.component.w": lambda a, n: f"({a[0]}).z",
    "compare.lt": _cmp("<"), "compare.le": _cmp("<="),
    "compare.gt": _cmp(">"), "compare.ge": _cmp(">="),
    "compare.eq": _cmp("=="), "compare.ne": _cmp("!="),
    "bool.and": lambda a, n: f"((({a[0]} != 0.0) && ({a[1]} != 0.0)) ? 1.0 : 0.0)",
    "bool.or": lambda a, n: f"((({a[0]} != 0.0) || ({a[1]} != 0.0)) ? 1.0 : 0.0)",
    "bool.not": lambda a, n: f"(({a[0]} != 0.0) ? 0.0 : 1.0)",
    "flow.if": lambda a, n: f"(({a[0]} != 0.0) ? {a[1]} : {a[2]})",
    "texture.noise": lambda a, n: (
        f"cn_value_noise(vec3({a[0]})"
        f"{(' * ' + a[1]) if len(a) > 1 else ''}, Time, Seed)"
    ),
    "texture.voronoi": lambda a, n: (
        f"cn_voronoi_f1(vec3({a[0]})"
        f"{(' * ' + a[1]) if len(a) > 1 else ''}, Seed)"
    ),
    "attr.read": lambda a, n: "0.0",
    "attr.write": lambda a, n: (a[0] if a else "0.0"),
    "obj.read": lambda a, n: "vec3(0.0)",
}


def _flit(v) -> str:
    """GLSL float literal — always has a decimal point/exponent."""
    f = float(v)
    s = repr(f)
    if "." not in s and "e" not in s and "E" not in s and "inf" not in s:
        s += ".0"
    return s


def _swizzle(a, n):
    pat = n.params.get("pattern", "xyz")
    comps = ", ".join(f"({a[0]}).{c if c != 'w' else 'z'}" for c in pat)
    return f"vec3({comps})" if len(pat) >= 2 else comps


_TEMPLATES["vec.swizzle"] = _swizzle


def glsl_template_ops() -> set[str]:
    return set(_TEMPLATES)


_VEC_BINARY = {"vec.add", "vec.sub", "vec.mul", "vec.div",
               "vec.mod", "vec.pow", "vec.floordiv"}


def emit_glsl(compiled: CompiledExpression, func_name: str = "") -> str:
    """Return a complete GLSL fragment shader for the compiled
    expression. The expression is a function; main() exercises it so the
    shader is non-trivial and validator-checkable."""
    graph = compiled.graph
    name = func_name or f"expr_{compiled.entry_function}"

    nid, rsock = graph.outputs["result"]
    rtype = graph.nodes[nid].output_type(rsock)
    ret = _glsl_type(rtype)

    sig = ["vec3 P", "vec3 N", "float Time", "float Frame",
           "float DeltaTime", "int Seed"]
    for p in compiled.parameters:
        gt = _glsl_type(p.type.to_socket_type())
        sig.append(f"{gt} {p.name}")

    body: list[str] = []
    var: dict[int, str] = {}
    gtype: dict[int, str] = {}
    used_noise = False

    def in_ref(node, socket_name):
        for e in graph.in_edges(node):
            if e.target_socket == socket_name:
                return e.source_node
        return None

    for node in graph.topological_order():
        em = get_emitter(node.op)
        if em is not None and em.kind == "param_only":
            var[node.id], gtype[node.id] = "0.0", "float"
            continue
        if node.op == "input.parameter":
            pname = node.params["name"]
            var[node.id] = pname
            pmatch = next((p for p in compiled.parameters
                           if p.name == pname), None)
            gtype[node.id] = (_glsl_type(pmatch.type.to_socket_type())
                              if pmatch else "float")
            continue

        tmpl = _TEMPLATES.get(node.op)
        if tmpl is None:
            raise KeyError(
                f"no GLSL template for op {node.op!r} (add it to "
                f"backend/glsl.py)"
            )
        if node.op in ("texture.noise", "texture.voronoi"):
            used_noise = True

        args, atypes = [], []
        for sname, _ in node.input_sockets:
            src = in_ref(node, sname)
            if src is None:
                args.append("0.0")
                atypes.append("float")
            else:
                args.append(var[src])
                atypes.append(gtype[src])

        # GLSL has no implicit float->vec promotion: wrap scalar
        # operands of vector arithmetic in vec3(...).
        if node.op in _VEC_BINARY:
            args = [f"vec3({a})" if t == "float" else a
                    for a, t in zip(args, atypes)]

        expr = tmpl(args, node)
        out_t = _glsl_type(node.output_type(node.output_sockets[0][0]))
        vname = f"v{node.id}"
        body.append(f"    {out_t} {vname} = {expr};")
        var[node.id], gtype[node.id] = vname, out_t

    body.append(f"    return {var[nid]};")
    lib = GLSL_NOISE_LIB if used_noise else ""

    call_args = ["P", "N", "Time", "Frame", "DeltaTime", "Seed"] + \
                [p.name for p in compiled.parameters]
    main_locals = [
        "    vec3 P = gl_FragCoord.xyz;",
        "    vec3 N = vec3(0.0, 0.0, 1.0);",
        "    float Time = 0.0, Frame = 1.0, DeltaTime = 0.0416667;",
        "    int Seed = 0;",
    ] + [
        (f"    vec3 {p.name} = vec3(0.0);"
         if p.type.to_socket_type() == SocketType.VECTOR
         else f"    float {p.name} = {_flit(p.default or 0.0)};")
        for p in compiled.parameters
    ]
    result_expr = f"{name}({', '.join(call_args)})"
    frag_write = (f"_fragColor = vec4({result_expr}, 1.0);"
                  if ret == "vec3"
                  else f"_fragColor = vec4(vec3({result_expr}), 1.0);")

    return (
        "#version 330 core\n"
        "// generated by coding_nodes — GLSL backend\n"
        f"{lib}\n"
        f"{ret} {name}({', '.join(sig)}) {{\n"
        + "\n".join(body) + "\n}\n\n"
        "out vec4 _fragColor;\n"
        "void main() {\n"
        + "\n".join(main_locals) + "\n"
        f"    {frag_write}\n"
        "}\n"
    )
