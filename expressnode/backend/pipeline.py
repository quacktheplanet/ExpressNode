"""End-to-end glue: source -> compile -> group -> plan -> (Blender) tree.

`plan_source` is headless (no bpy) and is what the tests exercise.
`build_in_blender` adds the bpy execution step.

`apply_mode` selects how the expression result is delivered:
    raw       expression group only (Shape B — drop into a tree)
    offset    wrapped as a modifier; Result becomes a Set Position offset
    absolute  wrapped as a modifier; Result becomes the absolute position
"""

from __future__ import annotations

import json

from ..backend.plan import EmissionPlan, build_plan
from ..frontend.parser import CompiledExpression, compile


def plan_source(source: str, inline_threshold: int = 3,
                apply_mode: str = "raw") -> EmissionPlan:
    """Compile + group + plan. Pure, headless. Raises CompileError on
    unsupported syntax, KeyError if an op lacks an emitter."""
    compiled: CompiledExpression = compile(source)
    return build_plan(compiled, inline_threshold=inline_threshold,
                      apply_mode=apply_mode)


def osl_source(source: str, shader_name: str = "") -> str:
    """Compile + emit an OSL shader. Pure, headless."""
    from ..backend.osl import emit_osl
    return emit_osl(compile(source), shader_name=shader_name)


def glsl_source(source: str, func_name: str = "") -> str:
    """Compile + emit a GLSL fragment shader. Pure, headless."""
    from ..backend.glsl import emit_glsl
    return emit_glsl(compile(source), func_name=func_name)


def wgsl_source(source: str, fn_name: str = "") -> str:
    """Compile + emit a WGSL compute shader. Pure, headless."""
    from ..backend.wgsl import emit_wgsl
    return emit_wgsl(compile(source), fn_name=fn_name)


def build_in_blender(source: str, inline_threshold: int = 3,
                     apply_mode: str = "raw", suffix: str | None = None):
    """Compile + group + plan + execute. Requires Blender. Returns the
    deliverable root NodeTree (the modifier wrapper when apply_mode wraps,
    else the raw expression group).

    `suffix` is appended to the tree names. None picks one: the existing
    tree is rebuilt in place when it came from the same source, otherwise
    a fresh ".001"-style name is used.
    """
    plan = plan_source(source, inline_threshold=inline_threshold,
                       apply_mode=apply_mode)
    from ..backend.gn_executor import execute, tree_name_for
    if suffix is None:
        suffix = tree_name_for(plan, source)
    tree = execute(plan, suffix=suffix, source=source)
    tree["expressnode_params"] = json.dumps(plan.parameters)
    return tree
