"""Install the packaged extension zip, enable it, use it, and check that a file
saved with the old add-on's names is brought up to date.

    BLENDER_USER_RESOURCES=<temp dir> \\
    blender -b --factory-startup --python tests/blender/bl_install.py -- <zip>

Run it with Blender's user folders pointed at a temporary directory (the runner
does this): the script refuses to install anywhere else, so a real Blender
profile is never touched.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import check, done  # noqa: E402

import addon_utils  # noqa: E402
import bpy  # noqa: E402

OLD = "coding" + "_nodes_"


def _sandboxed():
    resources = pathlib.Path(bpy.utils.resource_path("USER")).resolve()
    sandbox = os.environ.get("EXPN_SANDBOX")
    ok = bool(sandbox) and str(resources).startswith(str(pathlib.Path(sandbox).resolve()))
    check("install sandboxed", ok, f"user resources {resources}, sandbox {sandbox}")
    return ok


def _module_name():
    for mod in addon_utils.modules(refresh=True):
        if mod.__name__.endswith(".expressnode"):
            return mod.__name__
    return None


def _old_file_round_trip():
    """Save a file the way the old add-on stored things, reopen it, and check
    the values arrive under the new names."""
    path = os.path.join(tempfile.mkdtemp(prefix="expn_old_"), "old.blend")
    mesh = bpy.data.meshes.new("old_mesh")
    obj = bpy.data.objects.new("OldObject", mesh)
    bpy.context.scene.collection.objects.link(obj)
    system = obj.bl_system_properties_get(do_create=True)
    system[OLD + "expression"] = "def f(P, t):\n    return vec3(0.0, 0.0, 2.0)\n"
    system[OLD + "apply_mode"] = 1
    scene_sys = bpy.context.scene.bl_system_properties_get(do_create=True)
    scene_sys[OLD + "group_expression"] = "def g(x):\n    return x * 2.0\n"
    tree = bpy.data.node_groups.new("OldTree", "GeometryNodeTree")
    tree.use_fake_user = True
    tree[OLD + "source"] = "def h(x):\n    return x\n"
    tree[OLD + "params"] = "[]"
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    obj = bpy.data.objects["OldObject"]
    tree = bpy.data.node_groups["OldTree"]
    check("old file: object expression migrated",
          obj.expressnode_expression.startswith("def f(P, t):"), repr(obj.expressnode_expression))
    check("old file: apply mode migrated", obj.expressnode_apply_mode == "absolute",
          obj.expressnode_apply_mode)
    check("old file: scene group expression migrated",
          bpy.context.scene.expressnode_group_expression.startswith("def g(x):"))
    check("old file: node-tree markers migrated",
          tree.get("expressnode_source", "").startswith("def h(x):")
          and "expressnode_params" in tree.keys()
          and OLD + "source" not in tree.keys())


def main():
    zip_path = sys.argv[sys.argv.index("--") + 1]
    if not _sandboxed():
        done()
        return

    result = bpy.ops.extensions.package_install_files(
        filepath=zip_path, repo="user_default", enable_on_install=True)
    check("installs as an extension from the zip", result == {"FINISHED"}, str(result))
    name = _module_name()
    check("installed under the user extensions repository",
          name is not None and name.startswith("bl_ext."), str(name))
    check("enables with no errors",
          name is not None and addon_utils.check(name)[1], str(name))
    check("both shapes registered",
          hasattr(bpy.ops.expressnode, "recompile")
          and hasattr(bpy.ops.expressnode, "add_expression_group")
          and hasattr(bpy.types, "EXPRESSNODE_PT_panel")
          and hasattr(bpy.types, "EXPRESSNODE_PT_group_panel"))

    # The installed copy works end to end.
    mesh = bpy.data.meshes.new("m")
    mesh.vertices.add(3)
    mesh.vertices.foreach_set("co", [0, 0, 0, 1, 0, 0, 0, 1, 0])
    obj = bpy.data.objects.new("o", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.expressnode_expression = "def f(P, t):\n    return vec3(0.0, 0.0, 1.0)\n"
    result = bpy.ops.expressnode.recompile()
    dg = bpy.context.evaluated_depsgraph_get()
    zs = [v.co.z for v in obj.evaluated_get(dg).to_mesh().vertices]
    check("installed extension compiles and runs an expression",
          result == {"FINISHED"} and all(abs(z - 1.0) < 1e-6 for z in zs), f"{result}, z = {zs}")

    import expressnode
    check("other add-ons can import it as `expressnode`",
          "extensions" in expressnode.__file__.replace("\\", "/"), expressnode.__file__)
    from expressnode.backend.pipeline import build_in_blender  # noqa: F401  (CodeNodes does this)
    old_name = __import__("coding" + "_nodes.backend.pipeline", fromlist=["x"])
    check("and by its old name, for older CodeNodes", hasattr(old_name, "build_in_blender"))

    _old_file_round_trip()

    addon_utils.disable(name)
    check("disables cleanly", not hasattr(bpy.types, "EXPRESSNODE_PT_panel"))
    check("blender version", True, bpy.app.version_string)
    done()


main()
