"""Documentation can't silently drift from the implementation.

These guards fail if a built-in is added/removed without updating
docs/expression-reference.md, or if an op loses its emitter. Keeping
docs trustworthy is an explicit project requirement.
"""

from pathlib import Path

from coding_nodes.backend.op_emitters import (
    BACKEND_ONLY_OPS,
    all_emitter_ops,
    frontend_op_universe,
)
from coding_nodes.frontend.builtins import BUILTIN_FNS, BUILTIN_VARS

DOCS = Path(__file__).resolve().parents[2] / "docs"
REF = DOCS / "expression-reference.md"


def test_every_builtin_function_is_documented():
    doc = REF.read_text()
    missing = sorted(n for n in BUILTIN_FNS if n not in doc)
    assert not missing, (
        f"built-in functions absent from expression-reference.md: {missing}"
    )


def test_every_builtin_variable_is_documented():
    doc = REF.read_text()
    missing = sorted(n for n in BUILTIN_VARS if n not in doc)
    assert not missing, (
        f"built-in variables absent from expression-reference.md: {missing}"
    )


def test_emitter_registry_covers_frontend_universe():
    """Restated here so the M5 suite alone guarantees the core contract:
    every frontend op has an emitter."""
    missing = sorted(frontend_op_universe() - all_emitter_ops())
    assert not missing, f"ops with no emitter: {missing}"


def test_backend_only_ops_are_registered_and_excluded_from_frontend():
    for op in BACKEND_ONLY_OPS:
        assert op in all_emitter_ops()
        assert op not in frontend_op_universe()


def test_key_docs_exist():
    for name in ("grouping.md", "emission.md", "evaluator.md", "osl.md",
                 "expression-reference.md", "existing-alternatives.md"):
        assert (DOCS / name).exists(), f"missing docs/{name}"
    root = DOCS.parents[1]
    for name in ("ROADMAP.md",):
        assert (root / name).exists(), f"missing {name}"
    cn = DOCS.parent
    for name in ("README.md", "SPEC.md", "SCOPE.md", "PLAN.md",
                 "TESTING.md"):
        assert (cn / name).exists(), f"missing coding-nodes/{name}"
