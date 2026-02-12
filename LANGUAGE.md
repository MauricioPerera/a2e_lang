# a2e-lang Language Reference

This document describes the syntax of the `a2e-lang` DSL, which compiles to [A2E protocol](https://github.com/MauricioPerera/a2e) JSONL.

## Top-Level Declarations

### Workflow
Every file must start with a workflow name:
```a2e
workflow "My Workflow"
```

### Operation Definition
Operations are defined with an ID and a type (from the [A2E operations catalog](https://github.com/MauricioPerera/a2e/blob/main/SPECIFICATION.md)):
```a2e
my_op = ApiCall {
    # Properties go here
}
```

### Execution Order
The `run` statement defines the starting operation and the execution sequence:
```a2e
run: first_op -> second_op -> third_op
```
This maps to the A2E `beginExecution.operationOrder` array.

## Operation Body

Within an operation `{}` block, you can define:

- **Properties**: `key: value`
- **Input path**: `from /workflow/path` → maps to `inputPath`
- **Output path**: `-> /workflow/path` → maps to `outputPath`
- **Filter conditions**: `where field == "value"` → maps to `conditions[]`
- **Conditional branching**: `if /path == "X" then op1 else op2` → maps to `condition` + `ifTrue`/`ifFalse`

## Data Types

| Type | Syntax | A2E JSON equivalent |
|---|---|---|
| String | `"double quoted"` | `"string"` |
| Number | `123`, `45.67` | `123`, `45.67` |
| Boolean | `true`, `false` | `true`, `false` |
| Null | `null` | `null` |
| Path | `/workflow/data` | `"/workflow/data"` |
| Credential | `credential("id")` | `{"credentialRef": {"id": "id"}}` |
| Object | `{ key: "value" }` | `{"key": "value"}` |
| Array | `[1, 2, "3"]` | `[1, 2, "3"]` |

## Conditions and Operators

Used in `where` and `if` clauses. These map directly to the A2E condition operators:

- **Comparison**: `==`, `!=`, `>`, `<`, `>=`, `<=`
- **Text**: `startsWith`, `endsWith`, `contains`
- **Collection**: `in`
- **Unary (no value)**: `exists`, `empty`

## Comments

Lines starting with `#` are comments:
```a2e
# This is a comment
workflow "example"
```

## Full Example

This a2e-lang source:
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

Compiles to this A2E JSONL:
```jsonl
{"operationUpdate":{"workflowId":"user-pipeline","operations":[{"id":"fetch_users","operation":{"ApiCall":{"outputPath":"/workflow/users","method":"GET","url":"https://api.example.com/users","headers":{"Authorization":{"credentialRef":{"id":"api-token"}}}}}},{"id":"filter_active","operation":{"FilterData":{"inputPath":"/workflow/users","outputPath":"/workflow/filtered","conditions":[{"field":"status","operator":"==","value":"active"},{"field":"points","operator":">","value":100}]}}},{"id":"store","operation":{"StoreData":{"inputPath":"/workflow/filtered","storage":"localStorage","key":"active-users"}}}]}}
{"beginExecution":{"workflowId":"user-pipeline","root":"fetch_users"}}
```
