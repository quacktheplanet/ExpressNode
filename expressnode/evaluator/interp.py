"""The evaluator: run a compiled expression's EvalGraph in numpy.

This is the reference oracle. It executes the expression graph directly
(the `result` output), independent of Blender, so we can prove the math
is correct and validate every other backend against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Any

import numpy as np

from ..evaluator.ops import OPS
from ..frontend.parser import CompiledExpression


@dataclass
class _Ctx:
    P: np.ndarray
    normals: np.ndarray
    index: np.ndarray
    t: float
    frame: float
    dt: float
    params: dict[str, Any]
    attributes: dict[str, np.ndarray]
    objects: dict[str, dict[str, Any]]
    seed: int
    shape: tuple
    written: dict[str, np.ndarray] = _dc_field(default_factory=dict)


@dataclass
class EvalResult:
    values: np.ndarray                       # the expression result
    written_attributes: dict[str, np.ndarray]

    def __array__(self, dtype=None):
        return np.asarray(self.values, dtype=dtype)


def evaluate(compiled: CompiledExpression,
             P: np.ndarray | None = None,
             t: float = 0.0,
             frame: float = 1.0,
             dt: float = 1.0 / 24.0,
             normals: np.ndarray | None = None,
             params: dict[str, Any] | None = None,
             attributes: dict[str, np.ndarray] | None = None,
             objects: dict[str, dict[str, Any]] | None = None,
             seed: int = 0) -> EvalResult:
    """Evaluate a compiled expression numerically.

    Args:
        compiled: result of `expressnode.compile(...)`.
        P:        (N, 3) positions. If omitted, a single point at origin.
        t/frame/dt: scene time scalars.
        normals:  (N, 3); defaults to normalized P (origin -> +Z).
        params:   name -> value overrides for exposed parameters
                  (defaults come from the expression's signature).
        attributes/objects: data for attr()/obj(); default zeros.
        seed:     noise seed.

    Returns an EvalResult whose `.values` is (N, 3) for a vec result or
    (N,) for a scalar result (N == len(P), or 1 when P is omitted).
    """
    graph = compiled.graph

    if P is None:
        P = np.zeros((1, 3), dtype=np.float64)
    else:
        P = np.asarray(P, dtype=np.float64)
        if P.ndim == 1:
            P = P[None, :]
    shape = P.shape[:-1]

    if normals is None:
        n = np.linalg.norm(P, axis=-1, keepdims=True)
        safe = np.where(n == 0, 1.0, n)
        normals = np.where(n == 0, np.array([0.0, 0.0, 1.0]), P / safe)
    else:
        normals = np.asarray(normals, dtype=np.float64)

    ctx = _Ctx(
        P=P,
        normals=normals,
        index=np.arange(shape[0] if shape else 1, dtype=np.float64),
        t=float(t), frame=float(frame), dt=float(dt),
        params=dict(params or {}),
        attributes={k: np.asarray(v, dtype=np.float64)
                    for k, v in (attributes or {}).items()},
        objects=objects or {},
        seed=int(seed),
        shape=shape,
    )

    # node id -> {output socket name -> ndarray}
    cache: dict[int, dict[str, np.ndarray]] = {}

    def input_value(node, socket_name):
        for e in graph.in_edges(node):
            if e.target_socket == socket_name:
                return cache[e.source_node][e.source_socket]
        return np.asarray(0.0)  # unconnected input -> 0

    for node in graph.topological_order():
        fn = OPS.get(node.op)
        if fn is None:
            # param-only / structural ops never need a numpy value.
            if node.op == "constant.string":
                cache[node.id] = {node.output_sockets[0][0]: np.asarray(0.0)}
                continue
            raise NotImplementedError(
                f"evaluator has no implementation for op {node.op!r}"
            )
        args = [input_value(node, sock_name)
                for sock_name, _ in node.input_sockets]
        out = fn(args, node, ctx)
        out_name = node.output_sockets[0][0] if node.output_sockets else "value"
        cache[node.id] = {out_name: out}

    nid, sock = graph.outputs["result"]
    result = cache[nid][sock]
    return EvalResult(values=np.asarray(result), written_attributes=ctx.written)
