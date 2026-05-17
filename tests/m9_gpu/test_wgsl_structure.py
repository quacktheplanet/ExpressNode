"""Emitted WGSL is a structurally valid compute shader: kernel function,
storage/uniform bindings, a @compute entry, balanced braces/parens, SSA
(every vN declared before use), faithful ripple chain, scalar/vector
result handling."""

import re
from pathlib import Path

import pytest

from coding_nodes import wgsl_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DECL = re.compile(r"^\s*let\s+(v\d+)\s*:", re.M)
USE = re.compile(r"\b(v\d+)\b")


def _src(name):
    return (EXAMPLES / name).read_text()


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_has_kernel_bindings_and_compute_entry(example):
    w = wgsl_source(_src(example))
    assert "fn expr_" in w
    assert "var<storage, read> in_P: array<f32>" in w
    assert "var<storage, read_write> out_R: array<f32>" in w
    assert "var<uniform> U: Uniforms" in w
    assert "@compute @workgroup_size(64)" in w
    assert "fn main(@builtin(global_invocation_id)" in w
    assert "arrayLength(&in_P)" in w


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_braces_and_parens_balanced(example):
    w = wgsl_source(_src(example))
    assert w.count("{") == w.count("}")
    assert w.count("(") == w.count(")")


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_ssa_declared_before_use_in_kernel(example):
    w = wgsl_source(_src(example))
    start = w.index("fn expr_")
    body = w[start:w.index("struct Uniforms")]
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


def test_uniforms_struct_lists_params():
    w = wgsl_source(_src("ripple.py"))
    st = w[w.index("struct Uniforms"):w.index("@group")]
    assert "Time: f32" in st and "Seed: i32" in st
    assert "freq: f32" in st and "amp: f32" in st


def test_scalar_result_writes_three_floats():
    w = wgsl_source("def f(P): return length(P)")
    assert "fn expr_f(" in w and "-> f32" in w
    assert "out_R[3u*i+0u] = r;" in w
    assert "out_R[3u*i+1u] = 0.0;" in w


def test_vector_result_writes_components():
    w = wgsl_source("def f(P): return P + vec3(1.0, 0.0, 0.0)")
    assert "-> vec3<f32>" in w
    assert "out_R[3u*i+0u] = r.x;" in w
    assert "out_R[3u*i+2u] = r.z;" in w


def test_vec_scalar_arith_promoted():
    w = wgsl_source("def f(P, k=2.0):\n    return P + k\n")
    assert re.search(r"\+ vec3<f32>\(", w)


def test_noise_lib_uint_only_when_used():
    assert "cn_value_noise" not in wgsl_source(_src("ripple.py"))
    cw = wgsl_source(_src("curl_noise.py"))
    assert "fn cn_hash(" in cw
    assert "0x9E3779B1u" in cw          # u32 hash literal
    assert "bitcast<u32>" in cw         # signed->unsigned reinterpret


def test_ripple_translation_faithful():
    w = wgsl_source(_src("ripple.py"))
    assert ").x" in w and "* freq" in w and "sin(" in w and "* amp" in w
    assert re.search(r"vec3<f32>\(v\d+, v\d+, v\d+\)", w)


def test_mod_is_floored_to_match_oracle():
    """numpy/OSL/GLSL use floored modulo; WGSL has no float mod builtin,
    so we emit a - b*floor(a/b) for parity with the oracle."""
    w = wgsl_source("def f(x=5.0): return x % 2.0")
    assert "floor(" in w and "- " in w


def test_fn_name_override():
    assert "fn kern(" in wgsl_source(
        "def f(): return vec3(1.0,2.0,3.0)", fn_name="kern")
