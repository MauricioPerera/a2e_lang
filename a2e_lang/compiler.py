"""Compiler: AST -> A2E JSONL."""

from __future__ import annotations

import json

from .ast_nodes import (
    ArrayValue,
    Condition,
    Credential,
    IfClause,
    ObjectValue,
    Operation,
    Path,
    Property,
    Workflow,
    Value,
)
from .errors import CompileError


class Compiler:
    """Compiles a validated Workflow AST to A2E protocol JSONL."""

    def compile(self, workflow: Workflow) -> str:
        """Return JSONL string (one JSON object per line)."""
        operations = [self._compile_operation(op) for op in workflow.operations]

        # Determine execution order
        if workflow.execution_order:
            exec_order = list(workflow.execution_order)
        else:
            exec_order = [op.id for op in workflow.operations]

        lines = []

        # Line 1: operationUpdate
        lines.append(json.dumps({
            "operationUpdate": {
                "workflowId": workflow.name,
                "operations": operations,
            }
        }, separators=(",", ":")))

        # Line 2: beginExecution
        lines.append(json.dumps({
            "beginExecution": {
                "workflowId": workflow.name,
                "root": exec_order[0] if exec_order else "",
            }
        }, separators=(",", ":")))

        return "\n".join(lines)

    def compile_pretty(self, workflow: Workflow) -> str:
        """Return pretty-printed JSONL (one JSON object per line, indented)."""
        operations = [self._compile_operation(op) for op in workflow.operations]

        if workflow.execution_order:
            exec_order = list(workflow.execution_order)
        else:
            exec_order = [op.id for op in workflow.operations]

        lines = []

        lines.append(json.dumps({
            "operationUpdate": {
                "workflowId": workflow.name,
                "operations": operations,
            }
        }, indent=2))

        lines.append(json.dumps({
            "beginExecution": {
                "workflowId": workflow.name,
                "root": exec_order[0] if exec_order else "",
            }
        }, indent=2))

        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Operation compilation
    # ------------------------------------------------------------------

    def _compile_operation(self, op: Operation) -> dict:
        config = {}

        # inputPath from 'from' clause
        if op.input_path:
            config["inputPath"] = op.input_path

        # outputPath from '->' clause
        if op.output_path:
            config["outputPath"] = op.output_path

        # Filter conditions from 'where' clause
        if op.conditions:
            config["conditions"] = [
                self._compile_condition(c) for c in op.conditions
            ]

        # Conditional from 'if' clause
        if op.if_clause:
            config["condition"] = {
                "path": op.if_clause.path,
                "operator": op.if_clause.operator,
            }
            if op.if_clause.value is not None:
                config["condition"]["value"] = self._compile_value(op.if_clause.value)

            # ifTrue/ifFalse: single string if one target, array if multiple
            config["ifTrue"] = _target_list(op.if_clause.if_true)
            if op.if_clause.if_false:
                config["ifFalse"] = _target_list(op.if_clause.if_false)

        # All other properties
        for prop in op.properties:
            config[prop.key] = self._compile_value(prop.value)

        return {
            "id": op.id,
            "operation": {
                op.op_type: config,
            },
        }

    def _compile_condition(self, cond: Condition) -> dict:
        result: dict = {
            "field": cond.field,
            "operator": cond.operator,
        }
        if cond.value is not None:
            result["value"] = self._compile_value(cond.value)
        return result

    def _compile_value(self, value: Value) -> object:
        if isinstance(value, (str, int, float, bool)):
            return value
        if value is None:
            return None
        if isinstance(value, Path):
            return value.raw
        if isinstance(value, Credential):
            return {"credentialRef": {"id": value.id}}
        if isinstance(value, ObjectValue):
            return self._compile_object(value)
        if isinstance(value, ArrayValue):
            return [self._compile_value(item) for item in value.items]
        raise CompileError(f"Unknown value type: {type(value)}")

    def _compile_object(self, obj: ObjectValue) -> dict:
        result = {}
        for prop in obj.properties:
            result[prop.key] = self._compile_value(prop.value)
        return result


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _target_list(targets: tuple[str, ...]) -> str | list[str]:
    """Return a single string for one target, or array for multiple."""
    if len(targets) == 1:
        return targets[0]
    return list(targets)
