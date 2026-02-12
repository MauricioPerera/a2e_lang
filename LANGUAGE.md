# a2e-lang Language Reference

This document describes the syntax and features of the `a2e-lang` DSL.

## Top-Level Declarations

### Workflow
Every file must start with a workflow name.
```a2e
workflow "My Workflow"
```

### Operation Definition
Operations are defined with an ID and a type.
```a2e
my_op = Message {
    # Properties go here
}
```

### Execution Order
The `run` statement defines the starting operation and the sequence.
```a2e
run: first_op -> second_op
```

## Operation Body

Within an operation `{}` block, you can define:

- **Properties**: `key: value`
- **Source**: `from /input/path`
- **Output**: `-> /output/path`
- **Filter**: `where field == "value"`
- **Conditional branching**: `if /path == "X" then op1 else op2`

## Data Types

- **Strings**: `"double quoted"`
- **Numbers**: `123`, `45.67`
- **Booleans**: `true`, `false`
- **Null**: `null`
- **Paths**: `/absolute/path/to/data`
- **Credentials**: `credential("secret-id")`
- **Objects**: `{ key: "value", list: [1, 2] }`
- **Arrays**: `[1, 2, "3"]`

## Conditions and Operators

Used in `where` and `if` clauses:
- Comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Text: `startsWith`, `endsWith`, `contains`
- Collection: `in`
- State: `exists`, `empty`

## Example: Conditional Workflow

```a2e
workflow "Conditional Flow"

check = Inspect {
    from /user/message
    if /text == "ping" then reply_pong else reply_hello
}

reply_pong = Message {
    text: "PONG!"
}

reply_hello = Message {
    text: "Hello!"
}

run: check
```
