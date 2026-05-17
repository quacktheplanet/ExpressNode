"""Backend: GroupedGraph -> EmissionPlan -> Blender node tree.

Headless, testable:
    op_emitters   op -> Blender node descriptor registry
    plan          build_plan(compiled) -> EmissionPlan
    pipeline      plan_source(source) -> EmissionPlan
    osl           emit_osl(compiled) -> OSL shader source

Requires Blender:
    gn_executor   execute(plan) -> bpy NodeTree
    pipeline      build_in_blender(source) -> bpy NodeTree
"""

from coding_nodes.backend.op_emitters import (
    OpEmitter,
    all_emitter_ops,
    frontend_op_universe,
    get_emitter,
)
from coding_nodes.backend.plan import (
    EmissionPlan,
    GroupDef,
    build_plan,
)
from coding_nodes.backend.pipeline import osl_source, plan_source
from coding_nodes.backend.osl import emit_osl, osl_template_ops

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
]
