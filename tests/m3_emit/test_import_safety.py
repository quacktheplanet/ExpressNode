"""The bpy-using modules must import cleanly without Blender (lazy
imports). The headless suite imports them; only execution needs bpy."""


def test_executor_imports_without_bpy():
    from coding_nodes.backend import gn_executor
    assert hasattr(gn_executor, "execute")


def test_modifier_imports_without_bpy():
    from coding_nodes.backend import modifier
    assert hasattr(modifier, "register")
    assert hasattr(modifier, "unregister")
    assert modifier.DEFAULT_EXPRESSION


def test_addon_shell_imports_without_bpy():
    import importlib
    import sys
    from pathlib import Path

    addon_dir = Path(__file__).resolve().parents[2] / "blender_addon"
    sys.path.insert(0, str(addon_dir.parent))
    mod = importlib.import_module("blender_addon")
    assert "bl_info" in dir(mod)
    assert mod.bl_info["name"]


def test_pipeline_headless_entry_is_importable():
    from coding_nodes.backend.pipeline import build_in_blender, plan_source
    assert callable(plan_source)
    assert callable(build_in_blender)
