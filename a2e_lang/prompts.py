"""Prompt templates for LLM-generated a2e-lang workflows.

Optimized system prompts that teach LLMs to produce valid a2e-lang syntax.
Each template includes the DSL grammar summary, examples, and model-specific
tuning hints.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    """An LLM prompt template for a2e-lang generation."""
    name: str
    model_family: str
    system_prompt: str
    user_template: str


# ---------------------------------------------------------------------------
# Grammar summary (shared across all templates)
# ---------------------------------------------------------------------------

_GRAMMAR_SUMMARY = """# a2e-lang DSL Syntax

## Structure
```
workflow "<name>"

<id> = <OpType> {
  <key>: <value>
  from /input/path
  where <field> <op> <value>
  if /path <op> <value> then <id> else <id>
  -> /output/path
}

run: <id1> -> <id2> -> <id3>
```

## Operation Types
ApiCall, FilterData, TransformData, Conditional, Loop, StoreData, Wait, MergeData,
GetCurrentDateTime, ConvertTimezone, DateCalculation, FormatText, ExtractText,
ValidateData, Calculate, EncodeDecode

## Value Types
- Strings: "hello"
- Numbers: 42, 3.14
- Booleans: true, false
- Null: null
- Paths: /workflow/data
- Objects: { key: "value" }
- Arrays: [1, 2, 3]
- Credentials: credential("api-key")

## Comparison Operators
==, !=, >, <, >=, <=, in, contains, startsWith, endsWith, exists, empty

## Rules
1. Operation IDs must be unique
2. Workflow name must be quoted: workflow "name"
3. ApiCall requires: method, url
4. Comments start with #
5. No semicolons, no trailing commas
"""

_EXAMPLE_WORKFLOW = '''```
workflow "user-pipeline"

# Fetch users from API
fetch_users = ApiCall {
  method: "GET"
  url: "https://api.example.com/users"
  headers: { Authorization: credential("api-key") }
  -> /workflow/users
}

# Filter active users
filter_active = FilterData {
  from /workflow/users
  where status == "active"
  -> /workflow/active_users
}

# Store results
save = StoreData {
  from /workflow/active_users
  storage: "localStorage"
  key: "active-users"
}

run: fetch_users -> filter_active -> save
```'''


# ---------------------------------------------------------------------------
# Templates per model family
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, PromptTemplate] = {}


def _register(t: PromptTemplate) -> None:
    TEMPLATES[t.name] = t


# --- GPT-4 / GPT-4o ---
_register(PromptTemplate(
    name="gpt4",
    model_family="OpenAI GPT-4",
    system_prompt=f"""You are a workflow architect that generates a2e-lang DSL code.

{_GRAMMAR_SUMMARY}

## Example
{_EXAMPLE_WORKFLOW}

Generate ONLY valid a2e-lang DSL code. Do NOT include markdown fences unless asked.
Always include a `run:` declaration at the end.
Use descriptive operation IDs (snake_case).
Output paths should follow the pattern: /workflow/<name>""",
    user_template="Write a2e-lang workflow that: {task_description}",
))


# --- Claude ---
_register(PromptTemplate(
    name="claude",
    model_family="Anthropic Claude",
    system_prompt=f"""You generate a2e-lang DSL — a declarative workflow language that compiles to JSON for the A2E protocol.

{_GRAMMAR_SUMMARY}

## Example
{_EXAMPLE_WORKFLOW}

<rules>
- Output ONLY a2e-lang code, no explanations
- Every workflow needs: workflow declaration, at least one operation, run declaration
- Use snake_case for operation IDs
- Always specify output paths with ->
- ApiCall always needs method and url properties
</rules>""",
    user_template="""<task>
{task_description}
</task>

Generate the a2e-lang workflow:""",
))


# --- Gemma / Gemini ---
_register(PromptTemplate(
    name="gemini",
    model_family="Google Gemini/Gemma",
    system_prompt=f"""Generate a2e-lang DSL workflows. a2e-lang is a declarative language for automation workflows.

{_GRAMMAR_SUMMARY}

## Example
{_EXAMPLE_WORKFLOW}

Output rules:
* Generate ONLY valid a2e-lang syntax
* Include run: declaration with execution order
* Use snake_case for all identifiers
* Every ApiCall must have method and url""",
    user_template="Generate a2e-lang workflow for: {task_description}",
))


# --- Llama / Mistral (open-source) ---
_register(PromptTemplate(
    name="opensource",
    model_family="Llama/Mistral/Open-source",
    system_prompt=f"""You write a2e-lang code. a2e-lang is a simple DSL for workflow automation.

{_GRAMMAR_SUMMARY}

## Example
{_EXAMPLE_WORKFLOW}

IMPORTANT:
- Output ONLY the a2e-lang code
- Start with: workflow "name"
- End with: run: id1 -> id2
- No semicolons, no type annotations
- Strings use double quotes only""",
    user_template="Write a2e-lang code: {task_description}",
))


def get_template(name: str) -> PromptTemplate:
    """Get a prompt template by name."""
    if name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")
    return TEMPLATES[name]


def format_prompt(template_name: str, task_description: str) -> dict[str, str]:
    """Format a complete prompt for a given task.

    Returns dict with 'system' and 'user' keys.
    """
    t = get_template(template_name)
    return {
        "system": t.system_prompt,
        "user": t.user_template.format(task_description=task_description),
    }


def list_templates() -> list[dict[str, str]]:
    """List available templates with their model families."""
    return [
        {"name": t.name, "model_family": t.model_family}
        for t in TEMPLATES.values()
    ]
