"""Coding Nodes — compile a Python expression to a Geometry Nodes subtree.

Phase 1 (M1): the frontend that parses Python source and emits an EvalGraph.
Later milestones add the group-wrapping pass, the GN backend extension, and
the Blender-side modifier / node-group surfaces.

Public API:
    compile(source: str) -> CompiledExpression   Parse a Python expression.
    CompileError                                  Raised on unsupported syntax.
"""

from coding_nodes.frontend import CompileError, CompiledExpression, compile

__all__ = ["compile", "CompiledExpression", "CompileError"]
__version__ = "0.1.0"
