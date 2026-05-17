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

from coding_nodes.backend.op_emitters import get_emitter
from coding_nodes.frontend.parser import CompiledExpression
from coding_nodes.grouping import GroupedGraph, GroupRegion, group


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

    def describe(self) -> dict:
        return {
            "root": self.root_name,
            "parameters": self.parameters,
            "groups": {n: g.describe() for n, g in self.groups.items()},
        }


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

        # Wrapped regions: from their BoundarySockets.
        for region in self.g.root.walk():
            if region.is_root or region.inlined:
                continue
            d = self.defs[region.path]
            for bs in region.inputs:
                d.inputs.append((bs.name, bs.socket_type.value))
            for bs in region.outputs:
                d.outputs.append((bs.name, bs.socket_type.value))

    def _endpoint_for_source(self, eval_id: int,
                             socket: str) -> Endpoint:
        node = self.graph.nodes[eval_id]
        if node.op == "input.parameter":
            return Endpoint("group_input", None, node.params["name"])
        return Endpoint("node", self.local_id[eval_id], socket)

    def _links(self) -> None:
        # 1. Intra-def edges (both endpoints share a home def, neither side
        #    crossing a wrapped boundary).
        for e in self.graph.edges:
            src_node = self.graph.nodes[e.source_node]
            if get_emitter(src_node.op).kind == "param_only":
                continue
            shome = self.home_path.get(e.source_node)
            thome = self.home_path.get(e.target_node)
            if shome is not None and shome == thome:
                d = self.defs[shome]
                d.links.append(PlannedLink(
                    src=self._endpoint_for_source(e.source_node,
                                                  e.source_socket),
                    dst=Endpoint("node", self.local_id[e.target_node],
                                 e.target_socket),
                ))

        # 2. Wrapped-region boundaries: thread producer -> instance ->
        #    consumer through the interface (one nesting level).
        for region in self.g.root.walk():
            if region.is_root or region.inlined:
                continue
            inst = self.instance_of_region[region.path]
            parent_home = self._home_region(
                self.region_by_path[region.path[:-1]]).path
            parent_def = self.defs[parent_home]
            child_def = self.defs[region.path]

            for bs in region.inputs:
                # parent side: producer -> instance input
                parent_def.links.append(PlannedLink(
                    src=self._endpoint_for_source(bs.producer_node,
                                                  bs.producer_socket),
                    dst=Endpoint("instance", inst.instance_id, bs.name),
                ))
                # child side: group input -> consumer
                child_def.links.append(PlannedLink(
                    src=Endpoint("group_input", None, bs.name),
                    dst=Endpoint("node", self.local_id[bs.consumer_node],
                                 bs.consumer_socket),
                ))
            for bs in region.outputs:
                # child side: producer -> group output
                child_def.links.append(PlannedLink(
                    src=Endpoint("node", self.local_id[bs.producer_node],
                                 bs.producer_socket),
                    dst=Endpoint("group_output", None, bs.name),
                ))
                # parent side: instance output -> consumer / group output
                if bs.consumer_node == -1:
                    dst = Endpoint("group_output", None, "Result")
                else:
                    dst = Endpoint("node",
                                   self.local_id.get(bs.consumer_node),
                                   bs.consumer_socket)
                parent_def.links.append(PlannedLink(
                    src=Endpoint("instance", inst.instance_id, bs.name),
                    dst=dst,
                ))

        # 3. Root result produced directly in the root def.
        if "result" in self.graph.outputs:
            nid, sock = self.graph.outputs["result"]
            if self.home_path.get(nid) == self.g.root.path:
                self.defs[self.g.root.path].links.append(PlannedLink(
                    src=self._endpoint_for_source(nid, sock),
                    dst=Endpoint("group_output", None, "Result"),
                ))


def build_plan(compiled: CompiledExpression,
                grouped: GroupedGraph | None = None,
                inline_threshold: int = 3) -> EmissionPlan:
    """Plan the Blender node tree for a compiled expression.

    `grouped` may be supplied to reuse a GroupedGraph; otherwise it is
    computed with `inline_threshold`.
    """
    if grouped is None:
        grouped = group(compiled, inline_threshold=inline_threshold)
    return _Planner(compiled, grouped).build()
