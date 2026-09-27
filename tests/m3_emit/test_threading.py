"""Values crossing group boundaries reach every consumer, at any depth.

Found by the Blender parity run (tests/blender/bl_gn.py): the planner
used to wire only the first consumer of each incoming value and threaded
one nesting level only, so `bump(p)` using p.x, p.y and p.z lost two of
them, and helpers inside helpers lost their inputs.
"""

from coding_nodes import compile
from coding_nodes.backend.op_emitters import get_emitter
from coding_nodes.backend.plan import build_plan

NESTED = (
    "def wave(x, k):\n"
    "    return sin(x * k) * 0.5\n"
    "\n"
    "def bump(p, k):\n"
    "    return wave(p.x, k) + wave(p.y, k * 2.0) + wave(p.z, k * 3.0)\n"
    "\n"
    "def helpers(P, t, k=1.7):\n"
    "    return vec3(bump(P, k), bump(P.yzx, k + t), bump(P * 2.0, k))\n"
)


def _inputs_fed(plan):
    """(group, local node id, input name) for every linked node input."""
    fed = set()
    for gname, g in plan.groups.items():
        for link in g.links:
            if link.dst.kind == "node":
                fed.add((gname, link.dst.ref, link.dst.socket))
    return fed


def test_every_node_input_is_linked():
    compiled = compile(NESTED)
    plan = build_plan(compiled, inline_threshold=0)
    fed = _inputs_fed(plan)
    missing = []
    for gname, g in plan.groups.items():
        for pn in g.nodes:
            for name in pn.input_names:
                if (gname, pn.local_id, name) not in fed:
                    missing.append((gname, pn.op, name))
    assert not missing, missing


def test_nesting_is_two_levels_deep():
    plan = build_plan(compile(NESTED), inline_threshold=0)
    root = plan.groups[plan.root_name]
    bumps = [plan.groups[i.group_name] for i in root.instances
             if i.group_name.startswith("bump")]
    assert bumps and all(b.instances for b in bumps)


def test_group_links_reference_existing_sockets():
    plan = build_plan(compile(NESTED), inline_threshold=0)
    for gname, g in plan.groups.items():
        ins = {n for n, _ in g.inputs}
        outs = {n for n, _ in g.outputs}
        for link in g.links:
            if link.src.kind == "group_input":
                assert link.src.socket in ins, (gname, link.src.socket)
            if link.dst.kind == "group_output":
                assert link.dst.socket in outs, (gname, link.dst.socket)
            for ep in (link.src, link.dst):
                if ep.kind == "instance":
                    inst = next(i for i in g.instances
                                if i.instance_id == ep.ref)
                    child = plan.groups[inst.group_name]
                    names = {n for n, _ in child.inputs + child.outputs}
                    assert ep.socket in names, (gname, ep.socket)


def test_parameters_and_builtins_get_readable_socket_names():
    plan = build_plan(compile(NESTED), inline_threshold=0)
    names = {n for g in plan.groups.values() if not g.is_root
             for n, _ in g.inputs}
    assert "P" in names or "k" in names


def test_set_attr_becomes_a_root_output():
    src = ("def f(P, t):\n"
           "    set_attr('heat', P.x * 2.0)\n"
           "    return vec3(0.0, 0.0, 1.0)\n")
    plan = build_plan(compile(src), apply_mode="offset")
    root = plan.groups[plan.root_name]
    assert [n for n, _ in root.outputs] == ["Result", "heat"]
    assert plan.attr_writes == [("heat", "float")]
    assert any(l.dst.kind == "group_output" and l.dst.socket == "heat"
               for l in root.links)
    assert all(pn.op != "attr.write" for pn in root.nodes)


def test_set_attr_inside_nested_helpers_reaches_the_root():
    src = ("def mark(p):\n"
           "    set_attr('heat', p.x * 2.0)\n"
           "    return p.y\n"
           "\n"
           "def outer(p):\n"
           "    return mark(p) + 1.0\n"
           "\n"
           "def f(P, t):\n"
           "    return vec3(0.0, 0.0, outer(P))\n")
    plan = build_plan(compile(src), apply_mode="offset", inline_threshold=0)
    root = plan.groups[plan.root_name]
    assert [n for n, _ in root.outputs] == ["Result", "heat"]
    assert plan.attr_writes == [("heat", "float")]
    # the value leaves each helper group through an extra output
    helpers = [g for name, g in plan.groups.items()
               if name not in (plan.root_name, plan.modifier_root_name)]
    assert sum(len(g.outputs) for g in helpers) >= 4   # 2 returns + heat out of each
    feeds_heat = [l for l in root.links
                  if l.dst.kind == "group_output" and l.dst.socket == "heat"]
    assert len(feeds_heat) == 1 and feeds_heat[0].src.kind == "instance"
    assert all(pn.op != "attr.write" for g in plan.groups.values() for pn in g.nodes)


def test_set_attr_in_a_helper_used_twice_is_a_clear_error():
    import pytest
    src = ("def mark(p):\n"
           "    set_attr('heat', p.x)\n"
           "    return p.y\n"
           "\n"
           "def f(P, t):\n"
           "    return vec3(mark(P), mark(P * 2.0), 0.0)\n")
    with pytest.raises(ValueError, match="more than once"):
        build_plan(compile(src), apply_mode="offset", inline_threshold=0)


def test_nodes_carry_their_input_order():
    plan = build_plan(compile("def f(P, t):\n    return vec3(clamp(P.x, 0.0, 1.0), 0.0, 0.0)\n"))
    root = plan.groups[plan.root_name]
    clamp = next(pn for pn in root.nodes if pn.op == "math.clamp")
    assert clamp.input_names == ("arg0", "arg1", "arg2")
    assert get_emitter("math.clamp").kind == "complex"
