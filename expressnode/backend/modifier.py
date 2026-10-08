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

# The modifier ExpressNode adds and finds again. Files from the old add-on
# (which named it "CodingNodesExpression") are renamed on load: see migrate.py.
MODIFIER_NAME = "ExpressNode"
APPLY_MODE_ITEMS = [
    ("offset", "Offset", "Move each point by the expression's result"),
    ("absolute", "Absolute", "Place each point at the expression's result"),
    ("normal", "Normal", "Push each point along its normal by the expression's result (a number)"),
]
_classes: list = []


def _input_items(tree):
    return [item for item in tree.interface.items_tree
            if item.item_type == "SOCKET" and item.in_out == "INPUT"
            and item.socket_type != "NodeSocketGeometry"]


def get_input(mod, ident):
    """A Geometry Nodes modifier input's value (5.2 moved inputs from ID properties to RNA)."""
    if hasattr(mod, "properties"):
        return getattr(mod.properties.inputs, ident).value
    return mod[ident]


def set_input(mod, ident, value):
    if hasattr(mod, "properties"):
        getattr(mod.properties.inputs, ident).value = value
    else:
        mod[ident] = value


def _modifier_values(mod) -> dict:
    """name -> value for the modifier's current expression inputs."""
    values = {}
    tree = mod.node_group if mod is not None else None
    if tree is None:
        return values
    for item in _input_items(tree):
        try:
            v = get_input(mod, item.identifier)
        except (KeyError, AttributeError):
            continue
        values[item.name] = list(v) if hasattr(v, "to_list") or type(v).__name__ == "bpy_prop_array" else v
    return values


def _apply(obj, source: str, apply_mode: str = "offset",
           inline_threshold: int = 3) -> str:
    """Compile + plan + execute + attach a modifier. Returns "" on
    success or an error string for the panel to display.

    Values the user tuned on the modifier survive the rebuild when the
    parameter still exists with the same type (params.reconcile).
    """
    import json
    from ..frontend.errors import CompileError
    from ..backend.params import reconcile
    from ..backend.pipeline import build_in_blender

    mod = obj.modifiers.get(MODIFIER_NAME)
    old_values = _modifier_values(mod)
    old_params = []
    if mod is not None and mod.node_group is not None:
        old_params = json.loads(mod.node_group.get("expressnode_params",
                                                   "[]"))
    try:
        # A modifier needs a Geometry-in/out tree; the wrapper applies
        # the Result as a Set Position offset or absolute position. One
        # set of trees per object, so objects don't overwrite each other.
        tree = build_in_blender(source, apply_mode=apply_mode,
                                inline_threshold=inline_threshold,
                                suffix=f" [{obj.name}]")
    except CompileError as e:
        return str(e)
    except Exception as e:  # surface, don't crash the UI
        return f"{type(e).__name__}: {e}"

    if mod is None:
        mod = obj.modifiers.new(MODIFIER_NAME, "NODES")
    mod.node_group = tree
    new_params = json.loads(tree.get("expressnode_params", "[]"))
    values = reconcile([tuple(p) for p in old_params],
                       [tuple(p) for p in new_params], old_values)
    for item in _input_items(tree):
        if item.name in values and values[item.name] is not None:
            try:
                set_input(mod, item.identifier, values[item.name])
            except (TypeError, ValueError):
                pass
    obj.update_tag()
    return ""


def _build_classes():
    import bpy

    class EXPRESSNODE_OT_recompile(bpy.types.Operator):
        bl_idname = "expressnode.recompile"
        bl_label = "Recompile Expression"
        bl_options = {"REGISTER", "UNDO"}

        def execute(self, context):
            obj = context.active_object
            if obj is None:
                self.report({"ERROR"}, "No active object")
                return {"CANCELLED"}
            err = _apply(obj, obj.expressnode_expression,
                         apply_mode=obj.expressnode_apply_mode)
            obj.expressnode_error = err
            if err:
                self.report({"WARNING"}, "Compile error (see panel)")
                return {"CANCELLED"}
            self.report({"INFO"}, "Expression compiled")
            return {"FINISHED"}

    class EXPRESSNODE_PT_panel(bpy.types.Panel):
        bl_idname = "EXPRESSNODE_PT_panel"
        bl_label = "ExpressNode"
        bl_space_type = "PROPERTIES"
        bl_region_type = "WINDOW"
        bl_context = "modifier"

        def draw(self, context):
            layout = self.layout
            obj = context.active_object
            if obj is None:
                layout.label(text="No active object")
                return
            layout.prop(obj, "expressnode_expression", text="")
            layout.prop(obj, "expressnode_apply_mode", expand=True)
            layout.operator("expressnode.recompile", icon="FILE_REFRESH")
            err = getattr(obj, "expressnode_error", "")
            if err:
                box = layout.box()
                for line in err.splitlines():
                    box.label(text=line, icon="ERROR")

    return [EXPRESSNODE_OT_recompile, EXPRESSNODE_PT_panel]


def register():
    import bpy
    global _classes
    bpy.types.Object.expressnode_expression = bpy.props.StringProperty(
        name="Expression", default=DEFAULT_EXPRESSION,
    )
    bpy.types.Object.expressnode_error = bpy.props.StringProperty(
        name="Compile Error", default="",
    )
    bpy.types.Object.expressnode_apply_mode = bpy.props.EnumProperty(
        name="Apply", items=APPLY_MODE_ITEMS, default="offset",
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
    del bpy.types.Object.expressnode_expression
    del bpy.types.Object.expressnode_error
    del bpy.types.Object.expressnode_apply_mode
