"""Tests for the LSP server functionality (unit tests, no pygls required)."""

import pytest

from a2e_lang.parser import parse
from a2e_lang.validator import Validator


class TestLspValidation:
    """Test the validation logic that the LSP uses."""

    def test_valid_document_no_errors(self):
        source = '''
        workflow "test"
        a = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        '''
        workflow = parse(source)
        errors = Validator().validate(workflow)
        assert errors == []

    def test_invalid_document_reports_errors(self):
        source = '''
        workflow "test"
        a = UnknownType { method: "GET" }
        '''
        workflow = parse(source)
        errors = Validator().validate(workflow)
        assert len(errors) > 0
        assert any("Unknown operation type" in str(e) for e in errors)

    def test_missing_required_property(self):
        source = '''
        workflow "test"
        a = ApiCall { url: "https://x.com" -> /workflow/out }
        '''
        workflow = parse(source)
        errors = Validator().validate(workflow)
        assert any("method" in str(e) for e in errors)


class TestLspCompletionData:
    """Test that completion data covers all operation types."""

    def test_all_op_types_have_descriptions(self):
        # Import here to avoid requiring pygls for test collection
        try:
            from a2e_lang.lsp import OPERATION_DESCRIPTIONS
        except ImportError:
            pytest.skip("pygls not installed")
        from a2e_lang.validator import VALID_OP_TYPES

        # All 8 core types should have descriptions
        core_types = {"ApiCall", "FilterData", "TransformData", "Conditional",
                      "Loop", "StoreData", "Wait", "MergeData"}
        for op_type in core_types:
            assert op_type in OPERATION_DESCRIPTIONS, f"Missing description for {op_type}"

    def test_keyword_completions_exist(self):
        try:
            from a2e_lang.lsp import KEYWORD_COMPLETIONS
        except ImportError:
            pytest.skip("pygls not installed")
        keywords = {k for k, _ in KEYWORD_COMPLETIONS}
        assert "workflow" in keywords
        assert "run" in keywords
        assert "from" in keywords
        assert "where" in keywords
        assert "if" in keywords
        assert "credential" in keywords
