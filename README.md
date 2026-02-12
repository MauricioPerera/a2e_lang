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

Compile it:

```bash
# Official A2E spec format (recommended)
a2e-lang compile pipeline.a2e --spec

# Pretty-printed
a2e-lang compile pipeline.a2e --spec --pretty

# Legacy bundled format
a2e-lang compile pipeline.a2e
```

## Output Formats

### `--spec` — Official A2E Protocol Format (recommended)

One JSONL line per operation, matching the [A2E specification](https://github.com/MauricioPerera/a2e/blob/main/SPECIFICATION.md):

```jsonl
{"type":"operationUpdate","operationId":"fetch_users","operation":{"ApiCall":{"outputPath":"/workflow/users","method":"GET","url":"https://api.example.com/users"}}}
{"type":"operationUpdate","operationId":"filter_active","operation":{"FilterData":{"inputPath":"/workflow/users","outputPath":"/workflow/filtered","conditions":[{"field":"status","operator":"==","value":"active"}]}}}
{"type":"operationUpdate","operationId":"store","operation":{"StoreData":{"inputPath":"/workflow/filtered","storage":"localStorage","key":"active-users"}}}
{"type":"beginExecution","executionId":"user-pipeline","operationOrder":["fetch_users","filter_active","store"]}
```

Each message has:
- `"type"` — Message type (`operationUpdate` or `beginExecution`)
- `"operationId"` — Unique operation identifier
- `"executionId"` — Workflow name as execution ID
- `"operationOrder"` — Full execution sequence

### Default — Legacy Bundled Format

All operations bundled in a single `operationUpdate` message:

```jsonl
{"operationUpdate":{"workflowId":"user-pipeline","operations":[...]}}
{"beginExecution":{"workflowId":"user-pipeline","root":"fetch_users"}}
```

## CLI Usage

```
a2e-lang compile <file> [--spec] [--pretty]  # Compile .a2e to JSONL
a2e-lang validate <file>                     # Validate without compiling
a2e-lang ast <file>                          # Show parsed AST (debug)
a2e-lang graph <file>                        # Generate Mermaid flowchart
a2e-lang simulate <file> [--input data.json] # Dry-run workflow simulation
a2e-lang decompile <file>                    # Convert JSONL back to .a2e DSL
a2e-lang recover <file>                      # Auto-fix LLM syntax mistakes
a2e-lang tokens <file>                       # Token budget analysis (DSL vs JSONL)
a2e-lang score <file>                        # Syntax learnability score
a2e-lang prompt [template] --task "..."      # Generate LLM prompt template
a2e-lang prompt --list                       # List available templates
```

> **💡 VSCode Extension**: Install from `vscode-extension/` for syntax highlighting, bracket matching, and code folding. See [vscode-extension/README.md](./vscode-extension/README.md).
>
> **💡 LSP Server**: Run `python -m a2e_lang.lsp` for diagnostics, autocompletion, and hover info. Requires `pip install pygls`.

| Flag | Description |
|---|---|
| `--spec` | Output in official A2E protocol format |
| `--pretty` | Pretty-print JSON output (indented) |
| `--watch` | Watch file and recompile on changes |
| `--input` | JSON file with mock data for simulation |
| `--max-operations` | Max operations limit (simulate) |
| `--max-depth` | Max nesting depth limit (simulate) |
| `--max-conditions` | Max conditions per operation (simulate) |

## Python API

```python
from a2e_lang import parse, Validator, Compiler, SpecCompiler
from a2e_lang import Simulator, Decompiler, generate_mermaid

# Parse and validate
workflow = parse(open("pipeline.a2e").read())
errors = Validator().validate(workflow)

# Validate with complexity limits (protects against LLM-generated bloat)
errors = Validator(max_operations=20, max_depth=3, max_conditions=5).validate(workflow)

# Compile — choose your format
jsonl_spec   = SpecCompiler().compile(workflow)       # Official A2E format
jsonl_legacy = Compiler().compile(workflow)            # Legacy bundled format
jsonl_pretty = SpecCompiler().compile_pretty(workflow) # Pretty-printed
```

## Project Structure

```
a2e_lang/
├── grammar.lark       # Lark EBNF grammar for the DSL
├── parser.py          # Lark-based parser → AST
├── ast_nodes.py       # Immutable AST data models (frozen dataclasses)
├── validator.py       # Semantic validator (9 checks + complexity limits)
├── compiler.py        # AST → Legacy bundled JSONL
├── compiler_spec.py   # AST → Official A2E spec JSONL
├── graph.py           # AST → Mermaid flowchart
├── simulator.py       # Dry-run workflow simulation engine
├── decompiler.py      # JSONL → DSL (reverse compiler)
├── watcher.py         # File watcher for auto-recompilation
├── lsp.py             # Language Server Protocol (diagnostics + completion)
├── recovery.py        # Error recovery (auto-fix LLM syntax mistakes)
├── tokens.py          # Token budget calculator (DSL vs JSONL)
├── prompts.py         # LLM prompt templates (GPT-4, Claude, Gemini, etc.)
├── scoring.py         # Syntax learnability scoring
├── errors.py          # Error types with source locations
└── cli.py             # Command-line interface (11 commands)
examples/
├── simple.a2e         # Basic 3-operation pipeline
├── full_workflow.a2e  # All 8 operation types demo
└── test_workers_ai.py # LLM agent generates a2e-lang from natural language
vscode-extension/          # VSCode syntax highlighting + LSP client
tests/                 # 184 tests (pytest)
```

## Architecture

The pipeline has three core stages plus visualization and simulation:

1. **Parsing**: `grammar.lark` + Lark (Earley parser) → AST (immutable frozen dataclasses)
2. **Validation**: 9 semantic checks + configurable complexity limits
3. **Compilation**: AST → A2E protocol JSONL via `Compiler` or `SpecCompiler`
4. **Visualization**: AST → Mermaid flowchart via `graph.py`
5. **Simulation**: Dry-run execution with condition evaluation via `simulator.py`

```
                        ┌─────────────┐
                   ┌──► │  Compiler   │ ──► Legacy JSONL
                   │    └─────────────┘
┌──────┐  ┌─────┐  │    ┌─────────────┐
│.a2e  │─►│Parse│──┼──► │SpecCompiler │ ──► A2E Spec JSONL
│source│  │+ AST│  │    └─────────────┘
└──────┘  └──┬──┘  │    ┌─────────────┐
             │     ├──► │   Graph     │ ──► Mermaid
         ┌───▼────┐│    └─────────────┘
         │Validate││    ┌─────────────┐
         └────────┘└──► │  Simulator  │ ──► Execution Trace
                        └─────────────┘
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

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for the strategic roadmap.

## Related

- **[A2E Protocol](https://github.com/MauricioPerera/a2e)** — The protocol specification this compiler targets
