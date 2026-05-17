"""curl_noise.py evaluates over arrays: finite, deterministic, shaped
right, and genuinely time/seed dependent."""

from pathlib import Path

import numpy as np

from coding_nodes import compile, evaluate

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _c():
    return compile((EXAMPLES / "curl_noise.py").read_text())


def _P(n=64, seed=0):
    return np.random.RandomState(seed).uniform(-2.0, 2.0, size=(n, 3))


def test_returns_vec3_per_point_and_finite():
    P = _P()
    r = evaluate(_c(), P=P, t=0.5).values
    assert r.shape == (64, 3)
    assert np.all(np.isfinite(r))


def test_deterministic_same_inputs_same_output():
    c, P = _c(), _P()
    a = evaluate(c, P=P, t=0.5, seed=7).values
    b = evaluate(c, P=P, t=0.5, seed=7).values
    np.testing.assert_array_equal(a, b)


def test_time_changes_the_field():
    c, P = _c(), _P()
    a = evaluate(c, P=P, t=0.0).values
    b = evaluate(c, P=P, t=5.0).values
    assert np.abs(a - b).max() > 1e-6


def test_seed_changes_the_field():
    c, P = _c(), _P()
    a = evaluate(c, P=P, t=1.0, seed=1).values
    b = evaluate(c, P=P, t=1.0, seed=2).values
    assert np.abs(a - b).max() > 1e-6


def test_strength_scales_magnitude_monotonically():
    c, P = _c(), _P()
    lo = evaluate(c, P=P, t=1.0, params={"strength": 0.2}).values
    hi = evaluate(c, P=P, t=1.0, params={"strength": 0.8}).values
    # curl body multiplies by strength; larger strength -> larger field.
    assert np.linalg.norm(hi) > np.linalg.norm(lo)
