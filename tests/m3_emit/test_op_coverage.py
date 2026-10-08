"""Every op the frontend can emit must have a registered GN emitter.

This is the load-bearing headless guarantee for M3: if the frontend can
produce an op, the backend knows how to turn it into Blender nodes.
"""

from pathlib import Path

import pytest

from expressnode import compile
from expressnode.backend.op_emitters import (
    all_emitter_ops,
    frontend_op_universe,
    get_emitter,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_every_frontend_op_has_an_emitter():
    universe = frontend_op_universe()
    registered = all_emitter_ops()
    missing = sorted(universe - registered)
    assert not missing, f"ops with no emitter: {missing}"


def test_emitter_kinds_are_valid():
    valid = {"simple", "complex", "interface", "param_only"}
    for op in all_emitter_ops():
        e = get_emitter(op)
        assert e.kind in valid, f"{op} has bad kind {e.kind!r}"


def test_simple_emitters_have_a_bl_idname():
    for op in all_emitter_ops():
        e = get_emitter(op)
        if e.kind == "simple":
            assert e.bl_idname, f"{op} is simple but has no bl_idname"


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_example_ops_are_all_covered(example):
    src = (EXAMPLES / example).read_text()
    c = compile(src)
    used_ops = {n.op for n in c.graph.nodes.values()}
    registered = all_emitter_ops()
    missing = sorted(used_ops - registered)
    assert not missing, f"{example} uses unmapped ops: {missing}"
