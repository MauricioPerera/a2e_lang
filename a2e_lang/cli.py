"""CLI for a2e-lang: compile, validate, and inspect .a2e files."""

from __future__ import annotations

import argparse
import json
import sys

from .compiler import Compiler
from .compiler_spec import SpecCompiler
from .decompiler import Decompiler
from .errors import A2ELangError
from .graph import generate_mermaid
from .parser import parse
from .simulator import Simulator
from .validator import Validator
from .watcher import watch_and_compile


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

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

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


if __name__ == "__main__":
    sys.exit(main())
