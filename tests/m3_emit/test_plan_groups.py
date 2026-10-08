"""The plan's group structure mirrors the M2 region tree: curl_noise
yields a root group plus a sub-group per wrapped `n` call, instantiated
in the root."""

from pathlib import Path

from expressnode import plan_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _src(name):
    return (EXAMPLES / name).read_text()


def test_curl_noise_plan_has_root_plus_subgroups():
    plan = plan_source(_src("curl_noise.py"), inline_threshold=2)
    root = plan.groups[plan.root_name]
    assert root.is_root
    # Sub-groups exist for the wrapped `n` regions.
    sub = [g for n, g in plan.groups.items() if not g.is_root]
    assert len(sub) >= 1


def test_curl_noise_root_instantiates_subgroups():
    plan = plan_source(_src("curl_noise.py"), inline_threshold=2)
    root = plan.groups[plan.root_name]
    # The 12 `n` calls become group instances inside the root.
    assert len(root.instances) == 12


def test_subgroup_has_interface_matching_boundaries():
    plan = plan_source(_src("curl_noise.py"), inline_threshold=2)
    sub = [g for n, g in plan.groups.items() if not g.is_root]
    one = sub[0]
    # n(P, seed) consumes an offset position; produces a noise scalar.
    assert len(one.inputs) >= 1
    assert len(one.outputs) >= 1
    # Output is a float (noise returns a scalar).
    assert one.outputs[0][1] == "float"


def test_subgroup_wires_group_input_to_a_node():
    plan = plan_source(_src("curl_noise.py"), inline_threshold=2)
    sub = [g for n, g in plan.groups.items() if not g.is_root][0]
    assert any(l.src.kind == "group_input" for l in sub.links)
    assert any(l.dst.kind == "group_output" for l in sub.links)


def test_root_links_instances_through():
    plan = plan_source(_src("curl_noise.py"), inline_threshold=2)
    root = plan.groups[plan.root_name]
    # Some root links feed an instance, some read from one.
    assert any(l.dst.kind == "instance" for l in root.links)
    assert any(l.src.kind == "instance" for l in root.links)


def test_ripple_has_no_subgroups():
    plan = plan_source(_src("ripple.py"))
    assert len(plan.groups) == 1
    assert not plan.groups[plan.root_name].instances


def test_inline_threshold_collapses_small_helpers():
    """With a high inline threshold the n() helper folds into curl, so
    the plan is a single group with no instances."""
    plan = plan_source(_src("curl_noise.py"), inline_threshold=999)
    assert len(plan.groups) == 1
    assert not plan.groups[plan.root_name].instances
