"""The grouping pass reconstructs the call tree from scope paths."""

from expressnode import compile, group


def test_single_function_is_root_only():
    c = compile("def f(): return 1.0 + 2.0 + 3.0")
    g = group(c)
    assert g.root.is_root
    assert g.root.function == "f"
    assert g.root.children == []
    # root is never wrapped, regardless of size
    assert g.wrapped_regions() == []


def test_helper_call_creates_child_region():
    c = compile(
        "def helper(x):\n"
        "    return x * 2.0 + 1.0 + x\n"          # >3 nodes so it stays wrapped
        "\n"
        "def main():\n"
        "    return helper(3.0) + helper(4.0)\n"
    )
    g = group(c, inline_threshold=2)
    # main is root; two helper call instances are children.
    assert g.root.function == "main"
    assert len(g.root.children) == 2
    assert all(child.function == "helper" for child in g.root.children)
    # distinct call instances get distinct instance numbers
    insts = sorted(ch.instance for ch in g.root.children)
    assert insts[0] != insts[1]


def test_nested_calls_nest_regions():
    c = compile(
        "def inner(x):\n"
        "    return x * x + x + 1.0\n"
        "\n"
        "def outer(y):\n"
        "    return inner(y) + inner(y * 2.0) + y\n"
        "\n"
        "def main():\n"
        "    return outer(2.0)\n"
    )
    g = group(c, inline_threshold=1)
    # main -> outer -> {inner, inner}
    assert g.root.function == "main"
    assert len(g.root.children) == 1
    outer = g.root.children[0]
    assert outer.function == "outer"
    assert len(outer.children) == 2
    assert all(ch.function == "inner" for ch in outer.children)


def test_every_node_belongs_to_exactly_one_region():
    c = compile(
        "def helper(x):\n"
        "    return x + 1.0\n"
        "\n"
        "def main():\n"
        "    return helper(0.0) * 2.0\n"
    )
    g = group(c, inline_threshold=0)  # nothing inlined; pure structure
    all_direct = []
    for r in g.root.walk():
        all_direct.extend(r.direct_node_ids)
    # No node assigned twice, and every graph node assigned once.
    assert sorted(all_direct) == sorted(g.graph.nodes.keys())
    assert len(all_direct) == len(set(all_direct))


def test_describe_is_serializable():
    c = compile(
        "def helper(x):\n"
        "    return x + 1.0\n"
        "\n"
        "def main():\n"
        "    return helper(2.0)\n"
    )
    d = group(c).describe()
    assert isinstance(d, dict)
    assert "tree" in d
    assert d["tree"]["is_root"] is True
