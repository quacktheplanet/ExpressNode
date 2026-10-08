"""Symbol graph — the IR closest to the DSL.

Each SacredEntity step produces one SymbolNode. The compiler walks the
symbol graph in declaration order and emits an EvalGraph from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Any


@dataclass(frozen=True)
class SymbolNode:
    """One step from the DSL. `kind` says what step it is; `payload` carries
    its parameters."""
    kind: str
    payload: dict[str, Any]


@dataclass
class SymbolGraph:
    """Linear sequence of DSL steps with named conveniences for the compiler."""
    nodes: list[SymbolNode] = _dc_field(default_factory=list)

    def add(self, kind: str, payload: dict[str, Any]) -> SymbolNode:
        node = SymbolNode(kind=kind, payload=dict(payload))
        self.nodes.append(node)
        return node

    def find(self, kind: str) -> SymbolNode | None:
        for n in self.nodes:
            if n.kind == kind:
                return n
        return None

    def find_all(self, kind: str) -> list[SymbolNode]:
        return [n for n in self.nodes if n.kind == kind]

    def __len__(self) -> int:
        return len(self.nodes)


def symbol_graph_from_entity(entity) -> SymbolGraph:
    """Build a SymbolGraph from a SacredEntity by walking its captured state.

    Order is fixed: primitive -> topology -> symmetry -> recursion -> fields
    -> material -> animation. Missing steps are simply omitted.
    """
    sg = SymbolGraph()
    s = entity._state

    if s.primitive is None:
        raise ValueError(
            "Entity has no primitive set. Call .primitive(...) before compile()."
        )

    sg.add("primitive", s.primitive)
    sg.add("topology", {"kind": s.topology})

    if s.symmetry is not None:
        sg.add("symmetry", s.symmetry)
    if s.recursion is not None:
        sg.add("recursion", s.recursion)
    for f in s.fields:
        sg.add("field", {"field": f})
    if s.material is not None:
        sg.add("material", s.material)
    if s.animation is not None:
        sg.add("animation", s.animation)

    return sg
