"""Webhook support: trigger workflow execution via HTTP.

Provides a lightweight HTTP server that accepts POST requests
to trigger a2e-lang workflow execution. Built on stdlib only
(http.server), no external dependencies required.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from .engine import ExecutionEngine, ExecutionResult
from .parser import parse
from .validator import Validator


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for webhook-triggered workflow execution."""

    # Set by WebhookServer before starting
    workflow_source: str = ""
    retry_policy: Any = None

    def do_POST(self):
        """Handle POST request to trigger workflow execution."""
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else ""

        # Parse input data
        input_data = {}
        if body:
            try:
                input_data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON body"})
                return

        try:
            # Parse and validate workflow
            workflow = parse(self.workflow_source)
            errors = Validator().validate(workflow)
            if errors:
                self._send_json(422, {
                    "error": "Validation failed",
                    "details": [str(e) for e in errors],
                })
                return

            # Execute workflow
            engine = ExecutionEngine(
                retry_policy=self.retry_policy,
                input_data=input_data,
            )
            result = engine.execute(workflow)

            # Return result
            response = {
                "success": result.success,
                "data": _safe_serialize(result.data),
            }
            if result.pipeline_log:
                response["log"] = result.pipeline_log.to_dict()
            if result.error:
                response["error"] = result.error

            status = 200 if result.success else 500
            self._send_json(status, response)

        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_GET(self):
        """Health check endpoint."""
        self._send_json(200, {"status": "ok", "endpoint": "a2e-lang webhook"})

    def _send_json(self, status: int, data: dict) -> None:
        """Send a JSON response."""
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Override to suppress default access logs."""
        pass


class WebhookServer:
    """Webhook server for triggering workflow execution via HTTP.

    Usage:
        server = WebhookServer("workflow.a2e", port=8080)
        server.start()  # Blocking
        # or
        server.start_background()  # Non-blocking
        server.stop()
    """

    def __init__(
        self,
        workflow_source: str,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        retry_policy: Any = None,
    ):
        self.workflow_source = workflow_source
        self.host = host
        self.port = port
        self.retry_policy = retry_policy
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the webhook server (blocking)."""
        WebhookHandler.workflow_source = self.workflow_source
        WebhookHandler.retry_policy = self.retry_policy

        self._server = HTTPServer((self.host, self.port), WebhookHandler)
        print(f"🌐 Webhook server listening on http://{self.host}:{self.port}")
        print(f"   POST to trigger workflow execution")
        print(f"   GET  for health check")
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Webhook server stopped")
            self._server.shutdown()

    def start_background(self) -> None:
        """Start the webhook server in a background thread."""
        WebhookHandler.workflow_source = self.workflow_source
        WebhookHandler.retry_policy = self.retry_policy

        self._server = HTTPServer((self.host, self.port), WebhookHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the webhook server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def _safe_serialize(obj: Any) -> Any:
    """Make object JSON-safe."""
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
