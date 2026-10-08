"""Every frontend op has an OSL template — the load-bearing M7
guarantee, mirroring the GN op-coverage test."""

from pathlib import Path

import pytest

from expressnode import compile
from expressnode.backend.op_emitters import (
    BACKEND_ONLY_OPS,
    frontend_op_universe,
)
from expressnode.backend.osl import osl_template_ops

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


# Handled directly in emit_osl(), not via the template table:
#   input.parameter  -> referenced by the shader-parameter name
#   constant.string  -> consumed via params, never emitted as a value
_SPECIAL = {"input.parameter", "constant.string"}


def test_every_frontend_op_has_an_osl_template_or_is_special_cased():
    missing = sorted(frontend_op_universe()
                     - osl_template_ops()
                     - BACKEND_ONLY_OPS
                     - _SPECIAL)
    assert not missing, f"ops with no OSL template: {missing}"


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_example_ops_all_have_templates(example):
    c = compile((EXAMPLES / example).read_text())
    used = {n.op for n in c.graph.nodes.values()}
    missing = sorted(used - osl_template_ops())
    # input.parameter / constant.string are handled specially in the
    # emitter (not via the template table); everything else needs one.
    missing = [m for m in missing
               if m not in ("input.parameter", "constant.string")]
    assert not missing, f"{example} uses ops with no OSL template: {missing}"
