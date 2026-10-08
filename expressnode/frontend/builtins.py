"""Built-in variables and functions exposed to user expressions.

Each entry describes how a built-in name lowers to one or more EvalGraph
ops. The parser consults this registry when it encounters a name or call
that isn't user-defined.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Callable

from ..frontend.types import TypeKind


# ---------------------------------------------------------------------------
# Built-in variables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuiltinVar:
    """A built-in variable like P, N, t. Lowers to a single EvalNode whose
    op tells the backend which Blender input to wire up."""
    name: str
    op: str               # the EvalGraph op identifier
    type: TypeKind
    description: str = ""


BUILTIN_VARS: dict[str, BuiltinVar] = {
    "P": BuiltinVar("P", "input.position", TypeKind.VEC3,
                    "Vertex position (vec3)"),
    "N": BuiltinVar("N", "input.normal", TypeKind.VEC3,
                    "Vertex normal (vec3)"),
    "i": BuiltinVar("i", "input.index", TypeKind.INT,
                    "Point index (int)"),
    "t": BuiltinVar("t", "input.scene_time", TypeKind.FLOAT,
                    "Scene time in seconds (float)"),
    "frame": BuiltinVar("frame", "input.frame", TypeKind.INT,
                        "Current scene frame (int)"),
    "dt": BuiltinVar("dt", "input.delta_time", TypeKind.FLOAT,
                     "Frame delta time (float)"),
}


# ---------------------------------------------------------------------------
# Built-in functions
# ---------------------------------------------------------------------------

@dataclass
class BuiltinFn:
    """A built-in function. The signature is a list of allowed argument-type
    tuples; the return type is determined by the matched signature.
    Lowers to an EvalGraph op of `op_name`."""
    name: str
    op_name: str
    # Each signature is (arg_types_tuple, return_type). The parser picks the
    # first matching signature.
    signatures: list[tuple[tuple[TypeKind, ...], TypeKind]]
    # Optional reducer for variadic-style ops (e.g. `min(a, b, c, ...)`).
    variadic: bool = False
    description: str = ""

    def match(self, arg_types: tuple[TypeKind, ...]) -> TypeKind | None:
        for sig_types, ret in self.signatures:
            if self.variadic:
                if len(arg_types) >= len(sig_types) and all(
                    a == sig_types[min(i, len(sig_types) - 1)]
                    for i, a in enumerate(arg_types)
                ):
                    return ret
            else:
                if len(arg_types) != len(sig_types):
                    continue
                if all(a == s or _coerces(a, s) for a, s in zip(arg_types, sig_types)):
                    return ret
        return None


def _coerces(a: TypeKind, target: TypeKind) -> bool:
    """Allowed implicit coercions."""
    # int promotes to float
    if a == TypeKind.INT and target == TypeKind.FLOAT:
        return True
    # bool promotes to int and float
    if a == TypeKind.BOOL and target in (TypeKind.INT, TypeKind.FLOAT):
        return True
    return False


F = TypeKind.FLOAT
I = TypeKind.INT
V2 = TypeKind.VEC2
V3 = TypeKind.VEC3
V4 = TypeKind.VEC4
B = TypeKind.BOOL


def _scalar_unary(name: str, op: str) -> BuiltinFn:
    return BuiltinFn(name=name, op_name=op, signatures=[((F,), F)])


def _scalar_binary(name: str, op: str) -> BuiltinFn:
    return BuiltinFn(name=name, op_name=op,
                     signatures=[((F, F), F)])


BUILTIN_FNS: dict[str, BuiltinFn] = {
    # --- trig & scalar math ---
    "sin": _scalar_unary("sin", "math.sin"),
    "cos": _scalar_unary("cos", "math.cos"),
    "tan": _scalar_unary("tan", "math.tan"),
    "asin": _scalar_unary("asin", "math.asin"),
    "acos": _scalar_unary("acos", "math.acos"),
    "atan": _scalar_unary("atan", "math.atan"),
    "atan2": _scalar_binary("atan2", "math.atan2"),
    "sqrt": _scalar_unary("sqrt", "math.sqrt"),
    "exp": _scalar_unary("exp", "math.exp"),
    "log": _scalar_unary("log", "math.log"),
    "pow": _scalar_binary("pow", "math.pow"),
    "abs": BuiltinFn("abs", "math.abs",
                     signatures=[((F,), F), ((I,), I), ((V3,), V3)]),
    "floor": _scalar_unary("floor", "math.floor"),
    "ceil": _scalar_unary("ceil", "math.ceil"),
    "round": _scalar_unary("round", "math.round"),
    "mod": _scalar_binary("mod", "math.mod"),
    "sign": _scalar_unary("sign", "math.sign"),
    "min": BuiltinFn("min", "math.min",
                     signatures=[((F, F), F), ((I, I), I)],
                     variadic=True),
    "max": BuiltinFn("max", "math.max",
                     signatures=[((F, F), F), ((I, I), I)],
                     variadic=True),
    "clamp": BuiltinFn("clamp", "math.clamp",
                       signatures=[((F, F, F), F)]),
    "mix": BuiltinFn("mix", "math.mix",
                     signatures=[((F, F, F), F),
                                 ((V3, V3, F), V3)]),
    "smoothstep": BuiltinFn("smoothstep", "math.smoothstep",
                            signatures=[((F, F, F), F)]),
    "fract": _scalar_unary("fract", "math.fract"),
    "step": _scalar_binary("step", "math.step"),
    "ping_pong": _scalar_binary("ping_pong", "math.ping_pong"),

    # --- procedural ---
    "noise": BuiltinFn(
        "noise", "texture.noise",
        signatures=[((V3,), F), ((V3, F), F)],
    ),
    "voronoi": BuiltinFn(
        "voronoi", "texture.voronoi",
        signatures=[((V3,), F), ((V3, F), F)],
    ),

    # --- vector ops ---
    "length": BuiltinFn("length", "vec.length",
                        signatures=[((V2,), F), ((V3,), F), ((V4,), F)]),
    "dot": BuiltinFn("dot", "vec.dot",
                     signatures=[((V3, V3), F), ((V2, V2), F), ((V4, V4), F)]),
    "cross": BuiltinFn("cross", "vec.cross",
                       signatures=[((V3, V3), V3)]),
    "normalize": BuiltinFn("normalize", "vec.normalize",
                           signatures=[((V2,), V2), ((V3,), V3), ((V4,), V4)]),
    "reflect": BuiltinFn("reflect", "vec.reflect",
                         signatures=[((V3, V3), V3)]),
    "distance": BuiltinFn("distance", "vec.distance",
                          signatures=[((V3, V3), F)]),

    # --- vector constructors ---
    "vec2": BuiltinFn("vec2", "vec.combine2",
                      signatures=[((F, F), V2)]),
    "vec3": BuiltinFn("vec3", "vec.combine3",
                      signatures=[((F, F, F), V3),
                                  ((I, I, I), V3),
                                  ((F, F, I), V3),
                                  ((F, I, F), V3),
                                  ((I, F, F), V3),
                                  ((F, I, I), V3),
                                  ((I, F, I), V3),
                                  ((I, I, F), V3)]),
    "vec4": BuiltinFn("vec4", "vec.combine4",
                      signatures=[((F, F, F, F), V4)]),

    # --- Blender access ---
    # attr("name") and attr("name", "dtype") - return type known after-the-fact;
    # parser uses the second arg's literal value (if present) to choose.
    # Signature here is a fallback; parser handles attr specially.
    "attr": BuiltinFn(
        "attr", "attr.read",
        signatures=[],  # parser dispatches specially based on string literal
    ),
    "set_attr": BuiltinFn(
        "set_attr", "attr.write",
        signatures=[],
    ),
    "obj": BuiltinFn(
        "obj", "obj.read",
        signatures=[],
    ),
}


# Names of functions that are special-cased by the parser (because their
# return type depends on a literal argument value, not just types).
SPECIAL_FUNCTIONS = frozenset({"attr", "set_attr", "obj"})
