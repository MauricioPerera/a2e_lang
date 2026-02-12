"""Graph visualization: AST -> Mermaid flowchart."""

from __future__ import annotations

from .ast_nodes import (
    ArrayValue,
    Operation,
    Path,
    Workflow,
)


# Operation type -> Mermaid style class
_OP_STYLES = {
    "ApiCall":           "fill:#1e40af,stroke:#3b82f6,color:#e2e8f0",
    "FilterData":        "fill:#7c3aed,stroke:#8b5cf6,color:#e2e8f0",
    "TransformData":     "fill:#7c3aed,stroke:#8b5cf6,color:#e2e8f0",
    "Conditional":       "fill:#b45309,stroke:#f59e0b,color:#e2e8f0",
    "Loop":              "fill:#b45309,stroke:#f59e0b,color:#e2e8f0",
    "StoreData":         "fill:#065f46,stroke:#10b981,color:#e2e8f0",
    "Wait":              "fill:#64748b,stroke:#94a3b8,color:#e2e8f0",
    "MergeData":         "fill:#065f46,stroke:#10b981,color:#e2e8f0",
}

_DEFAULT_STYLE = "fill:#1e293b,stroke:#64748b,color:#e2e8f0"


def generate_mermaid(workflow: Workflow) -> str:
    """Generate a Mermaid flowchart from a validated Workflow AST."""
    lines: list[str] = ["graph TD"]

    op_map = {op.id: op for op in workflow.operations}

    # Build write registry: output_path -> op_id
    write_registry: dict[str, str] = {}
    for op in workflow.operations:
        if op.output_path:
            write_registry[op.output_path] = op.id

    # Node declarations
    for op in workflow.operations:
        shape = _node_shape(op)
        lines.append(f"    {op.id}{shape}")

    lines.append("")

    # Data flow edges (from input paths)
    for op in workflow.operations:
        read_paths = _get_read_paths(op)
        for rp in read_paths:
            if rp in write_registry and write_registry[rp] != op.id:
                source_id = write_registry[rp]
                lines.append(f"    {source_id} -->|{rp}| {op.id}")

    # Conditional edges
    for op in workflow.operations:
        if op.if_clause:
            for target in op.if_clause.if_true:
                lines.append(f"    {op.id} -->|then| {target}")
            if op.if_clause.if_false:
                for target in op.if_clause.if_false:
                    lines.append(f"    {op.id} -->|else| {target}")

    # Loop edges
    for op in workflow.operations:
        if op.op_type == "Loop":
            ops_prop = _find_property(op, "operations")
            if ops_prop and isinstance(ops_prop.value, ArrayValue):
                for item in ops_prop.value.items:
                    if isinstance(item, str):
                        lines.append(f"    {op.id} -->|loop| {item}")

    # Execution order edges (if explicit)
    if workflow.execution_order and len(workflow.execution_order) > 1:
        lines.append("")
        lines.append("    %% Execution order")
        order = list(workflow.execution_order)
        for i in range(len(order) - 1):
            lines.append(f"    {order[i]} -.->|next| {order[i+1]}")

    lines.append("")

    # Styles
    for op in workflow.operations:
        style = _OP_STYLES.get(op.op_type, _DEFAULT_STYLE)
        lines.append(f"    style {op.id} {style}")

    return "\n".join(lines)


def _node_shape(op: Operation) -> str:
    """Return Mermaid node shape based on operation type."""
    label = f"{op.id}\\n{op.op_type}"
    if op.op_type == "Conditional":
        return "{" + f"{label}" + "}"  # diamond
    if op.op_type == "Loop":
        return f"(({label}))"  # circle
    if op.op_type in ("ApiCall",):
        return f"[/{label}/]"  # parallelogram (I/O)
    return f"[{label}]"  # rectangle


def _get_read_paths(op: Operation) -> list[str]:
    """Extract paths that an operation reads from."""
    paths: list[str] = []
    if op.input_path:
        paths.append(op.input_path)
    if op.if_clause:
        paths.append(op.if_clause.path)
    sources_prop = _find_property(op, "sources")
    if sources_prop and isinstance(sources_prop.value, ArrayValue):
        for item in sources_prop.value.items:
            if isinstance(item, Path):
                paths.append(item.raw)
    return paths


def _find_property(op, key):
    for p in op.properties:
        if p.key == key:
            return p
    return None
