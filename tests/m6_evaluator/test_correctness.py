"""The keystone: the evaluator computes the *right numbers*, proven
against hand-written numpy. This closes the gap that structural tests
alone leave open."""

from pathlib import Path

import numpy as np
import pytest

from expressnode import compile, evaluate

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _P(n=11, seed=0):
    return np.random.RandomState(seed).uniform(-3.0, 3.0, size=(n, 3))


def test_constant():
    r = evaluate(compile("def f(): return 2.5")).values
    assert float(r) == pytest.approx(2.5)


def test_scalar_arithmetic():
    r = evaluate(compile("def f(): return (1.0 + 2.0) * 4.0 - 3.0")).values
    assert float(r) == pytest.approx((1 + 2) * 4 - 3)


def test_position_component_and_sin():
    c = compile("def f(P): return sin(P.x * 2.0)")
    P = _P()
    r = evaluate(c, P=P).values
    np.testing.assert_allclose(r, np.sin(P[:, 0] * 2.0), atol=1e-12)


def test_ripple_exactly_matches_reference():
    c = compile((EXAMPLES / "ripple.py").read_text())
    P, t = _P(13, 1), 0.37
    r = evaluate(c, P=P, t=t).values
    expect = np.zeros((13, 3))
    expect[:, 2] = np.sin(P[:, 0] * 6.0 + t) * 0.3
    np.testing.assert_allclose(r, expect, atol=1e-12)


def test_ripple_parameter_override():
    c = compile((EXAMPLES / "ripple.py").read_text())
    P, t = _P(9, 2), 1.1
    r = evaluate(c, P=P, t=t, params={"freq": 12.0, "amp": 0.5}).values
    expect = np.zeros((9, 3))
    expect[:, 2] = np.sin(P[:, 0] * 12.0 + t) * 0.5
    np.testing.assert_allclose(r, expect, atol=1e-12)


def test_default_parameters_are_used():
    c = compile("def f(a=4.0): return a * 2.0")
    assert float(evaluate(c).values) == pytest.approx(8.0)
    assert float(evaluate(c, params={"a": 5.0}).values) == pytest.approx(10.0)


def test_user_function_inlined_numerically():
    c = compile(
        "def sq(x):\n    return x * x\n"
        "def cube(x):\n    return sq(x) * x\n"
        "def main():\n    return cube(3.0)\n"
    )
    assert float(evaluate(c).values) == pytest.approx(27.0)


def test_vector_math():
    c = compile(
        "def f():\n"
        "    a = vec3(1.0, 2.0, 3.0)\n"
        "    b = vec3(4.0, 5.0, 6.0)\n"
        "    return cross(a, b) + a\n"
    )
    r = evaluate(c).values
    expect = np.cross([1, 2, 3], [4, 5, 6]) + np.array([1, 2, 3])
    np.testing.assert_allclose(r.reshape(3), expect, atol=1e-12)


def test_dot_and_length():
    c = compile(
        "def f(P):\n"
        "    return dot(P, P) - length(P) * length(P)\n"
    )
    P = _P()
    r = evaluate(c, P=P).values
    np.testing.assert_allclose(r, np.zeros(len(P)), atol=1e-9)


def test_conditional_expression():
    c = compile("def f(x=1.0): return 10.0 if x > 0.0 else -10.0")
    assert float(evaluate(c, params={"x": 2.0}).values) == pytest.approx(10.0)
    assert float(evaluate(c, params={"x": -2.0}).values) == pytest.approx(-10.0)


def test_clamp_mix_smoothstep():
    c = compile(
        "def f(x=0.5):\n"
        "    return clamp(mix(0.0, 10.0, x), 2.0, 7.0)\n"
    )
    # mix(0,10,0.5)=5 -> clamp to [2,7] -> 5
    assert float(evaluate(c, params={"x": 0.5}).values) == pytest.approx(5.0)
    # mix(0,10,0.9)=9 -> clamp -> 7
    assert float(evaluate(c, params={"x": 0.9}).values) == pytest.approx(7.0)


def test_set_attr_is_recorded():
    c = compile(
        "def f(P):\n"
        "    set_attr('mask', length(P))\n"
        "    return P\n"
    )
    P = _P()
    res = evaluate(c, P=P)
    assert "mask" in res.written_attributes
    np.testing.assert_allclose(
        res.written_attributes["mask"], np.linalg.norm(P, axis=-1), atol=1e-9
    )
