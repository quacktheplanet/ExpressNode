"""The emission plan for the example expressions has the right shape."""

from pathlib import Path

from expressnode import plan_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _src(name):
    return (EXAMPLES / name).read_text()


def test_ripple_plan_is_single_root_group():
    plan = plan_source(_src("ripple.py"))
    assert len(plan.groups) == 1
    root = plan.groups[plan.root_name]
    assert root.is_root
    # freq and amp are exposed as inputs.
    in_names = {n for n, _ in root.inputs}
    assert {"freq", "amp"} <= in_names
    # One Result output.
    assert [n for n, _ in root.outputs] == ["Result"]


def test_ripple_plan_has_nodes_and_a_result_link():
    plan = plan_source(_src("ripple.py"))
    root = plan.groups[plan.root_name]
    assert len(root.nodes) > 0
    # There is a link into the group output.
    assert any(l.dst.kind == "group_output" for l in root.links)


def test_ripple_plan_has_no_param_only_or_interface_nodes():
    plan = plan_source(_src("ripple.py"))
    root = plan.groups[plan.root_name]
    kinds = {n.emitter_kind for n in root.nodes}
    assert "interface" not in kinds
    assert "param_only" not in kinds


def test_ripple_parameters_surface_on_the_plan():
    plan = plan_source(_src("ripple.py"))
    pnames = {p[0] for p in plan.parameters}
    assert {"freq", "amp"} <= pnames


def test_plan_describe_is_serializable():
    import json
    plan = plan_source(_src("ripple.py"))
    json.dumps(plan.describe(), default=str)  # must not raise


def test_every_eval_node_is_placed_or_interface():
    """Each EvalGraph node is either a PlannedNode somewhere, or an
    interface/param-only op that is intentionally not emitted."""
    from expressnode import compile
    from expressnode.backend.op_emitters import get_emitter

    c = compile(_src("ripple.py"))
    plan = plan_source(_src("ripple.py"))
    placed = {pn.eval_id for g in plan.groups.values() for pn in g.nodes}
    for nid, node in c.graph.nodes.items():
        e = get_emitter(node.op)
        if e.kind in ("interface", "param_only"):
            assert nid not in placed
        else:
            assert nid in placed, f"node {nid} ({node.op}) not placed"
