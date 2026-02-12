"""Tests for Phase 2: LLM Optimization features."""

import pytest

from a2e_lang.recovery import recover, parse_with_recovery, RecoveryResult
from a2e_lang.tokens import calculate_budget, TokenBudget
from a2e_lang.prompts import get_template, format_prompt, list_templates, TEMPLATES
from a2e_lang.scoring import score_syntax, SyntaxScore


# ---------------------------------------------------------------------------
# Error Recovery
# ---------------------------------------------------------------------------

class TestRecovery:

    def test_missing_quotes_on_workflow_name(self):
        src = 'workflow my-pipeline\n\na = Wait { duration: 1 }\n'
        result = recover(src)
        assert result.was_modified
        assert 'workflow "my-pipeline"' in result.source
        assert any("quotes" in f.lower() for f in result.fixes)

    def test_colon_after_workflow(self):
        src = 'workflow: "test"\n\na = Wait { duration: 1 }\n'
        result = recover(src)
        assert result.was_modified
        assert 'workflow "test"' in result.source

    def test_trailing_semicolons(self):
        src = '''workflow "test"\n\na = ApiCall {\n  method: "GET";\n  url: "https://x.com";\n}\n'''
        result = recover(src)
        assert result.was_modified
        assert ";" not in result.source

    def test_python_booleans(self):
        src = '''workflow "test"\n\na = Wait { duration: 1\n  enabled: True\n}\n'''
        result = recover(src)
        assert result.was_modified
        assert "true" in result.source
        assert "True" not in result.source

    def test_single_quotes_to_double(self):
        src = """workflow "test"\n\na = ApiCall {\n  method: 'GET'\n  url: 'https://x.com'\n}\n"""
        result = recover(src)
        assert result.was_modified
        assert '"GET"' in result.source

    def test_arrow_variant_fat_arrow(self):
        src = '''workflow "test"\n\na = ApiCall {\n  method: "GET"\n  url: "https://x.com"\n  => /workflow/out\n}\n'''
        result = recover(src)
        assert result.was_modified
        assert "-> /workflow/out" in result.source

    def test_input_keyword(self):
        src = '''workflow "test"\n\na = FilterData {\n  input /workflow/data\n  where status == "active"\n}\n'''
        result = recover(src)
        assert result.was_modified
        assert "from /workflow/data" in result.source

    def test_execute_keyword(self):
        src = '''workflow "test"\n\na = Wait { duration: 1 }\nexecute: a\n'''
        result = recover(src)
        assert result.was_modified
        assert "run: a" in result.source

    def test_no_fixes_needed(self):
        src = '''workflow "test"\n\na = Wait { duration: 1 }\n'''
        result = recover(src)
        assert not result.was_modified
        assert result.fixes == []

    def test_trailing_commas(self):
        src = '''workflow "test"\n\na = ApiCall {\n  method: "GET"\n  headers: { Authorization: "Bearer x", }\n}\n'''
        result = recover(src)
        assert result.was_modified

    def test_parse_with_recovery_valid_source(self):
        src = 'workflow "test"\n\na = Wait { duration: 1 }\n'
        workflow, result = parse_with_recovery(src)
        assert workflow.name == "test"
        assert not result.was_modified

    def test_parse_with_recovery_fixable_source(self):
        # Unquoted workflow name fails to parse, recovery fixes it
        src = 'workflow my-pipeline\n\na = Wait { duration: 1 }\n'
        workflow, result = parse_with_recovery(src)
        assert workflow.name == "my-pipeline"
        assert result.was_modified

    def test_summary(self):
        result = RecoveryResult("fixed", "original", ["Fix 1", "Fix 2"])
        summary = result.summary()
        assert "2 fix(es)" in summary
        assert "Fix 1" in summary


# ---------------------------------------------------------------------------
# Token Budget
# ---------------------------------------------------------------------------

class TestTokenBudget:

    def test_basic_budget(self):
        src = '''
        workflow "test"
        a = ApiCall {
          method: "GET"
          url: "https://api.example.com"
          -> /workflow/out
        }
        '''
        budget = calculate_budget(src)
        assert isinstance(budget, TokenBudget)
        assert budget.dsl_chars > 0
        assert budget.jsonl_chars > 0
        assert budget.dsl_tokens > 0
        assert budget.jsonl_tokens > 0

    def test_dsl_is_more_compact(self):
        src = '''
        workflow "test"
        a = ApiCall {
          method: "GET"
          url: "https://api.example.com/users"
          -> /workflow/users
        }
        b = FilterData {
          from /workflow/users
          where status == "active"
          -> /workflow/filtered
        }
        c = StoreData {
          from /workflow/filtered
          storage: "localStorage"
          key: "data"
        }
        run: a -> b -> c
        '''
        budget = calculate_budget(src)
        # DSL should be more compact than JSONL in tokens
        assert budget.dsl_chars < budget.jsonl_chars

    def test_summary_format(self):
        src = 'workflow "test"\n\na = Wait { duration: 1 }\n'
        budget = calculate_budget(src)
        summary = budget.summary()
        assert "Token Budget" in summary
        assert "DSL source" in summary
        assert "JSONL output" in summary
        assert "Savings" in summary

    def test_compression_ratio(self):
        src = 'workflow "test"\n\na = Wait { duration: 1 }\n'
        budget = calculate_budget(src)
        assert budget.compression_ratio > 0


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

class TestPrompts:

    def test_all_templates_exist(self):
        names = {"gpt4", "claude", "gemini", "opensource"}
        for name in names:
            t = get_template(name)
            assert t.name == name
            assert t.system_prompt
            assert t.user_template

    def test_format_prompt(self):
        result = format_prompt("gpt4", "Fetch users and filter by age > 25")
        assert "system" in result
        assert "user" in result
        assert "Fetch users" in result["user"]
        assert "a2e-lang" in result["system"]

    def test_templates_contain_grammar(self):
        for name in TEMPLATES:
            t = get_template(name)
            assert "ApiCall" in t.system_prompt
            assert "workflow" in t.system_prompt

    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            get_template("nonexistent")

    def test_list_templates(self):
        result = list_templates()
        assert len(result) >= 4
        names = {t["name"] for t in result}
        assert "gpt4" in names
        assert "claude" in names

    def test_claude_has_xml_tags(self):
        t = get_template("claude")
        assert "<rules>" in t.system_prompt
        assert "<task>" in t.user_template


# ---------------------------------------------------------------------------
# Syntax Scoring
# ---------------------------------------------------------------------------

class TestSyntaxScoring:

    def test_well_formed_scores_high(self):
        src = '''
        workflow "user-pipeline"

        fetch_users = ApiCall {
          method: "GET"
          url: "https://api.example.com/users"
          -> /workflow/users
        }

        filter_active = FilterData {
          from /workflow/users
          where status == "active"
          -> /workflow/filtered
        }

        save_data = StoreData {
          from /workflow/filtered
          storage: "localStorage"
          key: "data"
        }

        run: fetch_users -> filter_active -> save_data
        '''
        score = score_syntax(src)
        assert score.overall >= 70
        assert isinstance(score.summary(), str)

    def test_minimal_workflow_scores_lower(self):
        src = '''
        workflow "x"
        a = Wait { duration: 1 }
        '''
        score = score_syntax(src)
        # Missing execution order, single-char-ish naming
        assert score.completeness < 100

    def test_good_naming_scores_high(self):
        src = '''
        workflow "test"
        fetch_users = ApiCall {
          method: "GET"
          url: "https://x.com"
          -> /workflow/out
        }
        run: fetch_users
        '''
        score = score_syntax(src)
        assert score.naming >= 80

    def test_summary_format(self):
        src = 'workflow "test"\n\na = Wait { duration: 1 }\nrun: a\n'
        score = score_syntax(src)
        summary = score.summary()
        assert "/100" in summary
        assert "Regularity" in summary
        assert "Verbosity" in summary

    def test_score_range(self):
        src = '''
        workflow "test"
        a = Wait { duration: 1 }
        run: a
        '''
        score = score_syntax(src)
        assert 0 <= score.overall <= 100
        assert 0 <= score.regularity <= 100
        assert 0 <= score.verbosity <= 100
        assert 0 <= score.structure <= 100
        assert 0 <= score.naming <= 100
        assert 0 <= score.completeness <= 100
