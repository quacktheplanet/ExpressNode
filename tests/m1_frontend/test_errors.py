"""Compile errors: every unsupported construct gives a clear, located error."""

import pytest

from expressnode import CompileError, compile


def test_import_rejected():
    with pytest.raises(CompileError, match="Imports aren't allowed"):
        compile("import math\ndef f(): return math.pi\n")


def test_from_import_rejected():
    with pytest.raises(CompileError, match="Imports aren't allowed"):
        compile("from math import sin\ndef f(): return sin(0.0)\n")


def test_class_def_rejected():
    with pytest.raises(CompileError, match="ClassDef isn't compileable"):
        compile("class Foo: pass\n")


def test_async_def_rejected():
    with pytest.raises(CompileError, match="AsyncFunctionDef isn't compileable"):
        compile("async def f(): return 1.0\n")


def test_for_loop_rejected():
    with pytest.raises(CompileError, match="for loops aren't supported"):
        compile(
            "def f():\n"
            "    for i in range(10):\n"
            "        pass\n"
            "    return 1.0\n"
        )


def test_while_loop_rejected():
    with pytest.raises(CompileError, match="while loops aren't supported"):
        compile(
            "def f():\n"
            "    while True:\n"
            "        break\n"
            "    return 1.0\n"
        )


def test_try_except_rejected():
    with pytest.raises(CompileError, match="Exception handling"):
        compile(
            "def f():\n"
            "    try:\n"
            "        return 1.0\n"
            "    except Exception:\n"
            "        return 0.0\n"
        )


def test_if_statement_rejected_use_ternary():
    with pytest.raises(CompileError, match="`if` statements aren't supported"):
        compile(
            "def f(x):\n"
            "    if x > 0:\n"
            "        return 1.0\n"
            "    return 0.0\n"
        )


def test_aug_assign_rejected():
    with pytest.raises(CompileError, match="Augmented assignment"):
        compile(
            "def f():\n"
            "    a = 1.0\n"
            "    a += 2.0\n"
            "    return a\n"
        )


def test_star_args_rejected():
    with pytest.raises(CompileError, match=r"\* unpacking"):
        compile(
            "def f():\n"
            "    return min(*[1.0, 2.0, 3.0])\n"
        )


def test_keyword_args_rejected_for_now():
    with pytest.raises(CompileError, match="Keyword arguments"):
        compile(
            "def f():\n"
            "    return mix(0.0, 1.0, t=0.5)\n"
        )


def test_method_call_rejected():
    """We accept only simple-name calls. Method-style calls like
    `something.method(...)` aren't supported."""
    with pytest.raises(CompileError, match="simple name"):
        compile(
            "def f(P):\n"
            "    return P.normalize()\n"
        )


def test_tuple_assignment_rejected():
    with pytest.raises(CompileError, match="simple name"):
        compile(
            "def f():\n"
            "    a, b = 1.0, 2.0\n"
            "    return a + b\n"
        )


def test_unknown_name_rejected():
    with pytest.raises(CompileError, match="Unknown name"):
        compile("def f(): return unknown_var\n")


def test_chained_comparison_rejected():
    with pytest.raises(CompileError, match="Chained comparisons"):
        compile(
            "def f(x):\n"
            "    return 0.0 < x < 1.0\n"
        )


def test_error_carries_source_span():
    with pytest.raises(CompileError) as exc:
        compile(
            "def f():\n"
            "    return unknown_var\n"
        )
    assert exc.value.span is not None
    assert exc.value.span.line == 2


def test_attr_with_non_string_name_rejected():
    with pytest.raises(CompileError, match="string literal"):
        compile(
            "def f():\n"
            "    name = 'thickness'\n"
            "    return attr(name)\n"
        )
