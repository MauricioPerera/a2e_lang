"""Semantic validator for a2e-lang AST."""

from __future__ import annotations

from .ast_nodes import (
    ArrayValue,
    Credential,
    IfClause,
    ObjectValue,
    Operation,
    Path,
    Property,
    Workflow,
)
from .errors import ValidationError

# ---------------------------------------------------------------------------
# Valid operation types and their required properties
# ---------------------------------------------------------------------------

VALID_OP_TYPES = {
    "ApiCall", "FilterData", "TransformData", "Conditional",
    "Loop", "StoreData", "Wait", "MergeData",
    "GetCurrentDateTime", "ConvertTimezone", "DateCalculation",
    "FormatText", "ExtractText", "ValidateData", "Calculate",
    "EncodeDecode",
}

# Required fields per operation type (beyond from/where/if/-> which are structural)
REQUIRED_PROPERTIES: dict[str, set[str]] = {
    "ApiCall": {"method", "url"},
    "FilterData": set(),        # requires where clause (conditions), validated separately
    "TransformData": {"transform"},
    "Conditional": set(),       # requires if clause, validated separately
    "Loop": {"operations"},
    "StoreData": {"storage", "key"},
    "Wait": {"duration"},
    "MergeData": {"sources", "strategy"},
    "GetCurrentDateTime": set(),
    "ConvertTimezone": {"toTimezone"},
    "DateCalculation": {"operation"},
    "FormatText": {"format"},
    "ExtractText": {"pattern"},
    "ValidateData": {"validationType"},
    "Calculate": {"operation"},
    "EncodeDecode": {"operation", "encoding"},
}

# Operations that require an inputPath (from clause)
REQUIRES_INPUT_PATH = {
    "FilterData", "TransformData", "Loop",
    "StoreData", "ConvertTimezone", "DateCalculation",
    "FormatText", "ExtractText", "ValidateData", "Calculate", "EncodeDecode",
}

# Operations that require an outputPath (-> clause)
REQUIRES_OUTPUT_PATH = {
    "ApiCall", "FilterData", "TransformData", "MergeData",
    "GetCurrentDateTime", "ConvertTimezone", "DateCalculation",
    "FormatText", "ExtractText", "ValidateData", "Calculate", "EncodeDecode",
}

# Binary comparison operators (require a value)
BINARY_OPS = {"==", "!=", ">", "<", ">=", "<=", "in", "contains", "startsWith", "endsWith"}
# Unary operators (no value needed)
UNARY_OPS = {"exists", "empty"}


class Validator:
    """Validates a2e-lang AST for semantic correctness."""

    def validate(self, workflow: Workflow) -> list[ValidationError]:
        """Run all validations and return a list of errors (empty = valid)."""
        errors: list[ValidationError] = []
        errors += self._validate_unique_ids(workflow)
        errors += self._validate_op_types(workflow)
        errors += self._validate_required_properties(workflow)
        errors += self._validate_required_clauses(workflow)
        errors += self._validate_conditional_targets(workflow)
        errors += self._validate_loop_operations(workflow)
        errors += self._validate_execution_order(workflow)
        errors += self._validate_no_cycles(workflow)
        return errors

    def _validate_unique_ids(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        seen: dict[str, int] = {}
        for op in workflow.operations:
            if op.id in seen:
                errors.append(ValidationError(
                    f"Duplicate operation ID '{op.id}' (first defined at line {seen[op.id]})",
                    line=op.line,
                    column=op.column,
                ))
            seen[op.id] = op.line
        return errors

    def _validate_op_types(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        for op in workflow.operations:
            if op.op_type not in VALID_OP_TYPES:
                errors.append(ValidationError(
                    f"Unknown operation type '{op.op_type}' for '{op.id}'. "
                    f"Valid types: {', '.join(sorted(VALID_OP_TYPES))}",
                    line=op.line,
                    column=op.column,
                ))
        return errors

    def _validate_required_properties(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        for op in workflow.operations:
            required = REQUIRED_PROPERTIES.get(op.op_type, set())
            prop_keys = {p.key for p in op.properties}
            missing = required - prop_keys
            if missing:
                errors.append(ValidationError(
                    f"Operation '{op.id}' ({op.op_type}) missing required properties: "
                    f"{', '.join(sorted(missing))}",
                    line=op.line,
                    column=op.column,
                ))
        return errors

    def _validate_required_clauses(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        for op in workflow.operations:
            if op.op_type in REQUIRES_INPUT_PATH and op.input_path is None:
                errors.append(ValidationError(
                    f"Operation '{op.id}' ({op.op_type}) requires a 'from' clause",
                    line=op.line,
                    column=op.column,
                ))
            if op.op_type in REQUIRES_OUTPUT_PATH and op.output_path is None:
                errors.append(ValidationError(
                    f"Operation '{op.id}' ({op.op_type}) requires an output arrow (->)",
                    line=op.line,
                    column=op.column,
                ))
            if op.op_type == "FilterData" and not op.conditions:
                errors.append(ValidationError(
                    f"Operation '{op.id}' (FilterData) requires a 'where' clause",
                    line=op.line,
                    column=op.column,
                ))
            if op.op_type == "Conditional" and not op.if_clause:
                errors.append(ValidationError(
                    f"Operation '{op.id}' (Conditional) requires an 'if' clause",
                    line=op.line,
                    column=op.column,
                ))
        return errors

    def _validate_conditional_targets(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        op_ids = {op.id for op in workflow.operations}
        for op in workflow.operations:
            if op.if_clause:
                for target_id in op.if_clause.if_true:
                    if target_id not in op_ids:
                        errors.append(ValidationError(
                            f"Conditional '{op.id}': 'then' target '{target_id}' not found",
                            line=op.line,
                        ))
                if op.if_clause.if_false:
                    for target_id in op.if_clause.if_false:
                        if target_id not in op_ids:
                            errors.append(ValidationError(
                                f"Conditional '{op.id}': 'else' target '{target_id}' not found",
                                line=op.line,
                            ))
        return errors

    def _validate_loop_operations(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        op_ids = {op.id for op in workflow.operations}
        for op in workflow.operations:
            if op.op_type == "Loop":
                ops_prop = _find_property(op, "operations")
                if ops_prop and isinstance(ops_prop.value, ArrayValue):
                    for item in ops_prop.value.items:
                        ref_id = item if isinstance(item, str) else None
                        if ref_id and ref_id not in op_ids:
                            errors.append(ValidationError(
                                f"Loop '{op.id}': operation '{ref_id}' not found",
                                line=op.line,
                            ))
        return errors

    def _validate_execution_order(self, workflow: Workflow) -> list[ValidationError]:
        errors = []
        if workflow.execution_order:
            op_ids = {op.id for op in workflow.operations}
            for op_id in workflow.execution_order:
                if op_id not in op_ids:
                    errors.append(ValidationError(
                        f"Execution order references unknown operation '{op_id}'",
                    ))
        return errors

    def _validate_no_cycles(self, workflow: Workflow) -> list[ValidationError]:
        """Detect cycles in the dependency graph built from data paths."""
        errors = []

        # Build write registry: output_path -> op_id
        write_registry: dict[str, str] = {}
        for op in workflow.operations:
            if op.output_path:
                write_registry[op.output_path] = op.id

        # Build dependency graph: op_id -> [depends_on_op_ids]
        graph: dict[str, list[str]] = {op.id: [] for op in workflow.operations}
        for op in workflow.operations:
            read_paths = _extract_read_paths(op)
            for rp in read_paths:
                if rp in write_registry and write_registry[rp] != op.id:
                    graph[op.id].append(write_registry[rp])

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {op_id: WHITE for op_id in graph}

        def dfs(node: str) -> str | None:
            color[node] = GRAY
            for dep in graph.get(node, []):
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    return f"Cycle detected involving '{node}' -> '{dep}'"
                if color[dep] == WHITE:
                    result = dfs(dep)
                    if result:
                        return result
            color[node] = BLACK
            return None

        for op_id in graph:
            if color[op_id] == WHITE:
                cycle = dfs(op_id)
                if cycle:
                    errors.append(ValidationError(cycle))
                    break

        return errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_property(op: Operation, key: str) -> Property | None:
    for p in op.properties:
        if p.key == key:
            return p
    return None


def _extract_read_paths(op: Operation) -> list[str]:
    """Extract all paths that an operation reads from."""
    paths: list[str] = []
    if op.input_path:
        paths.append(op.input_path)
    if op.if_clause:
        paths.append(op.if_clause.path)
    # Check sources property (MergeData)
    sources_prop = _find_property(op, "sources")
    if sources_prop and isinstance(sources_prop.value, ArrayValue):
        for item in sources_prop.value.items:
            if isinstance(item, Path):
                paths.append(item.raw)
    return paths
