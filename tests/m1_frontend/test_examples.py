"""Verify the shipped example expressions compile cleanly. These are the
M1 done-criteria from PLAN.md."""

from pathlib import Path

from coding_nodes import compile


EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _read(name: str) -> str:
    return (EXAMPLES / name).read_text()


def test_ripple_example_compiles():
    src = _read("ripple.py")
    c = compile(src)
    assert c.entry_function == "ripple"
    assert c.return_type.value == "vec3"
    # Should have at least: input.scene_time, input.position, math.add,
    # math.mul, math.sin, vec.combine3.
    ops = {n.op for n in c.graph.nodes.values()}
    assert "input.position" in ops
    assert "input.scene_time" in ops
    assert "math.sin" in ops
    assert "vec.combine3" in ops
    # Parameters `freq` and `amp` exposed.
    pnames = {p.name for p in c.parameters}
    assert "freq" in pnames
    assert "amp" in pnames


def test_ripple_graph_is_acyclic():
    c = compile(_read("ripple.py"))
    order = c.graph.topological_order()
    assert len(order) == len(c.graph.nodes)


def test_curl_noise_example_compiles():
    src = _read("curl_noise.py")
    c = compile(src)
    assert c.entry_function == "curl"
    assert c.return_type.value == "vec3"
    ops = [n.op for n in c.graph.nodes.values()]
    # `noise` is called many times via the `n` helper.
    assert ops.count("texture.noise") >= 6
    # vec.combine3 used many times for the offset constants.
    assert ops.count("vec.combine3") >= 6


def test_curl_noise_tracks_helper_function_scope():
    """The `n` helper is called many times; the parser should record nodes
    belonging to those calls under function_scopes['n']."""
    c = compile(_read("curl_noise.py"))
    assert "n" in c.function_scopes
    assert len(c.function_scopes["n"]) > 0


def test_curl_noise_graph_is_acyclic():
    c = compile(_read("curl_noise.py"))
    order = c.graph.topological_order()
    assert len(order) == len(c.graph.nodes)
