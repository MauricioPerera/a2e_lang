"""Decompiler: A2E JSONL -> a2e-lang DSL source code.

Supports both the official spec format and the legacy bundled format.
This enables round-tripping: DSL -> JSONL -> DSL.
"""

from __future__ import annotations

import json


class Decompiler:
    """Converts A2E JSONL back to a2e-lang DSL source code."""

    def decompile(self, jsonl: str) -> str:
        """Decompile JSONL string to a2e-lang DSL source.

        Automatically detects whether the input is in spec format
        (one line per operation) or legacy format (bundled operations).
        """
        lines_raw = [ln.strip() for ln in jsonl.strip().splitlines() if ln.strip()]
        messages = [json.loads(ln) for ln in lines_raw]

        if not messages:
            raise ValueError("Empty JSONL input")

        # Detect format
        if messages[0].get("type") == "operationUpdate":
            return self._decompile_spec(messages)
        elif "operationUpdate" in messages[0]:
            return self._decompile_legacy(messages)
        else:
            raise ValueError(
                "Unrecognized JSONL format. Expected spec format "
                "(type: operationUpdate) or legacy format (operationUpdate: {...})."
            )

    def _decompile_spec(self, messages: list[dict]) -> str:
        """Decompile official A2E spec format."""
        operations = []
        workflow_name = "workflow"
        execution_order: list[str] = []

        for msg in messages:
            msg_type = msg.get("type")
            if msg_type == "operationUpdate":
                op_id = msg["operationId"]
                operation = msg["operation"]
                # operation is {OpType: {config...}}
                op_type = next(iter(operation))
                config = operation[op_type]
                operations.append((op_id, op_type, config))
            elif msg_type == "beginExecution":
                workflow_name = msg.get("executionId", "workflow")
                execution_order = msg.get("operationOrder", [])

        return self._render_dsl(workflow_name, operations, execution_order)

    def _decompile_legacy(self, messages: list[dict]) -> str:
        """Decompile legacy bundled format."""
        operations = []
        workflow_name = "workflow"
        execution_order: list[str] = []

        for msg in messages:
            if "operationUpdate" in msg:
                update = msg["operationUpdate"]
                workflow_name = update.get("workflowId", "workflow")
                for op_entry in update.get("operations", []):
                    op_id = op_entry["id"]
                    operation = op_entry["operation"]
                    op_type = next(iter(operation))
                    config = operation[op_type]
                    operations.append((op_id, op_type, config))
            elif "beginExecution" in msg:
                exec_data = msg["beginExecution"]
                workflow_name = exec_data.get("workflowId", workflow_name)
                root = exec_data.get("root", "")
                if root and not execution_order:
                    # Legacy only has root, reconstruct order from operations
                    execution_order = [op[0] for op in operations]

        return self._render_dsl(workflow_name, operations, execution_order)

    def _render_dsl(
        self,
        workflow_name: str,
        operations: list[tuple[str, str, dict]],
        execution_order: list[str],
    ) -> str:
        """Render a2e-lang DSL source from extracted data."""
        lines: list[str] = []
        lines.append(f'workflow "{workflow_name}"')
        lines.append("")

        for op_id, op_type, config in operations:
            lines.append(f"{op_id} = {op_type} {{")
            lines.extend(self._render_config(config, indent=2))
            lines.append("}")
            lines.append("")

        if execution_order and len(execution_order) > 1:
            lines.append("run: " + " -> ".join(execution_order))
            lines.append("")

        return "\n".join(lines)

    def _render_config(self, config: dict, indent: int = 2) -> list[str]:
        """Render operation config as DSL body lines."""
        lines: list[str] = []
        prefix = " " * indent

        # Handle structural fields first
        input_path = config.get("inputPath")
        output_path = config.get("outputPath")
        conditions = config.get("conditions")
        condition = config.get("condition")
        if_true = config.get("ifTrue")
        if_false = config.get("ifFalse")

        # inputPath -> from clause
        if input_path:
            lines.append(f"{prefix}from {input_path}")

        # Regular properties (excluding structural fields)
        structural = {"inputPath", "outputPath", "conditions", "condition", "ifTrue", "ifFalse"}
        for key, value in config.items():
            if key in structural:
                continue
            rendered = self._render_value(value, indent)
            lines.append(f"{prefix}{key}: {rendered}")

        # conditions -> where clause
        if conditions:
            cond_parts = []
            for c in conditions:
                field = c["field"]
                operator = c["operator"]
                if "value" in c:
                    val = self._render_value(c["value"], indent)
                    cond_parts.append(f"{field} {operator} {val}")
                else:
                    cond_parts.append(f"{field} {operator}")
            lines.append(f"{prefix}where " + ", ".join(cond_parts))

        # condition + ifTrue/ifFalse -> if clause
        if condition and if_true:
            path = condition["path"]
            operator = condition["operator"]
            cond_val = condition.get("value")
            if_line = f"{prefix}if {path} {operator}"
            if cond_val is not None:
                if_line += f" {self._render_value(cond_val, indent)}"

            # ifTrue targets
            if isinstance(if_true, list):
                if_line += f" then {', '.join(if_true)}"
            else:
                if_line += f" then {if_true}"
            lines.append(if_line)

            # ifFalse targets
            if if_false:
                if isinstance(if_false, list):
                    lines.append(f"{prefix}else {', '.join(if_false)}")
                else:
                    lines.append(f"{prefix}else {if_false}")

        # outputPath -> arrow clause
        if output_path:
            lines.append(f"{prefix}-> {output_path}")

        return lines

    def _render_value(self, value: object, indent: int = 2) -> str:
        """Render a JSON value as DSL syntax."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            # Check if it looks like a path
            if value.startswith("/"):
                return value
            return f'"{value}"'
        if isinstance(value, dict):
            # Check for credential ref
            if "credentialRef" in value:
                cred_id = value["credentialRef"].get("id", "")
                return f'credential("{cred_id}")'
            # Render as object
            return self._render_object(value, indent)
        if isinstance(value, list):
            # Check if all items are strings that look like paths
            items = [self._render_value(item, indent) for item in value]
            return "[" + ", ".join(items) + "]"
        return str(value)

    def _render_object(self, obj: dict, indent: int) -> str:
        """Render a dict as a DSL object literal."""
        if not obj:
            return "{}"
        parts = []
        for key, val in obj.items():
            parts.append(f"{key}: {self._render_value(val, indent)}")
        # Single-line if short enough
        inline = "{ " + ", ".join(parts) + " }"
        if len(inline) <= 80:
            return inline
        # Multi-line
        prefix = " " * (indent + 2)
        lines = ["{"]
        for part in parts:
            lines.append(f"{prefix}{part}")
        lines.append(" " * indent + "}")
        return "\n".join(lines)
