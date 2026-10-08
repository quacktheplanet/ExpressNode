"""Numpy reference evaluator — the correctness oracle.

Runs a compiled expression's EvalGraph directly in numpy, with no
Blender. It proves the math is right (not just that the plan is shaped
right) and is the reference every other backend (OSL, GLSL, GPU) is
validated against.

Depends on numpy (the only part of the package that does).
"""

from ..evaluator.interp import EvalResult, evaluate

__all__ = ["evaluate", "EvalResult"]
