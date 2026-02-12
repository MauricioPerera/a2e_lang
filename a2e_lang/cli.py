"""CLI for a2e-lang: compile, validate, and inspect .a2e files."""

from __future__ import annotations

import argparse
import json
import sys

from .compiler import Compiler
from .errors import A2ELangError
from .parser import parse
from .validator import Validator


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

    # validate
    validate_p = sub.add_parser("validate", help="Validate .a2e file without compiling")
    validate_p.add_argument("file", help="Input .a2e file")

    # ast
    ast_p = sub.add_parser("ast", help="Show parsed AST (debug)")
    ast_p.add_argument("file", help="Input .a2e file")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        source = _read_file(args.file)
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    try:
        if args.command == "compile":
            return _cmd_compile(source, pretty=args.pretty)
        elif args.command == "validate":
            return _cmd_validate(source)
        elif args.command == "ast":
            return _cmd_ast(source)
    except A2ELangError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _cmd_compile(source: str, pretty: bool = False) -> int:
    workflow = parse(source)

    validator = Validator()
    errors = validator.validate(workflow)
    if errors:
        for e in errors:
            print(f"Validation error: {e}", file=sys.stderr)
        return 1

    compiler = Compiler()
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


if __name__ == "__main__":
    sys.exit(main())
