"""Small regions inline into their parent instead of becoming a sub-group."""

from coding_nodes import compile, group


def _child_by_fn(region, fn):
    return [c for c in region.children if c.function == fn]


def test_trivial_function_is_inlined():
    c = compile(
        "def double(x):\n"
        "    return x * 2.0\n"            # 2 nodes: const 2.0, mul
        "\n"
        "def main():\n"
        "    return double(3.0)\n"
    )
    g = group(c, inline_threshold=3)
    doubles = _child_by_fn(g.root, "double")
    assert len(doubles) == 1
    assert doubles[0].inlined is True
    assert g.wrapped_regions() == []          # nothing big enough to wrap
    assert len(g.inlined_regions()) == 1


def test_substantial_function_is_wrapped():
    c = compile(
        "def lots(x):\n"
        "    return x * 2.0 + x * 3.0 - x + 1.0\n"   # several ops
        "\n"
        "def main():\n"
        "    return lots(3.0)\n"
    )
    g = group(c, inline_threshold=3)
    lots = _child_by_fn(g.root, "lots")[0]
    assert lots.inlined is False
    assert lots in g.wrapped_regions()


def test_threshold_is_configurable():
    src = (
        "def mid(x):\n"
        "    return x + 1.0 + 2.0\n"        # ~3-4 nodes
        "\n"
        "def main():\n"
        "    return mid(0.0)\n"
    )
    big_threshold = group(compile(src), inline_threshold=99)
    small_threshold = group(compile(src), inline_threshold=0)
    assert big_threshold.wrapped_regions() == []         # all inlined
    assert len(small_threshold.wrapped_regions()) == 1   # nothing inlined


def test_root_never_inlined_even_if_tiny():
    c = compile("def f(): return 1.0")
    g = group(c, inline_threshold=99)
    assert g.root.is_root
    assert g.root.inlined is False
