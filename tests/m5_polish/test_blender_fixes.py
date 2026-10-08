"""Headless guards for bugs found by the Blender verification run.

Each of these failed in real Blender before the fix; see
tests/blender/ for the in-Blender checks that found them.
"""

import numpy as np
import pytest

from expressnode import compile, evaluate, osl_source
from expressnode.backend.op_emitters import all_emitter_ops, get_emitter
from expressnode.frontend.errors import CompileError

# Operation enums of Blender 5.0/5.1's Math and Vector Math nodes.
BLENDER_MATH_OPS = {
    "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "MULTIPLY_ADD", "POWER",
    "LOGARITHM", "SQRT", "INVERSE_SQRT", "ABSOLUTE", "EXPONENT", "MINIMUM",
    "MAXIMUM", "LESS_THAN", "GREATER_THAN", "SIGN", "COMPARE", "SMOOTH_MIN",
    "SMOOTH_MAX", "ROUND", "FLOOR", "CEIL", "TRUNC", "FRACT", "MODULO",
    "FLOORED_MODULO", "WRAP", "SNAP", "PINGPONG", "SINE", "COSINE",
    "TANGENT", "ARCSINE", "ARCCOSINE", "ARCTANGENT", "ARCTAN2", "SINH",
    "COSH", "TANH", "RADIANS", "DEGREES"}
BLENDER_VMATH_OPS = {
    "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "MULTIPLY_ADD", "CROSS_PRODUCT",
    "PROJECT", "REFLECT", "REFRACT", "FACEFORWARD", "DOT_PRODUCT",
    "DISTANCE", "LENGTH", "SCALE", "NORMALIZE", "ABSOLUTE", "POWER", "SIGN",
    "MINIMUM", "MAXIMUM", "FLOOR", "CEIL", "FRACTION", "MODULO", "WRAP",
    "SNAP", "SINE", "COSINE", "TANGENT"}


def test_emitter_operations_exist_in_blender():
    for op in all_emitter_ops():
        e = get_emitter(op)
        operation = e.settings.get("operation")
        if operation is None:
            continue
        valid = (BLENDER_MATH_OPS if e.bl_idname == "ShaderNodeMath"
                 else BLENDER_VMATH_OPS if e.bl_idname == "ShaderNodeVectorMath"
                 else None)
        if valid is not None:
            assert operation in valid, (op, operation)


def test_modulo_is_floored_like_python():
    assert get_emitter("math.mod").settings["operation"] == "FLOORED_MODULO"
    assert get_emitter("vec.mod").kind == "complex"   # expanded, not fmod


P = np.array([[1.3, 0, 0], [-0.7, 0, 0], [0.5, 0, 0], [0.2, 0, 0],
              [0.0, 0, 0]])


def _eval(expr):
    return evaluate(compile(f"def f(P):\n    return {expr}\n"), P=P).values


def test_oracle_fract_step_ping_pong_round():
    assert np.allclose(_eval("fract(P.x)"), [0.3, 0.3, 0.5, 0.2, 0.0])
    assert np.allclose(_eval("step(0.2, P.x)"), [1, 0, 1, 1, 0])
    # Blender's Ping-Pong: 0 at 0, scale at scale
    assert np.allclose(_eval("ping_pong(P.x, 0.5)"), [0.3, 0.3, 0.5, 0.2, 0.0])
    # half up, like Blender's Round
    assert np.allclose(_eval("round(P.x)"), [1, -1, 1, 0, 0])


def test_osl_indexes_names_not_expressions():
    src = osl_source("def f(P):\n    return vec3(P.x, P.zy.x, 0.0) + P.zyx\n")
    assert ")[" not in src
    two = osl_source("def f(P):\n    v = vec2(P.x, P.y)\n    return vec3(v.y, 0.0, 0.0) + P.xy.xyy\n")
    assert ")[" not in two


def test_osl_hash_emulates_uint32():
    src = osl_source("def f(P):\n    return vec3(voronoi(P), noise(P), 0.0)\n")
    assert "cn_srl" in src and "cn_h01_4(" in src


def test_string_in_arithmetic_is_a_located_compile_error():
    with pytest.raises(CompileError) as e:
        compile("def f(P):\n    return P.x + 'a'\n")
    assert e.value.span is not None
    assert "Text can't be used" in str(e.value)
