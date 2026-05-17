"""The reference noise/voronoi are a precise, stable spec — other
backends must reproduce them exactly, so their properties are pinned
here."""

import numpy as np

from coding_nodes.evaluator.noise import value_noise, voronoi_f1


def _grid(n=20):
    xs = np.linspace(-3, 3, n)
    P = np.stack(np.meshgrid(xs, xs, xs, indexing="ij"), axis=-1)
    return P.reshape(-1, 3)


def test_value_noise_in_unit_range():
    v = value_noise(_grid(), w=0.0, seed=0)
    assert v.min() >= 0.0 and v.max() <= 1.0


def test_value_noise_deterministic():
    P = _grid(8)
    a = value_noise(P, w=1.5, seed=3)
    b = value_noise(P, w=1.5, seed=3)
    np.testing.assert_array_equal(a, b)


def test_value_noise_seed_and_time_matter():
    P = _grid(8)
    base = value_noise(P, w=0.0, seed=0)
    assert np.abs(value_noise(P, w=0.0, seed=1) - base).max() > 1e-6
    assert np.abs(value_noise(P, w=3.0, seed=0) - base).max() > 1e-6


def test_value_noise_continuous_in_space():
    """Small position change -> small value change (no lattice jumps)."""
    P = np.zeros((1, 3)) + 0.123
    a = value_noise(P, w=0.0, seed=0)
    b = value_noise(P + 1e-4, w=0.0, seed=0)
    assert np.abs(a - b).max() < 1e-2


def test_value_noise_continuous_in_time():
    P = np.zeros((1, 3)) + 0.4
    a = value_noise(P, w=2.0, seed=0)
    b = value_noise(P, w=2.0 + 1e-4, seed=0)
    assert np.abs(a - b).max() < 1e-2


def test_voronoi_nonnegative_and_deterministic():
    P = _grid(8)
    d = voronoi_f1(P, seed=0)
    assert d.min() >= 0.0
    np.testing.assert_array_equal(d, voronoi_f1(P, seed=0))


def test_voronoi_bounded_for_in_cell_points():
    """A feature point lives within the 3x3x3 neighbourhood, so the F1
    distance is comfortably bounded."""
    P = _grid(12)
    assert voronoi_f1(P, seed=0).max() < 4.0
