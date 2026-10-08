"""Parameter values survive a recompile when the signature is stable."""

from expressnode.backend.params import changed_signature, reconcile


def test_kept_when_name_and_type_unchanged():
    old = [("freq", "float", 6.0), ("amp", "float", 0.3)]
    new = [("freq", "float", 6.0), ("amp", "float", 0.3)]
    vals = {"freq": 12.0, "amp": 0.5}
    assert reconcile(old, new, vals) == {"freq": 12.0, "amp": 0.5}


def test_new_param_takes_default():
    old = [("freq", "float", 6.0)]
    new = [("freq", "float", 6.0), ("phase", "float", 1.5)]
    out = reconcile(old, new, {"freq": 9.0})
    assert out == {"freq": 9.0, "phase": 1.5}


def test_removed_param_dropped():
    old = [("freq", "float", 6.0), ("amp", "float", 0.3)]
    new = [("freq", "float", 6.0)]
    out = reconcile(old, new, {"freq": 9.0, "amp": 0.9})
    assert out == {"freq": 9.0}
    assert "amp" not in out


def test_type_change_resets_to_default():
    old = [("k", "float", 1.0)]
    new = [("k", "vector", (0.0, 0.0, 0.0))]
    out = reconcile(old, new, {"k": 42.0})
    assert out == {"k": (0.0, 0.0, 0.0)}


def test_changed_signature_detects_name_change():
    assert changed_signature(
        [("a", "float", 0.0)], [("b", "float", 0.0)]
    )


def test_changed_signature_detects_type_change():
    assert changed_signature(
        [("a", "float", 0.0)], [("a", "vector", (0, 0, 0))]
    )


def test_changed_signature_false_when_only_defaults_differ():
    assert not changed_signature(
        [("a", "float", 0.0)], [("a", "float", 9.0)]
    )
