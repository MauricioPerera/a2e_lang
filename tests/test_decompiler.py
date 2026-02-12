"""Tests for the decompiler (JSONL -> DSL)."""

from a2e_lang import parse, Compiler, SpecCompiler
from a2e_lang.decompiler import Decompiler


SIMPLE_DSL = '''
workflow "test-workflow"

fetch = ApiCall {
  method: "GET"
  url: "https://api.example.com/users"
  -> /workflow/users
}

filter = FilterData {
  from /workflow/users
  where status == "active"
  -> /workflow/filtered
}

store = StoreData {
  from /workflow/filtered
  storage: "localStorage"
  key: "data"
}

run: fetch -> filter -> store
'''


class TestDecompileSpec:

    def test_roundtrip_spec(self):
        """Compile to spec JSONL, decompile back, recompile — should match."""
        original = parse(SIMPLE_DSL)
        jsonl = SpecCompiler().compile(original)
        dsl = Decompiler().decompile(jsonl)

        # The decompiled DSL should be valid and re-parseable
        reparsed = parse(dsl)
        assert reparsed.name == original.name
        assert len(reparsed.operations) == len(original.operations)
        assert [op.id for op in reparsed.operations] == [op.id for op in original.operations]
        assert [op.op_type for op in reparsed.operations] == [op.op_type for op in original.operations]

    def test_preserves_workflow_name(self):
        jsonl = SpecCompiler().compile(parse(SIMPLE_DSL))
        dsl = Decompiler().decompile(jsonl)
        assert 'workflow "test-workflow"' in dsl

    def test_preserves_execution_order(self):
        jsonl = SpecCompiler().compile(parse(SIMPLE_DSL))
        dsl = Decompiler().decompile(jsonl)
        assert "run: fetch -> filter -> store" in dsl

    def test_preserves_from_clause(self):
        jsonl = SpecCompiler().compile(parse(SIMPLE_DSL))
        dsl = Decompiler().decompile(jsonl)
        assert "from /workflow/users" in dsl
        assert "from /workflow/filtered" in dsl

    def test_preserves_output_path(self):
        jsonl = SpecCompiler().compile(parse(SIMPLE_DSL))
        dsl = Decompiler().decompile(jsonl)
        assert "-> /workflow/users" in dsl
        assert "-> /workflow/filtered" in dsl

    def test_preserves_where_clause(self):
        jsonl = SpecCompiler().compile(parse(SIMPLE_DSL))
        dsl = Decompiler().decompile(jsonl)
        assert "where status ==" in dsl


class TestDecompileLegacy:

    def test_roundtrip_legacy(self):
        """Compile to legacy JSONL, decompile back — should match."""
        original = parse(SIMPLE_DSL)
        jsonl = Compiler().compile(original)
        dsl = Decompiler().decompile(jsonl)

        reparsed = parse(dsl)
        assert reparsed.name == original.name
        assert len(reparsed.operations) == len(original.operations)

    def test_auto_detect_legacy_format(self):
        jsonl = Compiler().compile(parse(SIMPLE_DSL))
        dsl = Decompiler().decompile(jsonl)
        assert 'workflow "test-workflow"' in dsl


class TestDecompileCredentials:

    def test_credential_roundtrip(self):
        src = '''
        workflow "cred-test"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com"
            headers: { Authorization: credential("api-key") }
            -> /workflow/out
        }
        '''
        original = parse(src)
        jsonl = SpecCompiler().compile(original)
        dsl = Decompiler().decompile(jsonl)
        assert 'credential("api-key")' in dsl


class TestDecompileConditional:

    def test_conditional_roundtrip(self):
        src = '''
        workflow "cond-test"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        check = Conditional {
            if /workflow/count > 0
            then a
            else b
        }
        '''
        original = parse(src)
        jsonl = SpecCompiler().compile(original)
        dsl = Decompiler().decompile(jsonl)
        reparsed = parse(dsl)

        assert len(reparsed.operations) == 3
        cond_op = [op for op in reparsed.operations if op.op_type == "Conditional"][0]
        assert cond_op.if_clause is not None


class TestDecompileFullRoundtrip:

    def test_full_workflows_roundtrip(self):
        """Roundtrip: DSL -> SpecCompiler -> Decompiler -> parse -> SpecCompiler.
        The two JSONL outputs should be identical."""
        original = parse(SIMPLE_DSL)
        jsonl1 = SpecCompiler().compile(original)

        dsl = Decompiler().decompile(jsonl1)
        reparsed = parse(dsl)
        jsonl2 = SpecCompiler().compile(reparsed)

        # The JSONL should be identical
        assert jsonl1 == jsonl2
