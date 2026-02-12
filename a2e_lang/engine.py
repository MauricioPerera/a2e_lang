"""Execution engine: native Python runtime for A2E workflows.

Executes compiled a2e-lang workflows by dispatching operations to
registered handlers. Integrates structured logging and resilience
(retry + circuit breaker) at the operation level.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .ast_nodes import Operation, Path, Workflow
from .logging import ExecutionLogger, PipelineLog, OperationLog
from .resilience import (
    CircuitBreaker,
    RetryPolicy,
    API_RETRY,
    execute_with_retry,
)


# ---------------------------------------------------------------------------
# Operation handler registry
# ---------------------------------------------------------------------------

# Handler signature: (operation, context) -> result
OperationHandler = Callable[[Operation, "ExecutionContext"], Any]

_HANDLERS: dict[str, OperationHandler] = {}


def register_handler(op_type: str, handler: OperationHandler) -> None:
    """Register a handler for an operation type."""
    _HANDLERS[op_type] = handler


def get_handler(op_type: str) -> OperationHandler | None:
    """Get the registered handler for an operation type."""
    return _HANDLERS.get(op_type)


# ---------------------------------------------------------------------------
# Execution context
# ---------------------------------------------------------------------------

@dataclass
class ExecutionContext:
    """Runtime context available to operation handlers."""
    data: dict[str, Any] = field(default_factory=dict)
    logger: ExecutionLogger | None = None
    retry_policy: RetryPolicy = field(default_factory=lambda: API_RETRY)
    circuit_breakers: dict[str, CircuitBreaker] = field(default_factory=dict)

    def get(self, path: str) -> Any:
        """Read a value from the data store."""
        return self.data.get(path)

    def set(self, path: str, value: Any) -> None:
        """Write a value to the data store."""
        self.data[path] = value

    def get_circuit(self, op_id: str) -> CircuitBreaker:
        """Get or create a circuit breaker for an operation."""
        if op_id not in self.circuit_breakers:
            self.circuit_breakers[op_id] = CircuitBreaker()
        return self.circuit_breakers[op_id]


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------

def _handle_wait(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a Wait operation."""
    duration = _get_prop(op, "duration")
    if isinstance(duration, (int, float)):
        time.sleep(duration / 1000)  # duration is in ms
    return {"waited_ms": duration}


def _handle_store_data(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a StoreData operation."""
    input_data = ctx.get(op.input_path) if op.input_path else None
    key = _get_prop(op, "key")
    storage = _get_prop(op, "storage")
    return {"stored": True, "key": key, "storage": storage, "data": input_data}


def _handle_filter_data(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a FilterData operation."""
    input_data = ctx.get(op.input_path) if op.input_path else []
    if not isinstance(input_data, list):
        return input_data

    if not op.conditions:
        return input_data

    results = []
    for item in input_data:
        if not isinstance(item, dict):
            continue
        match = True
        for cond in op.conditions:
            val = item.get(cond.field)
            if not _eval_condition(val, cond.operator, _resolve_value(cond.value)):
                match = False
                break
        if match:
            results.append(item)
    return results


def _handle_transform_data(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a TransformData operation."""
    input_data = ctx.get(op.input_path) if op.input_path else None
    transform = _get_prop(op, "transform")
    # Basic transforms
    if isinstance(input_data, list) and transform == "sort":
        return sorted(input_data, key=lambda x: str(x))
    return input_data


def _handle_merge_data(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a MergeData operation."""
    sources = _get_prop(op, "sources")
    strategy = _get_prop(op, "strategy") or "concat"

    if not isinstance(sources, list):
        return None

    merged: list = []
    for src in sources:
        path = src if isinstance(src, str) else getattr(src, "raw", str(src))
        data = ctx.get(path)
        if isinstance(data, list):
            merged.extend(data)
        elif data is not None:
            merged.append(data)

    return merged


def _handle_get_datetime(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a GetCurrentDateTime operation."""
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _handle_calculate(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a Calculate operation."""
    expression = _get_prop(op, "expression")
    return {"expression": expression, "result": None}


def _handle_format_text(op: Operation, ctx: ExecutionContext) -> Any:
    """Execute a FormatText operation."""
    template = _get_prop(op, "template")
    return {"template": template, "formatted": template}


def _handle_noop(op: Operation, ctx: ExecutionContext) -> Any:
    """Default handler for operations without specific implementation."""
    input_data = ctx.get(op.input_path) if op.input_path else None
    return input_data


# Register built-in handlers
register_handler("Wait", _handle_wait)
register_handler("StoreData", _handle_store_data)
register_handler("FilterData", _handle_filter_data)
register_handler("TransformData", _handle_transform_data)
register_handler("MergeData", _handle_merge_data)
register_handler("GetCurrentDateTime", _handle_get_datetime)
register_handler("Calculate", _handle_calculate)
register_handler("FormatText", _handle_format_text)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Result of a workflow execution."""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    pipeline_log: PipelineLog | None = None
    error: str | None = None

    def summary(self) -> str:
        if self.pipeline_log:
            return self.pipeline_log.summary()
        status = "✅ Success" if self.success else "❌ Failed"
        return f"{status}: {self.error or 'OK'}"


class ExecutionEngine:
    """Native Python runtime for executing a2e-lang workflows.

    Features:
    - Dispatches operations to registered handlers
    - Structured logging with per-operation timing
    - Retry + circuit breaker per operation
    - Data flow through paths
    """

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        input_data: dict[str, Any] | None = None,
    ):
        self.retry_policy = retry_policy or API_RETRY
        self.initial_data = input_data or {}

    def execute(self, workflow: Workflow) -> ExecutionResult:
        """Execute a workflow and return the result."""
        logger = ExecutionLogger(workflow.name)
        ctx = ExecutionContext(
            data=dict(self.initial_data),
            logger=logger,
            retry_policy=self.retry_policy,
        )

        op_map = {op.id: op for op in workflow.operations}

        # Determine execution order
        if workflow.execution_order:
            exec_order = list(workflow.execution_order)
        else:
            exec_order = [op.id for op in workflow.operations]

        try:
            for op_id in exec_order:
                if op_id not in op_map:
                    logger.skip_operation(op_id, "unknown", reason="Not defined")
                    continue

                op = op_map[op_id]
                self._execute_operation(op, ctx, logger, op_map)

        except Exception as e:
            logger.finish("failed")
            return ExecutionResult(
                success=False,
                data=ctx.data,
                pipeline_log=logger.pipeline,
                error=str(e),
            )

        pipeline = logger.finish()
        return ExecutionResult(
            success=pipeline.error_count == 0,
            data=ctx.data,
            pipeline_log=pipeline,
        )

    def _execute_operation(
        self,
        op: Operation,
        ctx: ExecutionContext,
        logger: ExecutionLogger,
        op_map: dict[str, Operation],
    ) -> None:
        """Execute a single operation with retry and logging."""

        # Handle Conditional branching
        if op.op_type == "Conditional" and op.if_clause:
            self._execute_conditional(op, ctx, logger, op_map)
            return

        handler = get_handler(op.op_type) or _handle_noop
        circuit = ctx.get_circuit(op.id)

        logger.start_operation(op.id, op.op_type)

        # Wrap handler in retry + circuit breaker
        result = execute_with_retry(
            fn=lambda: handler(op, ctx),
            policy=ctx.retry_policy,
            circuit=circuit,
            sleep_fn=time.sleep,
        )

        if result.success:
            # Write output to data store
            if op.output_path and result.value is not None:
                ctx.set(op.output_path, result.value)
            logger.complete_operation(op.id, output=result.value, output_path=op.output_path)
        else:
            logger.fail_operation(op.id, str(result.error))

    def _execute_conditional(
        self,
        op: Operation,
        ctx: ExecutionContext,
        logger: ExecutionLogger,
        op_map: dict[str, Operation],
    ) -> None:
        """Execute a Conditional operation (branching)."""
        ic = op.if_clause
        actual = ctx.get(ic.path)
        expected = _resolve_value(ic.value)
        condition_met = _eval_condition(actual, ic.operator, expected)

        logger.start_operation(op.id, "Conditional")

        if condition_met:
            logger.complete_operation(op.id, output={"branch": "then"})
            for target_id in ic.if_true:
                if target_id in op_map:
                    self._execute_operation(op_map[target_id], ctx, logger, op_map)
        else:
            logger.complete_operation(op.id, output={"branch": "else"})
            if ic.if_false:
                for target_id in ic.if_false:
                    if target_id in op_map:
                        self._execute_operation(op_map[target_id], ctx, logger, op_map)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_prop(op: Operation, key: str) -> Any:
    """Get property value from an operation."""
    for p in op.properties:
        if p.key == key:
            v = p.value
            if isinstance(v, Path):
                return v.raw
            return v
    return None


def _resolve_value(value: Any) -> Any:
    """Resolve AST value to Python value."""
    if isinstance(value, Path):
        return value.raw
    return value


def _eval_condition(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate a comparison condition."""
    if actual is None:
        return operator in ("empty",)
    try:
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == ">":
            return actual > expected
        if operator == "<":
            return actual < expected
        if operator == ">=":
            return actual >= expected
        if operator == "<=":
            return actual <= expected
        if operator == "contains":
            return expected in actual
        if operator == "in":
            return actual in expected
        if operator == "startsWith":
            return str(actual).startswith(str(expected))
        if operator == "endsWith":
            return str(actual).endswith(str(expected))
        if operator == "exists":
            return actual is not None
        if operator == "empty":
            return not actual
    except (TypeError, ValueError):
        return False
    return False
