"""The Shape B module and the updated addon import cleanly without bpy."""


def test_node_group_imports_without_bpy():
    from expressnode.backend import node_group
    assert hasattr(node_group, "register")
    assert hasattr(node_group, "unregister")
    assert node_group.DEFAULT_EXPRESSION


def test_addon_registers_both_shapes():
    """The extension wires both the modifier (Shape A) and the node group
    (Shape B), and the old-file migration. It must import with no bpy present."""
    import inspect
    import expressnode
    src = inspect.getsource(expressnode.register)
    assert "node_group.register()" in src
    assert "modifier.register()" in src
    assert "migrate.register()" in src
