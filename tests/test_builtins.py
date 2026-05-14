"""Built-in functions and variables resolve correctly."""

import pytest

from coding_nodes import CompileError, compile


def _ops(c):
    return [n.op for n in c.graph.nodes.values()]


def test_builtin_variable_P():
    c = compile("def f(P): return P")
    assert "input.position" in _ops(c)


def test_builtin_variable_t():
    c = compile("def f(t): return sin(t)")
    assert "input.scene_time" in _ops(c)
    assert "math.sin" in _ops(c)


def test_builtin_variable_referenced_inside_body():
    """P used without being a function parameter — implicit lookup."""
    c = compile(
        "def f():\n"
        "    return P.x\n"
    )
    assert "input.position" in _ops(c)


def test_sin_takes_float_returns_float():
    c = compile("def f(): return sin(0.0)")
    assert "math.sin" in _ops(c)
    assert c.return_type.value == "float"


def test_atan2_takes_two_floats():
    c = compile("def f(): return atan2(1.0, 2.0)")
    assert "math.atan2" in _ops(c)


def test_noise_returns_float():
    c = compile(
        "def f():\n"
        "    return noise(vec3(0.0, 0.0, 0.0))\n"
    )
    assert "texture.noise" in _ops(c)
    assert c.return_type.value == "float"


def test_length_on_vec3_returns_float():
    c = compile(
        "def f():\n"
        "    return length(vec3(1.0, 2.0, 3.0))\n"
    )
    assert "vec.length" in _ops(c)
    assert c.return_type.value == "float"


def test_cross_returns_vec3():
    c = compile(
        "def f():\n"
        "    return cross(vec3(1.0, 0.0, 0.0), vec3(0.0, 1.0, 0.0))\n"
    )
    assert "vec.cross" in _ops(c)
    assert c.return_type.value == "vec3"


def test_min_with_two_args():
    c = compile("def f(): return min(1.0, 2.0)")
    assert "math.min" in _ops(c)


def test_clamp_with_three_args():
    c = compile("def f(): return clamp(0.5, 0.0, 1.0)")
    assert "math.clamp" in _ops(c)


def test_mix_vec3_with_scalar_t():
    c = compile(
        "def f():\n"
        "    return mix(vec3(0.0, 0.0, 0.0), vec3(1.0, 1.0, 1.0), 0.5)\n"
    )
    assert "math.mix" in _ops(c)
    assert c.return_type.value == "vec3"


def test_unknown_function_rejected():
    with pytest.raises(CompileError, match="Unknown function"):
        compile("def f(): return frobnicate(1.0)")


def test_wrong_signature_rejected():
    with pytest.raises(CompileError, match="No matching signature"):
        compile(
            "def f():\n"
            "    return sin(vec3(0.0, 0.0, 0.0))\n"
        )


def test_attr_read_single_arg_defaults_float():
    c = compile("def f(): return attr('thickness')")
    assert c.return_type.value == "float"
    nodes = [n for n in c.graph.nodes.values() if n.op == "attr.read"]
    assert nodes and nodes[0].params["name"] == "thickness"


def test_attr_read_with_dtype():
    c = compile("def f(): return attr('color', 'color')")
    assert c.return_type.value == "vec4"


def test_attr_with_unknown_dtype_rejected():
    with pytest.raises(CompileError, match="Unknown attribute dtype"):
        compile("def f(): return attr('x', 'matrix')")


def test_set_attr_emits_attr_write():
    c = compile(
        "def f():\n"
        "    set_attr('thickness', 0.1)\n"
        "    return 0.0\n"
    )
    assert "attr.write" in _ops(c)


def test_obj_read_position_returns_vec3():
    c = compile("def f(): return obj('Cube', 'position')")
    assert c.return_type.value == "vec3"
    nodes = [n for n in c.graph.nodes.values() if n.op == "obj.read"]
    assert nodes and nodes[0].params["object"] == "Cube"


def test_obj_with_unknown_field_rejected():
    with pytest.raises(CompileError, match="Unknown object field"):
        compile("def f(): return obj('Cube', 'mass')")
