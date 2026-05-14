"""CompileError — carries source-line and column information so the UI can
mark the offending location and show a helpful message."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SourceSpan:
    """A span in the source text. Line/col are 1-based, matching Python's
    `ast` module conventions."""
    line: int
    col: int
    end_line: int | None = None
    end_col: int | None = None
    source_line: str | None = None  # the actual source-line text, for display

    @classmethod
    def from_ast(cls, node: Any, source_lines: list[str] | None = None
                 ) -> "SourceSpan":
        line = getattr(node, "lineno", 0)
        col = getattr(node, "col_offset", 0) + 1
        end_line = getattr(node, "end_lineno", None)
        end_col = getattr(node, "end_col_offset", None)
        if end_col is not None:
            end_col += 1
        source_line = None
        if source_lines is not None and 1 <= line <= len(source_lines):
            source_line = source_lines[line - 1]
        return cls(line=line, col=col, end_line=end_line, end_col=end_col,
                   source_line=source_line)


class CompileError(Exception):
    """Raised when an expression cannot be compiled. Carries a SourceSpan
    so the UI can underline the offending region."""

    def __init__(self, message: str, span: SourceSpan | None = None,
                 hint: str | None = None):
        self.message = message
        self.span = span
        self.hint = hint
        super().__init__(self._format())

    def _format(self) -> str:
        loc = ""
        if self.span is not None:
            loc = f" at line {self.span.line}, col {self.span.col}"
        out = f"CompileError{loc}: {self.message}"
        if self.span and self.span.source_line is not None:
            out += f"\n  {self.span.source_line}\n  {' ' * (self.span.col - 1)}^"
        if self.hint:
            out += f"\nhint: {self.hint}"
        return out

    def __repr__(self) -> str:
        return f"CompileError({self.message!r}, span={self.span!r})"
