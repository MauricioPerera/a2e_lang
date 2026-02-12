"""Syntax scoring: measure DSL learnability metrics.

Analyzes a2e-lang source code to produce a "learnability score" that
estimates how easy the syntax is for LLMs to generate correctly.
Higher scores = easier to learn/generate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import parse


@dataclass(frozen=True)
class SyntaxScore:
    """Learnability metrics for a2e-lang source."""

    # Individual scores (0-100)
    regularity: int        # How consistent/predictable the syntax is
    verbosity: int         # How concise vs verbose (higher = more concise)
    structure: int         # How well-structured (nesting, blocks)
    naming: int            # Quality of identifier naming
    completeness: int      # Whether all best practices are followed

    @property
    def overall(self) -> int:
        """Weighted overall learnability score (0-100)."""
        return int(
            self.regularity * 0.25 +
            self.verbosity * 0.20 +
            self.structure * 0.20 +
            self.naming * 0.20 +
            self.completeness * 0.15
        )

    def summary(self) -> str:
        grade = _grade(self.overall)
        lines = [
            f"Syntax Learnability Score: {self.overall}/100 ({grade})",
            "═" * 45,
            f"  Regularity:    {self.regularity:>3}/100  (pattern consistency)",
            f"  Verbosity:     {self.verbosity:>3}/100  (conciseness)",
            f"  Structure:     {self.structure:>3}/100  (block organization)",
            f"  Naming:        {self.naming:>3}/100  (identifier quality)",
            f"  Completeness:  {self.completeness:>3}/100  (best practices)",
        ]
        return "\n".join(lines)


def _grade(score: int) -> str:
    """Convert score to letter grade."""
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def score_syntax(source: str) -> SyntaxScore:
    """Analyze a2e-lang source and return learnability metrics."""
    workflow = parse(source)
    lines = source.strip().splitlines()
    non_empty = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]

    regularity = _score_regularity(workflow, non_empty)
    verbosity = _score_verbosity(source, workflow)
    structure = _score_structure(workflow, non_empty)
    naming = _score_naming(workflow)
    completeness = _score_completeness(workflow)

    return SyntaxScore(
        regularity=regularity,
        verbosity=verbosity,
        structure=structure,
        naming=naming,
        completeness=completeness,
    )


def _score_regularity(workflow, lines: list[str]) -> int:
    """How consistent the syntax patterns are."""
    score = 100

    # Check that all operations follow id = Type { ... } pattern
    for op in workflow.operations:
        if not op.id or not op.op_type:
            score -= 20

    # Check consistent path usage
    paths = set()
    for op in workflow.operations:
        if op.input_path:
            paths.add(op.input_path.split("/")[1] if "/" in op.input_path else "")
        if op.output_path:
            paths.add(op.output_path.split("/")[1] if "/" in op.output_path else "")

    # Penalize mixing path namespaces
    if len(paths) > 2:
        score -= 10

    return max(0, min(100, score))


def _score_verbosity(source: str, workflow) -> int:
    """How concise the source is (higher = better)."""
    char_count = len(source.strip())
    op_count = len(workflow.operations)

    if op_count == 0:
        return 50

    # Average chars per operation — lower is more concise
    chars_per_op = char_count / op_count

    if chars_per_op < 80:
        return 95
    if chars_per_op < 120:
        return 85
    if chars_per_op < 180:
        return 75
    if chars_per_op < 250:
        return 60
    return 40


def _score_structure(workflow, lines: list[str]) -> int:
    """How well-organized the blocks are."""
    score = 100

    # Has workflow declaration
    has_workflow = any("workflow" in ln for ln in lines)
    if not has_workflow:
        score -= 30

    # Has execution order
    if not workflow.execution_order:
        score -= 15

    # Operations have output paths (data flows are explicit)
    ops_with_output = sum(1 for op in workflow.operations if op.output_path)
    if workflow.operations:
        output_ratio = ops_with_output / len(workflow.operations)
        if output_ratio < 0.5:
            score -= 15

    return max(0, min(100, score))


def _score_naming(workflow) -> int:
    """Quality of identifier naming."""
    score = 100

    for op in workflow.operations:
        name = op.id

        # Penalize very short names (single char)
        if len(name) <= 1:
            score -= 15

        # Penalize names that are just the type lowered
        if name.lower() == op.op_type.lower():
            score -= 5

        # Reward snake_case (convention)
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            score -= 5

    return max(0, min(100, score))


def _score_completeness(workflow) -> int:
    """Whether best practices are followed."""
    score = 100

    # Has at least one operation
    if not workflow.operations:
        score -= 40

    # Has workflow name
    if not workflow.name or workflow.name == "unnamed":
        score -= 20

    # Has execution order
    if not workflow.execution_order:
        score -= 15

    # All ApiCalls have method and url
    for op in workflow.operations:
        if op.op_type == "ApiCall":
            props = {p.key for p in op.properties}
            if "method" not in props:
                score -= 10
            if "url" not in props:
                score -= 10

    return max(0, min(100, score))
