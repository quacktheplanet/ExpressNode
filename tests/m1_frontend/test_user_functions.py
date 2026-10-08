"""User-defined function inlining and scope handling."""

import pytest

from expressnode import CompileError, compile


def _ops(c):
    return [n.op for n in c.graph.nodes.values()]


def test_user_function_inlines():
    c = compile(
        "def helper(x):\n"
        "    return x * 2.0\n"
        "\n"
        "def main():\n"
        "    return helper(3.0)\n"
    )
    # helper's body should be inlined: a mul of 3.0 and 2.0.
    assert "math.mul" in _ops(c)
    assert c.return_type.value == "float"


def test_two_helpers_both_inline():
    c = compile(
        "def square(x):\n"
        "    return x * x\n"
        "\n"
        "def cube(x):\n"
        "    return square(x) * x\n"
        "\n"
        "def main():\n"
        "    return cube(2.0)\n"
    )
    # square(x) inlines to x*x = 1 mul; cube wraps it in *x = 1 mul.
    # 2 muls total in the compiled graph.
    assert _ops(c).count("math.mul") >= 2
    # function_scopes records both helpers.
    assert "square" in c.function_scopes
    assert "cube" in c.function_scopes


def test_user_function_with_vector_argument():
    c = compile(
        "def displace(P):\n"
        "    return P + vec3(0.0, 0.0, 1.0)\n"
        "\n"
        "def main():\n"
        "    return displace(vec3(1.0, 0.0, 0.0))\n"
    )
    assert "vec.add" in _ops(c)
    assert c.return_type.value == "vec3"


def test_wrong_argument_count_rejected():
    with pytest.raises(CompileError, match="takes 1 argument"):
        compile(
            "def helper(x):\n"
            "    return x\n"
            "\n"
            "def main():\n"
            "    return helper(1.0, 2.0)\n"
        )


def test_function_with_no_return_rejected():
    with pytest.raises(CompileError, match="no return value"):
        compile(
            "def helper(x):\n"
            "    y = x * 2.0\n"
            "\n"
            "def main():\n"
            "    return helper(1.0)\n"
        )


def test_assignment_then_use():
    c = compile(
        "def f():\n"
        "    a = 2.0\n"
        "    b = 3.0\n"
        "    return a + b\n"
    )
    assert "math.add" in _ops(c)


def test_function_parameter_with_default_exposed():
    c = compile(
        "def f(freq=6.0):\n"
        "    return sin(freq)\n"
    )
    assert any(p.name == "freq" and p.default == 6.0 for p in c.parameters)


def test_function_scope_tracking_records_helper_nodes():
    """Inlined helper-function nodes should be tagged with the helper's
    name so the M2 grouping pass can wrap them."""
    c = compile(
        "def helper(x):\n"
        "    return x + 1.0\n"
        "\n"
        "def main():\n"
        "    return helper(0.0) + helper(2.0)\n"
    )
    assert "helper" in c.function_scopes
    assert len(c.function_scopes["helper"]) >= 1
