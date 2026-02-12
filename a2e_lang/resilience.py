"""Retry and circuit breaker: operation-level failure handling.

Provides:
- RetryPolicy: configurable retries with exponential backoff
- CircuitBreaker: prevent cascading failures by tripping after N errors
- resilient(): decorator combining both patterns
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar, Any

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for operation retry behavior."""

    max_retries: int = 3
    base_delay_ms: float = 1000
    max_delay_ms: float = 30000
    backoff_factor: float = 2.0
    retryable_errors: tuple[type[Exception], ...] = (Exception,)

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay in seconds for a given attempt number."""
        delay_ms = self.base_delay_ms * (self.backoff_factor ** attempt)
        delay_ms = min(delay_ms, self.max_delay_ms)
        return delay_ms / 1000

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if an operation should be retried."""
        if attempt >= self.max_retries:
            return False
        return isinstance(error, self.retryable_errors)


# Preset policies
NO_RETRY = RetryPolicy(max_retries=0)
CONSERVATIVE = RetryPolicy(max_retries=2, base_delay_ms=2000, backoff_factor=3.0)
AGGRESSIVE = RetryPolicy(max_retries=5, base_delay_ms=500, backoff_factor=1.5)
API_RETRY = RetryPolicy(max_retries=3, base_delay_ms=1000, backoff_factor=2.0)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker pattern for preventing cascading failures.

    - CLOSED: requests flow normally; failures increment counter
    - OPEN: all requests rejected immediately; after reset_timeout, moves to HALF_OPEN
    - HALF_OPEN: single test request allowed; success resets, failure re-opens
    """

    failure_threshold: int = 5
    reset_timeout_ms: float = 60000
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _success_count: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        """Current state, with automatic OPEN → HALF_OPEN transition."""
        if self._state == CircuitState.OPEN:
            elapsed_ms = (time.time() - self._last_failure_time) * 1000
            if elapsed_ms >= self.reset_timeout_ms:
                self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def is_available(self) -> bool:
        """Whether the circuit allows requests."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful operation."""
        self._failure_count = 0
        self._success_count += 1
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed operation."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset the circuit breaker to initial state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0

    def status(self) -> dict[str, Any]:
        """Return current status as a dict."""
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "is_available": self.is_available,
        }


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting requests."""
    pass


# ---------------------------------------------------------------------------
# Resilient execution helper
# ---------------------------------------------------------------------------

@dataclass
class RetryResult:
    """Result of a resilient execution attempt."""
    success: bool
    value: Any = None
    error: Exception | None = None
    attempts: int = 0
    total_delay_ms: float = 0
    circuit_state: str = "closed"

    def summary(self) -> str:
        status = "✅ Success" if self.success else "❌ Failed"
        lines = [
            f"{status} after {self.attempts} attempt(s)",
            f"  Total delay: {self.total_delay_ms:.0f}ms",
            f"  Circuit: {self.circuit_state}",
        ]
        if self.error:
            lines.append(f"  Error: {self.error}")
        return "\n".join(lines)


def execute_with_retry(
    fn: Callable[[], T],
    policy: RetryPolicy | None = None,
    circuit: CircuitBreaker | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> RetryResult:
    """Execute a function with retry and circuit breaker support.

    Args:
        fn: The function to execute.
        policy: Retry policy (defaults to API_RETRY).
        circuit: Optional circuit breaker.
        sleep_fn: Optional custom sleep function (for testing).

    Returns:
        RetryResult with execution details.
    """
    if policy is None:
        policy = API_RETRY
    if sleep_fn is None:
        sleep_fn = time.sleep

    # Check circuit breaker
    if circuit and not circuit.is_available:
        return RetryResult(
            success=False,
            error=CircuitOpenError("Circuit breaker is open"),
            attempts=0,
            circuit_state=circuit.state.value,
        )

    total_delay = 0.0
    last_error: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            result = fn()

            if circuit:
                circuit.record_success()

            return RetryResult(
                success=True,
                value=result,
                attempts=attempt + 1,
                total_delay_ms=total_delay,
                circuit_state=circuit.state.value if circuit else "closed",
            )

        except Exception as e:
            last_error = e

            if circuit:
                circuit.record_failure()

            if not policy.should_retry(e, attempt):
                break

            delay = policy.delay_for_attempt(attempt)
            total_delay += delay * 1000
            sleep_fn(delay)

    return RetryResult(
        success=False,
        error=last_error,
        attempts=policy.max_retries + 1,
        total_delay_ms=total_delay,
        circuit_state=circuit.state.value if circuit else "closed",
    )
