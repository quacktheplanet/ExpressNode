"""Execute an EmissionPlan as real Blender Geometry Nodes datablocks.

`bpy` is imported lazily inside functions, so this module imports cleanly
without Blender (the headless tests import it but never call execute()).
Correctness here is verified in Blender by `tests/blender/bl_gn.py`, which
evaluates the built trees and compares them with the numpy oracle.

The executor is a two-pass walk of the plan:
  pass 1  create (or reuse) every GroupDef as a NodeTree with its
          interface, then build the nodes and group-instance nodes,
  pass 2  resolve every PlannedLink to concrete sockets and connect them.

Every planned node is built into a `_Built`: the socket its value comes
out of, plus, for each of its abstract inputs (in the eval node's
declared order), the real Blender input sockets that value feeds. Most
ops are one node with inputs in declared order; some expand into a few
nodes (floored modulo, floor division, reflect, <=, ...) so the numbers
match the oracle exactly.
"""

from __future__ import annotations

import math
from typing import Any

from coding_nodes.backend.plan import (
    EmissionPlan,
    Endpoint,
    GroupDef,
    PlannedNode,
)

_SOCKET_BL = {
    "geometry": "NodeSocketGeometry",
    "float": "NodeSocketFloat",
    "int": "NodeSocketInt",
    "vector": "NodeSocketVector",
    "color": "NodeSocketColor",
    "string": "NodeSocketString",
}

_SWITCH_TYPE = {"float": "FLOAT", "int": "INT", "vector": "VECTOR",
                "color": "RGBA"}

_ATTR_TYPE = {
    "float": "FLOAT", "int": "INT", "bool": "BOOLEAN",
    "vec3": "FLOAT_VECTOR", "vec2": "FLOAT_VECTOR",
    "vec4": "FLOAT_COLOR", "color": "FLOAT_COLOR",
    # socket-type spellings (set_attr records the value's socket type)
    "vector": "FLOAT_VECTOR",
}

_OBJ_FIELD = {"position": "Location", "scale": "Scale",
              "rotation": "Rotation"}


class _Built:
    """A planned node realised in a tree."""

    def __init__(self, output, inputs: list[list[Any]]):
        self.output = output
        self.inputs = inputs


# ---------------------------------------------------------------------------
# Trees and interfaces
# ---------------------------------------------------------------------------

def _interface_spec(gdef: GroupDef) -> list[tuple[str, str, str]]:
    spec = [("INPUT", n, _SOCKET_BL.get(t, "NodeSocketFloat"))
            for n, t in gdef.inputs]
    spec += [("OUTPUT", n, _SOCKET_BL.get(t, "NodeSocketFloat"))
             for n, t in gdef.outputs]
    return spec


def _current_spec(tree) -> list[tuple[str, str, str]]:
    # Blender lists outputs before inputs; compare inputs then outputs,
    # each in their own order, like _interface_spec.
    items = [(item.in_out, item.name, item.socket_type)
             for item in tree.interface.items_tree
             if item.item_type == "SOCKET"]
    return ([i for i in items if i[0] == "INPUT"]
            + [i for i in items if i[0] == "OUTPUT"])


def _prepare_tree(name: str, gdef: GroupDef, defaults: dict[str, Any]):
    """Return a GeometryNodeTree named `name`, ready to be filled.

    An existing tree of that name is reused in place, so modifiers and
    group nodes that point at it keep pointing at it. Its interface is
    kept when the socket signature is unchanged (links into group nodes
    and tuned modifier values survive), otherwise rebuilt.
    """
    import bpy
    tree = bpy.data.node_groups.get(name)
    if tree is not None and tree.bl_idname != "GeometryNodeTree":
        tree.name = name + "_old"
        tree = None
    if tree is None:
        tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.nodes.clear()

    spec = _interface_spec(gdef)
    if _current_spec(tree) != spec:
        tree.interface.clear()
        for in_out, sname, stype in spec:
            sock = tree.interface.new_socket(name=sname, in_out=in_out,
                                             socket_type=stype)
            if in_out == "INPUT" and sname in defaults:
                _set_default(sock, defaults[sname])
    return tree


def _set_default(sock, value) -> None:
    try:
        if sock.socket_type == "NodeSocketInt":
            sock.default_value = int(value)
        elif sock.socket_type == "NodeSocketVector":
            sock.default_value = tuple(value)[:3]
        else:
            sock.default_value = float(value)
    except (TypeError, ValueError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Socket helpers
# ---------------------------------------------------------------------------

def _out(node, name):
    """The enabled output called `name` (identifier accepted too). Nodes
    like Mix and Vector Math have several outputs with one name, one per
    data type; only the enabled one carries the value."""
    if isinstance(name, int):
        return node.outputs[name]
    for s in node.outputs:
        if s.name == name and s.enabled:
            return s
    for s in node.outputs:
        if s.identifier == name:
            return s
    raise KeyError(f"{node.bl_idname} has no output {name!r}")


def _in(node, name):
    for s in node.inputs:
        if s.name == name and s.enabled:
            return s
    for s in node.inputs:
        if s.identifier == name:
            return s
    raise KeyError(f"{node.bl_idname} has no input {name!r}")


def _math(tree, operation):
    n = tree.nodes.new("ShaderNodeMath")
    n.operation = operation
    return n


def _vmath(tree, operation):
    n = tree.nodes.new("ShaderNodeVectorMath")
    n.operation = operation
    return n


def _one_minus(tree, node):
    """1 - node.outputs[0]; returns the subtract node."""
    sub = _math(tree, "SUBTRACT")
    sub.inputs[0].default_value = 1.0
    tree.links.new(node.outputs[0], sub.inputs[1])
    return sub


def _positional(node, count: int) -> list[list[Any]]:
    return [[node.inputs[i]] for i in range(count)]


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

class _Context:
    """Per-execute state shared by the builders."""

    def __init__(self):
        import bpy
        scene = bpy.context.scene
        self.fps = scene.render.fps / (scene.render.fps_base or 1.0)
        self._time_nodes: dict[int, Any] = {}

    def time_node(self, tree):
        key = tree.as_pointer()
        if key not in self._time_nodes:
            self._time_nodes[key] = tree.nodes.new(
                "GeometryNodeInputSceneTime")
        return self._time_nodes[key]


def _build_node(tree, pn: PlannedNode, ctx: _Context) -> _Built:
    count = len(pn.input_names)
    op = pn.op

    if op in ("constant.float", "constant.int", "constant.bool"):
        node = tree.nodes.new("ShaderNodeValue")
        val = pn.params.get("value", 0.0)
        node.outputs[0].default_value = float(
            1.0 if val is True else 0.0 if val is False else val)
        return _Built(node.outputs[0], [])

    if op == "input.delta_time":
        node = tree.nodes.new("ShaderNodeValue")
        node.outputs[0].default_value = 1.0 / ctx.fps
        node.label = "Delta Time"
        return _Built(node.outputs[0], [])

    if op == "math.neg":
        node = _math(tree, "MULTIPLY")
        node.inputs[1].default_value = -1.0
        return _Built(node.outputs[0], [[node.inputs[0]]])

    if op == "vec.neg":
        node = _vmath(tree, "SCALE")
        _in(node, "Scale").default_value = -1.0
        return _Built(_out(node, "Vector"), [[node.inputs[0]]])

    if op == "math.floordiv":
        div = _math(tree, "DIVIDE")
        flo = _math(tree, "FLOOR")
        tree.links.new(div.outputs[0], flo.inputs[0])
        return _Built(flo.outputs[0], [[div.inputs[0]], [div.inputs[1]]])

    if op == "vec.floordiv":
        div = _vmath(tree, "DIVIDE")
        flo = _vmath(tree, "FLOOR")
        tree.links.new(_out(div, "Vector"), flo.inputs[0])
        return _Built(_out(flo, "Vector"),
                      [[div.inputs[0]], [div.inputs[1]]])

    if op == "vec.mod":
        # Floored modulo, a - b * floor(a / b): Vector Math's Modulo is
        # truncated (fmod), which differs for negative operands.
        div = _vmath(tree, "DIVIDE")
        flo = _vmath(tree, "FLOOR")
        mul = _vmath(tree, "MULTIPLY")
        sub = _vmath(tree, "SUBTRACT")
        tree.links.new(_out(div, "Vector"), flo.inputs[0])
        tree.links.new(_out(flo, "Vector"), mul.inputs[0])
        tree.links.new(_out(mul, "Vector"), sub.inputs[1])
        return _Built(_out(sub, "Vector"),
                      [[div.inputs[0], sub.inputs[0]],
                       [div.inputs[1], mul.inputs[1]]])

    if op == "vec.reflect":
        # v - 2 dot(v, n) n. Vector Math's Reflect normalizes n first,
        # which the language (like GLSL/OSL/WGSL) does not.
        dot = _vmath(tree, "DOT_PRODUCT")
        two = _math(tree, "MULTIPLY")
        two.inputs[1].default_value = 2.0
        scl = _vmath(tree, "SCALE")
        sub = _vmath(tree, "SUBTRACT")
        tree.links.new(_out(dot, "Value"), two.inputs[0])
        tree.links.new(two.outputs[0], _in(scl, "Scale"))
        tree.links.new(_out(scl, "Vector"), sub.inputs[1])
        return _Built(_out(sub, "Vector"),
                      [[dot.inputs[0], sub.inputs[0]],
                       [dot.inputs[1], scl.inputs[0]]])

    if op == "math.clamp":
        node = tree.nodes.new("ShaderNodeClamp")
        node.clamp_type = "MINMAX"
        return _Built(node.outputs[0], _positional(node, 3))

    if op == "math.mix":
        # mix(a, b, t) = a + (b - a) * t, t not clamped.
        node = tree.nodes.new("ShaderNodeMix")
        node.clamp_factor = False
        is_vec = "vector" in pn.input_types[:2] or pn.output_type == "vector"
        if is_vec:
            node.data_type = "VECTOR"
            if pn.input_types[2:3] == ("vector",):
                node.factor_mode = "NON_UNIFORM"
                fac = _in(node, "Factor_Vector")
            else:
                node.factor_mode = "UNIFORM"
                fac = _in(node, "Factor_Float")
            a, b = _in(node, "A_Vector"), _in(node, "B_Vector")
            out = _out(node, "Result_Vector")
        else:
            node.data_type = "FLOAT"
            fac = _in(node, "Factor_Float")
            a, b = _in(node, "A_Float"), _in(node, "B_Float")
            out = _out(node, "Result_Float")
        return _Built(out, [[a], [b], [fac]])

    if op == "math.smoothstep":
        # smoothstep(lo, hi, x)
        node = tree.nodes.new("ShaderNodeMapRange")
        node.data_type = "FLOAT"
        node.interpolation_type = "SMOOTHSTEP"
        node.clamp = True
        node.inputs["To Min"].default_value = 0.0
        node.inputs["To Max"].default_value = 1.0
        return _Built(node.outputs[0],
                      [[node.inputs[1]], [node.inputs[2]], [node.inputs[0]]])

    if op == "math.step":
        # step(edge, x) = x >= edge = 1 - (x < edge)
        lt = _math(tree, "LESS_THAN")
        sub = _one_minus(tree, lt)
        return _Built(sub.outputs[0], [[lt.inputs[1]], [lt.inputs[0]]])

    if op in ("compare.le", "compare.ge", "compare.ne"):
        base = {"compare.le": "GREATER_THAN", "compare.ge": "LESS_THAN",
                "compare.ne": "COMPARE"}[op]
        cmp = _math(tree, base)
        if base == "COMPARE":
            cmp.inputs[2].default_value = 0.0
        sub = _one_minus(tree, cmp)
        return _Built(sub.outputs[0], [[cmp.inputs[0]], [cmp.inputs[1]]])

    if op == "compare.eq":
        cmp = _math(tree, "COMPARE")
        cmp.inputs[2].default_value = 0.0
        return _Built(cmp.outputs[0], _positional(cmp, 2))

    if op == "flow.if":
        node = tree.nodes.new("GeometryNodeSwitch")
        node.input_type = _SWITCH_TYPE.get(pn.output_type, "FLOAT")
        return _Built(node.outputs[0],
                      [[_in(node, "Switch")], [_in(node, "True")],
                       [_in(node, "False")]])

    if op == "texture.noise":
        node = tree.nodes.new("ShaderNodeTexNoise")
        node.noise_dimensions = "4D"
        node.inputs["Scale"].default_value = 1.0
        node.inputs["Detail"].default_value = 0.0
        node.inputs["Distortion"].default_value = 0.0
        tree.links.new(_out(ctx.time_node(tree), "Seconds"),
                       node.inputs["W"])
        return _Built(node.outputs[0],
                      [[node.inputs["Vector"]], [node.inputs["Scale"]]])

    if op == "texture.voronoi":
        node = tree.nodes.new("ShaderNodeTexVoronoi")
        node.inputs["Scale"].default_value = 1.0
        return _Built(node.outputs[0],
                      [[node.inputs["Vector"]], [node.inputs["Scale"]]])

    if op == "attr.read":
        node = tree.nodes.new("GeometryNodeInputNamedAttribute")
        node.data_type = _ATTR_TYPE.get(pn.params.get("dtype", "float"),
                                        "FLOAT")
        node.inputs["Name"].default_value = pn.params.get("name", "")
        return _Built(_out(node, "Attribute"), [])

    if op == "obj.read":
        import bpy
        node = tree.nodes.new("GeometryNodeObjectInfo")
        node.transform_space = "ORIGINAL"
        node.inputs["Object"].default_value = bpy.data.objects.get(
            pn.params.get("object", ""))
        field = _OBJ_FIELD.get(pn.params.get("field", "position"),
                               "Location")
        out = _out(node, field)
        if field == "Rotation":
            conv = tree.nodes.new("FunctionNodeRotationToEuler")
            tree.links.new(out, conv.inputs[0])
            out = conv.outputs[0]
        return _Built(out, [])

    if op in ("vec.combine2", "vec.combine4"):
        node = tree.nodes.new("ShaderNodeCombineXYZ")
        ins = _positional(node, min(count, 3))
        while len(ins) < count:     # vec4's w has nowhere to go
            ins.append([])
        return _Built(node.outputs[0], ins)

    if op == "vec.component.w":
        node = tree.nodes.new("ShaderNodeSeparateXYZ")
        return _Built(_out(node, "Z"), [[node.inputs[0]]])

    if op == "vec.swizzle":
        sep = tree.nodes.new("ShaderNodeSeparateXYZ")
        comb = tree.nodes.new("ShaderNodeCombineXYZ")
        pattern = pn.params.get("pattern", "xyz")
        comp_out = {"x": "X", "y": "Y", "z": "Z", "w": "Z"}
        for i, ch in enumerate(pattern[:3]):
            tree.links.new(sep.outputs[comp_out[ch]], comb.inputs[i])
        return _Built(comb.outputs[0], [[sep.inputs[0]]])

    if op == "modifier.set_position":
        node = tree.nodes.new("GeometryNodeSetPosition")
        return _Built(_out(node, "Geometry"),
                      [[_in(node, n)] for n in pn.input_names])

    if op == "modifier.normal_offset":
        # Normal * distance, for the Normal apply mode
        normal = tree.nodes.new("GeometryNodeInputNormal")
        scale = tree.nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        tree.links.new(normal.outputs[0], scale.inputs[0])
        return _Built(scale.outputs[0], [[_in(scale, "Scale")]])

    if pn.emitter_kind == "simple":
        # One node, inputs in declared order. Checked last, so ops with a
        # handler above (neg, clamp, ...) never fall through to here.
        node = tree.nodes.new(pn.bl_idname)
        for k, v in pn.settings.items():
            setattr(node, k, v)
        if op == "math.log":
            # Blender's Logarithm takes a base; the language means ln.
            node.inputs[1].default_value = math.e
        return _Built(_out(node, pn.output_socket), _positional(node, count))

    raise NotImplementedError(
        f"The Geometry Nodes backend has no builder for op {op!r}.")


def _build_store(tree, name: str, dtype: str):
    node = tree.nodes.new("GeometryNodeStoreNamedAttribute")
    node.data_type = _ATTR_TYPE.get(dtype, "FLOAT")
    node.domain = "POINT"
    node.inputs["Name"].default_value = name
    return node


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

def execute(plan: EmissionPlan, suffix: str = "", source: str = ""):
    """Build the whole plan as Blender datablocks. Returns the deliverable
    root NodeTree. Requires Blender.

    `suffix` is appended to every tree name, so separate uses (one per
    object for the modifier) don't overwrite each other's trees. `source`
    is recorded on the root trees so a later rebuild can tell whether an
    existing tree came from the same expression.
    """
    ctx = _Context()
    defaults = {name: default for name, _, default in plan.parameters}
    trees: dict[str, Any] = {}
    built: dict[tuple[str, int], _Built] = {}
    instance_handles: dict[tuple[str, int], Any] = {}

    # Pass 1: trees, interfaces, nodes, instances.
    for gname, gdef in plan.groups.items():
        tree = _prepare_tree(gname + suffix, gdef, defaults)
        trees[gname] = tree
        tree.nodes.new("NodeGroupInput")
        out_node = tree.nodes.new("NodeGroupOutput")
        out_node.is_active_output = True

    for gname, gdef in plan.groups.items():
        tree = trees[gname]
        for pn in gdef.nodes:
            built[(gname, pn.local_id)] = _build_node(tree, pn, ctx)
        for inst in gdef.instances:
            gnode = tree.nodes.new("GeometryNodeGroup")
            gnode.node_tree = trees[inst.group_name]
            instance_handles[(gname, inst.instance_id)] = gnode

    # Pass 2: links.
    for gname, gdef in plan.groups.items():
        tree = trees[gname]
        gin = next(n for n in tree.nodes if n.bl_idname == "NodeGroupInput")
        gout = next(n for n in tree.nodes if n.bl_idname == "NodeGroupOutput")
        nodes_by_id = {pn.local_id: pn for pn in gdef.nodes}

        def resolve_out(ep: Endpoint):
            if ep.kind == "group_input":
                return [_out(gin, ep.socket)]
            if ep.kind == "instance":
                return [_out(instance_handles[(gname, ep.ref)], ep.socket)]
            return [built[(gname, ep.ref)].output]

        def resolve_in(ep: Endpoint):
            if ep.kind == "group_output":
                return [_in(gout, ep.socket)]
            if ep.kind == "instance":
                return [_in(instance_handles[(gname, ep.ref)], ep.socket)]
            pn = nodes_by_id[ep.ref]
            if isinstance(ep.socket, int):
                idx = ep.socket
            elif ep.socket in pn.input_names:
                idx = pn.input_names.index(ep.socket)
            else:
                raise KeyError(
                    f"{gname}: {pn.op} has no input {ep.socket!r} "
                    f"(inputs {pn.input_names})")
            return built[(gname, ep.ref)].inputs[idx]

        for link in gdef.links:
            for s in resolve_out(link.src):
                for d in resolve_in(link.dst):
                    tree.links.new(s, d)

    # Attribute writes: the expression group exposes each written value
    # as an extra output; the modifier wrapper stores it on the points.
    # The stores go before Set Position, so the values are computed from
    # the incoming points, like the Result is.
    if plan.modifier_root_name and plan.attr_writes:
        w = trees[plan.modifier_root_name]
        inst = next(n for n in w.nodes if n.bl_idname == "GeometryNodeGroup")
        setpos = next(n for n in w.nodes
                      if n.bl_idname == "GeometryNodeSetPosition")
        geo_link = next(l for l in w.links
                        if l.to_socket == setpos.inputs["Geometry"])
        geo = geo_link.from_socket
        w.links.remove(geo_link)
        for name, dtype in plan.attr_writes:
            store = _build_store(w, name, dtype)
            w.links.new(geo, store.inputs["Geometry"])
            w.links.new(_out(inst, name), _in(store, "Value"))
            geo = store.outputs["Geometry"]
        w.links.new(geo, setpos.inputs["Geometry"])

    for tree in trees.values():
        _layout(tree)
    for gname in {plan.root_name, plan.deliverable_root()}:
        trees[gname]["coding_nodes_source"] = source
    return trees[plan.deliverable_root()]


def tree_name_for(plan: EmissionPlan, source: str) -> str:
    """Suffix for a Shape B build: "" when the expression's tree doesn't
    exist yet or was built from this same source (rebuilt in place),
    else the first free ".001"-style suffix, so an unrelated group that
    happens to share the function name is never overwritten."""
    import bpy
    k = 0
    while True:
        suffix = "" if k == 0 else f".{k:03d}"
        tree = bpy.data.node_groups.get(plan.root_name + suffix)
        if tree is None or tree.get("coding_nodes_source") == source:
            return suffix
        k += 1


def _layout(tree) -> None:
    """Place nodes in columns by link depth so the tree reads left to
    right when opened."""
    depth: dict[Any, int] = {n: 0 for n in tree.nodes}
    for _ in range(len(tree.nodes)):
        changed = False
        for link in tree.links:
            d = depth[link.from_node] + 1
            if d > depth[link.to_node]:
                depth[link.to_node] = d
                changed = True
        if not changed:
            break
    rows: dict[int, int] = {}
    for n in tree.nodes:
        col = depth[n]
        row = rows.get(col, 0)
        rows[col] = row + 1
        n.location = (col * 220.0, -row * 180.0)
