"""Smoke tests: imports work and the simplest expressions compile."""

import pytest

import expressnode
from expressnode import CompileError, compile


def test_top_level_imports():
    assert hasattr(expressnode, "compile")
    assert hasattr(expressnode, "CompiledExpression")
    assert hasattr(expressnode, "CompileError")


def test_simplest_expression():
    """A bare expression becomes a synthetic entry function."""
    c = compile("1.0")
    assert c.entry_function == "__expr__"
    assert c.return_type is not None
    assert "result" in c.graph.outputs


def test_function_definition_is_entry():
    c = compile("def f(): return 2.0")
    assert c.entry_function == "f"


def test_last_function_wins():
    c = compile(
        "def a(): return 1.0\n"
        "def b(): return 2.0\n"
    )
    assert c.entry_function == "b"


def test_duplicate_function_rejected():
    with pytest.raises(CompileError, match="defined more than once"):
        compile(
            "def f(): return 1.0\n"
            "def f(): return 2.0\n"
        )


def test_no_entry_raises():
    with pytest.raises(CompileError, match="No entry function"):
        compile("")


def test_syntax_error_reports_line():
    with pytest.raises(CompileError) as exc:
        compile("def f(:\n    return 1\n")
    assert exc.value.span is not None
    assert exc.value.span.line == 1
