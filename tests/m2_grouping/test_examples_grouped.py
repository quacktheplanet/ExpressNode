"""M2 done-criterion: the curl_noise example groups into a readable
tree (a `curl` root with `n` sub-regions) rather than a flat sea of
nodes."""

from pathlib import Path

from expressnode import compile, group

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _read(name: str) -> str:
    return (EXAMPLES / name).read_text()


def test_ripple_groups_to_root_only():
    """ripple has no helper calls, so the whole thing is the root tree —
    no sub-groups, which is correct (it's already small and readable)."""
    g = group(compile(_read("ripple.py")))
    assert g.root.function == "ripple"
    assert g.root.children == []


def test_curl_noise_produces_n_subregions():
    c = compile(_read("curl_noise.py"))
    g = group(c, inline_threshold=2)
    assert g.root.function == "curl"
    # The helper n() is called 12 times in curl_noise.py.
    n_children = [ch for ch in g.root.children if ch.function == "n"]
    assert len(n_children) == 12, (
        f"expected 12 'n' call regions, got {len(n_children)}"
    )


def test_curl_noise_is_not_a_flat_sea_of_nodes():
    """The whole point of M2: the top level should be a handful of
    regions, not dozens of loose math nodes."""
    c = compile(_read("curl_noise.py"))
    g = group(c, inline_threshold=2)
    total_nodes = len(g.graph.nodes)
    # Each `n` call wraps several nodes; the root's *direct* node count
    # should be far smaller than the total.
    assert len(g.root.direct_node_ids) < total_nodes
    # And we get real sub-groups.
    assert len(g.wrapped_regions()) >= 1


def test_curl_noise_every_node_accounted_for():
    c = compile(_read("curl_noise.py"))
    g = group(c, inline_threshold=2)
    seen = []
    for r in g.root.walk():
        seen.extend(r.direct_node_ids)
    assert sorted(seen) == sorted(g.graph.nodes.keys())


def test_curl_noise_graph_still_acyclic_after_grouping():
    """Grouping never mutates the underlying graph; it stays acyclic."""
    c = compile(_read("curl_noise.py"))
    g = group(c)
    order = g.graph.topological_order()
    assert len(order) == len(g.graph.nodes)
