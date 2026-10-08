"""Op emitter registry: maps each EvalGraph op the frontend can produce to
a description of the Blender Geometry Nodes node(s) it becomes.

This is **pure data** — no `bpy`. The headless tests assert that every op
the frontend can emit has a registered emitter, so we know the coverage
is complete before any Blender run. The bpy executor (gn_executor.py)
reads these descriptors to build real nodes.

`kind`:
    simple     1:1 mapping; the executor instantiates `bl_idname`,
               applies `settings`, wires inputs in declared order, reads
               `output`.
    complex    needs hand-written executor logic (multi-node expansion or
               dynamic settings). Registered so coverage is provable;
               correctness verified in Blender.
    interface  not a node — becomes a Group Input socket (user parameters).
    param_only never emitted as a node; consumed via params (e.g. the
               string literal inside attr()/obj()).
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field

from ..frontend.builtins import BUILTIN_FNS, BUILTIN_VARS


@dataclass(frozen=True)
class OpEmitter:
    op: str
    bl_idname: str
    settings: dict = _dc_field(default_factory=dict)
    output: object = 0                  # output socket name or index
    kind: str = "simple"
    note: str = ""


def _math(op: str, operation: str) -> OpEmitter:
    return OpEmitter(op, "ShaderNodeMath", {"operation": operation},
                     output="Value")


def _vmath(op: str, operation: str, out: str = "Vector") -> OpEmitter:
    return OpEmitter(op, "ShaderNodeVectorMath", {"operation": operation},
                     output=out)


_EMITTERS: dict[str, OpEmitter] = {}


def _reg(e: OpEmitter) -> None:
    _EMITTERS[e.op] = e


# --- inputs ---
_reg(OpEmitter("input.position", "GeometryNodeInputPosition", output="Position"))
_reg(OpEmitter("input.normal", "GeometryNodeInputNormal", output="Normal"))
_reg(OpEmitter("input.index", "GeometryNodeInputIndex", output="Index"))
_reg(OpEmitter("input.scene_time", "GeometryNodeInputSceneTime",
               output="Seconds"))
_reg(OpEmitter("input.frame", "GeometryNodeInputSceneTime", output="Frame",
               note="same node as scene_time, reads the Frame output"))
_reg(OpEmitter("input.delta_time", "GeometryNodeInputSceneTime",
               output="Seconds", kind="complex",
               note="no native delta-time node; approximate via frame step"))
_reg(OpEmitter("input.parameter", "", kind="interface",
               note="exposed as a Group Input socket on the root tree"))

# --- constants ---
_reg(OpEmitter("constant.float", "ShaderNodeValue", output="Value",
               kind="complex", note="set outputs[0].default_value"))
_reg(OpEmitter("constant.int", "ShaderNodeValue", output="Value",
               kind="complex", note="int surfaced as a float Value node"))
_reg(OpEmitter("constant.bool", "ShaderNodeValue", output="Value",
               kind="complex", note="bool surfaced as 0.0/1.0 Value node"))
_reg(OpEmitter("constant.string", "", kind="param_only",
               note="string literals are consumed via params, never wired"))

# --- scalar arithmetic ---
_reg(_math("math.add", "ADD"))
_reg(_math("math.sub", "SUBTRACT"))
_reg(_math("math.mul", "MULTIPLY"))
_reg(_math("math.div", "DIVIDE"))
_reg(OpEmitter("math.mod", "ShaderNodeMath", {"operation": "FLOORED_MODULO"},
               output="Value", note="floored, like Python's %"))
_reg(_math("math.pow", "POWER"))
_reg(OpEmitter("math.floordiv", "ShaderNodeMath", {"operation": "DIVIDE"},
               output="Value", kind="complex",
               note="DIVIDE then FLOOR — two nodes"))
_reg(_math("math.neg", "MULTIPLY"))  # neg = * -1; executor sets the -1 input

# --- scalar math functions ---
_reg(_math("math.sin", "SINE"))
_reg(_math("math.cos", "COSINE"))
_reg(_math("math.tan", "TANGENT"))
_reg(_math("math.asin", "ARCSINE"))
_reg(_math("math.acos", "ARCCOSINE"))
_reg(_math("math.atan", "ARCTANGENT"))
_reg(_math("math.atan2", "ARCTAN2"))
_reg(_math("math.sqrt", "SQRT"))
_reg(_math("math.exp", "EXPONENT"))
_reg(_math("math.log", "LOGARITHM"))
_reg(_math("math.abs", "ABSOLUTE"))
_reg(_math("math.floor", "FLOOR"))
_reg(_math("math.ceil", "CEIL"))
_reg(_math("math.round", "ROUND"))
_reg(_math("math.sign", "SIGN"))
_reg(_math("math.min", "MINIMUM"))
_reg(_math("math.max", "MAXIMUM"))
_reg(OpEmitter("math.clamp", "ShaderNodeClamp", output="Result",
               kind="complex", note="Clamp node; Min/Max from inputs"))
_reg(OpEmitter("math.mix", "ShaderNodeMix",
               {"data_type": "FLOAT"}, output="Result",
               kind="complex", note="Mix node, FLOAT or VECTOR by arg type"))
_reg(OpEmitter("math.smoothstep", "ShaderNodeMapRange",
               {"interpolation_type": "SMOOTHSTEP"}, output="Result",
               kind="complex", note="Map Range smoothstep emulation"))
_reg(_math("math.fract", "FRACT"))
_reg(OpEmitter("math.step", "ShaderNodeMath", {"operation": "GREATER_THAN"},
               output="Value", kind="complex",
               note="1 - LESS_THAN(x, edge): x >= edge"))
_reg(_math("math.ping_pong", "PINGPONG"))

# --- vector ops ---
_reg(_vmath("vec.add", "ADD"))
_reg(_vmath("vec.sub", "SUBTRACT"))
_reg(_vmath("vec.mul", "MULTIPLY"))
_reg(_vmath("vec.div", "DIVIDE"))
_reg(OpEmitter("vec.mod", "ShaderNodeVectorMath", {"operation": "DIVIDE"},
               output="Vector", kind="complex",
               note="floored a - b*floor(a/b); Vector Math Modulo is fmod"))
_reg(_vmath("vec.pow", "POWER"))
_reg(OpEmitter("vec.floordiv", "ShaderNodeVectorMath",
               {"operation": "DIVIDE"}, output="Vector", kind="complex"))
_reg(_vmath("vec.neg", "SCALE"))   # scale by -1; executor sets factor
_reg(_vmath("vec.length", "LENGTH", out="Value"))
_reg(_vmath("vec.dot", "DOT_PRODUCT", out="Value"))
_reg(_vmath("vec.cross", "CROSS_PRODUCT"))
_reg(_vmath("vec.normalize", "NORMALIZE"))
_reg(OpEmitter("vec.reflect", "ShaderNodeVectorMath",
               {"operation": "DOT_PRODUCT"}, output="Vector", kind="complex",
               note="v - 2 dot(v,n) n; Vector Math Reflect normalizes n"))
_reg(_vmath("vec.distance", "DISTANCE", out="Value"))

# --- vector construction / access ---
_reg(OpEmitter("vec.combine3", "ShaderNodeCombineXYZ", output="Vector"))
_reg(OpEmitter("vec.combine2", "ShaderNodeCombineXYZ", output="Vector",
               kind="complex", note="CombineXYZ with Z=0"))
_reg(OpEmitter("vec.combine4", "ShaderNodeCombineXYZ", output="Vector",
               kind="complex", note="vec4 surfaced as vec3 (w dropped)"))
_reg(OpEmitter("vec.component.x", "ShaderNodeSeparateXYZ", output="X"))
_reg(OpEmitter("vec.component.y", "ShaderNodeSeparateXYZ", output="Y"))
_reg(OpEmitter("vec.component.z", "ShaderNodeSeparateXYZ", output="Z"))
_reg(OpEmitter("vec.component.w", "ShaderNodeSeparateXYZ", output="Z",
               kind="complex", note="vec3 has no w; treated as z"))
_reg(OpEmitter("vec.swizzle", "", kind="complex",
               note="SeparateXYZ + CombineXYZ wired per .pattern param"))

# --- comparisons ---
_reg(_math("compare.lt", "LESS_THAN"))
_reg(_math("compare.gt", "GREATER_THAN"))
_reg(OpEmitter("compare.le", "ShaderNodeMath", {"operation": "GREATER_THAN"},
               output="Value", kind="complex", note="not greater-than"))
_reg(OpEmitter("compare.ge", "ShaderNodeMath", {"operation": "LESS_THAN"},
               output="Value", kind="complex", note="not less-than"))
_reg(OpEmitter("compare.eq", "ShaderNodeMath", {"operation": "COMPARE"},
               output="Value", kind="complex", note="COMPARE with epsilon"))
_reg(OpEmitter("compare.ne", "ShaderNodeMath", {"operation": "COMPARE"},
               output="Value", kind="complex", note="not (COMPARE)"))

# --- boolean ---
_reg(OpEmitter("bool.and", "FunctionNodeBooleanMath",
               {"operation": "AND"}, output="Boolean"))
_reg(OpEmitter("bool.or", "FunctionNodeBooleanMath",
               {"operation": "OR"}, output="Boolean"))
_reg(OpEmitter("bool.not", "FunctionNodeBooleanMath",
               {"operation": "NOT"}, output="Boolean"))

# --- control flow ---
_reg(OpEmitter("flow.if", "GeometryNodeSwitch", output="Output",
               kind="complex",
               note="Switch node; input_type set from the branch socket"))

# --- procedural textures ---
_reg(OpEmitter("texture.noise", "ShaderNodeTexNoise", output="Fac",
               kind="complex", note="4D noise; Vector + W(time) wiring"))
_reg(OpEmitter("texture.voronoi", "ShaderNodeTexVoronoi",
               output="Distance", kind="complex"))

# --- Blender access ---
_reg(OpEmitter("attr.read", "GeometryNodeInputNamedAttribute",
               output="Attribute", kind="complex",
               note="data_type + name from params"))
_reg(OpEmitter("attr.write", "GeometryNodeStoreNamedAttribute",
               output="Geometry", kind="complex",
               note="threads geometry; handled at modifier level"))
_reg(OpEmitter("obj.read", "GeometryNodeObjectInfo", output="Location",
               kind="complex", note="object + field from params"))

# --- modifier wrapper (backend-only; not frontend-emittable) ---
_reg(OpEmitter("modifier.set_position", "GeometryNodeSetPosition",
               output="Geometry", kind="complex",
               note="apply-mode wrapper: Offset or Position from Result"))

# Ops the backend adds for the modifier wrapper, never produced by the
# frontend. Kept separate so the frontend-coverage test stays exact.
BACKEND_ONLY_OPS = frozenset({"modifier.set_position"})


# ---------------------------------------------------------------------------
# Coverage helpers
# ---------------------------------------------------------------------------

def all_emitter_ops() -> set[str]:
    return set(_EMITTERS)


def get_emitter(op: str) -> OpEmitter | None:
    return _EMITTERS.get(op)


def frontend_op_universe() -> set[str]:
    """Every op name the frontend can possibly emit. Derived from the
    builtin registry plus the structural ops the parser emits directly,
    so a coverage test can prove the emitter table is complete."""
    ops: set[str] = set()

    # Built-in variables.
    for bv in BUILTIN_VARS.values():
        ops.add(bv.op)
    ops.add("input.parameter")

    # Built-in functions.
    for fn in BUILTIN_FNS.values():
        if fn.op_name:
            ops.add(fn.op_name)

    # Constants.
    ops |= {"constant.float", "constant.int",
            "constant.bool", "constant.string"}

    # BinOp / UnaryOp — scalar and vector variants.
    for base in ("add", "sub", "mul", "div", "floordiv", "mod", "pow"):
        ops.add(f"math.{base}")
        ops.add(f"vec.{base}")
    ops |= {"math.neg", "vec.neg"}

    # Comparisons, boolean, conditional.
    ops |= {f"compare.{c}" for c in ("eq", "ne", "lt", "le", "gt", "ge")}
    ops |= {"bool.and", "bool.or", "bool.not", "flow.if"}

    # Vector component access + swizzle.
    ops |= {f"vec.component.{c}" for c in ("x", "y", "z", "w")}
    ops.add("vec.swizzle")

    return ops
