"""Error recovery: auto-fix common LLM syntax mistakes before parsing.

LLMs often produce a2e-lang with minor syntax issues. This module
applies heuristic fixes to source code before parsing, increasing
tolerance for LLM-generated output.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Fix registry — ordered list of (pattern, replacement, description)
# ---------------------------------------------------------------------------

_FIXES: list[tuple[re.Pattern, str, str]] = [
    # 1. Missing quotes around workflow name
    #    workflow my-pipeline  →  workflow "my-pipeline"
    (
        re.compile(r'^(\s*workflow\s+)([a-zA-Z_][a-zA-Z0-9_-]*)\s*$', re.MULTILINE),
        r'\1"\2"',
        "Added quotes around workflow name",
    ),

    # 2. Colon after 'workflow' keyword
    #    workflow: "name"  →  workflow "name"
    (
        re.compile(r'^(\s*workflow)\s*:\s*', re.MULTILINE),
        r'\1 ',
        "Removed colon after 'workflow'",
    ),

    # 3. Semicolons at end of lines (JS/TS habit)
    #    method: "GET";  →  method: "GET"
    (
        re.compile(r';\s*$', re.MULTILINE),
        '',
        "Removed trailing semicolons",
    ),

    # 4. Type annotations (TypeScript habit)
    #    method: string = "GET"  →  method: "GET"
    (
        re.compile(r':\s*(?:string|number|boolean|int|float)\s*=\s*', re.MULTILINE),
        ': ',
        "Removed type annotations",
    ),

    # 5. 'operation' or 'op' keyword instead of just the type
    #    fetch = operation ApiCall {  →  fetch = ApiCall {
    (
        re.compile(r'=\s*(?:operation|op)\s+([A-Z]\w+)'),
        r'= \1',
        "Removed 'operation' keyword prefix",
    ),

    # 6. Arrow syntax variants (=> or --> instead of ->)
    #    => /workflow/out  →  -> /workflow/out
    (
        re.compile(r'(?<!=)\s*=>\s*(/\S+)'),
        r' -> \1',
        "Converted => to ->",
    ),
    (
        re.compile(r'-->\s*(/\S+)'),
        r'-> \1',
        "Converted --> to ->",
    ),

    # 7. 'input' instead of 'from'
    #    input /workflow/data  →  from /workflow/data
    (
        re.compile(r'^\s*input\s+(/\S+)', re.MULTILINE),
        r'  from \1',
        "Converted 'input' to 'from'",
    ),

    # 8. 'output' instead of '->'
    #    output /workflow/result  →  -> /workflow/result
    (
        re.compile(r'^\s*output\s+(/\S+)', re.MULTILINE),
        r'  -> \1',
        "Converted 'output' to '->'",
    ),

    # 9. 'execute' or 'order' instead of 'run'
    #    execute: a -> b -> c  →  run: a -> b -> c
    (
        re.compile(r'^(\s*)(?:execute|order)\s*:', re.MULTILINE),
        r'\1run:',
        "Converted 'execute'/'order' to 'run'",
    ),

    # 10. Trailing commas in objects
    #     { key: "val", }  →  { key: "val" }
    (
        re.compile(r',\s*(\})'),
        r' \1',
        "Removed trailing commas",
    ),

    # 11. Python-style True/False/None
    #     True  →  true, False  →  false, None  →  null
    (
        re.compile(r'\bTrue\b'),
        'true',
        "Converted Python 'True' to 'true'",
    ),
    (
        re.compile(r'\bFalse\b'),
        'false',
        "Converted Python 'False' to 'false'",
    ),
    (
        re.compile(r'\bNone\b'),
        'null',
        "Converted Python 'None' to 'null'",
    ),

    # 12. Single quotes → double quotes (Python/JS habit)
    #     method: 'GET'  →  method: "GET"
    (
        re.compile(r"(?<=:\s)'([^']*)'"),
        r'"\1"',
        "Converted single quotes to double quotes",
    ),
]


class RecoveryResult:
    """Result of error recovery processing."""

    def __init__(self, source: str, original: str, fixes: list[str]):
        self.source = source
        self.original = original
        self.fixes = fixes

    @property
    def was_modified(self) -> bool:
        return self.source != self.original

    def summary(self) -> str:
        if not self.fixes:
            return "No fixes needed"
        lines = [f"Applied {len(self.fixes)} fix(es):"]
        for fix in self.fixes:
            lines.append(f"  • {fix}")
        return "\n".join(lines)


def recover(source: str) -> RecoveryResult:
    """Apply heuristic fixes to source code.

    Returns a RecoveryResult with the fixed source and a list of
    applied fixes. The original source is preserved in the result.
    """
    original = source
    fixes: list[str] = []

    for pattern, replacement, description in _FIXES:
        new_source = pattern.sub(replacement, source)
        if new_source != source:
            fixes.append(description)
            source = new_source

    return RecoveryResult(source=source, original=original, fixes=fixes)


def parse_with_recovery(source: str):
    """Try to parse source, falling back to error recovery on failure.

    Returns (workflow, recovery_result) tuple.
    """
    from .parser import parse
    from .errors import ParseError

    # First try: parse as-is
    try:
        workflow = parse(source)
        return workflow, RecoveryResult(source, source, [])
    except ParseError:
        pass

    # Second try: apply fixes and parse again
    result = recover(source)
    if not result.was_modified:
        # No fixes to try — re-raise original error
        workflow = parse(source)  # will raise
        return workflow, result  # unreachable

    workflow = parse(result.source)
    return workflow, result
