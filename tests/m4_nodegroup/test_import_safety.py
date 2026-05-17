"""The Shape B module and the updated addon import cleanly without bpy."""


def test_node_group_imports_without_bpy():
    from coding_nodes.backend import node_group
    assert hasattr(node_group, "register")
    assert hasattr(node_group, "unregister")
    assert node_group.DEFAULT_EXPRESSION


def test_addon_registers_both_shapes():
    """The addon shell wires both the modifier (Shape A) and the node
    group (Shape B). It must still import with no bpy present."""
    import importlib
    import sys
    from pathlib import Path

    addon_parent = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(addon_parent))
    mod = importlib.import_module("blender_addon")
    assert callable(mod.register)
    assert callable(mod.unregister)
    src = (addon_parent / "blender_addon" / "__init__.py").read_text()
    assert "node_group.register()" in src
    assert "modifier.register()" in src
