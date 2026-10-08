"""Vector constructors, component access, swizzling."""

import pytest

from expressnode import CompileError, compile


def _ops(c):
    return [n.op for n in c.graph.nodes.values()]


def test_vec3_constructor():
    c = compile("def f(): return vec3(1.0, 2.0, 3.0)")
    assert "vec.combine3" in _ops(c)
    assert c.return_type.value == "vec3"


def test_vec2_constructor():
    c = compile("def f(): return vec2(1.0, 2.0)")
    assert "vec.combine2" in _ops(c)
    assert c.return_type.value == "vec2"


def test_vec4_constructor():
    c = compile("def f(): return vec4(1.0, 2.0, 3.0, 4.0)")
    assert "vec.combine4" in _ops(c)
    assert c.return_type.value == "vec4"


def test_component_access_x():
    c = compile(
        "def f():\n"
        "    return vec3(1.0, 2.0, 3.0).x\n"
    )
    assert "vec.component.x" in _ops(c)
    assert c.return_type.value == "float"


def test_swizzle_xy():
    c = compile(
        "def f():\n"
        "    return vec3(1.0, 2.0, 3.0).xy\n"
    )
    assert "vec.swizzle" in _ops(c)
    assert c.return_type.value == "vec2"


def test_swizzle_zyx():
    c = compile(
        "def f():\n"
        "    return vec3(1.0, 2.0, 3.0).zyx\n"
    )
    assert c.return_type.value == "vec3"
    # find the swizzle node and check the pattern
    swiz = [n for n in c.graph.nodes.values() if n.op == "vec.swizzle"]
    assert swiz and swiz[0].params["pattern"] == "zyx"


def test_subscript_constant():
    c = compile(
        "def f():\n"
        "    return vec3(1.0, 2.0, 3.0)[1]\n"
    )
    assert "vec.component.y" in _ops(c)


def test_dynamic_subscript_rejected():
    with pytest.raises(CompileError, match="constant integer"):
        compile(
            "def f(i):\n"
            "    return vec3(1.0, 2.0, 3.0)[i]\n"
        )


def test_out_of_range_component_rejected():
    with pytest.raises(CompileError, match="not available"):
        compile(
            "def f():\n"
            "    return vec2(1.0, 2.0).z\n"
        )


def test_swizzle_uses_unavailable_component_rejected():
    with pytest.raises(CompileError, match="not available"):
        compile(
            "def f():\n"
            "    return vec2(1.0, 2.0).xyz\n"
        )
