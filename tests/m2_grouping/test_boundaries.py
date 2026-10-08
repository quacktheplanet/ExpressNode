"""Region boundary computation: edges crossing into/out of a region
become the sub-group's input/output sockets."""

from expressnode import compile, group


def _child_by_fn(region, fn):
    return [c for c in region.children if c.function == fn]


def test_helper_region_has_input_and_output():
    c = compile(
        "def helper(x):\n"
        "    return x * 2.0 + x + 1.0\n"   # 4+ nodes -> stays wrapped
        "\n"
        "def main():\n"
        "    return helper(3.0)\n"
    )
    g = group(c, inline_threshold=2)
    helpers = _child_by_fn(g.root, "helper")
    assert len(helpers) == 1
    h = helpers[0]
    # The constant 3.0 is produced in main and consumed inside helper -> 1 input.
    assert len(h.inputs) >= 1
    # helper's result flows back out to main -> 1 output.
    assert len(h.outputs) == 1


def test_input_dedup_when_same_value_used_twice():
    """If the same external value feeds two internal nodes, the region
    exposes one input, not two."""
    c = compile(
        "def helper(x):\n"
        "    return x * x + x\n"            # x used 3 times internally
        "\n"
        "def main():\n"
        "    return helper(5.0)\n"
    )
    g = group(c, inline_threshold=1)
    h = _child_by_fn(g.root, "helper")[0]
    # The single external producer (constant 5.0) -> exactly one input socket.
    assert len(h.inputs) == 1


def test_output_dedup_when_result_used_twice():
    c = compile(
        "def helper(x):\n"
        "    return x + 1.0 + x\n"
        "\n"
        "def main():\n"
        "    r = helper(2.0)\n"
        "    return r + r\n"                 # helper result consumed twice
    )
    g = group(c, inline_threshold=1)
    h = _child_by_fn(g.root, "helper")[0]
    assert len(h.outputs) == 1


def test_boundary_sockets_carry_socket_type():
    c = compile(
        "def shift(P):\n"
        "    return P + vec3(0.0, 0.0, 1.0) + vec3(1.0, 0.0, 0.0)\n"
        "\n"
        "def main():\n"
        "    return shift(vec3(1.0, 2.0, 3.0))\n"
    )
    g = group(c, inline_threshold=2)
    h = _child_by_fn(g.root, "shift")[0]
    assert h.outputs
    # shift returns a vec3
    assert h.outputs[0].socket_type.value == "vector"
