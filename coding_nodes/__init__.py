"""Coding Nodes — compile a Python expression to a Geometry Nodes subtree.

Milestones (see PLAN.md):
    M1  frontend: Python source -> EvalGraph                 [done]
    M2  grouping: flat EvalGraph -> hierarchy of named regions [done]
    M3  GN op emitters + Expression Modifier                  [next]
    M4  Expression Node Group
    M5  polish, examples, ship

Public API:
    compile(source) -> CompiledExpression   Parse a Python expression.
    group(compiled) -> GroupedGraph         Wrap user functions as regions.
    CompileError                            Raised on unsupported syntax.
"""

from coding_nodes.frontend import CompileError, CompiledExpression, compile
from coding_nodes.grouping import GroupedGraph, GroupRegion, group

__all__ = [
    "compile",
    "CompiledExpression",
    "CompileError",
    "group",
    "GroupedGraph",
    "GroupRegion",
]
__version__ = "0.2.0"
