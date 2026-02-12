"""Error types for a2e-lang with source location context."""

from __future__ import annotations


class A2ELangError(Exception):
    """Base error with optional source location."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        self.message = message
        self.line = line
        self.column = column
        loc = ""
        if line is not None:
            loc = f" (line {line}"
            if column is not None:
                loc += f", col {column}"
            loc += ")"
        super().__init__(f"{message}{loc}")


class ParseError(A2ELangError):
    """Raised when source code cannot be parsed."""


class ValidationError(A2ELangError):
    """Raised when the AST fails semantic validation."""


class CompileError(A2ELangError):
    """Raised when compilation to JSONL fails."""
