"""Tests for a2e_lang.parser."""

import pytest

from a2e_lang.ast_nodes import (
    ArrayValue,
    Condition,
    Credential,
    IfClause,
    ObjectValue,
    Operation,
    Path,
    Property,
    Workflow,
)
from a2e_lang.errors import ParseError
from a2e_lang.parser import parse


# ---------------------------------------------------------------------------
# Workflow declaration
# ---------------------------------------------------------------------------

class TestWorkflowDecl:

    def test_parse_workflow_name(self):
        w = parse('workflow "my-workflow"')
        assert w.name == "my-workflow"

    def test_parse_workflow_name_with_spaces(self):
        w = parse('workflow "hello world"')
        assert w.name == "hello world"

    def test_empty_workflow(self):
        w = parse('workflow "empty"')
        assert w.operations == ()
        assert w.execution_order is None


# ---------------------------------------------------------------------------
# Operation definitions
# ---------------------------------------------------------------------------

class TestOperationDef:

    def test_simple_operation(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "GET"
            url: "https://example.com"
            -> /workflow/data
        }
        ''')
        assert len(w.operations) == 1
        op = w.operations[0]
        assert op.id == "fetch"
        assert op.op_type == "ApiCall"
        assert op.output_path == "/workflow/data"

    def test_operation_with_from(self):
        w = parse('''
        workflow "t"
        f = FilterData {
            from /workflow/users
            where status == "active"
            -> /workflow/filtered
        }
        ''')
        op = w.operations[0]
        assert op.input_path == "/workflow/users"

    def test_operation_with_where(self):
        w = parse('''
        workflow "t"
        f = FilterData {
            from /workflow/data
            where points > 100, status == "active"
            -> /workflow/out
        }
        ''')
        op = w.operations[0]
        assert len(op.conditions) == 2
        assert op.conditions[0].field == "points"
        assert op.conditions[0].operator == ">"
        assert op.conditions[0].value == 100
        assert op.conditions[1].field == "status"
        assert op.conditions[1].operator == "=="
        assert op.conditions[1].value == "active"

    def test_operation_with_if_then_else(self):
        w = parse('''
        workflow "t"
        check = Conditional {
            if /workflow/data > 0
            then process
            else fallback
        }
        ''')
        op = w.operations[0]
        assert op.if_clause is not None
        assert op.if_clause.path == "/workflow/data"
        assert op.if_clause.operator == ">"
        assert op.if_clause.value == 0
        assert op.if_clause.if_true == ("process",)
        assert op.if_clause.if_false == ("fallback",)

    def test_conditional_without_else(self):
        w = parse('''
        workflow "t"
        check = Conditional {
            if /workflow/data > 0
            then process
        }
        ''')
        op = w.operations[0]
        assert op.if_clause.if_false is None

    def test_multiple_operations(self):
        w = parse('''
        workflow "t"
        a = ApiCall {
            method: "GET"
            url: "https://example.com/a"
            -> /workflow/a
        }
        b = ApiCall {
            method: "POST"
            url: "https://example.com/b"
            -> /workflow/b
        }
        ''')
        assert len(w.operations) == 2
        assert w.operations[0].id == "a"
        assert w.operations[1].id == "b"


# ---------------------------------------------------------------------------
# Properties and values
# ---------------------------------------------------------------------------

class TestProperties:

    def test_string_value(self):
        w = parse('''
        workflow "t"
        op = Wait {
            duration: 5000
        }
        ''')
        prop = w.operations[0].properties[0]
        assert prop.key == "duration"
        assert prop.value == 5000

    def test_number_int(self):
        w = parse('''
        workflow "t"
        op = Wait { duration: 42 }
        ''')
        assert w.operations[0].properties[0].value == 42
        assert isinstance(w.operations[0].properties[0].value, int)

    def test_number_float(self):
        w = parse('''
        workflow "t"
        op = Wait { duration: 3.14 }
        ''')
        assert w.operations[0].properties[0].value == 3.14
        assert isinstance(w.operations[0].properties[0].value, float)

    def test_boolean_true(self):
        w = parse('''
        workflow "t"
        op = ExtractText {
            from /workflow/data
            pattern: "[0-9]+"
            extractAll: true
            -> /workflow/out
        }
        ''')
        extract_all = [p for p in w.operations[0].properties if p.key == "extractAll"][0]
        assert extract_all.value is True

    def test_boolean_false(self):
        w = parse('''
        workflow "t"
        op = ExtractText {
            from /workflow/data
            pattern: "[0-9]+"
            extractAll: false
            -> /workflow/out
        }
        ''')
        extract_all = [p for p in w.operations[0].properties if p.key == "extractAll"][0]
        assert extract_all.value is False

    def test_null_value(self):
        w = parse('''
        workflow "t"
        op = ApiCall {
            method: "GET"
            url: "https://example.com"
            body: null
            -> /workflow/out
        }
        ''')
        body = [p for p in w.operations[0].properties if p.key == "body"][0]
        assert body.value is None

    def test_path_value(self):
        w = parse('''
        workflow "t"
        op = MergeData {
            sources: [/workflow/a, /workflow/b]
            strategy: "concat"
            -> /workflow/merged
        }
        ''')
        sources = [p for p in w.operations[0].properties if p.key == "sources"][0]
        assert isinstance(sources.value, ArrayValue)
        assert len(sources.value.items) == 2
        assert isinstance(sources.value.items[0], Path)
        assert sources.value.items[0].raw == "/workflow/a"

    def test_credential_value(self):
        w = parse('''
        workflow "t"
        op = ApiCall {
            method: "GET"
            url: "https://example.com"
            headers: { Authorization: credential("my-key") }
            -> /workflow/out
        }
        ''')
        headers = [p for p in w.operations[0].properties if p.key == "headers"][0]
        assert isinstance(headers.value, ObjectValue)
        auth = headers.value.properties[0]
        assert isinstance(auth.value, Credential)
        assert auth.value.id == "my-key"

    def test_object_value(self):
        w = parse('''
        workflow "t"
        op = TransformData {
            from /workflow/data
            transform: "sort"
            config: { field: "name", order: "asc" }
            -> /workflow/sorted
        }
        ''')
        config = [p for p in w.operations[0].properties if p.key == "config"][0]
        assert isinstance(config.value, ObjectValue)
        assert len(config.value.properties) == 2
        assert config.value.properties[0].key == "field"
        assert config.value.properties[0].value == "name"

    def test_array_value(self):
        w = parse('''
        workflow "t"
        op = Loop {
            from /workflow/items
            operations: [process, transform]
            -> /workflow/results
        }
        ''')
        ops = [p for p in w.operations[0].properties if p.key == "operations"][0]
        assert isinstance(ops.value, ArrayValue)
        assert len(ops.value.items) == 2
        assert ops.value.items[0] == "process"
        assert ops.value.items[1] == "transform"

    def test_ident_value_unquoted(self):
        w = parse('''
        workflow "t"
        op = StoreData {
            from /workflow/data
            storage: localStorage
            key: "my-key"
        }
        ''')
        storage = [p for p in w.operations[0].properties if p.key == "storage"][0]
        assert storage.value == "localStorage"

    def test_quoted_property_key(self):
        w = parse('''
        workflow "t"
        op = ApiCall {
            method: "GET"
            url: "https://example.com"
            headers: { "Content-Type": "application/json" }
            -> /workflow/out
        }
        ''')
        headers = [p for p in w.operations[0].properties if p.key == "headers"][0]
        ct = headers.value.properties[0]
        assert ct.key == "Content-Type"
        assert ct.value == "application/json"


# ---------------------------------------------------------------------------
# Run declaration
# ---------------------------------------------------------------------------

class TestRunDecl:

    def test_single_operation(self):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        run: op
        ''')
        assert w.execution_order == ("op",)

    def test_chain(self):
        w = parse('''
        workflow "t"
        a = ApiCall { method: "GET" url: "https://x.com" -> /workflow/a }
        b = ApiCall { method: "GET" url: "https://x.com" -> /workflow/b }
        run: a -> b
        ''')
        assert w.execution_order == ("a", "b")

    def test_no_run(self):
        w = parse('''
        workflow "t"
        op = Wait { duration: 100 }
        ''')
        assert w.execution_order is None


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class TestComments:

    def test_comments_ignored(self):
        w = parse('''
        # This is a comment
        workflow "t"
        # Another comment
        op = Wait { duration: 100 }
        # End comment
        ''')
        assert w.name == "t"
        assert len(w.operations) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestParseErrors:

    def test_missing_workflow(self):
        with pytest.raises(ParseError):
            parse('op = Wait { duration: 100 }')

    def test_unclosed_brace(self):
        with pytest.raises(ParseError):
            parse('workflow "t"\nop = Wait { duration: 100')

    def test_invalid_syntax(self):
        with pytest.raises(ParseError):
            parse('workflow "t"\n!!invalid!!')


# ---------------------------------------------------------------------------
# All 16 operation types parse
# ---------------------------------------------------------------------------

class TestAllOperationTypes:

    def test_api_call(self):
        w = parse('workflow "t"\nop = ApiCall { method: "GET" url: "https://x.com" -> /workflow/r }')
        assert w.operations[0].op_type == "ApiCall"

    def test_filter_data(self):
        w = parse('workflow "t"\nop = FilterData { from /workflow/d where x == 1 -> /workflow/r }')
        assert w.operations[0].op_type == "FilterData"

    def test_transform_data(self):
        w = parse('workflow "t"\nop = TransformData { from /workflow/d transform: "sort" -> /workflow/r }')
        assert w.operations[0].op_type == "TransformData"

    def test_conditional(self):
        w = parse('workflow "t"\na = Wait { duration: 1 }\nop = Conditional { if /workflow/d > 0 then a }')
        assert w.operations[1].op_type == "Conditional"

    def test_loop(self):
        w = parse('workflow "t"\nop = Loop { from /workflow/d operations: [x] -> /workflow/r }')
        assert w.operations[0].op_type == "Loop"

    def test_store_data(self):
        w = parse('workflow "t"\nop = StoreData { from /workflow/d storage: "localStorage" key: "k" }')
        assert w.operations[0].op_type == "StoreData"

    def test_wait(self):
        w = parse('workflow "t"\nop = Wait { duration: 5000 }')
        assert w.operations[0].op_type == "Wait"

    def test_merge_data(self):
        w = parse('workflow "t"\nop = MergeData { sources: [/workflow/a, /workflow/b] strategy: "concat" -> /workflow/r }')
        assert w.operations[0].op_type == "MergeData"

    def test_get_current_date_time(self):
        w = parse('workflow "t"\nop = GetCurrentDateTime { timezone: "UTC" -> /workflow/r }')
        assert w.operations[0].op_type == "GetCurrentDateTime"

    def test_convert_timezone(self):
        w = parse('workflow "t"\nop = ConvertTimezone { from /workflow/d toTimezone: "US/Pacific" -> /workflow/r }')
        assert w.operations[0].op_type == "ConvertTimezone"

    def test_date_calculation(self):
        w = parse('workflow "t"\nop = DateCalculation { from /workflow/d operation: "add" days: 7 -> /workflow/r }')
        assert w.operations[0].op_type == "DateCalculation"

    def test_format_text(self):
        w = parse('workflow "t"\nop = FormatText { from /workflow/d format: "upper" -> /workflow/r }')
        assert w.operations[0].op_type == "FormatText"

    def test_extract_text(self):
        w = parse('workflow "t"\nop = ExtractText { from /workflow/d pattern: "[0-9]+" -> /workflow/r }')
        assert w.operations[0].op_type == "ExtractText"

    def test_validate_data(self):
        w = parse('workflow "t"\nop = ValidateData { from /workflow/d validationType: "email" -> /workflow/r }')
        assert w.operations[0].op_type == "ValidateData"

    def test_calculate(self):
        w = parse('workflow "t"\nop = Calculate { from /workflow/d operation: "sum" -> /workflow/r }')
        assert w.operations[0].op_type == "Calculate"

    def test_encode_decode(self):
        w = parse('workflow "t"\nop = EncodeDecode { from /workflow/d operation: "encode" encoding: "base64" -> /workflow/r }')
        assert w.operations[0].op_type == "EncodeDecode"
