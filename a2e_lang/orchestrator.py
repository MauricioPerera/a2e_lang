"""Multi-agent orchestration: chain workflows across agents.

Allows composing multiple workflows into an orchestrated pipeline
where the output of one workflow feeds into another. Supports
sequential, parallel, and conditional chaining patterns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .engine import ExecutionEngine, ExecutionResult
from .logging import ExecutionLogger, PipelineLog
from .parser import parse
from .resilience import RetryPolicy, API_RETRY, NO_RETRY
from .validator import Validator


class ChainMode(Enum):
    """How workflows are chained together."""
    SEQUENTIAL = "sequential"   # One after another
    PARALLEL = "parallel"       # All at once (simulated)
    CONDITIONAL = "conditional"  # Based on previous result


@dataclass
class AgentStep:
    """A single step in a multi-agent orchestration."""
    name: str
    source: str
    mode: ChainMode = ChainMode.SEQUENTIAL
    condition: str | None = None  # For CONDITIONAL: key to check in previous output
    retry_policy: RetryPolicy = field(default_factory=lambda: API_RETRY)
    input_mapping: dict[str, str] = field(default_factory=dict)
    # input_mapping: maps target_path -> source_path from previous step output


@dataclass
class OrchestrationResult:
    """Result of a multi-agent orchestration."""
    success: bool
    steps_completed: int = 0
    steps_total: int = 0
    step_results: list[dict[str, Any]] = field(default_factory=list)
    total_duration_ms: float = 0
    error: str | None = None

    def summary(self) -> str:
        status = "✅ Success" if self.success else "❌ Failed"
        lines = [
            f"Orchestration: {status}",
            f"Steps: {self.steps_completed}/{self.steps_total} completed",
            f"Duration: {self.total_duration_ms:.1f}ms",
            "─" * 50,
        ]
        for sr in self.step_results:
            icon = "✅" if sr.get("success") else "❌"
            dur = sr.get("duration_ms", 0)
            lines.append(f"  {icon} {sr['name']} [{dur:.1f}ms]")
            if sr.get("error"):
                lines.append(f"     └─ {sr['error']}")
        if self.error:
            lines.append(f"\n  ⚠ {self.error}")
        return "\n".join(lines)


class Orchestrator:
    """Orchestrate multiple workflow executions across agents.

    Usage:
        orch = Orchestrator()
        orch.add_step("fetch", fetch_source)
        orch.add_step("process", process_source, input_mapping={
            "/workflow/input": "/workflow/output"
        })
        result = orch.run()
    """

    def __init__(self):
        self.steps: list[AgentStep] = []

    def add_step(
        self,
        name: str,
        source: str,
        *,
        mode: ChainMode = ChainMode.SEQUENTIAL,
        condition: str | None = None,
        retry_policy: RetryPolicy | None = None,
        input_mapping: dict[str, str] | None = None,
    ) -> "Orchestrator":
        """Add a workflow step to the orchestration."""
        self.steps.append(AgentStep(
            name=name,
            source=source,
            mode=mode,
            condition=condition,
            retry_policy=retry_policy or API_RETRY,
            input_mapping=input_mapping or {},
        ))
        return self

    def run(
        self,
        input_data: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        """Execute the orchestration pipeline."""
        result = OrchestrationResult(steps_total=len(self.steps), success=False)
        start_time = time.time()
        accumulated_data: dict[str, Any] = dict(input_data or {})

        for step in self.steps:
            step_start = time.time()

            # Check condition
            if step.mode == ChainMode.CONDITIONAL and step.condition:
                condition_value = accumulated_data.get(step.condition)
                if not condition_value:
                    result.step_results.append({
                        "name": step.name,
                        "success": True,
                        "skipped": True,
                        "duration_ms": 0,
                        "reason": f"Condition '{step.condition}' not met",
                    })
                    result.steps_completed += 1
                    continue

            # Map inputs from previous step outputs
            step_input = dict(accumulated_data)
            for target_path, source_path in step.input_mapping.items():
                if source_path in accumulated_data:
                    step_input[target_path] = accumulated_data[source_path]

            # Parse and validate
            try:
                workflow = parse(step.source)
                errors = Validator().validate(workflow)
                if errors:
                    step_duration = (time.time() - step_start) * 1000
                    result.step_results.append({
                        "name": step.name,
                        "success": False,
                        "duration_ms": step_duration,
                        "error": f"Validation: {errors[0]}",
                    })
                    result.error = f"Step '{step.name}' failed validation"
                    break

            except Exception as e:
                step_duration = (time.time() - step_start) * 1000
                result.step_results.append({
                    "name": step.name,
                    "success": False,
                    "duration_ms": step_duration,
                    "error": str(e),
                })
                result.error = f"Step '{step.name}' failed: {e}"
                break

            # Execute
            engine = ExecutionEngine(
                retry_policy=step.retry_policy,
                input_data=step_input,
            )
            exec_result = engine.execute(workflow)
            step_duration = (time.time() - step_start) * 1000

            result.step_results.append({
                "name": step.name,
                "success": exec_result.success,
                "duration_ms": step_duration,
                "error": exec_result.error,
            })

            if exec_result.success:
                result.steps_completed += 1
                # Merge outputs into accumulated data for next step
                accumulated_data.update(exec_result.data)
            else:
                result.error = f"Step '{step.name}' failed: {exec_result.error}"
                break

        result.total_duration_ms = (time.time() - start_time) * 1000
        result.success = result.steps_completed == result.steps_total
        return result
