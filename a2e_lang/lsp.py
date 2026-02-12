"""a2e-lang Language Server Protocol (LSP) implementation.

Provides:
- Diagnostics (validation errors on save)
- Autocompletion (operation types, keywords, properties)
- Hover information (operation type descriptions)

Requires: pygls (`pip install pygls`)

Usage:
    python -m a2e_lang.lsp
"""

from __future__ import annotations

import logging
import sys

try:
    from lsprotocol import types
    from pygls.server import LanguageServer
except ImportError:
    raise ImportError(
        "LSP dependencies not installed. Run: pip install pygls"
    )

from .errors import A2ELangError
from .parser import parse
from .validator import Validator, VALID_OP_TYPES, REQUIRED_PROPERTIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Completion data
# ---------------------------------------------------------------------------

OPERATION_DESCRIPTIONS = {
    "ApiCall": "HTTP request (GET, POST, PUT, DELETE, PATCH)",
    "FilterData": "Filter array data with conditions",
    "TransformData": "Transform data (sort, select, map, group)",
    "Conditional": "Conditional branching (if/then/else)",
    "Loop": "Iterate over array items",
    "StoreData": "Store data to persistent storage",
    "Wait": "Wait for a duration (ms)",
    "MergeData": "Merge multiple data sources",
    "GetCurrentDateTime": "Get current date and time",
    "ConvertTimezone": "Convert between timezones",
    "DateCalculation": "Date arithmetic operations",
    "FormatText": "Format text with templates",
    "ExtractText": "Extract text with patterns",
    "ValidateData": "Validate data against rules",
    "Calculate": "Mathematical calculations",
    "EncodeDecode": "Encode or decode data",
}

KEYWORD_COMPLETIONS = [
    ("workflow", "Declare workflow name"),
    ("run", "Define execution order"),
    ("from", "Input data path"),
    ("where", "Filter conditions"),
    ("if", "Conditional branch"),
    ("then", "True branch target"),
    ("else", "False branch target"),
    ("credential", "Credential reference"),
    ("true", "Boolean true"),
    ("false", "Boolean false"),
    ("null", "Null value"),
]

PROPERTY_SNIPPETS = {
    "ApiCall": [
        ("method", '"${1|GET,POST,PUT,DELETE,PATCH|}"'),
        ("url", '"${1:https://api.example.com}"'),
        ("headers", "{ ${1:key}: ${2:value} }"),
        ("body", "{ ${1:key}: ${2:value} }"),
        ("timeout", "${1:30000}"),
    ],
    "FilterData": [],
    "TransformData": [
        ("transform", '"${1|sort,select,map,group|}"'),
        ("config", "{ ${1:field}: ${2:value} }"),
    ],
    "Loop": [
        ("operations", "[${1:op_id}]"),
    ],
    "StoreData": [
        ("storage", '"${1|localStorage,sessionStorage,database|}"'),
        ("key", '"${1:key-name}"'),
    ],
    "Wait": [
        ("duration", "${1:5000}"),
    ],
    "MergeData": [
        ("sources", "[${1:/workflow/a}, ${2:/workflow/b}]"),
        ("strategy", '"${1|concat,union,intersect,deepMerge|}"'),
    ],
}

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

server = LanguageServer("a2e-lang-lsp", "v0.1.0")


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: types.DidOpenTextDocumentParams) -> None:
    _validate_document(params.text_document.uri, params.text_document.text)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: types.DidSaveTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    _validate_document(params.text_document.uri, doc.source)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: types.DidChangeTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    _validate_document(params.text_document.uri, doc.source)


@server.feature(types.TEXT_DOCUMENT_COMPLETION)
def completion(params: types.CompletionParams) -> types.CompletionList:
    """Provide autocompletion for operation types, keywords, and properties."""
    items: list[types.CompletionItem] = []

    # Operation type completions
    for op_type, desc in OPERATION_DESCRIPTIONS.items():
        items.append(types.CompletionItem(
            label=op_type,
            kind=types.CompletionItemKind.Class,
            detail=desc,
            insert_text=f"{op_type} {{\n  $0\n}}",
            insert_text_format=types.InsertTextFormat.Snippet,
        ))

    # Keyword completions
    for keyword, desc in KEYWORD_COMPLETIONS:
        items.append(types.CompletionItem(
            label=keyword,
            kind=types.CompletionItemKind.Keyword,
            detail=desc,
        ))

    # Property completions (context-sensitive would require more analysis)
    for op_type, props in PROPERTY_SNIPPETS.items():
        for prop_name, snippet in props:
            items.append(types.CompletionItem(
                label=prop_name,
                kind=types.CompletionItemKind.Property,
                detail=f"{op_type} property",
                insert_text=f"{prop_name}: {snippet}",
                insert_text_format=types.InsertTextFormat.Snippet,
            ))

    # Comparison operator completions
    for op in ["==", "!=", ">", "<", ">=", "<=", "contains", "startsWith", "endsWith", "in", "exists", "empty"]:
        items.append(types.CompletionItem(
            label=op,
            kind=types.CompletionItemKind.Operator,
            detail="Comparison operator",
        ))

    return types.CompletionList(is_incomplete=False, items=items)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(params: types.HoverParams) -> types.Hover | None:
    """Show hover information for operation types."""
    doc = server.workspace.get_text_document(params.text_document.uri)
    line = doc.source.splitlines()[params.position.line]
    word = _get_word_at_position(line, params.position.character)

    if word in OPERATION_DESCRIPTIONS:
        desc = OPERATION_DESCRIPTIONS[word]
        required = REQUIRED_PROPERTIES.get(word, set())
        req_str = ", ".join(sorted(required)) if required else "none"
        content = f"**{word}**\n\n{desc}\n\nRequired properties: `{req_str}`"
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=content,
            )
        )

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_document(uri: str, source: str) -> None:
    """Parse and validate the document, publishing diagnostics."""
    diagnostics: list[types.Diagnostic] = []

    try:
        workflow = parse(source)
        validator = Validator()
        errors = validator.validate(workflow)

        for error in errors:
            line = max(0, (error.line or 1) - 1)
            col = max(0, (error.column or 1) - 1)
            diagnostics.append(types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=line, character=col),
                    end=types.Position(line=line, character=col + 1),
                ),
                message=str(error),
                severity=types.DiagnosticSeverity.Error,
                source="a2e-lang",
            ))
    except A2ELangError as e:
        # Parse error
        diagnostics.append(types.Diagnostic(
            range=types.Range(
                start=types.Position(line=0, character=0),
                end=types.Position(line=0, character=1),
            ),
            message=str(e),
            severity=types.DiagnosticSeverity.Error,
            source="a2e-lang",
        ))
    except Exception as e:
        logger.error(f"Unexpected error validating document: {e}")

    server.publish_diagnostics(uri, diagnostics)


def _get_word_at_position(line: str, character: int) -> str:
    """Extract the word at the given character position."""
    if character >= len(line):
        return ""
    start = character
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1
    end = character
    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1
    return line[start:end]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Start the LSP server."""
    server.start_io()


if __name__ == "__main__":
    main()
