# a2e-lang Roadmap

## Current (v0.1.0) ✅

- DSL compiler for 16 A2E operation types
- Dual output: legacy format + official A2E spec format (`--spec`)
- 8 semantic validations + cycle detection
- Configurable complexity limits (`max_operations`, `max_depth`, `max_conditions`)
- Workflow visualization (`a2e-lang graph` → Mermaid)
- Dry-run simulation (`a2e-lang simulate`)
- **156 tests**

## Phase 1: DX & Tooling

- [x] **Watch mode** — `a2e-lang compile --watch` for auto-recompilation
- [x] **Decompiler** — JSONL → a2e-lang DSL (reverse engineering existing workflows)
- [x] **VSCode extension** — Syntax highlighting for `.a2e` files
- [x] **LSP** — Language Server Protocol for autocompletion and inline errors

## Phase 2: LLM Optimization

- [ ] **Prompt templates** — Optimized system prompts per model (GPT-4, Claude, Gemma)
- [ ] **Syntax scoring** — Measure DSL syntax learnability across LLM families
- [ ] **Error recovery** — Auto-fix common LLM syntax mistakes before parsing
- [ ] **Token budget calculator** — Estimate token cost of DSL vs raw JSONL

## Phase 3: Runtime & Observability

- [ ] **Execution engine** — Native Python runtime for A2E workflows
- [ ] **Structured logging** — Per-operation execution logs with timing metrics
- [ ] **Webhook support** — Trigger workflows via HTTP
- [ ] **Retry/circuit breaker** — Operation-level failure handling

## Phase 4: Ecosystem

- [ ] **Plugin system** — Register custom operation types
- [ ] **Workflow registry** — Publish/discover reusable workflows
- [ ] **Multi-agent orchestration** — Chain workflows across agents
- [ ] **Source maps** — DSL → JSONL mapping for runtime debugging

## Strategic Positioning

```
                    Function Calling     a2e-lang
                    ───────────────     ────────
LLM role:           Tool user           Workflow author
Validation:         Per-call            Full graph
Execution:          Immediate           Deferred + validated
Composability:      Ad-hoc              Declarative DAG
Observability:      Per-tool logs       Full pipeline trace
```

a2e-lang makes the LLM a **workflow architect** instead of a tool user. The model describes intention within formal limits, and the runtime guarantees safe execution.
