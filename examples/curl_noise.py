"""Example: curl-noise vector field (divergence-free).

curl(P, t, scale, strength) approximates a curl-noise field via finite
differences of three independent scalar noise channels (offset by seed
index). The result is a vec3 used as a position offset to produce
organic swirling motion.

Helper function `n` becomes a named sub-group in the compiled output
(in the M2 grouping pass). For M1, the parser inlines n() each time
it's called.
"""


def n(P, seed):
    return noise(P + vec3(seed * 13.7, seed * 29.1, seed * 47.3))


def curl(P, t, scale=2.0, strength=0.4):
    eps = 0.001
    nx_dy = n(P + vec3(0.0, eps, 0.0), 1.0) - n(P + vec3(0.0, -eps, 0.0), 1.0)
    nx_dz = n(P + vec3(0.0, 0.0, eps), 1.0) - n(P + vec3(0.0, 0.0, -eps), 1.0)
    ny_dx = n(P + vec3(eps, 0.0, 0.0), 2.0) - n(P + vec3(-eps, 0.0, 0.0), 2.0)
    ny_dz = n(P + vec3(0.0, 0.0, eps), 2.0) - n(P + vec3(0.0, 0.0, -eps), 2.0)
    nz_dx = n(P + vec3(eps, 0.0, 0.0), 3.0) - n(P + vec3(-eps, 0.0, 0.0), 3.0)
    nz_dy = n(P + vec3(0.0, eps, 0.0), 3.0) - n(P + vec3(0.0, -eps, 0.0), 3.0)
    return vec3(nz_dy - ny_dz, nx_dz - nz_dx, ny_dx - nx_dy)
