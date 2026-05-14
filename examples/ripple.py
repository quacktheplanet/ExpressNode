"""Example: time-varying ripple displacement.

The function ripple(P, t) takes the implicit position `P` (vec3) and
the implicit scene time `t` (float). Optional parameters `freq` and
`amp` are exposed as runtime inputs on the generated GN group.

When compiled, this becomes a small Geometry Nodes subtree:
    P.x * freq + t -> sin -> * amp -> vec3(0, 0, .) -> output
"""


def ripple(P, t, freq=6.0, amp=0.3):
    return vec3(0.0, 0.0, sin(P.x * freq + t) * amp)
