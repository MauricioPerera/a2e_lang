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
The `run` statement defines the execution sequence:
```a2e
run: first_op -> second_op -> third_op
```

In `--spec` mode this maps to `beginExecution.operationOrder`:
```json
{"type":"beginExecution","executionId":"...","operationOrder":["first_op","second_op","third_op"]}
```

## Operation Body

Within an operation `{}` block, you can define:

| DSL syntax | A2E JSON field | Description |
|---|---|---|
| `key: value` | `"key": value` | Property |
| `from /workflow/path` | `"inputPath"` | Data input source |
| `-> /workflow/path` | `"outputPath"` | Data output destination |
| `where field == "val"` | `"conditions"` | Filter conditions |
| `if /path > 0 then a else b` | `"condition"` + `"ifTrue"`/`"ifFalse"` | Conditional branching |

## Data Types

| Type | DSL Syntax | A2E JSON equivalent |
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

### Source (pipeline.a2e)

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

### Output with `--spec` (official A2E format)

```bash
a2e-lang compile pipeline.a2e --spec
```

```jsonl
{"type":"operationUpdate","operationId":"fetch_users","operation":{"ApiCall":{"outputPath":"/workflow/users","method":"GET","url":"https://api.example.com/users","headers":{"Authorization":{"credentialRef":{"id":"api-token"}}}}}}
{"type":"operationUpdate","operationId":"filter_active","operation":{"FilterData":{"inputPath":"/workflow/users","outputPath":"/workflow/filtered","conditions":[{"field":"status","operator":"==","value":"active"},{"field":"points","operator":">","value":100}]}}}
{"type":"operationUpdate","operationId":"store","operation":{"StoreData":{"inputPath":"/workflow/filtered","storage":"localStorage","key":"active-users"}}}
{"type":"beginExecution","executionId":"user-pipeline","operationOrder":["fetch_users","filter_active","store"]}
```

### Output without `--spec` (legacy bundled format)

```bash
a2e-lang compile pipeline.a2e
```

```jsonl
{"operationUpdate":{"workflowId":"user-pipeline","operations":[{"id":"fetch_users","operation":{"ApiCall":{...}}},{"id":"filter_active","operation":{"FilterData":{...}}},{"id":"store","operation":{"StoreData":{...}}}]}}
{"beginExecution":{"workflowId":"user-pipeline","root":"fetch_users"}}
```

## Operation Reference

### ApiCall
```a2e
fetch = ApiCall {
  method: "GET"                                # Required: HTTP method
  url: "https://api.example.com/users"         # Required: endpoint URL
  headers: { Authorization: credential("key") } # Optional: HTTP headers
  body: { name: "test", value: 42 }            # Optional: request body
  timeout: 30000                               # Optional: timeout in ms
  -> /workflow/response                        # Required: output path
}
```

### FilterData
```a2e
filter = FilterData {
  from /workflow/users                         # Required: input path
  where status == "active", points > 100       # Required: filter conditions
  -> /workflow/filtered                        # Required: output path
}
```

### TransformData
```a2e
transform = TransformData {
  from /workflow/data                          # Required: input path
  transform: "sort"                            # Required: sort|select|map|group
  config: { field: "name", order: "asc" }      # Optional: transform config
  -> /workflow/sorted                          # Required: output path
}
```

### Conditional
```a2e
check = Conditional {
  if /workflow/count > 0                       # Required: condition
  then process_op                              # Required: true branch
  else fallback_op                             # Optional: false branch
}
```

### Loop
```a2e
loop = Loop {
  from /workflow/items                         # Required: input array
  operations: [process_item]                   # Required: ops per iteration
  -> /workflow/results                         # Optional: output path
}
```

### StoreData
```a2e
store = StoreData {
  from /workflow/data                          # Required: input path
  storage: "localStorage"                      # Required: storage type
  key: "my-data"                               # Required: storage key
}
```

### Wait
```a2e
pause = Wait {
  duration: 5000                               # Required: milliseconds
}
```

### MergeData
```a2e
merged = MergeData {
  sources: [/workflow/a, /workflow/b]           # Required: input paths
  strategy: "deepMerge"                        # Required: concat|union|intersect|deepMerge
  -> /workflow/combined                        # Required: output path
}
```
