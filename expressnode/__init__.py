"""ExpressNode: type a maths expression, get a clean Geometry Nodes tree.

The package is both the compiler (importable without Blender) and a Blender
extension (register / unregister below, blender_manifest.toml beside this file).

Public API:
    compile(source) -> CompiledExpression   Parse a Python expression.
    group(compiled) -> GroupedGraph         Wrap user functions as regions.
    plan_source(source) -> EmissionPlan     Plan the Blender node tree.
    osl_source / glsl_source / wgsl_source  The same expression for Cycles OSL,
                                            Blender's GPU module, and WebGPU.
    evaluate(compiled, P=...) -> EvalResult Run it in numpy (needs numpy).
    CompileError                            Raised on unsupported syntax.
"""

from .frontend import CompileError, CompiledExpression, compile
from .grouping import GroupedGraph, GroupRegion, group
from .backend import (
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
    from .evaluator import EvalResult, evaluate
    __all__ += ["evaluate", "EvalResult"]
except ImportError:  # pragma: no cover
    pass

__version__ = "0.9.0"


# --- Blender extension -------------------------------------------------------

def _publish_name():
    """Inside Blender the extension is imported as bl_ext.<repo>.expressnode.
    Other add-ons (CodeNodes' Bake to Nodes) import it as plain `expressnode`,
    so make that name, and the old `coding_nodes`, point at this same package and
    its submodules."""
    import pkgutil
    import sys
    me = __name__
    if me == "expressnode":
        return
    for info in pkgutil.walk_packages(__path__, me + "."):
        if info.name.endswith((".modifier", ".node_group", ".migrate")):
            continue                    # need bpy; imported by register()
        try:
            __import__(info.name)
        except ImportError:             # numpy-only parts, e.g. the evaluator
            pass
    for alias in ("expressnode", "coding" + "_nodes"):
        for name, module in list(sys.modules.items()):
            if name == me or name.startswith(me + "."):
                sys.modules.setdefault(alias + name[len(me):], module)


def register():
    from .backend import modifier, node_group
    from . import migrate
    modifier.register()
    node_group.register()
    migrate.register()
    _publish_name()


def unregister():
    from .backend import modifier, node_group
    from . import migrate
    migrate.unregister()
    node_group.unregister()
    modifier.unregister()
