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
    from ..backend.pipeline import build_in_blender
    return build_in_blender(source)


def update_group(old_tree, source: str) -> str:
    """Rebuild an expression group from new source. The tree is rebuilt
    in place when the function name is unchanged; otherwise the new tree
    replaces the old one in every group node that used it. Returns "" or
    an error message."""
    import bpy
    from ..frontend.errors import CompileError
    from ..backend.pipeline import build_in_blender, plan_source
    try:
        plan = plan_source(source)
        suffix = None
        if old_tree.name.startswith(plan.root_name):
            suffix = old_tree.name[len(plan.root_name):]
        tree = build_in_blender(source, suffix=suffix)
    except CompileError as e:
        return str(e)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    if tree != old_tree:
        for group in bpy.data.node_groups:
            for n in group.nodes:
                if (n.bl_idname == "GeometryNodeGroup"
                        and n.node_tree == old_tree):
                    n.node_tree = tree
                    n.label = tree.name
    return ""


def _build_classes():
    import bpy

    class EXPRESSNODE_OT_add_expression_group(bpy.types.Operator):
        bl_idname = "expressnode.add_expression_group"
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
            from ..frontend.errors import CompileError
            scene = context.scene
            source = scene.expressnode_group_expression
            try:
                tree = _build_group_tree(source)
            except CompileError as e:
                scene.expressnode_group_error = str(e)
                self.report({"WARNING"}, "Compile error (see panel)")
                return {"CANCELLED"}
            except Exception as e:
                scene.expressnode_group_error = f"{type(e).__name__}: {e}"
                self.report({"ERROR"}, "Build failed (see panel)")
                return {"CANCELLED"}

            scene.expressnode_group_error = ""
            edit_tree = context.space_data.edit_tree
            gnode = edit_tree.nodes.new("GeometryNodeGroup")
            gnode.node_tree = tree
            gnode.label = tree.name
            gnode["expressnode_source"] = source
            gnode.location = tuple(getattr(context.space_data,
                                           "cursor_location", (0.0, 0.0)))
            for n in edit_tree.nodes:
                n.select = False
            gnode.select = True
            edit_tree.nodes.active = gnode
            self.report({"INFO"}, f"Added {tree.name}")
            return {"FINISHED"}

    class EXPRESSNODE_OT_update_expression_group(bpy.types.Operator):
        bl_idname = "expressnode.update_expression_group"
        bl_label = "Update Selected Group"
        bl_description = (
            "Recompile the active expression group node from the text "
            "above; every node using that group updates"
        )
        bl_options = {"REGISTER", "UNDO"}

        @classmethod
        def poll(cls, context):
            space = context.space_data
            tree = getattr(space, "edit_tree", None)
            node = tree.nodes.active if tree is not None else None
            return (node is not None
                    and node.bl_idname == "GeometryNodeGroup"
                    and node.node_tree is not None
                    and "expressnode_source" in node.node_tree)

        def execute(self, context):
            scene = context.scene
            node = context.space_data.edit_tree.nodes.active
            err = update_group(node.node_tree,
                               scene.expressnode_group_expression)
            scene.expressnode_group_error = err
            if err:
                self.report({"WARNING"}, "Compile error (see panel)")
                return {"CANCELLED"}
            node["expressnode_source"] = scene.expressnode_group_expression
            self.report({"INFO"}, f"Updated {node.node_tree.name}")
            return {"FINISHED"}

    class EXPRESSNODE_PT_group_panel(bpy.types.Panel):
        bl_idname = "EXPRESSNODE_PT_group_panel"
        bl_label = "ExpressNode Group"
        bl_space_type = "NODE_EDITOR"
        bl_region_type = "UI"
        bl_category = "ExpressNode"

        @classmethod
        def poll(cls, context):
            return getattr(context.space_data, "type", None) == "NODE_EDITOR"

        def draw(self, context):
            layout = self.layout
            scene = context.scene
            layout.label(text="Drop a Python expression as a group node:")
            layout.prop(scene, "expressnode_group_expression", text="")
            layout.operator("expressnode.add_expression_group",
                             icon="NODETREE")
            layout.operator("expressnode.update_expression_group",
                             icon="FILE_REFRESH")
            err = getattr(scene, "expressnode_group_error", "")
            if err:
                box = layout.box()
                for line in err.splitlines():
                    box.label(text=line, icon="ERROR")

    return [EXPRESSNODE_OT_add_expression_group, EXPRESSNODE_OT_update_expression_group,
            EXPRESSNODE_PT_group_panel]


def register():
    import bpy
    global _classes
    bpy.types.Scene.expressnode_group_expression = bpy.props.StringProperty(
        name="Group Expression", default=DEFAULT_EXPRESSION,
    )
    bpy.types.Scene.expressnode_group_error = bpy.props.StringProperty(
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
    del bpy.types.Scene.expressnode_group_expression
    del bpy.types.Scene.expressnode_group_error
