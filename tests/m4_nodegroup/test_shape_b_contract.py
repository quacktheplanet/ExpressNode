"""Shape B (Expression Node Group) requires the plan's root group to be a
clean, reusable group: its interface is exactly the user parameters in
plus a Result out, and nothing interface/param-only leaks inside. These
headless assertions are the contract Shape B drops into any GN tree.
"""

from pathlib import Path

import pytest

from expressnode import compile, plan_source
from expressnode.backend.op_emitters import get_emitter

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _src(name):
    return (EXAMPLES / name).read_text()


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_root_group_interface_is_params_in_result_out(example):
    plan = plan_source(_src(example), inline_threshold=2)
    root = plan.groups[plan.root_name]

    param_names = {p[0] for p in plan.parameters}
    input_names = {n for n, _ in root.inputs}
    assert input_names == param_names, (
        f"{example}: root inputs {input_names} != params {param_names}"
    )

    assert [n for n, _ in root.outputs] == ["Result"], (
        f"{example}: root must expose exactly one 'Result' output"
    )


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_no_interface_or_param_only_nodes_emitted(example):
    """A droppable group must not contain interface/param-only ops as
    real nodes — they belong on the group boundary, not inside."""
    plan = plan_source(_src(example), inline_threshold=2)
    for g in plan.groups.values():
        for pn in g.nodes:
            assert pn.emitter_kind not in ("interface", "param_only"), (
                f"{example}: {pn.op} leaked into group {g.name} as a node"
            )


def test_root_group_result_is_wired():
    """The reusable group is useless if its Result output is dangling."""
    plan = plan_source(_src("ripple.py"))
    root = plan.groups[plan.root_name]
    assert any(l.dst.kind == "group_output" for l in root.links)


def test_shape_a_and_shape_b_share_one_plan():
    """Both shapes call the same pipeline; the plan is identical, so the
    node tree they produce is identical."""
    from expressnode.backend.pipeline import plan_source as ps
    src = _src("ripple.py")
    a = ps(src).describe()
    b = ps(src).describe()
    assert a == b


def test_result_type_is_preserved_for_grouping():
    c = compile(_src("ripple.py"))
    plan = plan_source(_src("ripple.py"))
    root = plan.groups[plan.root_name]
    # ripple returns vec3 -> the group's Result socket type is 'vector'.
    out_type = dict(root.outputs)["Result"]
    nid, sock = c.graph.outputs["result"]
    assert out_type == c.graph.nodes[nid].output_type(sock).value
    assert out_type == "vector"
