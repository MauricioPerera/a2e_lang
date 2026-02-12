"""Tests for Phase 3: Runtime & Observability features."""

import json
import time
import urllib.request
import pytest

from a2e_lang.parser import parse
from a2e_lang.logging import (
    ExecutionLogger,
    OperationLog,
    PipelineLog,
    LogLevel,
)
from a2e_lang.resilience import (
    RetryPolicy,
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    execute_with_retry,
    NO_RETRY,
    CONSERVATIVE,
    AGGRESSIVE,
    API_RETRY,
)
from a2e_lang.engine import (
    ExecutionEngine,
    ExecutionContext,
    ExecutionResult,
    register_handler,
    get_handler,
)
from a2e_lang.webhook import WebhookServer


# ---------------------------------------------------------------------------
# Structured Logging
# ---------------------------------------------------------------------------

class TestStructuredLogging:

    def test_execution_logger_basic(self):
        logger = ExecutionLogger("test-workflow")
        logger.start_operation("op1", "ApiCall")
        logger.complete_operation("op1", output={"status": 200})
        pipeline = logger.finish()

        assert pipeline.workflow_name == "test-workflow"
        assert pipeline.status == "completed"
        assert pipeline.operation_count == 1
        assert pipeline.success_count == 1
        assert pipeline.error_count == 0

    def test_execution_logger_failure(self):
        logger = ExecutionLogger("test")
        logger.start_operation("op1", "ApiCall")
        logger.fail_operation("op1", "Connection timeout")
        pipeline = logger.finish()

        assert pipeline.status == "failed"
        assert pipeline.error_count == 1
        assert len(pipeline.errors) == 1

    def test_execution_logger_skip(self):
        logger = ExecutionLogger("test")
        logger.skip_operation("op1", "Wait", reason="Condition not met")
        pipeline = logger.finish()

        assert pipeline.operation_count == 1
        assert pipeline.operations[0].status == "skipped"

    def test_pipeline_log_duration(self):
        logger = ExecutionLogger("test")
        logger.start_operation("op1", "Wait")
        logger.complete_operation("op1")
        pipeline = logger.finish()

        assert pipeline.total_duration_ms is not None
        assert pipeline.total_duration_ms >= 0

    def test_pipeline_log_to_json(self):
        logger = ExecutionLogger("test")
        logger.start_operation("op1", "Wait")
        logger.complete_operation("op1")
        pipeline = logger.finish()

        json_str = pipeline.to_json(pretty=True)
        parsed = json.loads(json_str)
        assert parsed["workflow_name"] == "test"
        assert parsed["status"] == "completed"

    def test_pipeline_summary(self):
        logger = ExecutionLogger("test")
        logger.start_operation("op1", "ApiCall")
        logger.complete_operation("op1")
        pipeline = logger.finish()

        summary = pipeline.summary()
        assert "test" in summary
        assert "✅" in summary

    def test_operation_log_to_dict(self):
        log = OperationLog(
            operation_id="op1",
            operation_type="ApiCall",
            status="completed",
            duration_ms=42.5,
            error=None,
        )
        d = log.to_dict()
        assert d["operation_id"] == "op1"
        assert d["duration_ms"] == 42.5
        assert "error" not in d  # None values excluded


# ---------------------------------------------------------------------------
# Retry & Circuit Breaker
# ---------------------------------------------------------------------------

class TestRetryPolicy:

    def test_delay_calculation(self):
        policy = RetryPolicy(base_delay_ms=1000, backoff_factor=2.0)
        assert policy.delay_for_attempt(0) == 1.0  # 1000ms
        assert policy.delay_for_attempt(1) == 2.0  # 2000ms
        assert policy.delay_for_attempt(2) == 4.0  # 4000ms

    def test_max_delay_cap(self):
        policy = RetryPolicy(base_delay_ms=10000, max_delay_ms=15000, backoff_factor=2.0)
        assert policy.delay_for_attempt(5) == 15.0  # capped at max

    def test_should_retry(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(Exception("test"), 0) is True
        assert policy.should_retry(Exception("test"), 2) is True
        assert policy.should_retry(Exception("test"), 3) is False

    def test_presets_exist(self):
        assert NO_RETRY.max_retries == 0
        assert CONSERVATIVE.max_retries == 2
        assert AGGRESSIVE.max_retries == 5
        assert API_RETRY.max_retries == 3


class TestCircuitBreaker:

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False

    def test_success_resets_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_status_dict(self):
        cb = CircuitBreaker()
        status = cb.status()
        assert "state" in status
        assert "is_available" in status
        assert status["state"] == "closed"


class TestExecuteWithRetry:

    def test_success_first_try(self):
        result = execute_with_retry(lambda: 42, policy=NO_RETRY)
        assert result.success is True
        assert result.value == 42
        assert result.attempts == 1

    def test_failure_no_retry(self):
        result = execute_with_retry(
            lambda: (_ for _ in ()).throw(ValueError("fail")),
            policy=NO_RETRY,
        )
        assert result.success is False
        assert result.attempts == 1

    def test_retry_then_success(self):
        call_count = 0
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = execute_with_retry(
            fn,
            policy=RetryPolicy(max_retries=3, base_delay_ms=1),
            sleep_fn=lambda _: None,
        )
        assert result.success is True
        assert result.value == "ok"
        assert result.attempts == 3

    def test_circuit_open_rejects(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()

        result = execute_with_retry(
            lambda: 42,
            policy=API_RETRY,
            circuit=cb,
        )
        assert result.success is False
        assert result.circuit_state == "open"

    def test_summary_format(self):
        result = execute_with_retry(lambda: 42, policy=NO_RETRY)
        summary = result.summary()
        assert "Success" in summary


# ---------------------------------------------------------------------------
# Execution Engine
# ---------------------------------------------------------------------------

SIMPLE_WORKFLOW = '''
workflow "test-engine"

a = Wait {
  duration: 1
}

run: a
'''

PIPELINE_WORKFLOW = '''
workflow "pipeline"

store = StoreData {
  from /workflow/input
  storage: "localStorage"
  key: "result"
}

run: store
'''

FILTER_WORKFLOW = '''
workflow "filter-test"

filter = FilterData {
  from /workflow/users
  where age > 25
  -> /workflow/filtered
}

run: filter
'''


class TestExecutionEngine:

    def test_execute_simple(self):
        workflow = parse(SIMPLE_WORKFLOW)
        engine = ExecutionEngine(retry_policy=NO_RETRY)
        result = engine.execute(workflow)

        assert result.success is True
        assert result.pipeline_log is not None
        assert result.pipeline_log.operation_count == 1

    def test_execute_with_input_data(self):
        workflow = parse(PIPELINE_WORKFLOW)
        engine = ExecutionEngine(
            retry_policy=NO_RETRY,
            input_data={"/workflow/input": {"key": "value"}},
        )
        result = engine.execute(workflow)

        assert result.success is True

    def test_execute_filter_data(self):
        workflow = parse(FILTER_WORKFLOW)
        engine = ExecutionEngine(
            retry_policy=NO_RETRY,
            input_data={"/workflow/users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 20},
                {"name": "Charlie", "age": 35},
            ]},
        )
        result = engine.execute(workflow)

        assert result.success is True
        filtered = result.data.get("/workflow/filtered")
        assert isinstance(filtered, list)
        assert len(filtered) == 2  # Alice and Charlie

    def test_execution_context(self):
        ctx = ExecutionContext()
        ctx.set("/a", 42)
        assert ctx.get("/a") == 42
        assert ctx.get("/b") is None

    def test_handler_registry(self):
        assert get_handler("Wait") is not None
        assert get_handler("StoreData") is not None
        assert get_handler("FilterData") is not None
        assert get_handler("NonExistent") is None

    def test_execution_result_summary(self):
        workflow = parse(SIMPLE_WORKFLOW)
        engine = ExecutionEngine(retry_policy=NO_RETRY)
        result = engine.execute(workflow)
        summary = result.summary()
        assert "test-engine" in summary


# ---------------------------------------------------------------------------
# Webhook Server
# ---------------------------------------------------------------------------

class TestWebhookServer:

    def test_webhook_health_check(self):
        source = 'workflow "test"\n\na = Wait { duration: 1 }\nrun: a\n'
        server = WebhookServer(source, port=0)
        server.start_background()

        try:
            # Get actual port
            actual_port = server._server.server_address[1]
            url = f"http://127.0.0.1:{actual_port}"

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                assert data["status"] == "ok"
        finally:
            server.stop()

    def test_webhook_execute(self):
        source = 'workflow "test"\n\na = Wait { duration: 1 }\nrun: a\n'
        server = WebhookServer(source, port=0)
        server.start_background()

        try:
            actual_port = server._server.server_address[1]
            url = f"http://127.0.0.1:{actual_port}"

            body = json.dumps({}).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                assert data["success"] is True
        finally:
            server.stop()

    def test_webhook_invalid_json(self):
        source = 'workflow "test"\n\na = Wait { duration: 1 }\nrun: a\n'
        server = WebhookServer(source, port=0)
        server.start_background()

        try:
            actual_port = server._server.server_address[1]
            url = f"http://127.0.0.1:{actual_port}"

            body = b"not json"
            req = urllib.request.Request(url, data=body, method="POST")
            try:
                urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            server.stop()
