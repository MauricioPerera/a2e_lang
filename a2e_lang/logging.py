"""Structured logging: per-operation execution logs with timing metrics.

Provides a logging framework for workflow execution that captures:
- Operation start/end timestamps
- Execution duration per operation
- Input/output data snapshots
- Error details with context
- Pipeline-level metrics
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class OperationLog:
    """Log entry for a single operation execution."""
    operation_id: str
    operation_type: str
    status: str  # "started", "completed", "failed", "skipped"
    timestamp: float = field(default_factory=time.time)
    duration_ms: float | None = None
    input_path: str | None = None
    output_path: str | None = None
    input_snapshot: Any = None
    output_snapshot: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        d = {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "timestamp": self.timestamp,
        }
        if self.duration_ms is not None:
            d["duration_ms"] = round(self.duration_ms, 3)
        if self.input_path:
            d["input_path"] = self.input_path
        if self.output_path:
            d["output_path"] = self.output_path
        if self.input_snapshot is not None:
            d["input_snapshot"] = self.input_snapshot
        if self.output_snapshot is not None:
            d["output_snapshot"] = self.output_snapshot
        if self.error:
            d["error"] = self.error
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class PipelineLog:
    """Aggregated log for an entire pipeline execution."""
    workflow_name: str
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"
    operations: list[OperationLog] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_duration_ms(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at) * 1000

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    @property
    def error_count(self) -> int:
        return sum(1 for op in self.operations if op.status == "failed")

    @property
    def success_count(self) -> int:
        return sum(1 for op in self.operations if op.status == "completed")

    def finish(self, status: str = "completed") -> None:
        self.finished_at = time.time()
        self.status = status

    def to_dict(self) -> dict:
        d = {
            "workflow_name": self.workflow_name,
            "started_at": self.started_at,
            "status": self.status,
            "operations": [op.to_dict() for op in self.operations],
        }
        if self.finished_at:
            d["finished_at"] = self.finished_at
            d["total_duration_ms"] = round(self.total_duration_ms, 3)
        if self.errors:
            d["errors"] = self.errors
        return d

    def to_json(self, pretty: bool = False) -> str:
        indent = 2 if pretty else None
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def summary(self) -> str:
        duration = f"{self.total_duration_ms:.1f}ms" if self.total_duration_ms else "running"
        lines = [
            f"Pipeline: {self.workflow_name} [{self.status}]",
            f"Duration: {duration}",
            f"Operations: {self.success_count}/{self.operation_count} succeeded",
            "─" * 50,
        ]
        for op in self.operations:
            dur = f"{op.duration_ms:.1f}ms" if op.duration_ms else "—"
            icon = "✅" if op.status == "completed" else "❌" if op.status == "failed" else "⏭️"
            lines.append(f"  {icon} {op.operation_id} ({op.operation_type}) [{dur}]")
            if op.error:
                lines.append(f"     └─ {op.error}")
        if self.errors:
            lines.append("─" * 50)
            for err in self.errors:
                lines.append(f"  ⚠ {err}")
        return "\n".join(lines)


class ExecutionLogger:
    """Logger that tracks operation executions in a pipeline."""

    def __init__(self, workflow_name: str):
        self.pipeline = PipelineLog(workflow_name=workflow_name)
        self._op_starts: dict[str, float] = {}

    def start_operation(self, op_id: str, op_type: str, **metadata) -> None:
        """Log the start of an operation."""
        self._op_starts[op_id] = time.time()
        log = OperationLog(
            operation_id=op_id,
            operation_type=op_type,
            status="started",
            metadata=metadata,
        )
        self.pipeline.operations.append(log)

    def complete_operation(
        self,
        op_id: str,
        output: Any = None,
        output_path: str | None = None,
    ) -> None:
        """Log the successful completion of an operation."""
        log = self._find_log(op_id)
        if log:
            log.status = "completed"
            start = self._op_starts.get(op_id)
            if start:
                log.duration_ms = (time.time() - start) * 1000
            if output is not None:
                log.output_snapshot = output
            if output_path:
                log.output_path = output_path

    def fail_operation(self, op_id: str, error: str) -> None:
        """Log an operation failure."""
        log = self._find_log(op_id)
        if log:
            log.status = "failed"
            log.error = error
            start = self._op_starts.get(op_id)
            if start:
                log.duration_ms = (time.time() - start) * 1000
        self.pipeline.errors.append(f"{op_id}: {error}")

    def skip_operation(self, op_id: str, op_type: str, reason: str = "") -> None:
        """Log a skipped operation."""
        log = OperationLog(
            operation_id=op_id,
            operation_type=op_type,
            status="skipped",
            metadata={"reason": reason} if reason else {},
        )
        self.pipeline.operations.append(log)

    def finish(self, status: str | None = None) -> PipelineLog:
        """Finalize the pipeline log."""
        if status is None:
            status = "failed" if self.pipeline.errors else "completed"
        self.pipeline.finish(status)
        return self.pipeline

    def _find_log(self, op_id: str) -> OperationLog | None:
        """Find the most recent log entry for an operation."""
        for log in reversed(self.pipeline.operations):
            if log.operation_id == op_id:
                return log
        return None
