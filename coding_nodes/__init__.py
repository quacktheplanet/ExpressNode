"""Expression Nodes — compile a Python expression to a Geometry Nodes subtree.

Milestones (see PLAN.md):
    M1  frontend: Python source -> EvalGraph                  [done]
    M2  grouping: flat EvalGraph -> hierarchy of named regions [done]
    M3  backend: op emitters + EmissionPlan + executor         [headless done;
                                                                Blender pending]
    M4  Expression Node Group (Shape B)                        [headless done;
                                                                Blender pending]
    M5  polish: apply modes, param reconcile, packaging        [headless done;
                                                                Blender pending]
    M6  numpy reference evaluator (correctness oracle)         [headless done]
    M7  OSL backend (validate vs the oracle)                   [headless done;
                                                                OSL-runtime
                                                                checklist]
    M8  GLSL/Eevee backend (validate vs the oracle)            [headless done;
                                                                GLSL-runtime
                                                                checklist]
    M9  WGSL GPU compute backend (validate vs the oracle)      [headless done;
                                                                GPU-runtime
                                                                checklist]

Public API:
    compile(source) -> CompiledExpression   Parse a Python expression.
    group(compiled) -> GroupedGraph         Wrap user functions as regions.
    plan_source(source) -> EmissionPlan     Plan the Blender node tree.
    evaluate(compiled, P=...) -> EvalResult Run it in numpy (needs numpy).
    CompileError                            Raised on unsupported syntax.
"""

from coding_nodes.frontend import CompileError, CompiledExpression, compile
from coding_nodes.grouping import GroupedGraph, GroupRegion, group
from coding_nodes.backend import (
    EmissionPlan,
    build_plan,
    emit_glsl,
    emit_osl,
    emit_wgsl,
    glsl_source,
    osl_source,
    plan_source,
    wgsl_source,
)

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
    "osl_source",
    "emit_osl",
    "glsl_source",
    "emit_glsl",
    "wgsl_source",
    "emit_wgsl",
]

# The evaluator needs numpy — the only part of the package that does.
# Exposed at top level when numpy is present; the rest works without it.
try:  # pragma: no cover - trivial import guard
    from coding_nodes.evaluator import EvalResult, evaluate
    __all__ += ["evaluate", "EvalResult"]
except ImportError:  # pragma: no cover
    pass

__version__ = "0.9.0"
