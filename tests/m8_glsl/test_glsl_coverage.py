"""Every frontend op has a GLSL template — the M8 coverage guarantee,
mirroring the GN and OSL op-coverage tests."""

from pathlib import Path

import pytest

from coding_nodes import compile
from coding_nodes.backend.op_emitters import (
    BACKEND_ONLY_OPS,
    frontend_op_universe,
)
from coding_nodes.backend.glsl import glsl_template_ops

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

# Handled directly in emit_glsl(), not via the template table.
_SPECIAL = {"input.parameter", "constant.string"}


def test_every_frontend_op_has_a_glsl_template_or_is_special_cased():
    missing = sorted(frontend_op_universe()
                     - glsl_template_ops()
                     - BACKEND_ONLY_OPS
                     - _SPECIAL)
    assert not missing, f"ops with no GLSL template: {missing}"


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_example_ops_all_have_templates(example):
    c = compile((EXAMPLES / example).read_text())
    used = {n.op for n in c.graph.nodes.values()}
    missing = sorted(used - glsl_template_ops() - _SPECIAL)
    assert not missing, f"{example} uses ops with no GLSL template: {missing}"
