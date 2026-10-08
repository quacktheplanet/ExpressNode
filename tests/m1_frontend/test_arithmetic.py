"""Arithmetic ops: add/sub/mul/div/mod/pow with scalar and vector types."""

import pytest

from expressnode import CompileError, compile


def _ops(c):
    return [n.op for n in c.graph.nodes.values()]


def test_scalar_add_emits_math_add():
    c = compile("def f(): return 1.0 + 2.0")
    assert "math.add" in _ops(c)


def test_scalar_mul_emits_math_mul():
    c = compile("def f(): return 1.0 * 2.0")
    assert "math.mul" in _ops(c)


def test_vector_arithmetic_uses_vec_ops():
    c = compile(
        "def f():\n"
        "    return vec3(1.0, 0.0, 0.0) + vec3(0.0, 1.0, 0.0)\n"
    )
    assert "vec.add" in _ops(c)


def test_vector_scalar_mul_uses_vec_mul():
    """vec3 * scalar broadcasts; the parser still uses vec.mul because the
    result type is a vector. The backend handles broadcasting."""
    c = compile(
        "def f():\n"
        "    return vec3(1.0, 1.0, 1.0) * 0.5\n"
    )
    assert "vec.mul" in _ops(c)


def test_negation_emits_neg():
    c = compile("def f(): return -3.0")
    assert "math.neg" in _ops(c)


def test_power_emits_math_pow():
    c = compile("def f(): return 2.0 ** 3.0")
    assert "math.pow" in _ops(c)


def test_modulo_emits_math_mod():
    c = compile("def f(): return 5.0 % 2.0")
    assert "math.mod" in _ops(c)


def test_vector_vector_arity_mismatch_rejected():
    with pytest.raises(CompileError, match="Vector arity mismatch"):
        compile(
            "def f():\n"
            "    return vec3(1.0, 1.0, 1.0) + vec2(0.0, 0.0)\n"
        )


def test_mixed_int_float_promotes_to_float():
    c = compile("def f(): return 1 + 2.0")
    assert c.return_type.value == "float"
