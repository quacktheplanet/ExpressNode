"""The bpy-using modules must import cleanly without Blender (lazy
imports). The headless suite imports them; only execution needs bpy."""


def test_executor_imports_without_bpy():
    from expressnode.backend import gn_executor
    assert hasattr(gn_executor, "execute")


def test_modifier_imports_without_bpy():
    from expressnode.backend import modifier
    assert hasattr(modifier, "register")
    assert hasattr(modifier, "unregister")
    assert modifier.DEFAULT_EXPRESSION


def test_extension_imports_without_bpy():
    """The package is also the Blender extension: importing it (and finding
    register / unregister) must not need bpy."""
    import expressnode
    assert callable(expressnode.register)
    assert callable(expressnode.unregister)


def test_pipeline_headless_entry_is_importable():
    from expressnode.backend.pipeline import build_in_blender, plan_source
    assert callable(plan_source)
    assert callable(build_in_blender)
