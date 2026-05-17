"""Data model for the grouping pass.

A `GroupRegion` is a node in the call tree: the entry function is the
root, each inlined call is a child. A region knows which EvalGraph nodes
belong to it directly, which sub-regions it contains, and which edges
cross its boundary (those become the sub-group's input/output sockets).

Everything here is pure data — no `bpy`. The bpy emitter (M3) consumes
this structure to build actual Geometry Nodes sub-trees.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field

from sacred_geometry.ir.eval_graph import EvalGraph, SocketType


@dataclass(frozen=True)
class BoundarySocket:
    """One edge crossing a region boundary.

    For an input boundary: `producer_node`/`producer_socket` live outside
    the region, `consumer_node`/`consumer_socket` live inside.
    For an output boundary: the reverse.
    """
    name: str
    producer_node: int
    producer_socket: str
    consumer_node: int
    consumer_socket: str
    socket_type: SocketType


@dataclass
class GroupRegion:
    """One region in the call tree."""
    function: str                       # e.g. "n", "curl", "__expr__"
    instance: int                       # call-instance number (from frame id)
    path: tuple[str, ...]               # full scope path of this region
    direct_node_ids: list[int] = _dc_field(default_factory=list)
    children: list["GroupRegion"] = _dc_field(default_factory=list)
    inputs: list[BoundarySocket] = _dc_field(default_factory=list)
    outputs: list[BoundarySocket] = _dc_field(default_factory=list)
    # True when the region is small enough to inline into its parent
    # instead of becoming its own sub-group.
    inlined: bool = False
    # True for the entry region (the main tree; never wrapped as a group).
    is_root: bool = False

    @property
    def frame_id(self) -> str:
        return f"{self.function}#{self.instance}"

    def all_node_ids(self) -> set[int]:
        """This region's direct nodes plus every descendant's nodes."""
        ids = set(self.direct_node_ids)
        for c in self.children:
            ids |= c.all_node_ids()
        return ids

    def node_count(self) -> int:
        return len(self.all_node_ids())

    def walk(self):
        """Pre-order traversal yielding this region then descendants."""
        yield self
        for c in self.children:
            yield from c.walk()

    def describe(self) -> dict:
        return {
            "function": self.function,
            "instance": self.instance,
            "frame": self.frame_id,
            "is_root": self.is_root,
            "inlined": self.inlined,
            "direct_nodes": len(self.direct_node_ids),
            "total_nodes": self.node_count(),
            "inputs": [s.name for s in self.inputs],
            "outputs": [s.name for s in self.outputs],
            "children": [c.describe() for c in self.children],
        }


@dataclass
class GroupedGraph:
    """Result of the grouping pass: the original flat graph plus the call
    tree of regions over it."""
    graph: EvalGraph
    root: GroupRegion

    def wrapped_regions(self) -> list[GroupRegion]:
        """Regions that will become real GN sub-groups: every non-root,
        non-inlined region, in pre-order."""
        out = []
        for r in self.root.walk():
            if not r.is_root and not r.inlined:
                out.append(r)
        return out

    def inlined_regions(self) -> list[GroupRegion]:
        return [r for r in self.root.walk()
                if not r.is_root and r.inlined]

    def describe(self) -> dict:
        return {
            "num_nodes": len(self.graph.nodes),
            "num_wrapped": len(self.wrapped_regions()),
            "num_inlined": len(self.inlined_regions()),
            "tree": self.root.describe(),
        }
