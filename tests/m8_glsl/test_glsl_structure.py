"""Emitted GLSL is structurally valid: #version, balanced braces/parens,
SSA (every vN declared before use), the expr function + a main() that
uses it, scalar/vector return, float-literal correctness."""

import re
from pathlib import Path

import pytest

from coding_nodes import glsl_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DECL = re.compile(r"^\s*(?:float|vec3)\s+(v\d+)\s*=", re.M)
USE = re.compile(r"\b(v\d+)\b")


def _src(name):
    return (EXAMPLES / name).read_text()


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_has_version_function_and_main(example):
    g = glsl_source(_src(example))
    assert g.startswith("#version 330 core")
    assert "void main()" in g
    assert "_fragColor = vec4(" in g


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_braces_and_parens_balanced(example):
    g = glsl_source(_src(example))
    assert g.count("{") == g.count("}")
    assert g.count("(") == g.count(")")


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_ssa_declared_before_use_in_expr_function(example):
    g = glsl_source(_src(example))
    start = g.index(f"expr_{'ripple' if 'ripple' in example else 'curl'}(")
    body = g[start:g.index("out vec4 _fragColor;")]
    declared: set[str] = set()
    for line in body.splitlines():
        m = DECL.match(line)
        rhs = line.split("=", 1)[1] if "=" in line else ""
        for u in USE.findall(rhs):
            assert u in declared, (
                f"{example}: {u} used before declaration: {line.strip()}"
            )
        if m:
            declared.add(m.group(1))


def test_float_literals_have_decimal_point():
    g = glsl_source("def f(): return 2.0 + 3.0")
    # No bare-int float literals like "= 2;" — must be 2.0
    assert re.search(r"=\s*2\.0", g)
    assert not re.search(r"=\s*2\s*;", g)


def test_scalar_vs_vector_return_type():
    assert "float expr_" in glsl_source("def f(P): return length(P)")
    assert "vec3 expr_" in glsl_source(
        "def f(P): return P + vec3(1.0, 0.0, 0.0)")


def test_scalar_result_wrapped_to_vec4_in_main():
    g = glsl_source("def f(P): return length(P)")
    assert "vec4(vec3(" in g  # scalar promoted for the frag write


def test_vec_scalar_arith_promotes_to_vec3():
    """GLSL has no implicit float->vec; scalar operands of vec ops must
    be wrapped in vec3(...)."""
    g = glsl_source(
        "def f(P, k=2.0):\n"
        "    return P + k\n"          # vec3 + float -> must become vec3 + vec3(k)
    )
    assert "vec3(" in g
    # the add must not be a raw 'vN + k' of mismatched types
    assert re.search(r"\+ vec3\(", g)


def test_noise_lib_uint_only_when_used():
    assert "cn_value_noise" not in glsl_source(_src("ripple.py"))
    cg = glsl_source(_src("curl_noise.py"))
    assert "cn_value_noise" in cg
    assert "0x9E3779B1u" in cg          # uint32 hash literal
    assert "uint cn_hash(" in cg


def test_ripple_translation_faithful():
    g = glsl_source(_src("ripple.py"))
    assert ".x" in g and "* freq" in g and "sin(" in g and "* amp" in g
    assert re.search(r"vec3\(v\d+, v\d+, v\d+\)", g)


def test_func_name_override():
    assert "vec3 kern(" in glsl_source(
        "def f(): return vec3(1.0,2.0,3.0)", func_name="kern")
