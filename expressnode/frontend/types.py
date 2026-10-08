"""Type inference helpers for the expression frontend.

Types in the expression language are intentionally small: float, int, bool,
vec2, vec3, vec4. Type rules are static — each AST node has a single
inferred type at compile time."""

from __future__ import annotations

from enum import Enum

from .._ir.eval_graph import SocketType


class TypeKind(Enum):
    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    VEC2 = "vec2"
    VEC3 = "vec3"
    VEC4 = "vec4"

    def is_vector(self) -> bool:
        return self in (TypeKind.VEC2, TypeKind.VEC3, TypeKind.VEC4)

    def is_scalar(self) -> bool:
        return self in (TypeKind.FLOAT, TypeKind.INT, TypeKind.BOOL)

    def vector_arity(self) -> int:
        return {TypeKind.VEC2: 2, TypeKind.VEC3: 3, TypeKind.VEC4: 4}.get(self, 0)

    def to_socket_type(self) -> SocketType:
        """Map to the existing EvalGraph SocketType. vec2/4 are surfaced as
        VECTOR for v1; the GN backend treats them as vec3 with the unused
        components zero."""
        if self.is_scalar():
            return SocketType.FLOAT if self != TypeKind.INT else SocketType.INT
        return SocketType.VECTOR


def promote(a: TypeKind, b: TypeKind) -> TypeKind:
    """Numeric promotion rules for arithmetic.

    Rules:
    - vector op vector -> the vector type (must match arity)
    - vector op scalar -> the vector type (broadcasts scalar)
    - scalar op scalar -> float if either is float, else int
    - bool participating in arithmetic is treated as int
    """
    if a.is_vector() and b.is_vector():
        if a != b:
            raise TypeError(
                f"Vector arity mismatch: cannot combine {a.value} and {b.value}"
            )
        return a
    if a.is_vector():
        return a
    if b.is_vector():
        return b
    if a == TypeKind.FLOAT or b == TypeKind.FLOAT:
        return TypeKind.FLOAT
    return TypeKind.INT


def vec_type_for_arity(n: int) -> TypeKind:
    return {2: TypeKind.VEC2, 3: TypeKind.VEC3, 4: TypeKind.VEC4}[n]
