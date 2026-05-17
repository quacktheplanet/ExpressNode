"""End-to-end glue: source -> compile -> group -> plan -> (Blender) tree.

`plan_source` is headless (no bpy) and is what the tests exercise.
`build_in_blender` adds the bpy execution step and is called by the
Expression Modifier.
"""

from __future__ import annotations

from coding_nodes.backend.plan import EmissionPlan, build_plan
from coding_nodes.frontend.parser import CompiledExpression, compile


def plan_source(source: str, inline_threshold: int = 3) -> EmissionPlan:
    """Compile + group + plan. Pure, headless. Raises CompileError on
    unsupported syntax, KeyError if an op lacks an emitter."""
    compiled: CompiledExpression = compile(source)
    return build_plan(compiled, inline_threshold=inline_threshold)


def build_in_blender(source: str, inline_threshold: int = 3):
    """Compile + group + plan + execute. Requires Blender."""
    plan = plan_source(source, inline_threshold=inline_threshold)
    from coding_nodes.backend.gn_executor import execute
    return execute(plan)
