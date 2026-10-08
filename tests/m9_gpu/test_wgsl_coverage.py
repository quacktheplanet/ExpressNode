"""Every frontend op has a WGSL template — the M9 coverage guarantee,
mirroring GN / OSL / GLSL."""

from pathlib import Path

import pytest

from expressnode import compile
from expressnode.backend.op_emitters import (
    BACKEND_ONLY_OPS,
    frontend_op_universe,
)
from expressnode.backend.wgsl import wgsl_template_ops

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_SPECIAL = {"input.parameter", "constant.string"}


def test_every_frontend_op_has_a_wgsl_template_or_is_special_cased():
    missing = sorted(frontend_op_universe()
                     - wgsl_template_ops()
                     - BACKEND_ONLY_OPS
                     - _SPECIAL)
    assert not missing, f"ops with no WGSL template: {missing}"


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_example_ops_all_have_templates(example):
    c = compile((EXAMPLES / example).read_text())
    used = {n.op for n in c.graph.nodes.values()}
    missing = sorted(used - wgsl_template_ops() - _SPECIAL)
    assert not missing, f"{example} uses ops with no WGSL template: {missing}"
