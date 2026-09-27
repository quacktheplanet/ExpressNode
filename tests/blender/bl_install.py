"""Install the packaged add-on zip and enable it (TESTING.md 5.1).

    BLENDER_USER_RESOURCES=<temp dir> \\
    blender -b --factory-startup --python tests/blender/bl_install.py -- <zip>

Run it with Blender's user folders pointed at a temporary directory (the
runner does this): the script refuses to install anywhere else, so a
real Blender profile is never touched.
"""

from __future__ import annotations

import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import check, done  # noqa: E402

import bpy  # noqa: E402


def main():
    zip_path = sys.argv[sys.argv.index("--") + 1]
    scripts = pathlib.Path(bpy.utils.user_resource("SCRIPTS")).resolve()
    sandbox = os.environ.get("EXPN_SANDBOX")
    if not sandbox or not str(scripts).startswith(
            str(pathlib.Path(sandbox).resolve())):
        check("install sandboxed", False,
              f"user scripts folder {scripts} is not inside EXPN_SANDBOX; "
              "refusing to install into a real profile")
        done()
        return
    check("install sandboxed", True, str(scripts))

    result = bpy.ops.preferences.addon_install(filepath=zip_path,
                                               overwrite=True)
    check("5.1 Install from Disk accepts the zip", result == {"FINISHED"},
          str(result))
    installed = scripts / "addons" / "coding_nodes_addon" / "__init__.py"
    check("5.1 installed as one package folder", installed.exists(),
          str(installed))
    result = bpy.ops.preferences.addon_enable(module="coding_nodes_addon")
    check("5.1 enables with no errors", result == {"FINISHED"}, str(result))
    check("5.1 both shapes registered (no sys.path setup needed)",
          hasattr(bpy.ops.coding_nodes, "recompile")
          and hasattr(bpy.ops.coding_nodes, "add_expression_group")
          and hasattr(bpy.types, "CN_PT_panel")
          and hasattr(bpy.types, "CN_PT_group_panel"))

    # The installed copy works end to end.
    mesh = bpy.data.meshes.new("m")
    mesh.vertices.add(3)
    mesh.vertices.foreach_set("co", [0, 0, 0, 1, 0, 0, 0, 1, 0])
    obj = bpy.data.objects.new("o", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.coding_nodes_expression = "def f(P, t):\n    return vec3(0.0, 0.0, 1.0)\n"
    result = bpy.ops.coding_nodes.recompile()
    dg = bpy.context.evaluated_depsgraph_get()
    zs = [v.co.z for v in obj.evaluated_get(dg).to_mesh().vertices]
    check("installed add-on compiles and runs an expression",
          result == {"FINISHED"} and all(abs(z - 1.0) < 1e-6 for z in zs),
          f"{result}, z = {zs}")
    import coding_nodes
    check("the installed package is the one in use",
          "coding_nodes_addon" in coding_nodes.__file__, coding_nodes.__file__)

    result = bpy.ops.preferences.addon_disable(module="coding_nodes_addon")
    check("disables cleanly", result == {"FINISHED"}
          and not hasattr(bpy.types, "CN_PT_panel"), str(result))
    check("blender version", True, bpy.app.version_string)
    done()


main()
