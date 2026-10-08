"""GPU compute backend: compile a CompiledExpression to a WGSL compute
shader — the "fast at scale" target (ROADMAP §4b).

The expression becomes a parallel kernel: a flat `array<f32>` of N
positions in, a flat `array<f32>` of N*3 results out, one invocation
per point. WGSL is the portable modern GPU language (WebGPU / wgpu /
naga / tint → SPIR-V), so this is the path to million-point kernels.

Like GLSL, WGSL `u32` has defined wraparound == numpy `uint32`, so the
reference noise is **bit-exact** with the M6 oracle. WGSL has no
implicit scalar→vector promotion, so scalar operands of vector
arithmetic are wrapped in `vec3<f32>(...)`.

Correctness model (same split as GN/OSL/GLSL):
- Headless, proven here: op-template coverage; structural validity
  (entry point, bindings, balanced braces, SSA declared-before-use,
  uniforms surfaced, faithful ripple chain).
- GPU-runtime checklist: `naga`/`tint` validates the WGSL (auto-runs
  when on PATH); a standalone wgpu run over a grid equals
  `evaluate(...)` — exact for noise-free, bit-exact for noise.
"""

from __future__ import annotations

from .._ir.eval_graph import SocketType

from ..backend.op_emitters import get_emitter
from ..frontend.parser import CompiledExpression

# ---------------------------------------------------------------------------
# Reference noise/voronoi in WGSL — mirrors evaluator/noise.py exactly.
# WGSL u32 == numpy uint32 (defined wraparound) -> bit parity.
# ---------------------------------------------------------------------------

WGSL_NOISE_LIB = r'''
// Reference value noise / voronoi — mirrors the numpy oracle
// (expressnode/evaluator/noise.py). WGSL u32 == numpy uint32: bit-exact.

fn cn_hash(a: u32, b: u32, c: u32, d: u32, e: u32) -> u32 {
    var h: u32 = 0x9E3779B1u;
    var p = array<u32, 5>(a, b, c, d, e);
    for (var i: i32 = 0; i < 5; i = i + 1) {
        h = (h ^ p[i]) * 0x85EBCA77u;
        h = h ^ (h >> 13u);
    }
    h = (h ^ (h >> 15u)) * 0xC2B2AE3Du;
    h = h ^ (h >> 13u);
    return h;
}

fn cn_h01(a: u32, b: u32, c: u32, d: u32, e: u32) -> f32 {
    return f32(cn_hash(a, b, c, d, e)) / 4294967296.0;
}

// Voronoi's feature points hash four values, like the oracle.
fn cn_h01_4(a: u32, b: u32, c: u32, d: u32) -> f32 {
    var h: u32 = 0x9E3779B1u;
    var p = array<u32, 4>(a, b, c, d);
    for (var i: i32 = 0; i < 4; i = i + 1) {
        h = (h ^ p[i]) * 0x85EBCA77u;
        h = h ^ (h >> 13u);
    }
    h = (h ^ (h >> 15u)) * 0xC2B2AE3Du;
    h = h ^ (h >> 13u);
    return f32(h) / 4294967296.0;
}

fn cn_fade(t: f32) -> f32 { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }

fn cn_slice(x: f32, y: f32, z: f32, iw: i32, seed: i32) -> f32 {
    let ix: i32 = i32(floor(x));
    let iy: i32 = i32(floor(y));
    let iz: i32 = i32(floor(z));
    let ux: f32 = cn_fade(x - f32(ix));
    let uy: f32 = cn_fade(y - f32(iy));
    let uz: f32 = cn_fade(z - f32(iz));
    let S: u32 = bitcast<u32>(seed);
    let W: u32 = bitcast<u32>(iw);
    let c000 = cn_h01(bitcast<u32>(ix),     bitcast<u32>(iy),     bitcast<u32>(iz),     S, W);
    let c100 = cn_h01(bitcast<u32>(ix + 1), bitcast<u32>(iy),     bitcast<u32>(iz),     S, W);
    let c010 = cn_h01(bitcast<u32>(ix),     bitcast<u32>(iy + 1), bitcast<u32>(iz),     S, W);
    let c110 = cn_h01(bitcast<u32>(ix + 1), bitcast<u32>(iy + 1), bitcast<u32>(iz),     S, W);
    let c001 = cn_h01(bitcast<u32>(ix),     bitcast<u32>(iy),     bitcast<u32>(iz + 1), S, W);
    let c101 = cn_h01(bitcast<u32>(ix + 1), bitcast<u32>(iy),     bitcast<u32>(iz + 1), S, W);
    let c011 = cn_h01(bitcast<u32>(ix),     bitcast<u32>(iy + 1), bitcast<u32>(iz + 1), S, W);
    let c111 = cn_h01(bitcast<u32>(ix + 1), bitcast<u32>(iy + 1), bitcast<u32>(iz + 1), S, W);
    let x00 = mix(c000, c100, ux);
    let x10 = mix(c010, c110, ux);
    let x01 = mix(c001, c101, ux);
    let x11 = mix(c011, c111, ux);
    return mix(mix(x00, x10, uy), mix(x01, x11, uy), uz);
}

fn cn_value_noise(p: vec3<f32>, w: f32, seed: i32) -> f32 {
    let iw: i32 = i32(floor(w));
    let fw: f32 = cn_fade(w - f32(iw));
    let a = cn_slice(p.x, p.y, p.z, iw, seed);
    let b = cn_slice(p.x, p.y, p.z, iw + 1, seed);
    return mix(a, b, fw);
}

fn cn_voronoi_f1(p: vec3<f32>, seed: i32) -> f32 {
    let bx: i32 = i32(floor(p.x));
    let by: i32 = i32(floor(p.y));
    let bz: i32 = i32(floor(p.z));
    var best: f32 = 1.0e30;
    let S: u32 = bitcast<u32>(seed);
    for (var dx: i32 = -1; dx <= 1; dx = dx + 1) {
    for (var dy: i32 = -1; dy <= 1; dy = dy + 1) {
    for (var dz: i32 = -1; dz <= 1; dz = dz + 1) {
        let cx: i32 = bx + dx;
        let cy: i32 = by + dy;
        let cz: i32 = bz + dz;
        let fx = cn_h01_4(bitcast<u32>(cx), bitcast<u32>(cy), bitcast<u32>(cz), S);
        let fy = cn_h01_4(bitcast<u32>(cy), bitcast<u32>(cz), bitcast<u32>(cx), S);
        let fz = cn_h01_4(bitcast<u32>(cz), bitcast<u32>(cx), bitcast<u32>(cy), S);
        let f = vec3<f32>(f32(cx) + fx, f32(cy) + fy, f32(cz) + fz);
        best = min(best, distance(p, f));
    }}}
    return best;
}
'''


# ---------------------------------------------------------------------------
# Op -> WGSL expression templates
# ---------------------------------------------------------------------------

def _wt(t: SocketType) -> str:
    return "vec3<f32>" if t == SocketType.VECTOR else "f32"


def _bin(sym):
    return lambda a, n: f"({a[0]} {sym} {a[1]})"


def _fn(name):
    return lambda a, n: f"{name}({', '.join(a)})"


def _cmp(sym):
    return lambda a, n: f"select(0.0, 1.0, {a[0]} {sym} {a[1]})"


def _flit(v) -> str:
    f = float(v)
    s = repr(f)
    if "." not in s and "e" not in s and "E" not in s and "inf" not in s:
        s += ".0"
    return s


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
    "math.mod": lambda a, n: f"({a[0]} - {a[1]} * floor({a[0]} / {a[1]}))",
    "math.pow": lambda a, n: f"pow({a[0]}, {a[1]})",
    "math.floordiv": lambda a, n: f"floor({a[0]} / {a[1]})",
    "math.neg": lambda a, n: f"(-({a[0]}))",
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
    "math.fract": lambda a, n: f"fract({a[0]})",
    "math.step": lambda a, n: f"step({a[0]}, {a[1]})",
    "math.ping_pong": lambda a, n: (
        f"abs((({a[0]}) - ({a[1]})) - 2.0 * ({a[1]}) * "
        f"floor((({a[0]}) - ({a[1]})) / (2.0 * ({a[1]}))) - ({a[1]}))"),
    "vec.add": _bin("+"), "vec.sub": _bin("-"),
    "vec.mul": _bin("*"), "vec.div": _bin("/"),
    "vec.mod": lambda a, n: f"({a[0]} - {a[1]} * floor({a[0]} / {a[1]}))",
    "vec.pow": lambda a, n: f"pow({a[0]}, {a[1]})",
    "vec.floordiv": lambda a, n: f"floor({a[0]} / {a[1]})",
    "vec.neg": lambda a, n: f"(-({a[0]}))",
    "vec.length": _fn("length"),
    "vec.dot": lambda a, n: f"dot({a[0]}, {a[1]})",
    "vec.cross": lambda a, n: f"cross({a[0]}, {a[1]})",
    "vec.normalize": _fn("normalize"),
    "vec.reflect": lambda a, n: f"reflect({a[0]}, {a[1]})",
    "vec.distance": lambda a, n: f"distance({a[0]}, {a[1]})",
    "vec.combine2": lambda a, n: f"vec3<f32>({a[0]}, {a[1]}, 0.0)",
    "vec.combine3": lambda a, n: f"vec3<f32>({a[0]}, {a[1]}, {a[2]})",
    "vec.combine4": lambda a, n: f"vec3<f32>({a[0]}, {a[1]}, {a[2]})",
    "vec.component.x": lambda a, n: f"({a[0]}).x",
    "vec.component.y": lambda a, n: f"({a[0]}).y",
    "vec.component.z": lambda a, n: f"({a[0]}).z",
    "vec.component.w": lambda a, n: f"({a[0]}).z",
    "compare.lt": _cmp("<"), "compare.le": _cmp("<="),
    "compare.gt": _cmp(">"), "compare.ge": _cmp(">="),
    "compare.eq": _cmp("=="), "compare.ne": _cmp("!="),
    "bool.and": lambda a, n: f"select(0.0, 1.0, ({a[0]} != 0.0) && ({a[1]} != 0.0))",
    "bool.or": lambda a, n: f"select(0.0, 1.0, ({a[0]} != 0.0) || ({a[1]} != 0.0))",
    "bool.not": lambda a, n: f"select(1.0, 0.0, {a[0]} != 0.0)",
    "flow.if": lambda a, n: f"select({a[2]}, {a[1]}, {a[0]} != 0.0)",
    "texture.noise": lambda a, n: (
        f"cn_value_noise(vec3<f32>({a[0]})"
        f"{(' * ' + a[1]) if len(a) > 1 else ''}, Time, Seed)"
    ),
    "texture.voronoi": lambda a, n: (
        f"cn_voronoi_f1(vec3<f32>({a[0]})"
        f"{(' * ' + a[1]) if len(a) > 1 else ''}, Seed)"
    ),
    "attr.read": lambda a, n: "0.0",
    "attr.write": lambda a, n: (a[0] if a else "0.0"),
    "obj.read": lambda a, n: "vec3<f32>(0.0, 0.0, 0.0)",
}


def _swizzle(a, n):
    pat = n.params.get("pattern", "xyz")
    comps = ", ".join(f"({a[0]}).{c if c != 'w' else 'z'}" for c in pat)
    return f"vec3<f32>({comps})" if len(pat) >= 2 else comps


_TEMPLATES["vec.swizzle"] = _swizzle


def wgsl_template_ops() -> set[str]:
    return set(_TEMPLATES)


_VEC_BINARY = {"vec.add", "vec.sub", "vec.mul", "vec.div",
               "vec.mod", "vec.pow", "vec.floordiv"}


def emit_wgsl(compiled: CompiledExpression, fn_name: str = "",
              workgroup_size: int = 64) -> str:
    """Return a complete WGSL compute shader: a per-point kernel over
    flat f32 buffers (positions in, N*3 results out)."""
    graph = compiled.graph
    name = fn_name or f"expr_{compiled.entry_function}"

    nid, rsock = graph.outputs["result"]
    rtype = graph.nodes[nid].output_type(rsock)
    ret = _wt(rtype)

    fparams = [(p.name, p.type.to_socket_type()) for p in compiled.parameters]
    sig = ["P: vec3<f32>", "N: vec3<f32>", "Time: f32", "Frame: f32",
           "DeltaTime: f32", "Seed: i32"]
    for pn, pt in fparams:
        sig.append(f"{pn}: {_wt(pt)}")

    body: list[str] = []
    var: dict[int, str] = {}
    gtype: dict[int, str] = {}
    used_noise = False

    def in_ref(node, sname):
        for e in graph.in_edges(node):
            if e.target_socket == sname:
                return e.source_node
        return None

    for node in graph.topological_order():
        em = get_emitter(node.op)
        if em is not None and em.kind == "param_only":
            var[node.id], gtype[node.id] = "0.0", "f32"
            continue
        if node.op == "input.parameter":
            pn = node.params["name"]
            var[node.id] = pn
            pm = next((p for p in compiled.parameters if p.name == pn), None)
            gtype[node.id] = (_wt(pm.type.to_socket_type())
                              if pm else "f32")
            continue
        tmpl = _TEMPLATES.get(node.op)
        if tmpl is None:
            raise KeyError(
                f"no WGSL template for op {node.op!r} (add it to "
                f"backend/wgsl.py)"
            )
        if node.op in ("texture.noise", "texture.voronoi"):
            used_noise = True
        args, atypes = [], []
        for sn, _ in node.input_sockets:
            src = in_ref(node, sn)
            if src is None:
                args.append("0.0")
                atypes.append("f32")
            else:
                args.append(var[src])
                atypes.append(gtype[src])
        if node.op in _VEC_BINARY:
            args = [f"vec3<f32>({a})" if t == "f32" else a
                    for a, t in zip(args, atypes)]
        expr = tmpl(args, node)
        out_t = _wt(node.output_type(node.output_sockets[0][0]))
        vname = f"v{node.id}"
        body.append(f"    let {vname}: {out_t} = {expr};")
        var[node.id], gtype[node.id] = vname, out_t

    body.append(f"    return {var[nid]};")
    lib = WGSL_NOISE_LIB if used_noise else ""

    # Uniform block: Time/Frame/DeltaTime + Seed + scalar params.
    uni_fields = ["    Time: f32,", "    Frame: f32,",
                  "    DeltaTime: f32,", "    Seed: i32,"]
    for pn, pt in fparams:
        if pt == SocketType.VECTOR:
            uni_fields.append(f"    {pn}: vec3<f32>,")
        else:
            uni_fields.append(f"    {pn}: f32,")

    call = ["P", "N", "U.Time", "U.Frame", "U.DeltaTime", "U.Seed"] + \
           [f"U.{pn}" for pn, _ in fparams]
    call_s = f"{name}({', '.join(call)})"
    if ret == "vec3<f32>":
        write = (f"    out_R[3u*i+0u] = r.x;\n"
                 f"    out_R[3u*i+1u] = r.y;\n"
                 f"    out_R[3u*i+2u] = r.z;")
    else:
        write = (f"    out_R[3u*i+0u] = r;\n"
                 f"    out_R[3u*i+1u] = 0.0;\n"
                 f"    out_R[3u*i+2u] = 0.0;")

    return (
        "// generated by expressnode — WGSL compute backend\n"
        f"{lib}\n"
        f"fn {name}({', '.join(sig)}) -> {ret} {{\n"
        + "\n".join(body) + "\n}\n\n"
        "struct Uniforms {\n" + "\n".join(uni_fields) + "\n}\n\n"
        "@group(0) @binding(0) var<storage, read> in_P: array<f32>;\n"
        "@group(0) @binding(1) var<storage, read_write> out_R: array<f32>;\n"
        "@group(0) @binding(2) var<uniform> U: Uniforms;\n\n"
        f"@compute @workgroup_size({workgroup_size})\n"
        "fn main(@builtin(global_invocation_id) gid: vec3<u32>) {\n"
        "    let i: u32 = gid.x;\n"
        "    let n: u32 = arrayLength(&in_P) / 3u;\n"
        "    if (i >= n) { return; }\n"
        "    let P: vec3<f32> = vec3<f32>(in_P[3u*i+0u], in_P[3u*i+1u], "
        "in_P[3u*i+2u]);\n"
        "    let N: vec3<f32> = vec3<f32>(0.0, 0.0, 1.0);\n"
        f"    let r = {call_s};\n"
        f"{write}\n"
        "}\n"
    )
