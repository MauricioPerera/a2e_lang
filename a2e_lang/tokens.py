"""Token budget calculator: compare DSL vs JSONL token costs.

Estimates the token cost of a2e-lang DSL source vs its compiled JSONL output
using a simple tokenizer heuristic (GPT-4 style: ~4 chars per token on average,
or optionally tiktoken for exact counts).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .compiler_spec import SpecCompiler
from .parser import parse


@dataclass(frozen=True)
class TokenBudget:
    """Token cost comparison between DSL and JSONL."""

    dsl_chars: int
    dsl_tokens: int
    jsonl_chars: int
    jsonl_tokens: int

    @property
    def savings_tokens(self) -> int:
        return self.jsonl_tokens - self.dsl_tokens

    @property
    def savings_pct(self) -> float:
        if self.jsonl_tokens == 0:
            return 0.0
        return (self.savings_tokens / self.jsonl_tokens) * 100

    @property
    def compression_ratio(self) -> float:
        if self.dsl_tokens == 0:
            return 0.0
        return self.jsonl_tokens / self.dsl_tokens

    def summary(self) -> str:
        lines = [
            "Token Budget Analysis",
            "═" * 40,
            f"  DSL source:    {self.dsl_tokens:>6} tokens ({self.dsl_chars:>6} chars)",
            f"  JSONL output:  {self.jsonl_tokens:>6} tokens ({self.jsonl_chars:>6} chars)",
            "─" * 40,
            f"  Savings:       {self.savings_tokens:>6} tokens ({self.savings_pct:.1f}%)",
            f"  Compression:   {self.compression_ratio:.1f}x",
        ]
        return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    """Estimate token count using GPT-4 style heuristic.

    Average ~4 characters per token for English text and code.
    JSON tends to be slightly more due to structural characters.
    """
    # Try tiktoken first for accuracy
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-4")
        return len(enc.encode(text))
    except (ImportError, Exception):
        pass

    # Heuristic fallback: ~4 chars per token for code
    return max(1, len(text) // 4)


def calculate_budget(source: str) -> TokenBudget:
    """Calculate token budget for a2e-lang source vs compiled JSONL.

    Args:
        source: a2e-lang DSL source code.

    Returns:
        TokenBudget with cost comparison.
    """
    workflow = parse(source)
    jsonl = SpecCompiler().compile(workflow)

    dsl_tokens = _estimate_tokens(source)
    jsonl_tokens = _estimate_tokens(jsonl)

    return TokenBudget(
        dsl_chars=len(source),
        dsl_tokens=dsl_tokens,
        jsonl_chars=len(jsonl),
        jsonl_tokens=jsonl_tokens,
    )
