"""AST node definitions for a2e-lang — all frozen (immutable) dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


# ---------------------------------------------------------------------------
# Leaf values
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Path:
    """A data-model path like /workflow/users."""
    raw: str  # full path string including leading /

    def __str__(self) -> str:
        return self.raw


@dataclass(frozen=True)
class Credential:
    """A credential reference: credential("api-token")."""
    id: str


@dataclass(frozen=True)
class ObjectValue:
    """An inline object: { key: value, ... }."""
    properties: tuple[Property, ...]


@dataclass(frozen=True)
class ArrayValue:
    """An inline array: [val1, val2, ...]."""
    items: tuple[Value, ...]


# Value is the union of all possible value types
Value = Union[str, int, float, bool, None, Path, Credential, ObjectValue, ArrayValue]


# ---------------------------------------------------------------------------
# Structural nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Property:
    """A key-value pair: key: value."""
    key: str
    value: Value


@dataclass(frozen=True)
class Condition:
    """A filter condition: field operator value."""
    field: str
    operator: str
    value: Value


@dataclass(frozen=True)
class IfClause:
    """Conditional clause: if /path op value then targets else targets."""
    path: str
    operator: str
    value: Value | None  # None for unary ops like exists/empty
    if_true: tuple[str, ...]   # operation IDs
    if_false: tuple[str, ...] | None


@dataclass(frozen=True)
class Operation:
    """A single operation definition."""
    id: str
    op_type: str
    properties: tuple[Property, ...]
    input_path: str | None = None         # from clause
    output_path: str | None = None        # -> clause
    conditions: tuple[Condition, ...] | None = None   # where clause
    if_clause: IfClause | None = None
    line: int = 0
    column: int = 0


@dataclass(frozen=True)
class Workflow:
    """Root AST node representing a complete workflow."""
    name: str
    operations: tuple[Operation, ...]
    execution_order: tuple[str, ...] | None = None  # from run: clause
