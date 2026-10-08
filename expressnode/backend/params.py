"""Parameter-binding reconciliation.

When the user edits an expression and recompiles, parameters they had
tuned should survive if they still exist with a compatible type. This is
a pure function so it is unit-tested headlessly; the modifier calls it
across a rebuild.
"""

from __future__ import annotations

from typing import Any

# (name, socket_type, default) — the shape EmissionPlan.parameters uses.
Param = tuple[str, str, Any]


def reconcile(old_params: list[Param],
              new_params: list[Param],
              user_values: dict[str, Any]) -> dict[str, Any]:
    """Carry tuned values from before a recompile into the new signature.

    A value is kept when the parameter name still exists AND its socket
    type is unchanged. New parameters take their declared default;
    removed parameters are dropped; type-changed parameters reset to the
    new default.

    Args:
        old_params:  parameters from the previous compile.
        new_params:  parameters from the fresh compile.
        user_values: name -> value the user had set on the modifier.

    Returns the value map to apply to the new modifier inputs.
    """
    old_type = {name: stype for name, stype, _ in old_params}
    result: dict[str, Any] = {}
    for name, stype, default in new_params:
        if (name in user_values
                and old_type.get(name) == stype):
            result[name] = user_values[name]
        else:
            result[name] = default
    return result


def changed_signature(old_params: list[Param],
                       new_params: list[Param]) -> bool:
    """True when the (name, type) signature differs — i.e. the node tree
    interface must be rebuilt, not just have values re-applied."""
    sig = lambda ps: [(n, t) for n, t, _ in ps]
    return sig(old_params) != sig(new_params)
