"""Lark-based parser for a2e-lang — transforms source text into AST."""

from __future__ import annotations

import os
from pathlib import Path as FilePath

from lark import Lark, Token, Transformer, Tree, v_args
from lark.exceptions import UnexpectedInput

from .ast_nodes import (
    ArrayValue,
    Condition,
    Credential,
    IfClause,
    ObjectValue,
    Operation,
    Path,
    Property,
    Workflow,
)
from .errors import ParseError

# ---------------------------------------------------------------------------
# Grammar loading (cached)
# ---------------------------------------------------------------------------

_GRAMMAR_PATH = FilePath(__file__).parent / "grammar.lark"
_lark_parser: Lark | None = None


def _get_parser() -> Lark:
    global _lark_parser
    if _lark_parser is None:
        grammar_text = _GRAMMAR_PATH.read_text(encoding="utf-8")
        _lark_parser = Lark(
            grammar_text,
            parser="earley",
            propagate_positions=True,
        )
    return _lark_parser


# ---------------------------------------------------------------------------
# Transformer: Lark parse tree -> AST nodes
# ---------------------------------------------------------------------------

class A2ETransformer(Transformer):
    """Converts Lark parse tree into a2e-lang AST."""

    # --- Top-level ---

    def start(self, items):
        name = None
        operations = []
        execution_order = None
        for item in items:
            if isinstance(item, str):
                name = item  # workflow name
            elif isinstance(item, Operation):
                operations.append(item)
            elif isinstance(item, tuple) and item and isinstance(item[0], str):
                # Could be execution_order or a workflow name
                # Distinguish by checking if name is already set
                if name is None:
                    name = item[0]
                else:
                    execution_order = item
        return Workflow(
            name=name or "unnamed",
            operations=tuple(operations),
            execution_order=execution_order,
        )

    def workflow_decl(self, items):
        # items[0] is an ESCAPED_STRING token
        return _unquote(items[0])

    def operation_def(self, items):
        op_id = str(items[0])  # IDENT
        op_type = str(items[1])  # IDENT (operation type name)

        properties = []
        input_path = None
        output_path = None
        conditions = None
        if_clause = None
        line = items[0].line if hasattr(items[0], "line") else 0
        column = items[0].column if hasattr(items[0], "column") else 0

        for item in items[2:]:
            if isinstance(item, Property):
                properties.append(item)
            elif isinstance(item, str) and item.startswith("/"):
                # Disambiguation: from_clause or output_arrow both produce strings
                # This shouldn't happen — we use tagged tuples below
                pass
            elif isinstance(item, tuple):
                tag, val = item
                if tag == "from":
                    input_path = val
                elif tag == "output":
                    output_path = val
                elif tag == "conditions":
                    conditions = val
            elif isinstance(item, IfClause):
                if_clause = item

        return Operation(
            id=op_id,
            op_type=op_type,
            properties=tuple(properties),
            input_path=input_path,
            output_path=output_path,
            conditions=conditions,
            if_clause=if_clause,
            line=line,
            column=column,
        )

    def run_decl(self, items):
        return tuple(str(tok) for tok in items)

    # --- Operation body items ---

    def property(self, items):
        key = _unquote(items[0]) if items[0].type == "ESCAPED_STRING" else str(items[0])
        value = items[1]
        return Property(key=key, value=value)

    def from_clause(self, items):
        return ("from", items[0].raw if isinstance(items[0], Path) else str(items[0]))

    def where_clause(self, items):
        return ("conditions", tuple(items))

    def if_clause(self, items):
        # items: path, COMPARE_OP, [value], "then" ident_list, ["else" ident_list]
        path_val = items[0].raw if isinstance(items[0], Path) else str(items[0])
        operator = str(items[1])

        idx = 2
        value = None
        if idx < len(items) and not isinstance(items[idx], tuple):
            # It's the optional value (not an ident_list tuple)
            value = items[idx]
            idx += 1

        if_true = items[idx] if idx < len(items) else ()
        idx += 1
        if_false = items[idx] if idx < len(items) else None

        return IfClause(
            path=path_val,
            operator=operator,
            value=value,
            if_true=if_true,
            if_false=if_false,
        )

    def output_arrow(self, items):
        return ("output", items[0].raw if isinstance(items[0], Path) else str(items[0]))

    def condition(self, items):
        field = str(items[0])
        operator = str(items[1])
        value = items[2] if len(items) > 2 else None
        return Condition(field=field, operator=operator, value=value)

    def ident_list(self, items):
        return tuple(str(tok) for tok in items)

    # --- Values ---

    def string_val(self, items):
        return _unquote(items[0])

    def number_val(self, items):
        s = str(items[0])
        if "." in s:
            return float(s)
        return int(s)

    def true_val(self, _items):
        return True

    def false_val(self, _items):
        return False

    def null_val(self, _items):
        return None

    def path_val(self, items):
        return items[0]  # already a Path from path()

    def ident_val(self, items):
        return str(items[0])

    def path(self, items):
        return Path(raw=str(items[0]))

    def credential(self, items):
        return Credential(id=_unquote(items[0]))

    def object(self, items):
        return ObjectValue(properties=tuple(items))

    def array(self, items):
        return ArrayValue(items=tuple(items))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unquote(token: Token) -> str:
    """Remove surrounding quotes from an ESCAPED_STRING token."""
    s = str(token)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(source: str) -> Workflow:
    """Parse a2e-lang source code and return a Workflow AST.

    Raises ParseError on syntax errors.
    """
    try:
        tree = _get_parser().parse(source)
        return A2ETransformer().transform(tree)
    except UnexpectedInput as e:
        raise ParseError(
            message=str(e),
            line=getattr(e, "line", None),
            column=getattr(e, "column", None),
        ) from e
