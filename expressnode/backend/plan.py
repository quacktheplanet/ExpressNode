"""Emission planner: GroupedGraph -> EmissionPlan.

An `EmissionPlan` is a complete, serializable description of the Blender
node tree the executor will build: every node group, the nodes inside
it, their links, the group interface, and the group-instance references
between them. It is **pure data** — no `bpy` — so the whole emission
shape is verifiable headlessly before any Blender run.

Scope (M3): the planner fully handles the root tree plus one level of
wrapped sub-groups with inlined regions folded in — which is exactly
what `ripple.py` (no nesting) and `curl_noise.py` (a `curl` root with
twelve `n` sub-groups) need. Deeper multi-level cross-group threading is
represented structurally; its wiring is on the Blender verification
checklist (see TESTING.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Any

from ..backend.op_emitters import get_emitter
from ..frontend.parser import CompiledExpression
from ..grouping import GroupedGraph, GroupRegion, group


# ---------------------------------------------------------------------------
# Plan data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Endpoint:
    """One side of a link inside a GroupDef.

    kind:
        "node"          ref = local node id, socket = out/in socket
        "instance"      ref = instance id, socket = interface socket name
        "group_input"   ref = None, socket = interface input name
        "group_output"  ref = None, socket = interface output name
    """
    kind: str
    ref: int | None
    socket: object


@dataclass
class PlannedNode:
    local_id: int
    eval_id: int
    op: str
    bl_idname: str
    settings: dict = _dc_field(default_factory=dict)
    params: dict = _dc_field(default_factory=dict)
    output_socket: object = 0
    emitter_kind: str = "simple"
    # The eval node's declared input sockets, in order, with their types,
    # and its result type. Links name inputs abstractly ("a", "arg1",
    # "cond"); the executor maps the position in `input_names` onto the
    # Blender node's real sockets.
    input_names: tuple = ()
    input_types: tuple = ()
    output_type: str = "float"


@dataclass
class GroupInstance:
    instance_id: int
    group_name: str
    region_path: tuple[str, ...]


@dataclass
class PlannedLink:
    src: Endpoint
    dst: Endpoint


@dataclass
class GroupDef:
    name: str
    region_path: tuple[str, ...]
    is_root: bool
    inputs: list[tuple[str, str]] = _dc_field(default_factory=list)   # (name, socket_type)
    outputs: list[tuple[str, str]] = _dc_field(default_factory=list)
    nodes: list[PlannedNode] = _dc_field(default_factory=list)
    instances: list[GroupInstance] = _dc_field(default_factory=list)
    links: list[PlannedLink] = _dc_field(default_factory=list)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "is_root": self.is_root,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "nodes": len(self.nodes),
            "instances": [i.group_name for i in self.instances],
            "links": len(self.links),
        }


@dataclass
class EmissionPlan:
    groups: dict[str, GroupDef]
    root_name: str
    parameters: list[tuple[str, str, Any]] = _dc_field(default_factory=list)
    # When an apply mode wraps the expression group for use as a modifier,
    # this names the Geometry-in/Geometry-out wrapper group. None for the
    # raw expression group (Shape B drops the raw group directly).
    modifier_root_name: str | None = None
    apply_mode: str = "raw"
    # set_attr() calls: (attribute name, value socket type). The root
    # group exposes each value as an extra output of that name; the
    # modifier wrapper stores it on the geometry's points.
    attr_writes: list[tuple[str, str]] = _dc_field(default_factory=list)

    def describe(self) -> dict:
        return {
            "root": self.root_name,
            "modifier_root": self.modifier_root_name,
            "apply_mode": self.apply_mode,
            "parameters": self.parameters,
            "attr_writes": self.attr_writes,
            "groups": {n: g.describe() for n, g in self.groups.items()},
        }

    def deliverable_root(self) -> str:
        """The group to attach/drop: the modifier wrapper if present
        (Shape A), else the raw expression group (Shape B)."""
        return self.modifier_root_name or self.root_name


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def _sanitize(frame: str) -> str:
    return frame.replace("#", "_")


class _Planner:
    def __init__(self, compiled: CompiledExpression, grouped: GroupedGraph):
        self.c = compiled
        self.g = grouped
        self.graph = grouped.graph

        # region path -> region
        self.region_by_path: dict[tuple[str, ...], GroupRegion] = {}
        for r in grouped.root.walk():
            self.region_by_path[r.path] = r

        # eval node id -> the region whose path it is assigned to
        self.region_of_node: dict[int, GroupRegion] = {}
        for r in grouped.root.walk():
            for nid in r.direct_node_ids:
                self.region_of_node[nid] = r

        # Group defs: one per root + wrapped region.
        self.defs: dict[tuple[str, ...], GroupDef] = {}
        self.def_name: dict[tuple[str, ...], str] = {}
        self._name_defs()

        # eval node id -> its home GroupDef path (nearest root/wrapped
        # enclosing region).
        self.home_path: dict[int, tuple[str, ...]] = {}
        for nid, region in self.region_of_node.items():
            self.home_path[nid] = self._home_region(region).path

        # Local id allocation per def, plus eval->local maps.
        self._local_counter: dict[tuple[str, ...], int] = {}
        self.local_id: dict[int, int] = {}      # eval id -> local id
        self.local_def: dict[int, tuple[str, ...]] = {}  # eval id -> def path

        # Instance allocation: region path -> GroupInstance (placed in parent)
        self.instance_of_region: dict[tuple[str, ...], GroupInstance] = {}
        self._instance_counter: dict[tuple[str, ...], int] = {}

        # set_attr() nodes are not emitted as nodes: their value leaves
        # the root group through an output named after the attribute.
        self.attr_write: dict[int, str] = {}    # eval id -> attribute name
        self.attr_writes: list[tuple[str, str]] = []

    # --- region helpers ---

    def _home_region(self, region: GroupRegion) -> GroupRegion:
        """Nearest enclosing region that owns a GroupDef (root or a
        non-inlined wrapped region)."""
        r = region
        while True:
            if r.is_root or not r.inlined:
                return r
            # climb to parent
            parent_path = r.path[:-1]
            r = self.region_by_path[parent_path]

    def _name_defs(self) -> None:
        used: set[str] = set()
        for region in self.g.root.walk():
            if region.is_root:
                name = f"Expr_{region.function}"
            elif region.inlined:
                continue
            else:
                name = _sanitize(region.frame_id)
            base = name
            i = 1
            while name in used:
                name = f"{base}_{i}"
                i += 1
            used.add(name)
            self.def_name[region.path] = name
            self.defs[region.path] = GroupDef(
                name=name,
                region_path=region.path,
                is_root=region.is_root,
            )

    def _alloc_local(self, def_path: tuple[str, ...], eval_id: int) -> int:
        n = self._local_counter.get(def_path, 0)
        self._local_counter[def_path] = n + 1
        self.local_id[eval_id] = n
        self.local_def[eval_id] = def_path
        return n

    # --- build ---

    def build(self) -> EmissionPlan:
        self._place_nodes()
        self._place_instances()
        self._interfaces()
        self._links()
        root_region = self.g.root
        return EmissionPlan(
            groups={gd.name: gd for gd in self.defs.values()},
            root_name=self.def_name[root_region.path],
            parameters=[
                (p.name, p.type.to_socket_type().value, p.default)
                for p in self.c.parameters
            ],
            attr_writes=list(self.attr_writes),
        )

    def _place_nodes(self) -> None:
        for nid, node in self.graph.nodes.items():
            emitter = get_emitter(node.op)
            if emitter is None:
                raise KeyError(
                    f"No emitter registered for op {node.op!r}. "
                    f"Add it to backend/op_emitters.py."
                )
            if emitter.kind in ("interface", "param_only"):
                continue
            home = self.home_path[nid]
            if node.op == "attr.write":
                # Called from a helper too: _links threads the value out of
                # every nested group to the root output named after it.
                name = node.params.get("name", "")
                if name in dict(self.attr_writes) or name == "Result":
                    raise ValueError(
                        f"set_attr({name!r}, ...) runs more than once (a "
                        f"helper that calls it may be used twice) or clashes "
                        f"with the Result output."
                    )
                self.attr_write[nid] = name
                self.attr_writes.append((name, node.input_sockets[0][1].value))
                continue
            local = self._alloc_local(home, nid)
            self.defs[home].nodes.append(PlannedNode(
                local_id=local,
                eval_id=nid,
                op=node.op,
                bl_idname=emitter.bl_idname,
                settings=dict(emitter.settings),
                params=dict(node.params),
                output_socket=emitter.output,
                emitter_kind=emitter.kind,
                input_names=tuple(n for n, _ in node.input_sockets),
                input_types=tuple(t.value for _, t in node.input_sockets),
                output_type=(node.output_sockets[0][1].value
                             if node.output_sockets else "float"),
            ))

    def _place_instances(self) -> None:
        for region in self.g.root.walk():
            if region.is_root or region.inlined:
                continue
            parent_region = self.region_by_path[region.path[:-1]]
            parent_home = self._home_region(parent_region).path
            iid = self._instance_counter.get(parent_home, 0)
            self._instance_counter[parent_home] = iid + 1
            inst = GroupInstance(
                instance_id=iid,
                group_name=self.def_name[region.path],
                region_path=region.path,
            )
            self.instance_of_region[region.path] = inst
            self.defs[parent_home].instances.append(inst)

    def _interfaces(self) -> None:
        # Root: user parameters in, the result out.
        root_def = self.defs[self.g.root.path]
        for p in self.c.parameters:
            root_def.inputs.append((p.name, p.type.to_socket_type().value))
        if "result" in self.graph.outputs:
            nid, sock = self.graph.outputs["result"]
            rt = self.graph.nodes[nid].output_type(sock).value
            root_def.outputs.append(("Result", rt))
        for name, stype in self.attr_writes:
            root_def.outputs.append((name, stype))

        # Wrapped regions get their sockets while links are threaded
        # (_thread), one per value that crosses their boundary.

    # --- threading values between groups ---

    _SHORT_NAMES = {"input.position": "P", "input.normal": "N",
                    "input.index": "i", "input.scene_time": "t",
                    "input.frame": "frame", "input.delta_time": "dt"}

    def _parent_def(self, def_path):
        if def_path == self.g.root.path:
            return None
        return self._home_region(self.region_by_path[def_path[:-1]]).path

    def _chain(self, def_path) -> list:
        """Def paths from the root down to def_path, inclusive."""
        chain = []
        d = def_path
        while d is not None:
            chain.append(d)
            d = self._parent_def(d)
        return chain[::-1]

    def _source_home(self, eval_id: int):
        if self.graph.nodes[eval_id].op == "input.parameter":
            return self.g.root.path
        return self.home_path[eval_id]

    def _endpoint_for_source(self, eval_id: int,
                             socket: str) -> Endpoint:
        node = self.graph.nodes[eval_id]
        if node.op == "input.parameter":
            return Endpoint("group_input", None, node.params["name"])
        if node.op == "attr.write":
            raise ValueError(
                "The value returned by set_attr() can't be used by the "
                "Geometry Nodes backend; call set_attr() as a statement."
            )
        return Endpoint("node", self.local_id[eval_id], socket)

    def _boundary_socket(self, def_path, side: str, eval_id: int,
                         socket: str) -> tuple[str, bool]:
        """Name of def_path's input or output socket carrying the value
        (eval_id, socket), creating it on first use. Returns (name,
        created)."""
        key = (def_path, side, eval_id, socket)
        if key in self._boundary:
            return self._boundary[key], False
        d = self.defs[def_path]
        sockets = d.inputs if side == "in" else d.outputs
        node = self.graph.nodes[eval_id]
        stype = node.output_type(socket).value
        taken = {n for n, _ in sockets}
        name = None
        if side == "in":
            if node.op == "input.parameter":
                name = node.params["name"]
            else:
                name = self._SHORT_NAMES.get(node.op)
        if name is None or name in taken:
            prefix = "in" if side == "in" else "out"
            k = sum(1 for n in taken if n.startswith(prefix + "_"))
            name = f"{prefix}_{k}"
            while name in taken:
                k += 1
                name = f"{prefix}_{k}"
        sockets.append((name, stype))
        self._boundary[key] = name
        return name, True

    def _thread(self, eval_id: int, socket: str, dst_home, dst: Endpoint):
        """Link the value (eval_id, socket) to `dst` inside dst_home,
        passing it out of every group between its home and the nearest
        common group, then into every group down to dst_home."""
        up = self._chain(self._source_home(eval_id))
        down = self._chain(dst_home)
        k = 0
        while k < min(len(up), len(down)) and up[k] == down[k]:
            k += 1
        ep = self._endpoint_for_source(eval_id, socket)
        for d in reversed(up[k:]):
            name, created = self._boundary_socket(d, "out", eval_id, socket)
            if created:
                self.defs[d].links.append(PlannedLink(
                    ep, Endpoint("group_output", None, name)))
            ep = Endpoint("instance", self.instance_of_region[d].instance_id,
                          name)
        for d in down[k:]:
            name, created = self._boundary_socket(d, "in", eval_id, socket)
            if created:
                self.defs[self._parent_def(d)].links.append(PlannedLink(
                    ep, Endpoint("instance",
                                 self.instance_of_region[d].instance_id,
                                 name)))
            ep = Endpoint("group_input", None, name)
        self.defs[dst_home].links.append(PlannedLink(ep, dst))

    def _links(self) -> None:
        self._boundary: dict = {}
        root = self.g.root.path
        for e in self.graph.edges:
            src_node = self.graph.nodes[e.source_node]
            if get_emitter(src_node.op).kind == "param_only":
                continue
            if e.target_node in self.attr_write:
                self._thread(e.source_node, e.source_socket, root,
                             Endpoint("group_output", None,
                                      self.attr_write[e.target_node]))
                continue
            self._thread(e.source_node, e.source_socket,
                         self.home_path[e.target_node],
                         Endpoint("node", self.local_id[e.target_node],
                                  e.target_socket))
        if "result" in self.graph.outputs:
            nid, sock = self.graph.outputs["result"]
            self._thread(nid, sock, root,
                         Endpoint("group_output", None, "Result"))


APPLY_MODES = ("raw", "offset", "absolute", "normal")


def _add_modifier_wrapper(plan: EmissionPlan, compiled: CompiledExpression,
                          apply_mode: str) -> EmissionPlan:
    """Wrap the raw expression group in a Geometry-in/Geometry-out group
    so it works as a Geometry Nodes modifier.

    raw       no wrapper (Shape B drops the raw group directly)
    offset    Set Position, Offset = expression Result (vec3)
    absolute  Set Position, Position = expression Result (vec3)
    normal    Set Position, Offset = Normal * expression Result (float)
    """
    if apply_mode == "raw":
        plan.apply_mode = "raw"
        return plan

    expr = plan.groups[plan.root_name]
    if apply_mode == "normal":
        rtype = dict(expr.outputs).get("Result")
        if rtype != "float":
            raise ValueError(
                "Normal mode pushes points along their normals, so the "
                "expression must return a number (the distance), not "
                f"{rtype or 'nothing'}.")
    wrapper_name = f"Modifier_{plan.root_name}"
    w = GroupDef(name=wrapper_name, region_path=(), is_root=False)
    w.inputs.append(("Geometry", "geometry"))
    for pname, ptype in expr.inputs:
        w.inputs.append((pname, ptype))
    w.outputs.append(("Geometry", "geometry"))

    inst = GroupInstance(instance_id=0, group_name=plan.root_name,
                         region_path=())
    w.instances.append(inst)

    sp = PlannedNode(
        local_id=0, eval_id=-1, op="modifier.set_position",
        bl_idname="GeometryNodeSetPosition", settings={},
        params={"mode": apply_mode}, output_socket="Geometry",
        emitter_kind="complex",
        input_names=("Geometry", "Position", "Offset"),
        input_types=("geometry", "vector", "vector"),
        output_type="geometry",
    )
    w.nodes.append(sp)

    # Geometry in -> Set Position geometry
    w.links.append(PlannedLink(
        Endpoint("group_input", None, "Geometry"),
        Endpoint("node", 0, "Geometry"),
    ))
    # parameters -> expression instance
    for pname, _ in expr.inputs:
        w.links.append(PlannedLink(
            Endpoint("group_input", None, pname),
            Endpoint("instance", 0, pname),
        ))
    # expression Result -> Set Position (Offset or Position)
    if apply_mode == "normal":
        # Result (a distance) scales the point normal into the offset
        w.nodes.append(PlannedNode(
            local_id=1, eval_id=-1, op="modifier.normal_offset",
            bl_idname="ShaderNodeVectorMath", settings={"operation": "SCALE"},
            params={}, output_socket="Vector", emitter_kind="complex",
            input_names=("Distance",), input_types=("float",),
            output_type="vector",
        ))
        w.links.append(PlannedLink(
            Endpoint("instance", 0, "Result"),
            Endpoint("node", 1, "Distance"),
        ))
        w.links.append(PlannedLink(
            Endpoint("node", 1, "Vector"),
            Endpoint("node", 0, "Offset"),
        ))
    else:
        sp_in = "Offset" if apply_mode == "offset" else "Position"
        w.links.append(PlannedLink(
            Endpoint("instance", 0, "Result"),
            Endpoint("node", 0, sp_in),
        ))
    # Set Position geometry -> Geometry out
    w.links.append(PlannedLink(
        Endpoint("node", 0, "Geometry"),
        Endpoint("group_output", None, "Geometry"),
    ))

    plan.groups[wrapper_name] = w
    plan.modifier_root_name = wrapper_name
    plan.apply_mode = apply_mode
    return plan


def build_plan(compiled: CompiledExpression,
                grouped: GroupedGraph | None = None,
                inline_threshold: int = 3,
                apply_mode: str = "raw") -> EmissionPlan:
    """Plan the Blender node tree for a compiled expression.

    `grouped` may be supplied to reuse a GroupedGraph; otherwise it is
    computed with `inline_threshold`.

    `apply_mode` controls the modifier wrapper:
        raw       expression group only (Shape B default)
        offset    wrap so Result becomes a Set Position offset (Shape A)
        absolute  wrap so Result becomes the absolute Set Position
    """
    if apply_mode not in APPLY_MODES:
        raise ValueError(
            f"unknown apply_mode {apply_mode!r}; one of {APPLY_MODES}"
        )
    if grouped is None:
        grouped = group(compiled, inline_threshold=inline_threshold)
    plan = _Planner(compiled, grouped).build()
    return _add_modifier_wrapper(plan, compiled, apply_mode)
