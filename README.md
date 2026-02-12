# a2e-lang

DSL compiler for the **A2E (Agent-to-Everything) protocol**. It compiles a human-readable domain-specific language into A2E JSONL format.

## Features

- **Compact Syntax**: Express complex agent workflows with minimal code.
- **Strong Validation**: Integrated validator ensures A2E protocol compliance before compilation.
- **Flexible AST**: Easily extend the language with new operation types.
- **CLI Tool**: Simple command-line interface for compilation, validation, and debugging.

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

Create a file named `hello.a2e`:

```a2e
workflow "Greeting Workflow"

hello = Message {
    text: "Hello, World!"
}

run: hello
```

Compile it to JSONL:

```bash
a2e-lang compile hello.a2e
```

## Project Structure

- `a2e_lang/`: Core source code.
  - `grammar.lark`: EBNF grammar for the DSL.
  - `parser.py`: Lark-based parser that generates the AST.
  - `ast_nodes.py`: Data models for the AST.
  - `validator.py`: Semantic validator for the AST.
  - `compiler.py`: Logic to transform AST into A2E JSONL.
- `examples/`: Sample `.a2e` files showing various features.
- `tests/`: Comprehensive test suite using `pytest`.

## Architecture

The compilation process follows three main stages:

1.  **Parsing**: The `parser.py` uses the `lark` library and `grammar.lark` to transform the source text into an Internal AST (defined in `ast_nodes.py`).
2.  **Validation**: The `Validator` checks for semantic errors, such as missing connections or invalid property values.
3.  **Compilation**: The `Compiler` traverses the validated AST and generates the standard A2E protocol JSONL output.

## CLI Usage

```text
usage: a2e-lang [-h] {compile,validate,ast} ...

DSL compiler for the A2E protocol

positional arguments:
  {compile,validate,ast}
    compile             Compile .a2e to JSONL
    validate            Validate .a2e file without compiling
    ast                 Show parsed AST (debug)

optional arguments:
  -h, --help            show this help message and exit
```

For detailed language reference, see [LANGUAGE.md](./LANGUAGE.md).
