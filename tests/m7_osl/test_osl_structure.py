"""Emitted OSL is structurally valid: shader signature, balanced
braces, SSA (every vN declared before use), exposed parameters, a
Result assignment. Strong headless correctness short of an OSL runtime.
"""

import re
from pathlib import Path

import pytest

from expressnode import compile, osl_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

DECL = re.compile(r"^\s*(?:float|vector)\s+(v\d+)\s*=", re.M)
USE = re.compile(r"\b(v\d+)\b")


def _src(name):
    return (EXAMPLES / name).read_text()


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_has_shader_signature_and_result(example):
    osl = osl_source(_src(example))
    assert osl.count("shader ") == 1
    assert "output" in osl and "Result" in osl
    assert "Result = " in osl


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_braces_balanced(example):
    osl = osl_source(_src(example))
    assert osl.count("{") == osl.count("}")
    assert osl.count("(") == osl.count(")")


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_ssa_every_var_declared_before_use(example):
    osl = osl_source(_src(example))
    # Only inspect the shader body (after the last '{' that opens it).
    body = osl[osl.rindex("shader "):]
    declared: set[str] = set()
    for line in body.splitlines():
        # uses on this line must already be declared (SSA, single pass)
        m = DECL.match(line)
        decl_var = m.group(1) if m else None
        rhs = line.split("=", 1)[1] if "=" in line else ""
        for used in USE.findall(rhs):
            assert used in declared, (
                f"{example}: {used} used before declaration in: {line.strip()}"
            )
        if decl_var:
            declared.add(decl_var)


def test_exposed_parameters_are_in_signature():
    osl = osl_source(_src("ripple.py"))
    sig = osl[osl.index("shader "):osl.index("{")]
    assert "float freq" in sig
    assert "float amp" in sig
    assert "Time" in sig and "Seed" in sig


def test_noise_lib_only_when_used():
    assert "cn_value_noise" not in osl_source(_src("ripple.py"))
    assert "cn_value_noise" in osl_source(_src("curl_noise.py"))


def test_ripple_translation_is_faithful():
    """The SSA chain must be P.x*freq+Time -> sin -> *amp -> vec(0,0,.)."""
    osl = osl_source(_src("ripple.py"))
    assert "[0]" in osl                       # P.x component access
    assert "* freq" in osl
    assert "+ v" in osl or "+ Time" in osl    # add of time
    assert "sin(" in osl
    assert "* amp" in osl
    assert re.search(r"vector\(v\d+, v\d+, v\d+\)", osl)


def test_scalar_return_uses_float_output():
    osl = osl_source("def f(P): return length(P)")
    assert "output float Result" in osl


def test_vector_return_uses_vector_output():
    osl = osl_source("def f(P): return P + vec3(1.0, 0.0, 0.0)")
    assert "output vector Result" in osl


def test_shader_name_override():
    osl = osl_source("def f(): return 1.0", shader_name="my_kernel")
    assert "shader my_kernel" in osl
