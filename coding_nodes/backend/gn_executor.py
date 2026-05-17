"""Execute an EmissionPlan as real Blender Geometry Nodes datablocks.

`bpy` is imported lazily inside functions, so this module imports cleanly
without Blender (the headless tests import it but never call execute()).
Correctness here is verified in Blender per the M3 checklist in
TESTING.md.

The executor is a straightforward two-pass walk of the plan:
  pass 1  create every GroupDef as a NodeTree with its interface, then
          create the nodes and group-instance nodes inside it,
  pass 2  resolve every PlannedLink to concrete sockets and connect them.

Simple emitters (kind="simple") are built generically from the emitter
descriptor. Complex emitters (kind="complex") have hand-written handlers
below.
"""

from __future__ import annotations

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


def _new_tree(name: str):
    import bpy
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name],
                                    do_unlink=True)
    return bpy.data.node_groups.new(name, "GeometryNodeTree")


def _add_interface(tree, gdef: GroupDef) -> None:
    for sock_name, sock_type in gdef.inputs:
        tree.interface.new_socket(
            name=sock_name, in_out="INPUT",
            socket_type=_SOCKET_BL.get(sock_type, "NodeSocketFloat"),
        )
    for sock_name, sock_type in gdef.outputs:
        tree.interface.new_socket(
            name=sock_name, in_out="OUTPUT",
            socket_type=_SOCKET_BL.get(sock_type, "NodeSocketFloat"),
        )


def _build_node(tree, pn: PlannedNode):
    """Create one bpy node for a PlannedNode. Returns the node."""
    if pn.emitter_kind == "complex":
        return _build_complex(tree, pn)
    node = tree.nodes.new(pn.bl_idname)
    for k, v in pn.settings.items():
        setattr(node, k, v)
    return node


def _build_complex(tree, pn: PlannedNode):
    """Hand-written handlers for ops that aren't a clean 1:1 node.

    Each handler creates the node(s) and configures defaults. Multi-node
    expansions return the node whose output the plan reads from.
    """
    op = pn.op

    if op in ("constant.float", "constant.int", "constant.bool"):
        node = tree.nodes.new("ShaderNodeValue")
        val = pn.params.get("value", 0.0)
        node.outputs[0].default_value = float(
            1.0 if val is True else 0.0 if val is False else val
        )
        return node

    if op == "math.neg":
        node = tree.nodes.new("ShaderNodeMath")
        node.operation = "MULTIPLY"
        node.inputs[1].default_value = -1.0
        return node

    if op == "vec.neg":
        node = tree.nodes.new("ShaderNodeVectorMath")
        node.operation = "SCALE"
        node.inputs["Scale"].default_value = -1.0
        return node

    if op == "math.clamp":
        node = tree.nodes.new("ShaderNodeClamp")
        return node

    if op == "math.mix":
        node = tree.nodes.new("ShaderNodeMix")
        node.data_type = pn.settings.get("data_type", "FLOAT")
        return node

    if op == "math.smoothstep":
        node = tree.nodes.new("ShaderNodeMapRange")
        node.interpolation_type = "SMOOTHSTEP"
        return node

    if op in ("compare.le", "compare.ge", "compare.eq", "compare.ne"):
        node = tree.nodes.new("ShaderNodeMath")
        node.operation = pn.settings.get("operation", "COMPARE")
        return node

    if op == "flow.if":
        node = tree.nodes.new("GeometryNodeSwitch")
        return node

    if op in ("texture.noise",):
        node = tree.nodes.new("ShaderNodeTexNoise")
        node.noise_dimensions = "4D"
        return node

    if op == "texture.voronoi":
        node = tree.nodes.new("ShaderNodeTexVoronoi")
        return node

    if op == "attr.read":
        node = tree.nodes.new("GeometryNodeInputNamedAttribute")
        dtype = pn.params.get("dtype", "float")
        node.data_type = {
            "float": "FLOAT", "int": "INT", "bool": "BOOLEAN",
            "vec3": "FLOAT_VECTOR", "vec2": "FLOAT_VECTOR",
            "vec4": "FLOAT_COLOR", "color": "FLOAT_COLOR",
        }.get(dtype, "FLOAT")
        return node

    if op == "obj.read":
        node = tree.nodes.new("GeometryNodeObjectInfo")
        return node

    if op in ("vec.combine2", "vec.combine4"):
        return tree.nodes.new("ShaderNodeCombineXYZ")

    if op.startswith("vec.component."):
        return tree.nodes.new("ShaderNodeSeparateXYZ")

    if op == "vec.swizzle":
        # Expansion (Separate -> Combine per pattern) is created by the
        # caller via _build_swizzle; placeholder kept for completeness.
        return _build_swizzle(tree, pn)

    if op in ("math.floordiv", "vec.floordiv", "vec.pow"):
        # Two-node expansions; the simple DIVIDE/MULTIPLY node plus a
        # follow-up. For the first cut we emit the primary node; the
        # Blender checklist tracks the exact follow-up wiring.
        node = tree.nodes.new(pn.bl_idname)
        for k, v in pn.settings.items():
            setattr(node, k, v)
        return node

    # Fallback: behave like a simple emitter.
    node = tree.nodes.new(pn.bl_idname or "ShaderNodeMath")
    for k, v in pn.settings.items():
        setattr(node, k, v)
    return node


def _build_swizzle(tree, pn: PlannedNode):
    """vec.swizzle -> SeparateXYZ feeding a CombineXYZ per .pattern.

    Returns the CombineXYZ node (the plan reads its Vector output). The
    SeparateXYZ node is stashed on the combine node so the linker can
    find it.
    """
    sep = tree.nodes.new("ShaderNodeSeparateXYZ")
    comb = tree.nodes.new("ShaderNodeCombineXYZ")
    pattern = pn.params.get("pattern", "xyz")
    comp_out = {"x": "X", "y": "Y", "z": "Z", "w": "Z"}
    comb_in = ["X", "Y", "Z"]
    for i, ch in enumerate(pattern[:3]):
        tree.links.new(sep.outputs[comp_out[ch]], comb.inputs[comb_in[i]])
    comb["__swizzle_separate__"] = sep.name
    return comb


def execute(plan: EmissionPlan):
    """Build the whole plan as Blender datablocks. Returns the root
    NodeTree. Requires Blender."""
    trees: dict[str, Any] = {}
    node_handles: dict[tuple[str, int], Any] = {}     # (group, local_id)
    instance_handles: dict[tuple[str, int], Any] = {}  # (group, inst_id)

    # Pass 1: trees, interfaces, nodes, instances.
    for gname, gdef in plan.groups.items():
        tree = _new_tree(gname)
        trees[gname] = tree
        _add_interface(tree, gdef)
        tree.nodes.new("NodeGroupInput")
        out_node = tree.nodes.new("NodeGroupOutput")
        out_node.is_active_output = True

    for gname, gdef in plan.groups.items():
        tree = trees[gname]
        for pn in gdef.nodes:
            node_handles[(gname, pn.local_id)] = _build_node(tree, pn)
        for inst in gdef.instances:
            gnode = tree.nodes.new("GeometryNodeGroup")
            gnode.node_tree = trees[inst.group_name]
            instance_handles[(gname, inst.instance_id)] = gnode

    # Pass 2: links.
    for gname, gdef in plan.groups.items():
        tree = trees[gname]
        gin = next(n for n in tree.nodes if n.bl_idname == "NodeGroupInput")
        gout = next(n for n in tree.nodes if n.bl_idname == "NodeGroupOutput")

        def resolve_out(ep: Endpoint):
            if ep.kind == "group_input":
                return gin.outputs.get(ep.socket) or gin.outputs[0]
            if ep.kind == "instance":
                gnode = instance_handles[(gname, ep.ref)]
                return gnode.outputs.get(ep.socket)
            n = node_handles[(gname, ep.ref)]
            return (n.outputs[ep.socket]
                    if isinstance(ep.socket, int)
                    else n.outputs.get(ep.socket) or n.outputs[0])

        def resolve_in(ep: Endpoint):
            if ep.kind == "group_output":
                return gout.inputs.get(ep.socket) or gout.inputs[0]
            if ep.kind == "instance":
                gnode = instance_handles[(gname, ep.ref)]
                return gnode.inputs.get(ep.socket)
            n = node_handles[(gname, ep.ref)]
            return (n.inputs[ep.socket]
                    if isinstance(ep.socket, int)
                    else n.inputs.get(ep.socket) or n.inputs[0])

        for link in gdef.links:
            s = resolve_out(link.src)
            d = resolve_in(link.dst)
            if s is not None and d is not None:
                tree.links.new(s, d)

    return trees[plan.root_name]
