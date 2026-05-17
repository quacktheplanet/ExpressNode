"""Coding Nodes — compile a Python expression to a Geometry Nodes subtree.

Milestones (see PLAN.md):
    M1  frontend: Python source -> EvalGraph                  [done]
    M2  grouping: flat EvalGraph -> hierarchy of named regions [done]
    M3  backend: op emitters + EmissionPlan + executor         [headless done;
                                                                Blender pending]
    M4  Expression Node Group
    M5  polish, examples, ship

Public API:
    compile(source) -> CompiledExpression   Parse a Python expression.
    group(compiled) -> GroupedGraph         Wrap user functions as regions.
    plan_source(source) -> EmissionPlan     Plan the Blender node tree.
    CompileError                            Raised on unsupported syntax.
"""

from coding_nodes.frontend import CompileError, CompiledExpression, compile
from coding_nodes.grouping import GroupedGraph, GroupRegion, group
from coding_nodes.backend import EmissionPlan, build_plan, plan_source

__all__ = [
    "compile",
    "CompiledExpression",
    "CompileError",
    "group",
    "GroupedGraph",
    "GroupRegion",
    "plan_source",
    "build_plan",
    "EmissionPlan",
]
__version__ = "0.3.0"
