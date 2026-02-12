"""Workflow simulator: dry-run execution tracing without external calls."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .ast_nodes import (
    ArrayValue,
    Credential,
    ObjectValue,
    Operation,
    Path,
    Workflow,
)
from .errors import CompileError


@dataclass
class SimulationResult:
    """Result of a workflow simulation."""
    operations_executed: list[str] = field(default_factory=list)
    paths_written: dict[str, object] = field(default_factory=dict)
    branches_taken: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = []
        lines.append(f"Operations executed: {len(self.operations_executed)}")
        for op_id in self.operations_executed:
            lines.append(f"  ✓ {op_id}")
        if self.skipped:
            lines.append(f"Operations skipped: {len(self.skipped)}")
            for op_id in self.skipped:
                lines.append(f"  ✗ {op_id}")
        if self.branches_taken:
            lines.append("Branches:")
            for b in self.branches_taken:
                lines.append(f"  → {b}")
        lines.append(f"Paths written: {len(self.paths_written)}")
        for path in self.paths_written:
            lines.append(f"  {path}")
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


class Simulator:
    """Simulates workflow execution without making real API calls.

    Traces the execution path, evaluates conditions against provided
    input data, and tracks which operations would run and which paths
    would be written.
    """

    def simulate(
        self,
        workflow: Workflow,
        input_data: dict | None = None,
    ) -> SimulationResult:
        """Run a dry simulation of the workflow.

        Args:
            workflow: Validated Workflow AST.
            input_data: Optional dict of path -> value mappings to seed
                       the simulation data model (e.g. mock API responses).
        """
        result = SimulationResult()

        # Data model: paths -> values
        data: dict[str, object] = {}
        if input_data:
            data.update(input_data)

        # Build operation map
        op_map = {op.id: op for op in workflow.operations}

        # Determine execution order
        if workflow.execution_order:
            exec_order = list(workflow.execution_order)
        else:
            exec_order = [op.id for op in workflow.operations]

        # Execute each operation
        for op_id in exec_order:
            if op_id not in op_map:
                result.warnings.append(f"Unknown operation '{op_id}' in execution order")
                continue

            op = op_map[op_id]
            self._simulate_operation(op, data, result, op_map)

        # Track skipped operations (defined but not in execution order)
        executed_set = set(result.operations_executed)
        for op in workflow.operations:
            if op.id not in executed_set:
                result.skipped.append(op.id)

        return result

    def _simulate_operation(
        self,
        op: Operation,
        data: dict[str, object],
        result: SimulationResult,
        op_map: dict[str, Operation],
    ) -> None:
        """Simulate a single operation."""

        # Handle Conditional
        if op.op_type == "Conditional" and op.if_clause:
            condition_met = self._evaluate_condition(
                op.if_clause.path,
                op.if_clause.operator,
                self._resolve_if_value(op.if_clause.value),
                data,
            )

            if condition_met:
                result.branches_taken.append(f"{op.id}: then (condition met)")
                result.operations_executed.append(op.id)
                for target_id in op.if_clause.if_true:
                    if target_id in op_map:
                        self._simulate_operation(op_map[target_id], data, result, op_map)
            else:
                result.branches_taken.append(f"{op.id}: else (condition not met)")
                result.operations_executed.append(op.id)
                if op.if_clause.if_false:
                    for target_id in op.if_clause.if_false:
                        if target_id in op_map:
                            self._simulate_operation(op_map[target_id], data, result, op_map)
            return

        # Handle Wait
        if op.op_type == "Wait":
            duration = self._get_prop_value(op, "duration")
            result.operations_executed.append(op.id)
            result.warnings.append(f"{op.id}: Would wait {duration}ms")
            return

        # Handle ApiCall
        if op.op_type == "ApiCall":
            method = self._get_prop_value(op, "method")
            url = self._get_prop_value(op, "url")
            result.operations_executed.append(op.id)
            if op.output_path:
                if op.output_path in data:
                    # Use mock data if provided
                    result.paths_written[op.output_path] = data[op.output_path]
                else:
                    data[op.output_path] = {"_simulated": True, "method": method, "url": url}
                    result.paths_written[op.output_path] = data[op.output_path]
                    result.warnings.append(
                        f"{op.id}: No mock data for {op.output_path}, using placeholder"
                    )
            return

        # Handle FilterData
        if op.op_type == "FilterData":
            result.operations_executed.append(op.id)
            input_val = data.get(op.input_path) if op.input_path else None
            if isinstance(input_val, list) and op.conditions:
                filtered = self._apply_filters(input_val, op.conditions)
                if op.output_path:
                    data[op.output_path] = filtered
                    result.paths_written[op.output_path] = filtered
            elif op.output_path:
                data[op.output_path] = input_val
                result.paths_written[op.output_path] = input_val
                if input_val is None and op.input_path:
                    result.warnings.append(f"{op.id}: Input path {op.input_path} has no data")
            return

        # Handle Loop
        if op.op_type == "Loop":
            result.operations_executed.append(op.id)
            input_val = data.get(op.input_path) if op.input_path else None
            if isinstance(input_val, list):
                result.warnings.append(f"{op.id}: Would loop over {len(input_val)} items")
            else:
                result.warnings.append(f"{op.id}: Loop input is not a list or not available")
            return

        # Generic operation: mark as executed, propagate data
        result.operations_executed.append(op.id)
        if op.input_path and op.output_path:
            input_val = data.get(op.input_path)
            data[op.output_path] = input_val
            result.paths_written[op.output_path] = input_val
        elif op.output_path:
            data[op.output_path] = {"_simulated": True, "op": op.op_type}
            result.paths_written[op.output_path] = data[op.output_path]

    def _evaluate_condition(
        self,
        path: str,
        operator: str,
        value: object,
        data: dict[str, object],
    ) -> bool:
        """Evaluate a condition against the data model."""
        actual = data.get(path)

        if actual is None:
            return operator in ("empty",)

        try:
            if operator == "==":
                return actual == value
            elif operator == "!=":
                return actual != value
            elif operator == ">":
                return actual > value  # type: ignore
            elif operator == "<":
                return actual < value  # type: ignore
            elif operator == ">=":
                return actual >= value  # type: ignore
            elif operator == "<=":
                return actual <= value  # type: ignore
            elif operator == "exists":
                return actual is not None
            elif operator == "empty":
                return not actual
            elif operator == "contains":
                return value in actual  # type: ignore
            elif operator == "in":
                return actual in value  # type: ignore
            elif operator == "startsWith":
                return str(actual).startswith(str(value))
            elif operator == "endsWith":
                return str(actual).endswith(str(value))
        except (TypeError, ValueError):
            return False

        return False

    def _apply_filters(self, items: list, conditions) -> list:
        """Apply filter conditions to a list of dicts."""
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            match = True
            for cond in conditions:
                field_val = item.get(cond.field)
                cond_val = cond.value
                if isinstance(cond_val, Path):
                    cond_val = cond_val.raw
                if not self._evaluate_condition_value(field_val, cond.operator, cond_val):
                    match = False
                    break
            if match:
                result.append(item)
        return result

    def _evaluate_condition_value(self, actual, operator, expected) -> bool:
        """Evaluate a single field condition."""
        if actual is None:
            return operator in ("empty",)
        try:
            if operator == "==":
                return actual == expected
            elif operator == "!=":
                return actual != expected
            elif operator == ">":
                return actual > expected
            elif operator == "<":
                return actual < expected
            elif operator == ">=":
                return actual >= expected
            elif operator == "<=":
                return actual <= expected
            elif operator == "contains":
                return expected in actual
            elif operator == "startsWith":
                return str(actual).startswith(str(expected))
            elif operator == "endsWith":
                return str(actual).endswith(str(expected))
            elif operator == "exists":
                return True
            elif operator == "empty":
                return not actual
        except (TypeError, ValueError):
            return False
        return False

    def _get_prop_value(self, op: Operation, key: str) -> object:
        """Get the raw value of a property."""
        for p in op.properties:
            if p.key == key:
                v = p.value
                if isinstance(v, (str, int, float, bool)):
                    return v
                if isinstance(v, Path):
                    return v.raw
                return str(v)
        return None

    def _resolve_if_value(self, value) -> object:
        """Resolve the value from an if clause."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return value.raw
        return str(value)
