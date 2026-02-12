# a2e-lang

DSL compiler for the **[A2E (Agent-to-Execution) Protocol](https://github.com/MauricioPerera/a2e)**. It compiles a human-readable domain-specific language into A2E JSONL format, enabling AI agents to generate workflows without writing verbose JSON.

## What is A2E?

A2E is a declarative protocol that enables AI agents to safely generate and execute workflows without arbitrary code execution. The protocol defines 8 core operations (`ApiCall`, `FilterData`, `TransformData`, `Conditional`, `Loop`, `StoreData`, `Wait`, `MergeData`) and uses JSONL as its transport format.

See the [full A2E specification](https://github.com/MauricioPerera/a2e/blob/main/SPECIFICATION.md).

## Why a2e-lang?

Writing A2E workflows in raw JSONL is verbose and error-prone. `a2e-lang` provides a compact, readable syntax that compiles down to valid A2E JSONL:

```
a2e-lang DSL (human-readable)  →  A2E JSONL (machine-readable)
```

This is especially useful when AI agents (LLMs) generate workflows from natural language — the DSL is more concise than raw JSON, reducing token usage and generation errors.

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

Create a file named `pipeline.a2e`:

```a2e
workflow "user-pipeline"

fetch_users = ApiCall {
  method: "GET"
  url: "https://api.example.com/users"
  headers: { Authorization: credential("api-token") }
  -> /workflow/users
}

filter_active = FilterData {
  from /workflow/users
  where status == "active", points > 100
  -> /workflow/filtered
}

store = StoreData {
  from /workflow/filtered
  storage: "localStorage"
  key: "active-users"
}

run: fetch_users -> filter_active -> store
```

Compile it to A2E JSONL:

```bash
a2e-lang compile pipeline.a2e
a2e-lang compile pipeline.a2e --pretty  # indented output
```

## Project Structure

```
a2e_lang/
├── grammar.lark      # Lark EBNF grammar for the DSL
├── parser.py         # Lark-based parser → AST
├── ast_nodes.py      # Immutable AST data models
├── validator.py      # Semantic validator (8 checks)
├── compiler.py       # AST → A2E JSONL
├── errors.py         # Error types with source locations
└── cli.py            # Command-line interface
examples/
├── simple.a2e        # Basic 3-operation pipeline
├── full_workflow.a2e # All 8 operation types
└── test_workers_ai.py # LLM agent generates a2e-lang from natural language
tests/                # 24 tests (pytest)
```

## Architecture

The compilation follows three stages:

1. **Parsing**: `grammar.lark` + Lark (Earley parser) → AST (immutable frozen dataclasses)
2. **Validation**: 8 semantic checks (unique IDs, valid types, required props, cycle detection, etc.)
3. **Compilation**: AST → A2E protocol JSONL (`operationUpdate` + `beginExecution`)

## CLI Usage

```
a2e-lang compile <file> [--pretty]  # Compile .a2e to JSONL
a2e-lang validate <file>            # Validate without compiling
a2e-lang ast <file>                 # Show parsed AST (debug)
```

## A2E Operations Supported

All 8 core operations from the [A2E protocol spec](https://github.com/MauricioPerera/a2e/blob/main/SPECIFICATION.md):

| Operation | Description |
|---|---|
| `ApiCall` | HTTP requests (GET, POST, PUT, DELETE, PATCH) |
| `FilterData` | Array filtering with conditions |
| `TransformData` | Data transformation (sort, select, map, group) |
| `Conditional` | Conditional branching (if/then/else) |
| `Loop` | Array iteration |
| `StoreData` | Persistent storage |
| `Wait` | Execution delay |
| `MergeData` | Merge multiple data sources |

Plus 8 additional utility operations: `GetCurrentDateTime`, `ConvertTimezone`, `DateCalculation`, `FormatText`, `ExtractText`, `ValidateData`, `Calculate`, `EncodeDecode`.

## Language Reference

See [LANGUAGE.md](./LANGUAGE.md) for the complete DSL syntax reference.

## Related

- **[A2E Protocol](https://github.com/MauricioPerera/a2e)** — The protocol specification this compiler targets
