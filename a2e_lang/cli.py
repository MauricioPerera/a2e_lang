"""CLI for a2e-lang: compile, validate, and inspect .a2e files."""

from __future__ import annotations

import argparse
import json
import sys

from .compiler import Compiler
from .compiler_spec import SpecCompiler
from .decompiler import Decompiler
from .engine import ExecutionEngine
from .errors import A2ELangError
from .graph import generate_mermaid
from .parser import parse
from .prompts import format_prompt, list_templates
from .recovery import parse_with_recovery
from .registry import WorkflowRegistry
from .resilience import NO_RETRY, API_RETRY
from .scoring import score_syntax
from .simulator import Simulator
from .sourcemap import generate_source_map
from .tokens import calculate_budget
from .validator import Validator
from .watcher import watch_and_compile
from .webhook import WebhookServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="a2e-lang",
        description="DSL compiler for the A2E protocol",
    )
    sub = parser.add_subparsers(dest="command")

    # compile
    compile_p = sub.add_parser("compile", help="Compile .a2e to JSONL")
    compile_p.add_argument("file", help="Input .a2e file")
    compile_p.add_argument("--pretty", action="store_true", help="Pretty-print output")
    compile_p.add_argument("--spec", action="store_true", help="Use official A2E spec format (one line per operation)")
    compile_p.add_argument("--watch", action="store_true", help="Watch file and recompile on changes")

    # validate
    validate_p = sub.add_parser("validate", help="Validate .a2e file without compiling")
    validate_p.add_argument("file", help="Input .a2e file")

    # ast
    ast_p = sub.add_parser("ast", help="Show parsed AST (debug)")
    ast_p.add_argument("file", help="Input .a2e file")

    # graph
    graph_p = sub.add_parser("graph", help="Generate Mermaid flowchart")
    graph_p.add_argument("file", help="Input .a2e file")

    # simulate
    sim_p = sub.add_parser("simulate", help="Dry-run workflow simulation")
    sim_p.add_argument("file", help="Input .a2e file")
    sim_p.add_argument("--input", dest="input_file", help="JSON file with mock data")
    sim_p.add_argument("--max-operations", type=int, default=None, help="Max operations limit")
    sim_p.add_argument("--max-depth", type=int, default=None, help="Max nesting depth limit")
    sim_p.add_argument("--max-conditions", type=int, default=None, help="Max conditions per operation")

    # decompile
    decompile_p = sub.add_parser("decompile", help="Convert JSONL back to .a2e DSL")
    decompile_p.add_argument("file", help="Input JSONL file")

    # recover
    recover_p = sub.add_parser("recover", help="Auto-fix LLM syntax mistakes")
    recover_p.add_argument("file", help="Input .a2e file")

    # tokens
    tokens_p = sub.add_parser("tokens", help="Token budget analysis (DSL vs JSONL)")
    tokens_p.add_argument("file", help="Input .a2e file")

    # score
    score_p = sub.add_parser("score", help="Syntax learnability score")
    score_p.add_argument("file", help="Input .a2e file")

    # prompt
    prompt_p = sub.add_parser("prompt", help="Generate LLM prompt template")
    prompt_p.add_argument("template", nargs="?", help="Template name (gpt4, claude, gemini, opensource)")
    prompt_p.add_argument("--task", dest="task_desc", help="Task description for the prompt")
    prompt_p.add_argument("--list", action="store_true", dest="list_all", help="List available templates")

    # run (execute)
    run_p = sub.add_parser("run", help="Execute workflow with the native engine")
    run_p.add_argument("file", help="Input .a2e file")
    run_p.add_argument("--input", dest="input_file", help="JSON file with input data")
    run_p.add_argument("--no-retry", action="store_true", help="Disable retry on failures")

    # webhook
    webhook_p = sub.add_parser("webhook", help="Start webhook server")
    webhook_p.add_argument("file", help="Input .a2e file")
    webhook_p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    webhook_p.add_argument("--host", default="0.0.0.0", help="Server host")

    # sourcemap
    sm_p = sub.add_parser("sourcemap", help="Generate source map (DSL -> JSONL)")
    sm_p.add_argument("file", help="Input .a2e file")
    sm_p.add_argument("--out", "-o", help="Output JSON file (default: stdout)")

    # registry
    reg_p = sub.add_parser("registry", help="Interact with workflow registry")
    reg_sub = reg_p.add_subparsers(dest="reg_command", required=True)

    # registry list
    reg_sub.add_parser("list", help="List all installed workflows")

    # registry search
    reg_search = reg_sub.add_parser("search", help="Search workflows")
    reg_search.add_argument("query", help="Search query (name, tag, or description)")

    # registry show
    reg_show = reg_sub.add_parser("show", help="Show workflow details")
    reg_show.add_argument("name", help="Workflow name")

    # registry publish
    reg_pub = reg_sub.add_parser("publish", help="Publish workflow to local registry")
    reg_pub.add_argument("file", help="Workflow file to publish")
    reg_pub.add_argument("--name", help="Override workflow name")
    reg_pub.add_argument("--author", help="Author name")
    reg_pub.add_argument("--tag", action="append", dest="tags", help="Tags (can use multiple times)")
    reg_pub.add_argument("--desc", dest="description", help="Description")

    # registry remove
    reg_rm = reg_sub.add_parser("remove", help="Remove workflow from registry")
    reg_rm.add_argument("name", help="Workflow name")
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # Commands that don't need a file
    if args.command == "prompt":
        return _cmd_prompt(
            template=args.template,
            task_desc=args.task_desc,
            list_all=args.list_all,
        )
    elif args.command == "registry":
        return _cmd_registry(args)

    try:
        if args.command == "compile":
            if args.watch:
                watch_and_compile(args.file, spec=args.spec, pretty=args.pretty)
                return 0
            source = _read_file(args.file)
            return _cmd_compile(source, pretty=args.pretty, spec=args.spec)
        elif args.command == "simulate":
            source = _read_file(args.file)
            return _cmd_simulate(
                source,
                input_file=args.input_file,
                max_operations=args.max_operations,
                max_depth=args.max_depth,
                max_conditions=args.max_conditions,
            )
        else:
            source = _read_file(args.file)
            if args.command == "validate":
                return _cmd_validate(source)
            elif args.command == "ast":
                return _cmd_ast(source)
            elif args.command == "graph":
                return _cmd_graph(source)
            elif args.command == "decompile":
                return _cmd_decompile(source)
            elif args.command == "recover":
                return _cmd_recover(source)
            elif args.command == "tokens":
                return _cmd_tokens(source)
            elif args.command == "score":
                return _cmd_score(source)
            elif args.command == "sourcemap":
                return _cmd_sourcemap(source, out_file=args.out)
            elif args.command == "run":
                return _cmd_run(source, input_file=getattr(args, 'input_file', None), no_retry=getattr(args, 'no_retry', False))
            elif args.command == "webhook":
                return _cmd_webhook(source, host=args.host, port=args.port)
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1
    except A2ELangError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _cmd_compile(source: str, pretty: bool = False, spec: bool = False) -> int:
    workflow = parse(source)

    validator = Validator()
    errors = validator.validate(workflow)
    if errors:
        for e in errors:
            print(f"Validation error: {e}", file=sys.stderr)
        return 1

    compiler = SpecCompiler() if spec else Compiler()
    if pretty:
        output = compiler.compile_pretty(workflow)
    else:
        output = compiler.compile(workflow)
    print(output)
    return 0


def _cmd_validate(source: str) -> int:
    workflow = parse(source)

    validator = Validator()
    errors = validator.validate(workflow)
    if errors:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"Valid: {len(workflow.operations)} operations, workflow '{workflow.name}'")
    return 0


def _cmd_ast(source: str) -> int:
    workflow = parse(source)
    _print_ast(workflow)
    return 0


def _print_ast(workflow) -> None:
    print(f"Workflow: {workflow.name!r}")
    print(f"Execution order: {workflow.execution_order}")
    for op in workflow.operations:
        print(f"\n  {op.id} = {op.op_type}")
        if op.input_path:
            print(f"    from {op.input_path}")
        for p in op.properties:
            print(f"    {p.key}: {_fmt_value(p.value)}")
        if op.conditions:
            conds = ", ".join(f"{c.field} {c.operator} {_fmt_value(c.value)}" for c in op.conditions)
            print(f"    where {conds}")
        if op.if_clause:
            ic = op.if_clause
            v = f" {_fmt_value(ic.value)}" if ic.value is not None else ""
            print(f"    if {ic.path} {ic.operator}{v} then {ic.if_true}")
            if ic.if_false:
                print(f"    else {ic.if_false}")
        if op.output_path:
            print(f"    -> {op.output_path}")


def _fmt_value(val) -> str:
    if isinstance(val, str):
        return repr(val)
    return str(val)


def _cmd_graph(source: str) -> int:
    workflow = parse(source)
    print(generate_mermaid(workflow))
    return 0


def _cmd_simulate(
    source: str,
    input_file: str | None = None,
    max_operations: int | None = None,
    max_depth: int | None = None,
    max_conditions: int | None = None,
) -> int:
    workflow = parse(source)

    # Validate with optional complexity limits
    validator = Validator(
        max_operations=max_operations,
        max_depth=max_depth,
        max_conditions=max_conditions,
    )
    errors = validator.validate(workflow)
    if errors:
        for e in errors:
            print(f"Validation error: {e}", file=sys.stderr)
        return 1

    # Load mock data
    input_data = None
    if input_file:
        try:
            with open(input_file, encoding="utf-8") as f:
                input_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            return 1

    simulator = Simulator()
    result = simulator.simulate(workflow, input_data=input_data)
    print(result.summary())
    return 0


def _cmd_decompile(source: str) -> int:
    decompiler = Decompiler()
    try:
        dsl = decompiler.decompile(source)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Decompile error: {e}", file=sys.stderr)
        return 1
    print(dsl)
    return 0


def _cmd_recover(source: str) -> int:
    workflow, result = parse_with_recovery(source)
    if result.was_modified:
        print(result.summary(), file=sys.stderr)
        print(file=sys.stderr)
    print(result.source)
    return 0


def _cmd_tokens(source: str) -> int:
    budget = calculate_budget(source)
    print(budget.summary())
    return 0


def _cmd_score(source: str) -> int:
    score = score_syntax(source)
    print(score.summary())
    return 0


def _cmd_prompt(
    template: str | None = None,
    task_desc: str | None = None,
    list_all: bool = False,
) -> int:
    if list_all or not template:
        templates = list_templates()
        print("Available prompt templates:")
        for t in templates:
            print(f"  {t['name']:12s}  {t['model_family']}")
        return 0

    if not task_desc:
        print("Error: --task is required with a template name", file=sys.stderr)
        return 1

    result = format_prompt(template, task_desc)
    print("=== SYSTEM PROMPT ===")
    print(result["system"])
    print()
    print("=== USER PROMPT ===")
    print(result["user"])
    return 0


def _cmd_run(source: str, input_file: str | None = None, no_retry: bool = False) -> int:
    workflow = parse(source)
    errors = Validator().validate(workflow)
    if errors:
        for e in errors:
            print(f"Validation error: {e}", file=sys.stderr)
        return 1

    input_data = None
    if input_file:
        try:
            with open(input_file, encoding="utf-8") as f:
                input_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            return 1

    policy = NO_RETRY if no_retry else API_RETRY
    engine = ExecutionEngine(retry_policy=policy, input_data=input_data)
    result = engine.execute(workflow)
    print(result.summary())
    return 0 if result.success else 1


def _cmd_webhook(source: str, host: str = "0.0.0.0", port: int = 8080) -> int:
    # Validate first
    workflow = parse(source)
    errors = Validator().validate(workflow)
    if errors:
        for e in errors:
            print(f"Validation error: {e}", file=sys.stderr)
        return 1

    server = WebhookServer(source, host=host, port=port)
    server.start()
    return 0


def _cmd_sourcemap(source: str, out_file: str | None = None) -> int:
    try:
        sm = generate_source_map(source)
    except Exception as e:
        print(f"Error generating source map: {e}", file=sys.stderr)
        return 1

    output = sm.to_json(pretty=True)
    if out_file:
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(output)
        except OSError as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
            return 1
    else:
        print(output)
    return 0


def _cmd_registry(args) -> int:
    reg = WorkflowRegistry()
    cmd = args.reg_command

    if cmd == "list":
        for entry in reg.list_all():
             print(entry.summary_line())
        return 0

    elif cmd == "search":
        results = reg.search(args.query)
        if not results:
            print("No workflows found.")
            return 0
        for entry in results:
            print(entry.summary_line())
        return 0

    elif cmd == "show":
        entry = reg.get(args.name)
        if not entry:
            print(f"Workflow '{args.name}' not found.", file=sys.stderr)
            return 1
        print(f"Name:        {entry.name}")
        print(f"Version:     {entry.version}")
        print(f"Author:      {entry.author}")
        print(f"Published:   {entry.published_at}")
        print(f"Tags:        {', '.join(entry.tags)}")
        print(f"Description: {entry.description}")
        print("\nSource:")
        print("-------")
        print(entry.source)
        return 0

    elif cmd == "publish":
        try:
            source = _read_file(args.file)
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            return 1

        # Validate before publishing
        workflow = parse(source)
        errors = Validator().validate(workflow)
        if errors:
            print("Validation failed:", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            return 1

        name = args.name or workflow.name
        entry = reg.publish(
            name=name,
            source=source,
            author=args.author or "",
            description=args.description or "",
            tags=args.tags,
        )
        print(f"Published: {entry.summary_line()}")
        return 0

    elif cmd == "remove":
        if reg.remove(args.name):
            print(f"Removed '{args.name}'")
        else:
            print(f"Workflow '{args.name}' not found", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
