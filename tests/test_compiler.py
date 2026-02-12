"""Tests for a2e_lang.compiler."""

import json

import pytest

from a2e_lang.compiler import Compiler
from a2e_lang.parser import parse


@pytest.fixture
def c():
    return Compiler()


# ---------------------------------------------------------------------------
# Basic compilation
# ---------------------------------------------------------------------------

class TestBasicCompilation:

    def test_produces_two_jsonl_lines(self, c):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = c.compile(w)
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_first_line_is_operation_update(self, c):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = c.compile(w)
        line1 = json.loads(result.split("\n")[0])
        assert "operationUpdate" in line1
        assert line1["operationUpdate"]["workflowId"] == "t"

    def test_second_line_is_begin_execution(self, c):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = c.compile(w)
        line2 = json.loads(result.split("\n")[1])
        assert "beginExecution" in line2
        assert line2["beginExecution"]["workflowId"] == "t"
        assert line2["beginExecution"]["root"] == "op"

    def test_execution_root_from_run_clause(self, c):
        w = parse('''
        workflow "t"
        a = ApiCall { method: "GET" url: "https://x.com" -> /workflow/a }
        b = Wait { duration: 100 }
        run: b -> a
        ''')
        result = c.compile(w)
        line2 = json.loads(result.split("\n")[1])
        assert line2["beginExecution"]["root"] == "b"


# ---------------------------------------------------------------------------
# ApiCall compilation
# ---------------------------------------------------------------------------

class TestApiCallCompilation:

    def test_basic_api_call(self, c):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            timeout: 30000
            -> /workflow/users
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        api_call = ops[0]["operation"]["ApiCall"]

        assert api_call["method"] == "GET"
        assert api_call["url"] == "https://api.example.com/users"
        assert api_call["timeout"] == 30000
        assert api_call["outputPath"] == "/workflow/users"

    def test_api_call_with_credential_header(self, c):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "POST"
            url: "https://api.example.com/data"
            headers: { Authorization: credential("my-token") }
            -> /workflow/result
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        headers = ops[0]["operation"]["ApiCall"]["headers"]
        assert headers["Authorization"] == {"credentialRef": {"id": "my-token"}}

    def test_api_call_with_body(self, c):
        w = parse('''
        workflow "t"
        post = ApiCall {
            method: "POST"
            url: "https://api.example.com/data"
            body: { name: "test", value: 42 }
            -> /workflow/result
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        body = ops[0]["operation"]["ApiCall"]["body"]
        assert body == {"name": "test", "value": 42}


# ---------------------------------------------------------------------------
# FilterData compilation
# ---------------------------------------------------------------------------

class TestFilterDataCompilation:

    def test_filter_with_conditions(self, c):
        w = parse('''
        workflow "t"
        f = FilterData {
            from /workflow/users
            where status == "active", points > 100
            -> /workflow/filtered
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        filter_op = ops[0]["operation"]["FilterData"]

        assert filter_op["inputPath"] == "/workflow/users"
        assert filter_op["outputPath"] == "/workflow/filtered"
        assert len(filter_op["conditions"]) == 2
        assert filter_op["conditions"][0] == {"field": "status", "operator": "==", "value": "active"}
        assert filter_op["conditions"][1] == {"field": "points", "operator": ">", "value": 100}


# ---------------------------------------------------------------------------
# TransformData compilation
# ---------------------------------------------------------------------------

class TestTransformDataCompilation:

    def test_transform_with_config(self, c):
        w = parse('''
        workflow "t"
        sort = TransformData {
            from /workflow/data
            transform: "sort"
            config: { field: "name", order: "asc" }
            -> /workflow/sorted
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        transform = ops[0]["operation"]["TransformData"]

        assert transform["inputPath"] == "/workflow/data"
        assert transform["transform"] == "sort"
        assert transform["config"] == {"field": "name", "order": "asc"}
        assert transform["outputPath"] == "/workflow/sorted"


# ---------------------------------------------------------------------------
# Conditional compilation
# ---------------------------------------------------------------------------

class TestConditionalCompilation:

    def test_conditional_with_value(self, c):
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        check = Conditional {
            if /workflow/count > 0
            then a
            else b
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        cond = ops[2]["operation"]["Conditional"]

        assert cond["condition"]["path"] == "/workflow/count"
        assert cond["condition"]["operator"] == ">"
        assert cond["condition"]["value"] == 0
        assert cond["ifTrue"] == "a"
        assert cond["ifFalse"] == "b"

    def test_conditional_single_target(self, c):
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        check = Conditional {
            if /workflow/data > 0
            then a
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        cond = ops[1]["operation"]["Conditional"]
        assert cond["ifTrue"] == "a"
        assert "ifFalse" not in cond


# ---------------------------------------------------------------------------
# Other operations
# ---------------------------------------------------------------------------

class TestOtherOperations:

    def test_wait(self, c):
        w = parse('workflow "t"\nop = Wait { duration: 5000 }')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        assert ops[0]["operation"]["Wait"]["duration"] == 5000

    def test_store_data(self, c):
        w = parse('''
        workflow "t"
        op = StoreData {
            from /workflow/data
            storage: "localStorage"
            key: "my-key"
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        store = ops[0]["operation"]["StoreData"]
        assert store["inputPath"] == "/workflow/data"
        assert store["storage"] == "localStorage"
        assert store["key"] == "my-key"

    def test_merge_data(self, c):
        w = parse('''
        workflow "t"
        op = MergeData {
            sources: [/workflow/a, /workflow/b]
            strategy: "deepMerge"
            -> /workflow/merged
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        merge = ops[0]["operation"]["MergeData"]
        assert merge["sources"] == ["/workflow/a", "/workflow/b"]
        assert merge["strategy"] == "deepMerge"
        assert merge["outputPath"] == "/workflow/merged"

    def test_loop(self, c):
        w = parse('''
        workflow "t"
        op = Loop {
            from /workflow/items
            operations: [process]
            -> /workflow/results
        }
        ''')
        result = c.compile(w)
        ops = json.loads(result.split("\n")[0])["operationUpdate"]["operations"]
        loop = ops[0]["operation"]["Loop"]
        assert loop["inputPath"] == "/workflow/items"
        assert loop["operations"] == ["process"]
        assert loop["outputPath"] == "/workflow/results"


# ---------------------------------------------------------------------------
# Pretty print
# ---------------------------------------------------------------------------

class TestPrettyPrint:

    def test_pretty_produces_valid_json(self, c):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = c.compile_pretty(w)
        blocks = result.split("\n\n")
        assert len(blocks) == 2
        json.loads(blocks[0])  # Should not raise
        json.loads(blocks[1])  # Should not raise


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_compile_full_workflow(self, c, full_ast):
        result = c.compile(full_ast)
        lines = result.strip().split("\n")
        assert len(lines) == 2

        line1 = json.loads(lines[0])
        assert line1["operationUpdate"]["workflowId"] == "full-pipeline"
        ops = line1["operationUpdate"]["operations"]
        assert len(ops) == 9  # 9 operations in full_workflow

        # Verify operation IDs
        op_ids = [op["id"] for op in ops]
        assert "fetch_users" in op_ids
        assert "filter_active" in op_ids
        assert "check" in op_ids
        assert "merged" in op_ids

    def test_compile_produces_valid_jsonl(self, c, simple_ast):
        """Every line should be valid JSON."""
        result = c.compile(simple_ast)
        for line in result.strip().split("\n"):
            parsed = json.loads(line)
            assert isinstance(parsed, dict)
