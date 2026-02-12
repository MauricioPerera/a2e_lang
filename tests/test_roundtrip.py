"""End-to-end roundtrip tests: .a2e source -> parse -> validate -> compile -> valid JSONL."""

import json

import pytest

from a2e_lang.compiler import Compiler
from a2e_lang.parser import parse
from a2e_lang.validator import Validator


def roundtrip(source: str) -> dict:
    """Parse, validate, compile, and return the parsed JSONL as dicts."""
    workflow = parse(source)

    errors = Validator().validate(workflow)
    assert errors == [], f"Validation errors: {errors}"

    jsonl = Compiler().compile(workflow)
    lines = jsonl.strip().split("\n")
    assert len(lines) == 2, f"Expected 2 JSONL lines, got {len(lines)}"

    op_update = json.loads(lines[0])
    begin_exec = json.loads(lines[1])
    return {
        "operationUpdate": op_update["operationUpdate"],
        "beginExecution": begin_exec["beginExecution"],
    }


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------

class TestRoundtrip:

    def test_minimal_workflow(self):
        r = roundtrip('''
        workflow "minimal"
        op = ApiCall {
            method: "GET"
            url: "https://api.example.com"
            -> /workflow/result
        }
        ''')
        ops = r["operationUpdate"]["operations"]
        assert len(ops) == 1
        assert ops[0]["id"] == "op"
        assert "ApiCall" in ops[0]["operation"]
        assert r["beginExecution"]["root"] == "op"

    def test_two_step_pipeline(self):
        r = roundtrip('''
        workflow "pipeline"

        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            -> /workflow/users
        }

        filter = FilterData {
            from /workflow/users
            where active == true
            -> /workflow/filtered
        }

        run: fetch -> filter
        ''')
        ops = r["operationUpdate"]["operations"]
        assert len(ops) == 2
        assert ops[0]["id"] == "fetch"
        assert ops[1]["id"] == "filter"

        # Verify filter structure
        fd = ops[1]["operation"]["FilterData"]
        assert fd["inputPath"] == "/workflow/users"
        assert fd["outputPath"] == "/workflow/filtered"
        assert fd["conditions"][0]["field"] == "active"
        assert fd["conditions"][0]["operator"] == "=="
        assert fd["conditions"][0]["value"] is True

        assert r["beginExecution"]["root"] == "fetch"

    def test_credential_roundtrip(self):
        r = roundtrip('''
        workflow "auth"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/secure"
            headers: { Authorization: credential("my-api-key") }
            -> /workflow/data
        }
        ''')
        ops = r["operationUpdate"]["operations"]
        headers = ops[0]["operation"]["ApiCall"]["headers"]
        assert headers["Authorization"] == {"credentialRef": {"id": "my-api-key"}}

    def test_conditional_roundtrip(self):
        r = roundtrip('''
        workflow "branching"

        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/data"
            -> /workflow/data
        }

        process = TransformData {
            from /workflow/data
            transform: "sort"
            -> /workflow/sorted
        }

        fallback = StoreData {
            from /workflow/data
            storage: "localStorage"
            key: "fallback"
        }

        check = Conditional {
            if /workflow/data > 0
            then process
            else fallback
        }

        run: fetch -> check
        ''')
        ops = r["operationUpdate"]["operations"]
        cond = next(op for op in ops if op["id"] == "check")
        c = cond["operation"]["Conditional"]
        assert c["condition"]["path"] == "/workflow/data"
        assert c["condition"]["operator"] == ">"
        assert c["condition"]["value"] == 0
        assert c["ifTrue"] == "process"
        assert c["ifFalse"] == "fallback"

    def test_merge_roundtrip(self):
        r = roundtrip('''
        workflow "merge-test"

        a = ApiCall { method: "GET" url: "https://a.com" -> /workflow/a }
        b = ApiCall { method: "GET" url: "https://b.com" -> /workflow/b }

        combined = MergeData {
            sources: [/workflow/a, /workflow/b]
            strategy: "concat"
            -> /workflow/combined
        }

        run: a -> b -> combined
        ''')
        ops = r["operationUpdate"]["operations"]
        merge = next(op for op in ops if op["id"] == "combined")
        m = merge["operation"]["MergeData"]
        assert m["sources"] == ["/workflow/a", "/workflow/b"]
        assert m["strategy"] == "concat"
        assert m["outputPath"] == "/workflow/combined"

    def test_loop_roundtrip(self):
        r = roundtrip('''
        workflow "loop-test"

        fetch = ApiCall { method: "GET" url: "https://api.com/items" -> /workflow/items }

        process = Loop {
            from /workflow/items
            operations: [fetch]
            -> /workflow/results
        }
        ''')
        ops = r["operationUpdate"]["operations"]
        loop = next(op for op in ops if op["id"] == "process")
        l = loop["operation"]["Loop"]
        assert l["inputPath"] == "/workflow/items"
        assert l["operations"] == ["fetch"]
        assert l["outputPath"] == "/workflow/results"

    def test_complex_workflow_roundtrip(self):
        """Full workflow matching A2E example_workflow.jsonl structure."""
        r = roundtrip('''
        workflow "user-api-workflow"

        # Fetch users from API
        fetch_users = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            headers: { Authorization: credential("api-token") }
            -> /workflow/api-response
        }

        # Extract user array
        extract_users = TransformData {
            from /workflow/api-response
            transform: "select"
            config: { field: "data.users" }
            -> /workflow/users
        }

        # Filter active users with enough points
        filter_active = FilterData {
            from /workflow/users
            where points > 100, status == "active"
            -> /workflow/filtered-users
        }

        # Store results
        store_result = StoreData {
            from /workflow/filtered-users
            storage: "localStorage"
            key: "active-users"
        }

        # Store empty indicator
        log_empty = StoreData {
            from /workflow/filtered-users
            storage: "localStorage"
            key: "empty-result"
        }

        # Branch based on results
        check_count = Conditional {
            if /workflow/filtered-users > 0
            then store_result
            else log_empty
        }

        run: fetch_users -> extract_users -> filter_active -> check_count
        ''')
        ops = r["operationUpdate"]["operations"]
        assert len(ops) == 6

        # Verify the workflow matches A2E structure
        api_call = next(op for op in ops if op["id"] == "fetch_users")
        assert api_call["operation"]["ApiCall"]["method"] == "GET"
        assert api_call["operation"]["ApiCall"]["outputPath"] == "/workflow/api-response"

        filter_op = next(op for op in ops if op["id"] == "filter_active")
        fd = filter_op["operation"]["FilterData"]
        assert fd["inputPath"] == "/workflow/users"
        assert len(fd["conditions"]) == 2

        assert r["beginExecution"]["root"] == "fetch_users"

    def test_workflow_id_preserved(self):
        r = roundtrip('''
        workflow "my-special-workflow-123"
        op = Wait { duration: 100 }
        ''')
        assert r["operationUpdate"]["workflowId"] == "my-special-workflow-123"
        assert r["beginExecution"]["workflowId"] == "my-special-workflow-123"
