"""Backend: GroupedGraph -> EmissionPlan -> Blender node tree.

Headless, testable:
    op_emitters   op -> Blender node descriptor registry
    plan          build_plan(compiled) -> EmissionPlan
    pipeline      plan_source(source) -> EmissionPlan
    osl           emit_osl(compiled) -> OSL shader source
    glsl          emit_glsl(compiled) -> GLSL fragment shader source
    wgsl          emit_wgsl(compiled) -> WGSL compute shader source

Requires Blender:
    gn_executor   execute(plan) -> bpy NodeTree
    pipeline      build_in_blender(source) -> bpy NodeTree
"""

from ..backend.op_emitters import (
    OpEmitter,
    all_emitter_ops,
    frontend_op_universe,
    get_emitter,
)
from ..backend.plan import (
    EmissionPlan,
    GroupDef,
    build_plan,
)
from ..backend.pipeline import (
    glsl_source,
    osl_source,
    plan_source,
    wgsl_source,
)
from ..backend.osl import emit_osl, osl_template_ops
from ..backend.glsl import emit_glsl, glsl_template_ops
from ..backend.wgsl import emit_wgsl, wgsl_template_ops

__all__ = [
    "OpEmitter",
    "get_emitter",
    "all_emitter_ops",
    "frontend_op_universe",
    "EmissionPlan",
    "GroupDef",
    "build_plan",
    "plan_source",
    "osl_source",
    "emit_osl",
    "osl_template_ops",
    "glsl_source",
    "emit_glsl",
    "glsl_template_ops",
    "wgsl_source",
    "emit_wgsl",
    "wgsl_template_ops",
]
