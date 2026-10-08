"""Grouping pass: turn a flat scope-annotated EvalGraph into a hierarchy of
named regions, so each user function call becomes its own GN sub-group."""

from ..grouping.regions import (
    BoundarySocket,
    GroupedGraph,
    GroupRegion,
)
from ..grouping.group_pass import group

__all__ = ["group", "GroupedGraph", "GroupRegion", "BoundarySocket"]
