"""Evaluation graph IR.

The compiler lowers a SymbolGraph into an EvalGraph. The EvalGraph is a
typed DAG of operations. Backends (GN tree emission, eventually a numpy
evaluator) consume it.

Design notes:
- Nodes are addressed by integer ids assigned at insertion.
- Edges carry a SocketType so backends can pick the right Blender socket.
- The graph has named "outputs" — typically a single GEOMETRY output, plus
  any attribute promises the material needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from enum import Enum
from typing import Any


class SocketType(Enum):
    GEOMETRY = "geometry"
    FLOAT = "float"
    INT = "int"
    VECTOR = "vector"
    COLOR = "color"
    STRING = "string"


@dataclass(frozen=True)
class EvalEdge:
    """An edge in the eval graph: an output socket on source feeding an
    input socket on target."""
    source_node: int
    source_socket: str
    target_node: int
    target_socket: str
    socket_type: SocketType


@dataclass
class EvalNode:
    """A typed operation in the eval graph.

    `op`             — what this node does (string identifier)
    `params`         — operation parameters not coming from input sockets
    `input_sockets`  — declared input socket names, in order
    `output_sockets` — declared output socket names, in order
    """
    id: int
    op: str
    params: dict[str, Any] = _dc_field(default_factory=dict)
    input_sockets: tuple[tuple[str, SocketType], ...] = ()
    output_sockets: tuple[tuple[str, SocketType], ...] = ()

    def output_type(self, name: str) -> SocketType:
        for n, t in self.output_sockets:
            if n == name:
                return t
        raise KeyError(f"Node {self.op} has no output socket {name!r}")

    def input_type(self, name: str) -> SocketType:
        for n, t in self.input_sockets:
            if n == name:
                return t
        raise KeyError(f"Node {self.op} has no input socket {name!r}")


@dataclass
class EvalGraph:
    """A typed DAG that backends consume."""
    nodes: dict[int, EvalNode] = _dc_field(default_factory=dict)
    edges: list[EvalEdge] = _dc_field(default_factory=list)
    outputs: dict[str, tuple[int, str]] = _dc_field(default_factory=dict)
    # Runtime-bindable parameters: name -> (node_id, param_key, default_value)
    parameters: dict[str, tuple[int, str, Any]] = _dc_field(default_factory=dict)
    # Attribute promises the material will read: name -> (dtype, domain)
    attribute_promises: dict[str, tuple[str, str]] = _dc_field(default_factory=dict)

    _next_id: int = 0

    def add_node(self, op: str,
                 params: dict[str, Any] | None = None,
                 input_sockets: tuple[tuple[str, SocketType], ...] = (),
                 output_sockets: tuple[tuple[str, SocketType], ...] = (),
                 ) -> EvalNode:
        nid = self._next_id
        self._next_id += 1
        node = EvalNode(
            id=nid,
            op=op,
            params=dict(params) if params else {},
            input_sockets=input_sockets,
            output_sockets=output_sockets,
        )
        self.nodes[nid] = node
        return node

    def link(self, source: EvalNode, source_socket: str,
             target: EvalNode, target_socket: str) -> EvalEdge:
        src_type = source.output_type(source_socket)
        tgt_type = target.input_type(target_socket)
        if src_type != tgt_type:
            raise TypeError(
                f"Type mismatch linking {source.op}.{source_socket} ({src_type}) "
                f"-> {target.op}.{target_socket} ({tgt_type})"
            )
        edge = EvalEdge(
            source_node=source.id, source_socket=source_socket,
            target_node=target.id, target_socket=target_socket,
            socket_type=src_type,
        )
        self.edges.append(edge)
        return edge

    def set_output(self, name: str, node: EvalNode, socket: str) -> None:
        node.output_type(socket)  # raises KeyError if missing
        self.outputs[name] = (node.id, socket)

    def add_parameter(self, name: str, node: EvalNode, param_key: str,
                      default: Any) -> None:
        self.parameters[name] = (node.id, param_key, default)

    def add_attribute_promise(self, name: str, dtype: str, domain: str) -> None:
        self.attribute_promises[name] = (dtype, domain)

    # ------------------------------------------------------------------
    # Introspection / debug
    # ------------------------------------------------------------------

    def in_edges(self, node: EvalNode) -> list[EvalEdge]:
        return [e for e in self.edges if e.target_node == node.id]

    def out_edges(self, node: EvalNode) -> list[EvalEdge]:
        return [e for e in self.edges if e.source_node == node.id]

    def topological_order(self) -> list[EvalNode]:
        """Kahn's algorithm. Raises if the graph contains a cycle."""
        indegree: dict[int, int] = {nid: 0 for nid in self.nodes}
        for e in self.edges:
            indegree[e.target_node] += 1
        ready = [nid for nid, d in indegree.items() if d == 0]
        order: list[EvalNode] = []
        while ready:
            nid = ready.pop(0)
            order.append(self.nodes[nid])
            for e in self.edges:
                if e.source_node == nid:
                    indegree[e.target_node] -= 1
                    if indegree[e.target_node] == 0:
                        ready.append(e.target_node)
        if len(order) != len(self.nodes):
            raise RuntimeError("EvalGraph contains a cycle")
        return order

    def describe(self) -> dict[str, Any]:
        return {
            "num_nodes": len(self.nodes),
            "num_edges": len(self.edges),
            "outputs": list(self.outputs.keys()),
            "parameters": list(self.parameters.keys()),
            "attribute_promises": dict(self.attribute_promises),
            "ops": sorted({n.op for n in self.nodes.values()}),
        }
