"""ExpressionParser — walks a Python AST and emits an EvalGraph.

Entry point: `compile(source)`. Returns a `CompiledExpression` carrying
the EvalGraph, the entry function's name, declared inputs (parameter
names + types), and the inferred return type.

The parser is intentionally strict: any construct outside the supported
subset raises `CompileError` with the source span pointing at the
offender.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field as _dc_field
from typing import Any

from coding_nodes._ir.eval_graph import EvalGraph, EvalNode, SocketType

from coding_nodes.frontend.builtins import (
    BUILTIN_FNS,
    BUILTIN_VARS,
    SPECIAL_FUNCTIONS,
)
from coding_nodes.frontend.errors import CompileError, SourceSpan
from coding_nodes.frontend.types import (
    TypeKind,
    promote,
    vec_type_for_arity,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ExprValue:
    """A subexpression's compiled result: the EvalNode that produces it,
    the name of the output socket on that node, and the inferred type."""
    node: EvalNode
    socket: str
    type: TypeKind

    def as_tuple(self) -> tuple[EvalNode, str]:
        return (self.node, self.socket)


@dataclass
class Parameter:
    """A user-declared parameter on the entry function. Exposed as a
    runtime input on the generated GN group."""
    name: str
    type: TypeKind
    default: Any | None = None


@dataclass
class CompiledExpression:
    """Result of `compile(source)`."""
    source: str
    graph: EvalGraph
    entry_function: str
    parameters: list[Parameter] = _dc_field(default_factory=list)
    return_type: TypeKind | None = None
    # Map function name -> list of EvalNode ids belonging to that function
    # (across all call instances). Kept for convenience / quick checks.
    function_scopes: dict[str, list[int]] = _dc_field(default_factory=dict)
    # Map node id -> its scope path, a tuple of frame ids like
    # ("curl#0", "n#3"). The M2 grouping pass uses this to reconstruct the
    # call tree and wrap each call instance as its own sub-group.
    scope_paths: dict[int, tuple[str, ...]] = _dc_field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "entry_function": self.entry_function,
            "parameters": [
                {"name": p.name, "type": p.type.value, "default": p.default}
                for p in self.parameters
            ],
            "return_type": self.return_type.value if self.return_type else None,
            "graph": self.graph.describe(),
            "user_functions": list(self.function_scopes.keys()),
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _Scope:
    """A lexical scope holding (name -> ExprValue) bindings."""

    def __init__(self, parent: "_Scope | None" = None):
        self.parent = parent
        self.bindings: dict[str, ExprValue] = {}

    def lookup(self, name: str) -> ExprValue | None:
        if name in self.bindings:
            return self.bindings[name]
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def bind(self, name: str, value: ExprValue) -> None:
        self.bindings[name] = value


class ExpressionParser:
    """The compiler frontend. Walks an AST and emits into self.graph."""

    def __init__(self, source: str):
        self.source = source
        self.source_lines = source.splitlines()
        self.graph = EvalGraph()
        self.user_functions: dict[str, ast.FunctionDef] = {}
        self.entry_function: ast.FunctionDef | None = None
        self.parameters: list[Parameter] = []
        self.return_type: TypeKind | None = None
        self.function_scopes: dict[str, list[int]] = {}
        self.scope_paths: dict[int, tuple[str, ...]] = {}
        # Stack of frame ids like "curl#0". Each function entry (the entry
        # function or an inlined call) pushes a uniquely-numbered frame so
        # the grouping pass can tell call instances apart.
        self._scope_stack: list[str] = []
        self._scope_counter: int = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def compile(self) -> CompiledExpression:
        try:
            tree = ast.parse(self.source)
        except SyntaxError as e:
            span = SourceSpan(
                line=e.lineno or 1,
                col=(e.offset or 1),
                source_line=(self.source_lines[e.lineno - 1]
                             if e.lineno and 1 <= e.lineno <= len(self.source_lines)
                             else None),
            )
            raise CompileError(f"Syntax error: {e.msg}", span=span) from e

        self._collect_top_level(tree)

        if self.entry_function is None:
            raise CompileError(
                "No entry function found. Define a function "
                "(e.g. `def ripple(P, t): ...`) or write a top-level expression."
            )

        scope = _Scope()
        return_value = self._compile_function(self.entry_function, scope)

        # Wire the entry function's return as the graph output.
        if return_value is not None:
            self.graph.set_output("result", return_value.node, return_value.socket)
            self.return_type = return_value.type

        return CompiledExpression(
            source=self.source,
            graph=self.graph,
            entry_function=self.entry_function.name,
            parameters=self.parameters,
            return_type=self.return_type,
            function_scopes=self.function_scopes,
            scope_paths=self.scope_paths,
        )

    # ------------------------------------------------------------------
    # Top-level scanning
    # ------------------------------------------------------------------

    def _collect_top_level(self, tree: ast.Module) -> None:
        """Pass 1: identify user-defined functions and pick an entry function.

        Rules:
        - If there's a top-level `def`, the LAST one is the entry.
        - If there's no `def` but there's a single top-level expression, we
          synthesize an entry function from it.
        - Multiple top-level expressions are an error.
        """
        bare_exprs: list[ast.Expr] = []
        for stmt in tree.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.name in self.user_functions:
                    raise CompileError(
                        f"Function {stmt.name!r} is defined more than once.",
                        span=SourceSpan.from_ast(stmt, self.source_lines),
                    )
                self.user_functions[stmt.name] = stmt
                self.entry_function = stmt
            elif isinstance(stmt, ast.Expr):
                bare_exprs.append(stmt)
            elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                raise CompileError(
                    "Imports aren't allowed inside an expression. "
                    "The built-ins (sin, noise, vec3, attr, …) are already "
                    "available.",
                    span=SourceSpan.from_ast(stmt, self.source_lines),
                )
            elif isinstance(stmt, (ast.ClassDef, ast.AsyncFunctionDef)):
                raise CompileError(
                    f"{type(stmt).__name__} isn't compileable. "
                    "Use plain `def` functions.",
                    span=SourceSpan.from_ast(stmt, self.source_lines),
                )
            else:
                raise CompileError(
                    f"Unsupported top-level statement: {type(stmt).__name__}.",
                    span=SourceSpan.from_ast(stmt, self.source_lines),
                )

        if self.entry_function is None and bare_exprs:
            if len(bare_exprs) > 1:
                raise CompileError(
                    "Multiple top-level expressions. Wrap them in a `def`.",
                    span=SourceSpan.from_ast(bare_exprs[1], self.source_lines),
                )
            self.entry_function = self._synthesize_entry_from(bare_exprs[0])

    def _synthesize_entry_from(self, expr_stmt: ast.Expr) -> ast.FunctionDef:
        """Wrap a bare expression in `def __expr__(): return <expr>` so the
        rest of the compiler can treat it uniformly."""
        ret = ast.Return(value=expr_stmt.value)
        ast.copy_location(ret, expr_stmt)
        fn = ast.FunctionDef(
            name="__expr__",
            args=ast.arguments(
                posonlyargs=[], args=[], kwonlyargs=[],
                kw_defaults=[], defaults=[],
            ),
            body=[ret],
            decorator_list=[],
        )
        ast.copy_location(fn, expr_stmt)
        ast.fix_missing_locations(fn)
        self.user_functions[fn.name] = fn
        return fn

    # ------------------------------------------------------------------
    # Function compilation
    # ------------------------------------------------------------------

    def _compile_function(self, fn: ast.FunctionDef,
                           outer_scope: _Scope,
                           arg_values: list[ExprValue] | None = None
                           ) -> ExprValue | None:
        """Compile a function body. For the entry function, `arg_values` is
        None and we bind each parameter to either a built-in variable or a
        new exposed parameter. For inlined user-function calls, `arg_values`
        provides the caller's argument bindings."""

        is_entry = (arg_values is None)
        scope = _Scope(parent=outer_scope)

        # Bind parameters.
        if is_entry:
            for arg in fn.args.args:
                pname = arg.arg
                if pname in BUILTIN_VARS:
                    bv = BUILTIN_VARS[pname]
                    node = self.graph.add_node(
                        op=bv.op,
                        output_sockets=(("value", bv.type.to_socket_type()),),
                    )
                    scope.bind(pname, ExprValue(node, "value", bv.type))
                else:
                    # User parameter — exposed as a runtime input.
                    pdefault = self._extract_default(fn, pname)
                    ptype = self._infer_param_type(pname, pdefault)
                    node = self.graph.add_node(
                        op="input.parameter",
                        params={"name": pname,
                                "default": pdefault,
                                "type": ptype.value},
                        output_sockets=(("value", ptype.to_socket_type()),),
                    )
                    self.graph.add_parameter(pname, node, "default", pdefault)
                    scope.bind(pname, ExprValue(node, "value", ptype))
                    self.parameters.append(
                        Parameter(name=pname, type=ptype, default=pdefault)
                    )
        else:
            # Inlined call: bind each formal to the caller's actual.
            if len(arg_values) != len(fn.args.args):
                raise CompileError(
                    f"Function {fn.name!r} takes {len(fn.args.args)} "
                    f"argument(s), got {len(arg_values)}.",
                    span=SourceSpan.from_ast(fn, self.source_lines),
                )
            for arg, val in zip(fn.args.args, arg_values):
                scope.bind(arg.arg, val)

        # Walk the body.
        self.function_scopes.setdefault(fn.name, [])
        frame_id = f"{fn.name}#{self._scope_counter}"
        self._scope_counter += 1
        self._scope_stack.append(frame_id)
        try:
            return_value: ExprValue | None = None
            for stmt in fn.body:
                if isinstance(stmt, ast.Return):
                    return_value = self._compile_expr(stmt.value, scope)
                    break
                elif isinstance(stmt, ast.Assign):
                    self._compile_assign(stmt, scope)
                elif isinstance(stmt, ast.AugAssign):
                    raise CompileError(
                        "Augmented assignment (+=, *=, …) isn't supported. "
                        "Use plain assignment.",
                        span=SourceSpan.from_ast(stmt, self.source_lines),
                    )
                elif isinstance(stmt, ast.FunctionDef):
                    # Nested function — register; can be called later in this
                    # scope.
                    self.user_functions[stmt.name] = stmt
                elif isinstance(stmt, ast.Expr):
                    # bare expression — evaluate for side effects (set_attr).
                    self._compile_expr(stmt.value, scope)
                elif isinstance(stmt, ast.If):
                    raise CompileError(
                        "`if` statements aren't supported. Use a conditional "
                        "expression: `a if cond else b`.",
                        span=SourceSpan.from_ast(stmt, self.source_lines),
                    )
                elif isinstance(stmt, (ast.For, ast.While)):
                    raise CompileError(
                        f"{type(stmt).__name__.lower()} loops aren't supported "
                        "in compiled expressions.",
                        span=SourceSpan.from_ast(stmt, self.source_lines),
                    )
                elif isinstance(stmt, (ast.Try, ast.Raise)):
                    raise CompileError(
                        "Exception handling isn't supported. "
                        "Use conditional expressions instead.",
                        span=SourceSpan.from_ast(stmt, self.source_lines),
                    )
                else:
                    raise CompileError(
                        f"Unsupported statement: {type(stmt).__name__}.",
                        span=SourceSpan.from_ast(stmt, self.source_lines),
                    )
            return return_value
        finally:
            self._scope_stack.pop()

    def _extract_default(self, fn: ast.FunctionDef, pname: str) -> Any | None:
        """Return the literal default for `pname`, if any."""
        args = fn.args.args
        defaults = fn.args.defaults
        # defaults align to the END of args.
        offset = len(args) - len(defaults)
        for i, a in enumerate(args):
            if a.arg == pname:
                idx = i - offset
                if idx < 0:
                    return None
                d = defaults[idx]
                return self._literal_value(d)
        return None

    def _literal_value(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
                and isinstance(node.operand, ast.Constant):
            return -node.operand.value
        raise CompileError(
            "Function parameter defaults must be plain literals.",
            span=SourceSpan.from_ast(node, self.source_lines),
        )

    def _infer_param_type(self, pname: str, default: Any | None) -> TypeKind:
        if isinstance(default, bool):
            return TypeKind.BOOL
        if isinstance(default, int):
            return TypeKind.INT
        if isinstance(default, float):
            return TypeKind.FLOAT
        # No default — assume float, the most useful for user-supplied scalars.
        return TypeKind.FLOAT

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _compile_assign(self, stmt: ast.Assign, scope: _Scope) -> None:
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            raise CompileError(
                "Assignment target must be a simple name (no tuples or "
                "subscripts).",
                span=SourceSpan.from_ast(stmt, self.source_lines),
            )
        name = stmt.targets[0].id
        value = self._compile_expr(stmt.value, scope)
        scope.bind(name, value)

    # ------------------------------------------------------------------
    # Expression compilation
    # ------------------------------------------------------------------

    def _compile_expr(self, node: ast.AST, scope: _Scope) -> ExprValue:
        method = getattr(self, f"_compile_{type(node).__name__}", None)
        if method is None:
            raise CompileError(
                f"Unsupported expression: {type(node).__name__}.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        try:
            return method(node, scope)
        except TypeError as e:
            # The graph refuses a link between incompatible sockets (e.g.
            # a string in arithmetic). Report it at this expression.
            if "SocketType.STRING" in str(e):
                msg = ("Text can't be used as a value; strings only name "
                       "things, as in attr('name') or obj('name', 'field').")
            else:
                msg = f"Type mismatch: {e}"
            raise CompileError(
                msg, span=SourceSpan.from_ast(node, self.source_lines),
            ) from None

    def _emit(self, op: str, *, params: dict | None = None,
              input_sockets: tuple = (),
              output_sockets: tuple = (),
              ) -> EvalNode:
        node = self.graph.add_node(
            op=op,
            params=dict(params) if params else {},
            input_sockets=input_sockets,
            output_sockets=output_sockets,
        )
        if self._scope_stack:
            path = tuple(self._scope_stack)
            node.params["__scope_path__"] = path
            self.scope_paths[node.id] = path
            fn_name = self._scope_stack[-1].rsplit("#", 1)[0]
            self.function_scopes.setdefault(fn_name, []).append(node.id)
            node.params["__function_scope__"] = fn_name
        return node

    # --- literals ---

    def _compile_Constant(self, node: ast.Constant, scope: _Scope) -> ExprValue:
        v = node.value
        if isinstance(v, bool):
            n = self._emit(
                "constant.bool",
                params={"value": v},
                output_sockets=(("value", SocketType.INT),),
            )
            return ExprValue(n, "value", TypeKind.BOOL)
        if isinstance(v, int):
            n = self._emit(
                "constant.int",
                params={"value": v},
                output_sockets=(("value", SocketType.INT),),
            )
            return ExprValue(n, "value", TypeKind.INT)
        if isinstance(v, float):
            n = self._emit(
                "constant.float",
                params={"value": v},
                output_sockets=(("value", SocketType.FLOAT),),
            )
            return ExprValue(n, "value", TypeKind.FLOAT)
        if isinstance(v, str):
            n = self._emit(
                "constant.string",
                params={"value": v},
                output_sockets=(("value", SocketType.STRING),),
            )
            # We don't have a TypeKind for strings; surface as FLOAT but the
            # parser only allows strings as literal args to attr()/obj().
            return ExprValue(n, "value", TypeKind.FLOAT)
        raise CompileError(
            f"Unsupported literal type: {type(v).__name__}.",
            span=SourceSpan.from_ast(node, self.source_lines),
        )

    # --- name lookup ---

    def _compile_Name(self, node: ast.Name, scope: _Scope) -> ExprValue:
        found = scope.lookup(node.id)
        if found is not None:
            return found
        if node.id in BUILTIN_VARS:
            bv = BUILTIN_VARS[node.id]
            n = self._emit(
                bv.op,
                output_sockets=(("value", bv.type.to_socket_type()),),
            )
            return ExprValue(n, "value", bv.type)
        raise CompileError(
            f"Unknown name: {node.id!r}.",
            span=SourceSpan.from_ast(node, self.source_lines),
            hint=("Built-in variables: "
                  + ", ".join(sorted(BUILTIN_VARS))
                  + "."),
        )

    # --- arithmetic ---

    def _compile_BinOp(self, node: ast.BinOp, scope: _Scope) -> ExprValue:
        left = self._compile_expr(node.left, scope)
        right = self._compile_expr(node.right, scope)
        op_map = {
            ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul",
            ast.Div: "div", ast.FloorDiv: "floordiv", ast.Mod: "mod",
            ast.Pow: "pow",
        }
        if type(node.op) not in op_map:
            raise CompileError(
                f"Unsupported binary operator: {type(node.op).__name__}.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        op_name = op_map[type(node.op)]
        try:
            result_type = promote(left.type, right.type)
        except TypeError as e:
            raise CompileError(
                str(e),
                span=SourceSpan.from_ast(node, self.source_lines),
            ) from None

        is_vector = result_type.is_vector()
        op = f"{'vec' if is_vector else 'math'}.{op_name}"
        in_type = SocketType.VECTOR if is_vector else SocketType.FLOAT
        out_sock = result_type.to_socket_type()
        # The op needs left and right with matching types — vector broadcasts
        # the scalar; we record the op only, the backend handles broadcasting.
        n = self._emit(
            op,
            input_sockets=(
                ("a", left.type.to_socket_type()),
                ("b", right.type.to_socket_type()),
            ),
            output_sockets=(("value", out_sock),),
        )
        self.graph.link(left.node, left.socket, n, "a")
        self.graph.link(right.node, right.socket, n, "b")
        return ExprValue(n, "value", result_type)

    def _compile_UnaryOp(self, node: ast.UnaryOp, scope: _Scope) -> ExprValue:
        operand = self._compile_expr(node.operand, scope)
        if isinstance(node.op, ast.USub):
            op = "vec.neg" if operand.type.is_vector() else "math.neg"
            n = self._emit(
                op,
                input_sockets=(("a", operand.type.to_socket_type()),),
                output_sockets=(("value", operand.type.to_socket_type()),),
            )
            self.graph.link(operand.node, operand.socket, n, "a")
            return ExprValue(n, "value", operand.type)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.Not):
            if operand.type != TypeKind.BOOL:
                raise CompileError(
                    "`not` requires a boolean operand.",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            n = self._emit(
                "bool.not",
                input_sockets=(("a", SocketType.INT),),
                output_sockets=(("value", SocketType.INT),),
            )
            self.graph.link(operand.node, operand.socket, n, "a")
            return ExprValue(n, "value", TypeKind.BOOL)
        raise CompileError(
            f"Unsupported unary operator: {type(node.op).__name__}.",
            span=SourceSpan.from_ast(node, self.source_lines),
        )

    # --- comparisons & boolean ---

    def _compile_Compare(self, node: ast.Compare, scope: _Scope) -> ExprValue:
        if len(node.ops) != 1:
            raise CompileError(
                "Chained comparisons (a < b < c) aren't supported. "
                "Use boolean operators: `a < b and b < c`.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        left = self._compile_expr(node.left, scope)
        right = self._compile_expr(node.comparators[0], scope)
        op_map = {
            ast.Eq: "eq", ast.NotEq: "ne",
            ast.Lt: "lt", ast.LtE: "le",
            ast.Gt: "gt", ast.GtE: "ge",
        }
        if type(node.ops[0]) not in op_map:
            raise CompileError(
                f"Unsupported comparison: {type(node.ops[0]).__name__}.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        n = self._emit(
            f"compare.{op_map[type(node.ops[0])]}",
            input_sockets=(
                ("a", left.type.to_socket_type()),
                ("b", right.type.to_socket_type()),
            ),
            output_sockets=(("value", SocketType.INT),),
        )
        self.graph.link(left.node, left.socket, n, "a")
        self.graph.link(right.node, right.socket, n, "b")
        return ExprValue(n, "value", TypeKind.BOOL)

    def _compile_BoolOp(self, node: ast.BoolOp, scope: _Scope) -> ExprValue:
        op_name = "and" if isinstance(node.op, ast.And) else "or"
        values = [self._compile_expr(v, scope) for v in node.values]
        current = values[0]
        for other in values[1:]:
            n = self._emit(
                f"bool.{op_name}",
                input_sockets=(
                    ("a", SocketType.INT),
                    ("b", SocketType.INT),
                ),
                output_sockets=(("value", SocketType.INT),),
            )
            self.graph.link(current.node, current.socket, n, "a")
            self.graph.link(other.node, other.socket, n, "b")
            current = ExprValue(n, "value", TypeKind.BOOL)
        return current

    # --- conditional expression ---

    def _compile_IfExp(self, node: ast.IfExp, scope: _Scope) -> ExprValue:
        cond = self._compile_expr(node.test, scope)
        if cond.type != TypeKind.BOOL:
            # Allow scalar truthiness in compiled form: nonzero == true.
            pass
        true_v = self._compile_expr(node.body, scope)
        false_v = self._compile_expr(node.orelse, scope)
        # Result type: must match; promote if compatible.
        if true_v.type != false_v.type:
            try:
                result_type = promote(true_v.type, false_v.type)
            except TypeError as e:
                raise CompileError(
                    f"Conditional branches have incompatible types "
                    f"({true_v.type.value} vs {false_v.type.value}): {e}",
                    span=SourceSpan.from_ast(node, self.source_lines),
                ) from None
        else:
            result_type = true_v.type

        socket_t = result_type.to_socket_type()
        n = self._emit(
            "flow.if",
            input_sockets=(
                ("cond", SocketType.INT),
                ("true", socket_t),
                ("false", socket_t),
            ),
            output_sockets=(("value", socket_t),),
        )
        self.graph.link(cond.node, cond.socket, n, "cond")
        self.graph.link(true_v.node, true_v.socket, n, "true")
        self.graph.link(false_v.node, false_v.socket, n, "false")
        return ExprValue(n, "value", result_type)

    # --- attribute access (P.x, v.xyz) ---

    def _compile_Attribute(self, node: ast.Attribute,
                           scope: _Scope) -> ExprValue:
        target = self._compile_expr(node.value, scope)
        attr = node.attr
        if not target.type.is_vector():
            raise CompileError(
                f"Attribute access {attr!r} requires a vector "
                f"(got {target.type.value}).",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        # Single-component access: .x, .y, .z, .w
        if attr in ("x", "y", "z", "w"):
            idx = "xyzw".index(attr)
            if idx >= target.type.vector_arity():
                raise CompileError(
                    f"Component .{attr} not available on {target.type.value}.",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            n = self._emit(
                f"vec.component.{attr}",
                input_sockets=(("vector", SocketType.VECTOR),),
                output_sockets=(("value", SocketType.FLOAT),),
            )
            self.graph.link(target.node, target.socket, n, "vector")
            return ExprValue(n, "value", TypeKind.FLOAT)
        # Swizzle: .xy, .xyz, .yxyx, etc.
        if all(c in "xyzw" for c in attr) and 2 <= len(attr) <= 4:
            arity = target.type.vector_arity()
            for c in attr:
                if "xyzw".index(c) >= arity:
                    raise CompileError(
                        f"Component .{c} in swizzle .{attr} not available "
                        f"on {target.type.value}.",
                        span=SourceSpan.from_ast(node, self.source_lines),
                    )
            n = self._emit(
                "vec.swizzle",
                params={"pattern": attr},
                input_sockets=(("vector", SocketType.VECTOR),),
                output_sockets=(("value", SocketType.VECTOR),),
            )
            self.graph.link(target.node, target.socket, n, "vector")
            return ExprValue(n, "value", vec_type_for_arity(len(attr)))
        raise CompileError(
            f"Unsupported attribute access: .{attr}.",
            span=SourceSpan.from_ast(node, self.source_lines),
            hint="Vector components are .x, .y, .z, .w and swizzles like .xy, .xyz.",
        )

    # --- subscript (v[0]) ---

    def _compile_Subscript(self, node: ast.Subscript,
                           scope: _Scope) -> ExprValue:
        target = self._compile_expr(node.value, scope)
        if not target.type.is_vector():
            raise CompileError(
                "Subscript requires a vector.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
            idx = node.slice.value
            if idx < 0 or idx >= target.type.vector_arity():
                raise CompileError(
                    f"Subscript {idx} out of range for {target.type.value}.",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            comp = "xyzw"[idx]
            n = self._emit(
                f"vec.component.{comp}",
                input_sockets=(("vector", SocketType.VECTOR),),
                output_sockets=(("value", SocketType.FLOAT),),
            )
            self.graph.link(target.node, target.socket, n, "vector")
            return ExprValue(n, "value", TypeKind.FLOAT)
        raise CompileError(
            "Vector subscript must be a constant integer (e.g. v[0]).",
            span=SourceSpan.from_ast(node, self.source_lines),
        )

    # --- function calls ---

    def _compile_Call(self, node: ast.Call, scope: _Scope) -> ExprValue:
        if node.keywords:
            # Reject **kwargs and keyword arguments for now (M1 simplification).
            for kw in node.keywords:
                if kw.arg is None:
                    raise CompileError(
                        "** unpacking isn't supported in calls.",
                        span=SourceSpan.from_ast(kw, self.source_lines),
                    )
            raise CompileError(
                "Keyword arguments aren't supported in calls yet. "
                "Pass arguments positionally.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        for a in node.args:
            if isinstance(a, ast.Starred):
                raise CompileError(
                    "* unpacking isn't supported in calls.",
                    span=SourceSpan.from_ast(a, self.source_lines),
                )

        if not isinstance(node.func, ast.Name):
            raise CompileError(
                "Function calls must use a simple name (e.g. `sin(x)`), "
                "not method or expression calls.",
                span=SourceSpan.from_ast(node, self.source_lines),
            )
        name = node.func.id

        # Special-case attr() / set_attr() / obj() because their return type
        # depends on string-literal arguments, not just types.
        if name in SPECIAL_FUNCTIONS:
            return self._compile_special_call(name, node, scope)

        # User-defined functions inline.
        if name in self.user_functions:
            fn = self.user_functions[name]
            arg_vals = [self._compile_expr(a, scope) for a in node.args]
            result = self._compile_function(fn, scope, arg_values=arg_vals)
            if result is None:
                raise CompileError(
                    f"Function {name!r} has no return value.",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            return result

        # Built-in functions.
        if name in BUILTIN_FNS:
            return self._compile_builtin_call(name, node, scope)

        raise CompileError(
            f"Unknown function {name!r}.",
            span=SourceSpan.from_ast(node, self.source_lines),
            hint="Built-in functions: " + ", ".join(sorted(BUILTIN_FNS)) + ".",
        )

    def _compile_builtin_call(self, name: str, node: ast.Call,
                              scope: _Scope) -> ExprValue:
        spec = BUILTIN_FNS[name]
        arg_vals = [self._compile_expr(a, scope) for a in node.args]
        arg_types = tuple(v.type for v in arg_vals)
        return_type = spec.match(arg_types)
        if return_type is None:
            raise CompileError(
                f"No matching signature for {name}("
                + ", ".join(t.value for t in arg_types) + ").",
                span=SourceSpan.from_ast(node, self.source_lines),
                hint=("Supported signatures: "
                      + "; ".join(
                          f"{name}(" + ", ".join(t.value for t in sig) + ")"
                          for sig, _ in spec.signatures
                      )),
            )
        # Build the eval node.
        input_sockets = tuple(
            (f"arg{i}", v.type.to_socket_type()) for i, v in enumerate(arg_vals)
        )
        n = self._emit(
            spec.op_name,
            input_sockets=input_sockets,
            output_sockets=(("value", return_type.to_socket_type()),),
        )
        for i, v in enumerate(arg_vals):
            self.graph.link(v.node, v.socket, n, f"arg{i}")
        return ExprValue(n, "value", return_type)

    def _compile_special_call(self, name: str, node: ast.Call,
                              scope: _Scope) -> ExprValue:
        """attr(), set_attr(), obj() — return type / behavior depends on
        string-literal arguments."""
        args = node.args

        def _str_literal(arg: ast.AST) -> str:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value
            raise CompileError(
                f"{name}() requires a string literal here.",
                span=SourceSpan.from_ast(arg, self.source_lines),
            )

        if name == "attr":
            if len(args) not in (1, 2):
                raise CompileError(
                    "attr() takes 1 or 2 arguments: attr('name') or "
                    "attr('name', 'dtype').",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            attr_name = _str_literal(args[0])
            dtype = "float"
            if len(args) == 2:
                dtype = _str_literal(args[1])
            type_map = {
                "float": TypeKind.FLOAT,
                "int": TypeKind.INT,
                "bool": TypeKind.BOOL,
                "vec3": TypeKind.VEC3,
                "vec2": TypeKind.VEC2,
                "vec4": TypeKind.VEC4,
                "color": TypeKind.VEC4,
            }
            if dtype not in type_map:
                raise CompileError(
                    f"Unknown attribute dtype {dtype!r}. "
                    f"Use one of: {', '.join(sorted(type_map))}.",
                    span=SourceSpan.from_ast(args[1], self.source_lines),
                )
            tk = type_map[dtype]
            n = self._emit(
                "attr.read",
                params={"name": attr_name, "dtype": dtype},
                output_sockets=(("value", tk.to_socket_type()),),
            )
            return ExprValue(n, "value", tk)

        if name == "set_attr":
            if len(args) != 2:
                raise CompileError(
                    "set_attr() takes 2 arguments: set_attr('name', value).",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            attr_name = _str_literal(args[0])
            value = self._compile_expr(args[1], scope)
            n = self._emit(
                "attr.write",
                params={"name": attr_name, "dtype": value.type.value},
                input_sockets=(("value", value.type.to_socket_type()),),
                output_sockets=(("ok", SocketType.INT),),
            )
            self.graph.link(value.node, value.socket, n, "value")
            return ExprValue(n, "ok", TypeKind.BOOL)

        if name == "obj":
            if len(args) != 2:
                raise CompileError(
                    "obj() takes 2 arguments: obj('name', 'field').",
                    span=SourceSpan.from_ast(node, self.source_lines),
                )
            obj_name = _str_literal(args[0])
            field = _str_literal(args[1])
            field_types = {
                "position": TypeKind.VEC3,
                "rotation": TypeKind.VEC3,
                "scale": TypeKind.VEC3,
            }
            if field not in field_types:
                raise CompileError(
                    f"Unknown object field {field!r}. "
                    f"Use one of: {', '.join(sorted(field_types))}.",
                    span=SourceSpan.from_ast(args[1], self.source_lines),
                )
            tk = field_types[field]
            n = self._emit(
                "obj.read",
                params={"object": obj_name, "field": field},
                output_sockets=(("value", tk.to_socket_type()),),
            )
            return ExprValue(n, "value", tk)

        raise CompileError(
            f"Internal: unhandled special function {name!r}.",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile(source: str) -> CompiledExpression:
    """Compile a Python expression to an EvalGraph.

    Raises CompileError if the source contains unsupported constructs.
    """
    return ExpressionParser(source).compile()
