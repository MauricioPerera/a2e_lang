"""Tests for a2e_lang.compiler_spec (official A2E protocol format)."""

import json

import pytest

from a2e_lang.compiler_spec import SpecCompiler
from a2e_lang.parser import parse


@pytest.fixture
def sc():
    return SpecCompiler()


# ---------------------------------------------------------------------------
# Message structure
# ---------------------------------------------------------------------------

class TestMessageStructure:

    def test_one_line_per_operation_plus_begin(self, sc):
        w = parse('''
        workflow "t"
        a = ApiCall { method: "GET" url: "https://x.com" -> /workflow/a }
        b = Wait { duration: 100 }
        ''')
        result = sc.compile(w)
        lines = result.strip().split("\n")
        # 2 operations + 1 beginExecution = 3 lines
        assert len(lines) == 3

    def test_each_operation_line_has_type_field(self, sc):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = sc.compile(w)
        lines = result.strip().split("\n")
        for line in lines:
            data = json.loads(line)
            assert "type" in data

    def test_operation_lines_have_operationUpdate_type(self, sc):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = sc.compile(w)
        line1 = json.loads(result.split("\n")[0])
        assert line1["type"] == "operationUpdate"

    def test_operation_lines_have_operationId(self, sc):
        w = parse('''
        workflow "t"
        my_fetch = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = sc.compile(w)
        line1 = json.loads(result.split("\n")[0])
        assert line1["operationId"] == "my_fetch"

    def test_last_line_is_begin_execution(self, sc):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = sc.compile(w)
        last = json.loads(result.strip().split("\n")[-1])
        assert last["type"] == "beginExecution"


# ---------------------------------------------------------------------------
# beginExecution format
# ---------------------------------------------------------------------------

class TestBeginExecution:

    def test_has_executionId(self, sc):
        w = parse('''
        workflow "my-workflow"
        op = Wait { duration: 100 }
        ''')
        result = sc.compile(w)
        last = json.loads(result.strip().split("\n")[-1])
        assert last["executionId"] == "my-workflow"

    def test_has_operationOrder_array(self, sc):
        w = parse('''
        workflow "t"
        a = Wait { duration: 100 }
        b = Wait { duration: 200 }
        run: b -> a
        ''')
        result = sc.compile(w)
        last = json.loads(result.strip().split("\n")[-1])
        assert last["operationOrder"] == ["b", "a"]

    def test_operationOrder_defaults_to_definition_order(self, sc):
        w = parse('''
        workflow "t"
        first = Wait { duration: 100 }
        second = Wait { duration: 200 }
        ''')
        result = sc.compile(w)
        last = json.loads(result.strip().split("\n")[-1])
        assert last["operationOrder"] == ["first", "second"]


# ---------------------------------------------------------------------------
# Operation content (matches existing compiler logic)
# ---------------------------------------------------------------------------

class TestOperationContent:

    def test_api_call_content(self, sc):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            -> /workflow/users
        }
        ''')
        result = sc.compile(w)
        line = json.loads(result.split("\n")[0])
        api = line["operation"]["ApiCall"]
        assert api["method"] == "GET"
        assert api["url"] == "https://api.example.com/users"
        assert api["outputPath"] == "/workflow/users"

    def test_filter_conditions(self, sc):
        w = parse('''
        workflow "t"
        f = FilterData {
            from /workflow/users
            where status == "active", points > 100
            -> /workflow/filtered
        }
        ''')
        result = sc.compile(w)
        line = json.loads(result.split("\n")[0])
        fd = line["operation"]["FilterData"]
        assert fd["inputPath"] == "/workflow/users"
        assert len(fd["conditions"]) == 2
        assert fd["conditions"][0] == {"field": "status", "operator": "==", "value": "active"}

    def test_credential_ref(self, sc):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com"
            headers: { Authorization: credential("my-token") }
            -> /workflow/out
        }
        ''')
        result = sc.compile(w)
        line = json.loads(result.split("\n")[0])
        headers = line["operation"]["ApiCall"]["headers"]
        assert headers["Authorization"] == {"credentialRef": {"id": "my-token"}}

    def test_conditional_ifTrue_is_array(self, sc):
        """Spec format: ifTrue/ifFalse are always arrays."""
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
        result = sc.compile(w)
        lines = result.strip().split("\n")
        cond_line = json.loads(lines[2])  # third operation
        cond = cond_line["operation"]["Conditional"]
        assert cond["ifTrue"] == ["a"]
        assert cond["ifFalse"] == ["b"]


# ---------------------------------------------------------------------------
# Pretty print
# ---------------------------------------------------------------------------

class TestPrettyPrint:

    def test_pretty_produces_valid_json_blocks(self, sc):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = sc.compile_pretty(w)
        blocks = result.split("\n\n")
        assert len(blocks) == 2
        for block in blocks:
            json.loads(block)  # Should not raise


# ---------------------------------------------------------------------------
# Full roundtrip with spec format
# ---------------------------------------------------------------------------

class TestSpecRoundtrip:

    def test_full_pipeline(self, sc):
        w = parse('''
        workflow "user-api-workflow"

        fetch_users = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            headers: { Authorization: credential("api-token") }
            -> /workflow/users
        }

        filter_active = FilterData {
            from /workflow/users
            where status == "active"
            -> /workflow/filtered
        }

        store = StoreData {
            from /workflow/filtered
            storage: "localStorage"
            key: "results"
        }

        run: fetch_users -> filter_active -> store
        ''')
        result = sc.compile(w)
        lines = result.strip().split("\n")
        assert len(lines) == 4  # 3 ops + 1 beginExecution

        # Verify each line is valid JSON with type field
        for line in lines:
            data = json.loads(line)
            assert "type" in data

        # Verify operationIds
        op_ids = [json.loads(l)["operationId"] for l in lines[:-1]]
        assert op_ids == ["fetch_users", "filter_active", "store"]

        # Verify execution
        begin = json.loads(lines[-1])
        assert begin["type"] == "beginExecution"
        assert begin["executionId"] == "user-api-workflow"
        assert begin["operationOrder"] == ["fetch_users", "filter_active", "store"]
