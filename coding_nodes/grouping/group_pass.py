"""The grouping pass.

`group(compiled)` reconstructs the call tree from per-node scope paths,
computes each region's boundary sockets, and applies the inline
heuristic (small regions stay flattened into their parent rather than
becoming their own sub-group).

Pure and headless — no `bpy`. Tested in tests/m2_grouping/.
"""

from __future__ import annotations

from coding_nodes.frontend.parser import CompiledExpression
from coding_nodes.grouping.regions import (
    BoundarySocket,
    GroupedGraph,
    GroupRegion,
)

DEFAULT_INLINE_THRESHOLD = 3


def _parse_frame(frame: str) -> tuple[str, int]:
    """'curl#0' -> ('curl', 0)."""
    name, _, num = frame.rpartition("#")
    if not name:
        return frame, 0
    try:
        return name, int(num)
    except ValueError:
        return frame, 0


def _scope_path_of(compiled: CompiledExpression, node_id: int
                   ) -> tuple[str, ...]:
    path = compiled.scope_paths.get(node_id)
    if path:
        return path
    # Fall back to the node's stored param (defensive).
    node = compiled.graph.nodes.get(node_id)
    if node is not None:
        p = node.params.get("__scope_path__")
        if p:
            return tuple(p)
    return ()


def _build_region_tree(compiled: CompiledExpression) -> GroupRegion:
    """Build the region tree from node scope paths."""
    graph = compiled.graph

    # Determine the root frame: the first element of any node's path.
    root_path: tuple[str, ...] | None = None
    for nid in graph.nodes:
        p = _scope_path_of(compiled, nid)
        if p:
            root_path = (p[0],)
            break
    if root_path is None:
        # No scoped nodes at all — synthesize an empty root.
        root_path = (f"{compiled.entry_function}#0",)

    regions: dict[tuple[str, ...], GroupRegion] = {}

    def ensure_region(path: tuple[str, ...]) -> GroupRegion:
        if path in regions:
            return regions[path]
        fn, inst = _parse_frame(path[-1])
        r = GroupRegion(
            function=fn,
            instance=inst,
            path=path,
            is_root=(len(path) == 1),
        )
        regions[path] = r
        if len(path) > 1:
            parent = ensure_region(path[:-1])
            parent.children.append(r)
        return r

    ensure_region(root_path)

    # Assign every node to the region at its exact path.
    for nid in graph.nodes:
        p = _scope_path_of(compiled, nid)
        if not p:
            p = root_path
        for k in range(1, len(p) + 1):
            ensure_region(p[:k])
        regions[p].direct_node_ids.append(nid)

    # Stable ordering: sort children by (function, instance) and node ids.
    for r in regions.values():
        r.children.sort(key=lambda c: (c.instance, c.function))
        r.direct_node_ids.sort()

    return regions[root_path]


def _compute_boundaries(graph, region: GroupRegion) -> None:
    """Compute input/output BoundarySockets for `region` and recurse."""
    members = region.all_node_ids()

    seen_inputs: dict[tuple[int, str], BoundarySocket] = {}
    seen_outputs: dict[tuple[int, str], BoundarySocket] = {}

    for e in graph.edges:
        src_in = e.source_node in members
        tgt_in = e.target_node in members
        if tgt_in and not src_in:
            key = (e.source_node, e.source_socket)
            if key not in seen_inputs:
                seen_inputs[key] = BoundarySocket(
                    name=f"in_{len(seen_inputs)}",
                    producer_node=e.source_node,
                    producer_socket=e.source_socket,
                    consumer_node=e.target_node,
                    consumer_socket=e.target_socket,
                    socket_type=e.socket_type,
                )
        elif src_in and not tgt_in:
            key = (e.source_node, e.source_socket)
            if key not in seen_outputs:
                seen_outputs[key] = BoundarySocket(
                    name=f"out_{len(seen_outputs)}",
                    producer_node=e.source_node,
                    producer_socket=e.source_socket,
                    consumer_node=e.target_node,
                    consumer_socket=e.target_socket,
                    socket_type=e.socket_type,
                )

    # A region that produces a graph-level output (the final result) must
    # also expose it: there's no edge to a consumer node, the value leaves
    # via graph.outputs. The root is the main tree and needs no socket.
    if not region.is_root:
        for out_name, (nid, sock) in graph.outputs.items():
            if nid in members:
                key = (nid, sock)
                if key not in seen_outputs:
                    node = graph.nodes[nid]
                    seen_outputs[key] = BoundarySocket(
                        name=f"out_{len(seen_outputs)}",
                        producer_node=nid,
                        producer_socket=sock,
                        consumer_node=-1,            # -1 = graph output
                        consumer_socket=out_name,
                        socket_type=node.output_type(sock),
                    )

    region.inputs = list(seen_inputs.values())
    region.outputs = list(seen_outputs.values())

    for child in region.children:
        _compute_boundaries(graph, child)


def _apply_inline_heuristic(region: GroupRegion, threshold: int) -> None:
    """Mark small non-root regions as inlined. Recurses depth-first so a
    region's own size accounts for its (possibly inlined) descendants."""
    for child in region.children:
        _apply_inline_heuristic(child, threshold)
    if not region.is_root and region.node_count() <= threshold:
        region.inlined = True


def group(compiled: CompiledExpression,
          inline_threshold: int = DEFAULT_INLINE_THRESHOLD) -> GroupedGraph:
    """Run the grouping pass over a compiled expression.

    Args:
        compiled: result of `coding_nodes.compile(...)`.
        inline_threshold: regions with this many nodes or fewer stay
            flattened into their parent instead of becoming a sub-group.

    Returns a `GroupedGraph`: the original flat graph plus the region tree.
    """
    root = _build_region_tree(compiled)
    _compute_boundaries(compiled.graph, root)
    _apply_inline_heuristic(root, inline_threshold)
    return GroupedGraph(graph=compiled.graph, root=root)
