"""Expression Modifier (Shape A).

The Blender-facing surface: an object property holding the expression
text, an operator that recompiles it into a Geometry Nodes modifier, and
a panel. All `bpy` use is lazy so this module imports cleanly headlessly;
the classes are built at register() time.

Verified in Blender per the M3 checklist in TESTING.md.
"""

from __future__ import annotations

DEFAULT_EXPRESSION = (
    "def ripple(P, t, freq=6.0, amp=0.3):\n"
    "    return vec3(0.0, 0.0, sin(P.x * freq + t) * amp)\n"
)

MODIFIER_NAME = "CodingNodesExpression"
_classes: list = []


def _apply(obj, source: str) -> str:
    """Compile + plan + execute + attach a modifier. Returns "" on
    success or an error string for the panel to display."""
    from coding_nodes.frontend.errors import CompileError
    from coding_nodes.backend.pipeline import build_in_blender

    try:
        # A modifier needs a Geometry-in/out tree; "offset" wraps the
        # expression group and applies Result as a Set Position offset.
        tree = build_in_blender(source, apply_mode="offset")
    except CompileError as e:
        return str(e)
    except Exception as e:  # surface, don't crash the UI
        return f"{type(e).__name__}: {e}"

    mod = obj.modifiers.get(MODIFIER_NAME)
    if mod is None:
        mod = obj.modifiers.new(MODIFIER_NAME, "NODES")
    mod.node_group = tree
    return ""


def _build_classes():
    import bpy

    class CN_OT_recompile(bpy.types.Operator):
        bl_idname = "coding_nodes.recompile"
        bl_label = "Recompile Expression"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            obj = context.active_object
            if obj is None:
                self.report({"ERROR"}, "No active object")
                return {"CANCELLED"}
            err = _apply(obj, obj.coding_nodes_expression)
            obj.coding_nodes_error = err
            if err:
                self.report({"WARNING"}, "Compile error (see panel)")
                return {"CANCELLED"}
            self.report({"INFO"}, "Expression compiled")
            return {"FINISHED"}

    class CN_PT_panel(bpy.types.Panel):
        bl_idname = "CN_PT_panel"
        bl_label = "Expression Nodes"
        bl_space_type = "PROPERTIES"
        bl_region_type = "WINDOW"
        bl_context = "modifier"

        def draw(self, context):
            layout = self.layout
            obj = context.active_object
            if obj is None:
                layout.label(text="No active object")
                return
            layout.prop(obj, "coding_nodes_expression", text="")
            layout.operator("coding_nodes.recompile", icon="FILE_REFRESH")
            err = getattr(obj, "coding_nodes_error", "")
            if err:
                box = layout.box()
                for line in err.splitlines():
                    box.label(text=line, icon="ERROR")

    return [CN_OT_recompile, CN_PT_panel]


def register():
    import bpy
    global _classes
    bpy.types.Object.coding_nodes_expression = bpy.props.StringProperty(
        name="Expression", default=DEFAULT_EXPRESSION,
    )
    bpy.types.Object.coding_nodes_error = bpy.props.StringProperty(
        name="Compile Error", default="",
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
    del bpy.types.Object.coding_nodes_expression
    del bpy.types.Object.coding_nodes_error
