"""Spec-compliant compiler: AST -> A2E protocol JSONL (official format).

Generates JSONL that matches the official A2E specification:
  https://github.com/MauricioPerera/a2e/blob/main/SPECIFICATION.md

Output format:
  - One {"type":"operationUpdate","operationId":"...","operation":{...}} per operation
  - One {"type":"beginExecution","executionId":"...","operationOrder":[...]} at the end
"""

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


class SpecCompiler:
    """Compiles a validated Workflow AST to official A2E protocol JSONL."""

    def compile(self, workflow: Workflow) -> str:
        """Return JSONL string matching the official A2E spec format."""
        if workflow.execution_order:
            exec_order = list(workflow.execution_order)
        else:
            exec_order = [op.id for op in workflow.operations]

        lines = []

        # One operationUpdate line per operation
        for op in workflow.operations:
            config = self._compile_operation_config(op)
            lines.append(json.dumps({
                "type": "operationUpdate",
                "operationId": op.id,
                "operation": {
                    op.op_type: config,
                },
            }, separators=(",", ":")))

        # Final beginExecution line
        lines.append(json.dumps({
            "type": "beginExecution",
            "executionId": workflow.name,
            "operationOrder": exec_order,
        }, separators=(",", ":")))

        return "\n".join(lines)

    def compile_pretty(self, workflow: Workflow) -> str:
        """Return pretty-printed JSONL in official A2E spec format."""
        if workflow.execution_order:
            exec_order = list(workflow.execution_order)
        else:
            exec_order = [op.id for op in workflow.operations]

        lines = []

        for op in workflow.operations:
            config = self._compile_operation_config(op)
            lines.append(json.dumps({
                "type": "operationUpdate",
                "operationId": op.id,
                "operation": {
                    op.op_type: config,
                },
            }, indent=2))

        lines.append(json.dumps({
            "type": "beginExecution",
            "executionId": workflow.name,
            "operationOrder": exec_order,
        }, indent=2))

        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Operation compilation
    # ------------------------------------------------------------------

    def _compile_operation_config(self, op: Operation) -> dict:
        config = {}

        if op.input_path:
            config["inputPath"] = op.input_path

        if op.output_path:
            config["outputPath"] = op.output_path

        if op.conditions:
            config["conditions"] = [
                self._compile_condition(c) for c in op.conditions
            ]

        if op.if_clause:
            config["condition"] = {
                "path": op.if_clause.path,
                "operator": op.if_clause.operator,
            }
            if op.if_clause.value is not None:
                config["condition"]["value"] = self._compile_value(op.if_clause.value)

            config["ifTrue"] = list(op.if_clause.if_true)
            if op.if_clause.if_false:
                config["ifFalse"] = list(op.if_clause.if_false)

        for prop in op.properties:
            config[prop.key] = self._compile_value(prop.value)

        return config

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
