"""The evaluate() API contract — defaults, shapes, the EvalResult, and
the oracle role for other backends."""

import numpy as np
import pytest

from expressnode import compile, evaluate
from expressnode.evaluator import EvalResult


def test_no_P_gives_single_point():
    r = evaluate(compile("def f(): return 1.0"))
    assert isinstance(r, EvalResult)
    assert float(r.values) == pytest.approx(1.0)


def test_1d_P_is_promoted():
    c = compile("def f(P): return P.x")
    r = evaluate(c, P=np.array([2.0, 0.0, 0.0])).values
    assert float(np.asarray(r).reshape(-1)[0]) == pytest.approx(2.0)


def test_result_shape_scalar_vs_vector():
    Pn = np.zeros((5, 3))
    s = evaluate(compile("def f(P): return P.x"), P=Pn).values
    v = evaluate(compile("def f(P): return P + vec3(1.0,0.0,0.0)"),
                 P=Pn).values
    assert s.shape == (5,)
    assert v.shape == (5, 3)


def test_normals_default_is_unit_or_z():
    c = compile("def f(N): return length(N)")
    P = np.random.RandomState(0).uniform(-2, 2, (10, 3))
    r = evaluate(c, P=P).values
    np.testing.assert_allclose(r, np.ones(10), atol=1e-9)
    # origin -> +Z fallback, still unit length
    r0 = evaluate(c, P=np.zeros((3, 3))).values
    np.testing.assert_allclose(r0, np.ones(3), atol=1e-9)


def test_attributes_passed_in_are_used():
    c = compile("def f(): return attr('h') * 2.0")
    P = np.zeros((4, 3))
    r = evaluate(c, P=P, attributes={"h": np.array([1.0, 2.0, 3.0, 4.0])})
    np.testing.assert_allclose(r.values, [2.0, 4.0, 6.0, 8.0], atol=1e-12)


def test_objects_passed_in_are_used():
    c = compile("def f(): return obj('Cube', 'position')")
    P = np.zeros((2, 3))
    r = evaluate(c, P=P, objects={"Cube": {"position": (1.0, 2.0, 3.0)}})
    np.testing.assert_allclose(r.values[0], [1.0, 2.0, 3.0], atol=1e-12)


def test_evalresult_is_array_like():
    r = evaluate(compile("def f(): return 3.0"))
    assert float(np.asarray(r)) == pytest.approx(3.0)


def test_core_imports_without_numpy_guard_present():
    """The top-level package exposes evaluate when numpy is available
    (it is in tests) but the guard keeps the core importable without it."""
    import expressnode
    assert "evaluate" in expressnode.__all__
