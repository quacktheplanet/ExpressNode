"""Reference procedural noise — the canonical definition.

The numpy evaluator is the *oracle*: every other backend (OSL, GLSL,
GPU) must reproduce these functions exactly. So the algorithms here are
the specification, not an approximation of Blender's built-in nodes.
(Blender's own Noise/Voronoi nodes differ; expressions that use
`noise()`/`voronoi()` therefore match the OSL/GLSL backends — which we
control — but not the GN backend, which delegates to Blender's nodes.
This is documented in docs/evaluator.md.)

Definitions:
  value noise   integer-lattice value noise with quintic fade and
                trilinear interpolation; 4D = two 3D lattice slices at
                floor(w) and floor(w)+1 blended by the faded frac(w).
                Range [0, 1].
  voronoi F1    cellular noise: one feature point per integer cell at
                cell + hash3(cell); returns the Euclidean distance to
                the nearest feature point over the 3x3x3 neighbourhood.
"""

from __future__ import annotations

import numpy as np

_U32 = np.uint32


def _hash_u32(*parts: np.ndarray) -> np.ndarray:
    """Deterministic uint32 hash of integer lattice coords. Wraps on
    overflow (intended); no warnings."""
    with np.errstate(over="ignore"):
        h = np.broadcast_to(_U32(0x9E3779B1), parts[0].shape).copy()
        for p in parts:
            h = (h ^ p.astype(_U32)) * _U32(0x85EBCA77)
            h ^= h >> _U32(13)
        h = (h ^ (h >> _U32(15))) * _U32(0xC2B2AE3D)
        h ^= h >> _U32(13)
    return h


def _hash01(*parts: np.ndarray) -> np.ndarray:
    """Hash -> float in [0, 1)."""
    return _hash_u32(*parts).astype(np.float64) / 4294967296.0


def _fade(t: np.ndarray) -> np.ndarray:
    """Quintic smootherstep 6t^5 - 15t^4 + 10t^3."""
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _lerp(a, b, w):
    return a + (b - a) * w


def _slice_3d(x, y, z, iw, seed: int) -> np.ndarray:
    """3D value noise of (x,y,z) on the lattice slice indexed by the
    integer-w array `iw`, so each time-slice is independent. Output in
    [0, 1] with the broadcast shape of the inputs."""
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    iz = np.floor(z).astype(np.int64)
    ux = _fade(x - ix)
    uy = _fade(y - iy)
    uz = _fade(z - iz)
    s = np.broadcast_to(_U32(np.uint32(seed & 0xFFFFFFFF)), ix.shape)
    iw32 = np.broadcast_to(iw, ix.shape).astype(_U32)

    def corner(dx, dy, dz):
        return _hash01(
            (ix + dx).astype(_U32),
            (iy + dy).astype(_U32),
            (iz + dz).astype(_U32),
            s, iw32,
        )

    c000, c100 = corner(0, 0, 0), corner(1, 0, 0)
    c010, c110 = corner(0, 1, 0), corner(1, 1, 0)
    c001, c101 = corner(0, 0, 1), corner(1, 0, 1)
    c011, c111 = corner(0, 1, 1), corner(1, 1, 1)
    x00 = _lerp(c000, c100, ux)
    x10 = _lerp(c010, c110, ux)
    x01 = _lerp(c001, c101, ux)
    x11 = _lerp(c011, c111, ux)
    y0 = _lerp(x00, x10, uy)
    y1 = _lerp(x01, x11, uy)
    return _lerp(y0, y1, uz)


def value_noise(P: np.ndarray, w: np.ndarray | float = 0.0,
                 seed: int = 0) -> np.ndarray:
    """4D value noise. P is (..., 3); w is the 4th coord (time). Result
    has P's leading shape, range [0, 1].

    The 4D field is two independent 3D value-noise slices, at integer
    w = floor(w) and floor(w)+1, blended by the quintic fade of frac(w).
    """
    P = np.asarray(P, dtype=np.float64)
    x = np.ascontiguousarray(P[..., 0])
    y = np.ascontiguousarray(P[..., 1])
    z = np.ascontiguousarray(P[..., 2])
    w = np.broadcast_to(np.asarray(w, dtype=np.float64), x.shape)
    iw = np.floor(w).astype(np.int64)
    fw = _fade(w - iw)
    a = _slice_3d(x, y, z, iw, seed)
    b = _slice_3d(x, y, z, iw + 1, seed)
    return _lerp(a, b, fw)


def voronoi_f1(P: np.ndarray, seed: int = 0) -> np.ndarray:
    """Cellular F1 distance. P is (..., 3); returns the Euclidean
    distance to the nearest per-cell feature point over the 3x3x3
    neighbourhood."""
    P = np.asarray(P, dtype=np.float64)
    base = np.floor(P).astype(np.int64)
    best = np.full(P.shape[:-1], np.inf, dtype=np.float64)
    s = np.uint32(seed & 0xFFFFFFFF)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cell = base + np.array([dx, dy, dz])
                cx = cell[..., 0].astype(_U32)
                cy = cell[..., 1].astype(_U32)
                cz = cell[..., 2].astype(_U32)
                sb = np.broadcast_to(_U32(s), cx.shape)
                fx = _hash01(cx, cy, cz, sb)
                fy = _hash01(cy, cz, cx, sb)
                fz = _hash01(cz, cx, cy, sb)
                feat = cell.astype(np.float64) + np.stack(
                    [fx, fy, fz], axis=-1)
                d = np.linalg.norm(P - feat, axis=-1)
                best = np.minimum(best, d)
    return best
