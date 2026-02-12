"""Tests for a2e_lang.validator."""

import pytest

from a2e_lang.parser import parse
from a2e_lang.validator import Validator


@pytest.fixture
def v():
    return Validator()


# ---------------------------------------------------------------------------
# Valid workflows
# ---------------------------------------------------------------------------

class TestValidWorkflows:

    def test_minimal_valid(self, v):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        assert v.validate(w) == []

    def test_full_workflow_valid(self, v, full_ast):
        errors = v.validate(full_ast)
        assert errors == []

    def test_simple_workflow_valid(self, v, simple_ast):
        assert v.validate(simple_ast) == []


# ---------------------------------------------------------------------------
# Duplicate IDs
# ---------------------------------------------------------------------------

class TestDuplicateIds:

    def test_duplicate_operation_id(self, v):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" -> /workflow/a }
        op = ApiCall { method: "POST" url: "https://y.com" -> /workflow/b }
        ''')
        errors = v.validate(w)
        assert any("Duplicate operation ID 'op'" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# Unknown operation types
# ---------------------------------------------------------------------------

class TestOpTypes:

    def test_unknown_op_type(self, v):
        w = parse('''
        workflow "t"
        op = UnknownThing { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("Unknown operation type 'UnknownThing'" in str(e) for e in errors)

    def test_all_valid_types(self, v):
        # Each valid type should not produce a "unknown type" error
        valid_types = [
            "ApiCall", "FilterData", "TransformData", "Conditional",
            "Loop", "StoreData", "Wait", "MergeData",
            "GetCurrentDateTime", "ConvertTimezone", "DateCalculation",
            "FormatText", "ExtractText", "ValidateData", "Calculate",
            "EncodeDecode",
        ]
        for op_type in valid_types:
            # Minimal valid syntax for type check only
            w = parse(f'workflow "t"\nop = {op_type} {{}}')
            type_errors = [e for e in v.validate(w) if "Unknown operation type" in str(e)]
            assert type_errors == [], f"Type '{op_type}' incorrectly flagged as unknown"


# ---------------------------------------------------------------------------
# Required properties
# ---------------------------------------------------------------------------

class TestRequiredProperties:

    def test_api_call_missing_method(self, v):
        w = parse('''
        workflow "t"
        op = ApiCall { url: "https://x.com" -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("missing required properties" in str(e) and "method" in str(e) for e in errors)

    def test_api_call_missing_url(self, v):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("missing required properties" in str(e) and "url" in str(e) for e in errors)

    def test_wait_missing_duration(self, v):
        w = parse('''
        workflow "t"
        op = Wait {}
        ''')
        errors = v.validate(w)
        assert any("missing required properties" in str(e) and "duration" in str(e) for e in errors)

    def test_merge_missing_sources(self, v):
        w = parse('''
        workflow "t"
        op = MergeData { strategy: "concat" -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("missing required properties" in str(e) and "sources" in str(e) for e in errors)

    def test_store_missing_key(self, v):
        w = parse('''
        workflow "t"
        op = StoreData { from /workflow/data storage: "localStorage" }
        ''')
        errors = v.validate(w)
        assert any("missing required properties" in str(e) and "key" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# Required clauses (from, ->, where, if)
# ---------------------------------------------------------------------------

class TestRequiredClauses:

    def test_filter_missing_from(self, v):
        w = parse('''
        workflow "t"
        op = FilterData { where x == 1 -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("requires a 'from' clause" in str(e) for e in errors)

    def test_filter_missing_where(self, v):
        w = parse('''
        workflow "t"
        op = FilterData { from /workflow/data -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("requires a 'where' clause" in str(e) for e in errors)

    def test_api_call_missing_output(self, v):
        w = parse('''
        workflow "t"
        op = ApiCall { method: "GET" url: "https://x.com" }
        ''')
        errors = v.validate(w)
        assert any("requires an output arrow" in str(e) for e in errors)

    def test_conditional_missing_if(self, v):
        w = parse('''
        workflow "t"
        op = Conditional { }
        ''')
        errors = v.validate(w)
        assert any("requires an 'if' clause" in str(e) for e in errors)

    def test_transform_missing_from(self, v):
        w = parse('''
        workflow "t"
        op = TransformData { transform: "sort" -> /workflow/out }
        ''')
        errors = v.validate(w)
        assert any("requires a 'from' clause" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# Conditional targets
# ---------------------------------------------------------------------------

class TestConditionalTargets:

    def test_invalid_then_target(self, v):
        w = parse('''
        workflow "t"
        check = Conditional {
            if /workflow/data > 0
            then nonexistent
        }
        ''')
        errors = v.validate(w)
        assert any("'then' target 'nonexistent' not found" in str(e) for e in errors)

    def test_invalid_else_target(self, v):
        w = parse('''
        workflow "t"
        valid_op = Wait { duration: 100 }
        check = Conditional {
            if /workflow/data > 0
            then valid_op
            else nonexistent
        }
        ''')
        errors = v.validate(w)
        assert any("'else' target 'nonexistent' not found" in str(e) for e in errors)

    def test_valid_targets(self, v):
        w = parse('''
        workflow "t"
        op_a = Wait { duration: 100 }
        op_b = Wait { duration: 200 }
        check = Conditional {
            if /workflow/data > 0
            then op_a
            else op_b
        }
        ''')
        target_errors = [e for e in v.validate(w) if "target" in str(e) and "not found" in str(e)]
        assert target_errors == []


# ---------------------------------------------------------------------------
# Execution order
# ---------------------------------------------------------------------------

class TestExecutionOrder:

    def test_invalid_run_reference(self, v):
        w = parse('''
        workflow "t"
        op = Wait { duration: 100 }
        run: op -> nonexistent
        ''')
        errors = v.validate(w)
        assert any("unknown operation 'nonexistent'" in str(e) for e in errors)

    def test_valid_run(self, v):
        w = parse('''
        workflow "t"
        a = Wait { duration: 100 }
        b = Wait { duration: 200 }
        run: a -> b
        ''')
        run_errors = [e for e in v.validate(w) if "unknown operation" in str(e)]
        assert run_errors == []


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:

    def test_no_cycle(self, v):
        w = parse('''
        workflow "t"
        a = ApiCall { method: "GET" url: "https://x.com" -> /workflow/a }
        b = FilterData { from /workflow/a where x == 1 -> /workflow/b }
        ''')
        cycle_errors = [e for e in v.validate(w) if "Cycle" in str(e)]
        assert cycle_errors == []

    def test_self_referencing_no_false_positive(self, v):
        # An operation that reads from a path it also writes shouldn't be a cycle
        w = parse('''
        workflow "t"
        op = TransformData { from /workflow/data transform: "sort" -> /workflow/data }
        ''')
        cycle_errors = [e for e in v.validate(w) if "Cycle" in str(e)]
        assert cycle_errors == []
