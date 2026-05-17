"""Expression Node Group (Shape B).

A node group the user drops into any existing Geometry Nodes tree via an
operator. It shares the M3 pipeline exactly — compile → plan → execute —
the only new surface is: build the expression group, then insert a
`GeometryNodeGroup` node pointing at it into the *active* node editor.

All `bpy` use is lazy; classes are built at register() time so the
module imports cleanly headlessly. Verified in Blender per the M4
checklist in TESTING.md.

Shape A (modifier) and Shape B (this) produce the same node tree from
the same compiler. The difference is purely where the result lands: a
modifier on an object, vs a group node inside a tree the user is
already editing.
"""

from __future__ import annotations

DEFAULT_EXPRESSION = (
    "def offset(P, t, amp=0.3):\n"
    "    return vec3(0.0, 0.0, sin(P.x * 6.0 + t) * amp)\n"
)

_classes: list = []


def _build_group_tree(source: str):
    """Compile + plan + execute, returning the root NodeTree to reference.
    Raises CompileError (caught by the operator) on bad syntax."""
    from coding_nodes.backend.pipeline import build_in_blender
    return build_in_blender(source)


def _build_classes():
    import bpy

    class CN_OT_add_expression_group(bpy.types.Operator):
        bl_idname = "coding_nodes.add_expression_group"
        bl_label = "Add Expression Node Group"
        bl_description = (
            "Compile an expression and drop it into the active node tree"
        )
        bl_options = {"REGISTER", "UNDO"}

        @classmethod
        def poll(cls, context):
            space = context.space_data
            return (space is not None
                    and getattr(space, "type", None) == "NODE_EDITOR"
                    and getattr(space, "edit_tree", None) is not None)

        def execute(self, context):
            from coding_nodes.frontend.errors import CompileError
            scene = context.scene
            source = scene.coding_nodes_group_expression
            try:
                tree = _build_group_tree(source)
            except CompileError as e:
                scene.coding_nodes_group_error = str(e)
                self.report({"WARNING"}, "Compile error (see panel)")
                return {"CANCELLED"}
            except Exception as e:
                scene.coding_nodes_group_error = f"{type(e).__name__}: {e}"
                self.report({"ERROR"}, "Build failed (see panel)")
                return {"CANCELLED"}

            scene.coding_nodes_group_error = ""
            edit_tree = context.space_data.edit_tree
            gnode = edit_tree.nodes.new("GeometryNodeGroup")
            gnode.node_tree = tree
            gnode.label = tree.name
            gnode["coding_nodes_source"] = source
            # place near the 2D cursor / origin
            gnode.location = (0.0, 0.0)
            self.report({"INFO"}, f"Added {tree.name}")
            return {"FINISHED"}

    class CN_PT_group_panel(bpy.types.Panel):
        bl_idname = "CN_PT_group_panel"
        bl_label = "Coding Nodes Expression Group"
        bl_space_type = "NODE_EDITOR"
        bl_region_type = "UI"
        bl_category = "Coding Nodes"

        @classmethod
        def poll(cls, context):
            return getattr(context.space_data, "type", None) == "NODE_EDITOR"

        def draw(self, context):
            layout = self.layout
            scene = context.scene
            layout.label(text="Drop a Python expression as a group node:")
            layout.prop(scene, "coding_nodes_group_expression", text="")
            layout.operator("coding_nodes.add_expression_group",
                             icon="NODETREE")
            err = getattr(scene, "coding_nodes_group_error", "")
            if err:
                box = layout.box()
                for line in err.splitlines():
                    box.label(text=line, icon="ERROR")

    return [CN_OT_add_expression_group, CN_PT_group_panel]


def register():
    import bpy
    global _classes
    bpy.types.Scene.coding_nodes_group_expression = bpy.props.StringProperty(
        name="Group Expression", default=DEFAULT_EXPRESSION,
    )
    bpy.types.Scene.coding_nodes_group_error = bpy.props.StringProperty(
        name="Group Compile Error", default="",
    )
    _classes = _build_classes()
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    import bpy
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _classes.clear()
    del bpy.types.Scene.coding_nodes_group_expression
    del bpy.types.Scene.coding_nodes_group_error
