"""Tests for Phase 4: Ecosystem features."""

import json
import pytest
from pathlib import Path

from a2e_lang.parser import parse
from a2e_lang.plugins import (
    PluginSpec,
    register_plugin,
    unregister_plugin,
    get_plugin,
    list_plugins,
    is_valid_op_type,
    get_all_op_types,
    clear_plugins,
)
from a2e_lang.registry import WorkflowRegistry, WorkflowEntry
from a2e_lang.orchestrator import (
    Orchestrator,
    ChainMode,
    OrchestrationResult,
)
from a2e_lang.sourcemap import (
    SourceMap,
    SourceLocation,
    Mapping,
    generate_source_map,
)


SIMPLE = 'workflow "test"\n\na = Wait { duration: 1 }\nrun: a\n'


# ---------------------------------------------------------------------------
# Plugin System
# ---------------------------------------------------------------------------

class TestPluginSystem:

    def setup_method(self):
        clear_plugins()

    def test_register_plugin(self):
        spec = PluginSpec(name="CustomOp", description="A custom op")
        register_plugin(spec)
        assert get_plugin("CustomOp") is not None
        assert get_plugin("CustomOp").description == "A custom op"

    def test_duplicate_plugin_raises(self):
        spec = PluginSpec(name="DupOp")
        register_plugin(spec)
        with pytest.raises(ValueError, match="already registered"):
            register_plugin(spec)

    def test_unregister_plugin(self):
        spec = PluginSpec(name="TempOp")
        register_plugin(spec)
        unregister_plugin("TempOp")
        assert get_plugin("TempOp") is None

    def test_list_plugins(self):
        register_plugin(PluginSpec(name="BetaOp"))
        register_plugin(PluginSpec(name="AlphaOp"))
        plugins = list_plugins()
        assert len(plugins) == 2
        assert plugins[0].name == "AlphaOp"  # sorted

    def test_is_valid_op_type_builtin(self):
        assert is_valid_op_type("ApiCall") is True
        assert is_valid_op_type("Wait") is True

    def test_is_valid_op_type_plugin(self):
        register_plugin(PluginSpec(name="MyCustomOp"))
        assert is_valid_op_type("MyCustomOp") is True
        assert is_valid_op_type("NonExistent") is False

    def test_get_all_op_types_includes_plugins(self):
        register_plugin(PluginSpec(name="ExtraOp"))
        all_types = get_all_op_types()
        assert "ApiCall" in all_types
        assert "ExtraOp" in all_types

    def test_plugin_with_handler(self):
        handler = lambda op, ctx: {"custom": True}
        spec = PluginSpec(name="HandlerOp", handler=handler)
        register_plugin(spec)
        from a2e_lang.engine import get_handler
        assert get_handler("HandlerOp") is not None

    def test_clear_plugins(self):
        register_plugin(PluginSpec(name="ToClear"))
        clear_plugins()
        assert len(list_plugins()) == 0


# ---------------------------------------------------------------------------
# Workflow Registry
# ---------------------------------------------------------------------------

class TestWorkflowRegistry:

    def test_publish_and_get(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        entry = reg.publish("test-wf", SIMPLE, author="me", tags=["test"])

        assert entry.name == "test-wf"
        assert entry.author == "me"
        fetched = reg.get("test-wf")
        assert fetched is not None
        assert fetched.source == SIMPLE

    def test_get_source(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        reg.publish("src-test", SIMPLE)
        source = reg.get_source("src-test")
        assert source == SIMPLE

    def test_search_by_name(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        reg.publish("data-fetcher", SIMPLE, tags=["api"])
        reg.publish("data-processor", SIMPLE, tags=["transform"])
        results = reg.search("fetcher")
        assert len(results) == 1
        assert results[0].name == "data-fetcher"

    def test_search_by_tag(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        reg.publish("wf1", SIMPLE, tags=["api", "rest"])
        reg.publish("wf2", SIMPLE, tags=["transform"])
        results = reg.search("api")
        assert len(results) == 1

    def test_remove(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        reg.publish("to-remove", SIMPLE)
        assert reg.remove("to-remove") is True
        assert reg.get("to-remove") is None

    def test_list_all(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        reg.publish("beta", SIMPLE)
        reg.publish("alpha", SIMPLE)
        all_wf = reg.list_all()
        assert len(all_wf) == 2
        assert all_wf[0].name == "alpha"  # sorted

    def test_persistence(self, tmp_path):
        reg_dir = tmp_path / "registry"
        reg1 = WorkflowRegistry(reg_dir)
        reg1.publish("persist-test", SIMPLE)

        # New instance should load from disk
        reg2 = WorkflowRegistry(reg_dir)
        assert reg2.get("persist-test") is not None

    def test_summary(self, tmp_path):
        reg = WorkflowRegistry(tmp_path / "registry")
        reg.publish("wf1", SIMPLE, author="alice", tags=["test"])
        summary = reg.summary()
        assert "wf1" in summary
        assert "alice" in summary

    def test_workflow_entry_serialization(self):
        entry = WorkflowEntry(name="wf", version="2.0.0", author="bob")
        d = entry.to_dict()
        restored = WorkflowEntry.from_dict(d)
        assert restored.name == "wf"
        assert restored.version == "2.0.0"
        assert restored.author == "bob"


# ---------------------------------------------------------------------------
# Multi-Agent Orchestration
# ---------------------------------------------------------------------------

WAIT_WF = 'workflow "step"\n\na = Wait { duration: 1 }\nrun: a\n'

STORE_WF = '''workflow "store"

store = StoreData {
  from /workflow/input
  storage: "localStorage"
  key: "result"
}

run: store
'''


class TestOrchestrator:

    def test_single_step(self):
        orch = Orchestrator()
        orch.add_step("step1", WAIT_WF)
        result = orch.run()

        assert result.success is True
        assert result.steps_completed == 1
        assert result.steps_total == 1

    def test_sequential_chain(self):
        orch = Orchestrator()
        orch.add_step("step1", WAIT_WF)
        orch.add_step("step2", WAIT_WF)
        result = orch.run()

        assert result.success is True
        assert result.steps_completed == 2

    def test_conditional_skip(self):
        orch = Orchestrator()
        orch.add_step("step1", WAIT_WF)
        orch.add_step(
            "step2",
            WAIT_WF,
            mode=ChainMode.CONDITIONAL,
            condition="/nonexistent",
        )
        result = orch.run()

        assert result.success is True
        assert result.steps_completed == 2
        # step2 should be marked as skipped
        assert result.step_results[1].get("skipped") is True

    def test_data_flow_between_steps(self):
        orch = Orchestrator()
        orch.add_step("step1", STORE_WF)
        orch.add_step(
            "step2",
            STORE_WF,
            input_mapping={"/workflow/input": "/workflow/output"},
        )
        result = orch.run(input_data={"/workflow/input": {"data": "hello"}})

        assert result.success is True
        assert result.steps_completed == 2

    def test_summary_format(self):
        orch = Orchestrator()
        orch.add_step("step1", WAIT_WF)
        result = orch.run()
        summary = result.summary()
        assert "Orchestration" in summary
        assert "step1" in summary

    def test_fluent_api(self):
        result = (
            Orchestrator()
            .add_step("a", WAIT_WF)
            .add_step("b", WAIT_WF)
            .run()
        )
        assert result.success is True
        assert result.steps_completed == 2


# ---------------------------------------------------------------------------
# Source Maps
# ---------------------------------------------------------------------------

MAPPED_SOURCE = '''workflow "mapped"

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

run: fetch -> process
'''


class TestSourceMap:

    def test_generate_source_map(self):
        sm = generate_source_map(MAPPED_SOURCE, source_file="test.a2e")
        assert sm.workflow_name == "mapped"
        assert sm.source_file == "test.a2e"
        assert len(sm.mappings) == 2

    def test_lookup_operation(self):
        sm = generate_source_map(MAPPED_SOURCE)
        mapping = sm.lookup_operation("fetch")
        assert mapping is not None
        assert mapping.operation_type == "ApiCall"

    def test_lookup_jsonl_line(self):
        sm = generate_source_map(MAPPED_SOURCE)
        mapping = sm.lookup_jsonl_line(0)
        assert mapping is not None
        assert mapping.operation_id == "fetch"

    def test_source_map_to_json(self):
        sm = generate_source_map(MAPPED_SOURCE)
        json_str = sm.to_json(pretty=True)
        parsed = json.loads(json_str)
        assert parsed["version"] == 1
        assert len(parsed["mappings"]) == 2

    def test_source_map_roundtrip(self):
        sm = generate_source_map(MAPPED_SOURCE, source_file="test.a2e")
        d = sm.to_dict()
        restored = SourceMap.from_dict(d)
        assert restored.workflow_name == sm.workflow_name
        assert len(restored.mappings) == len(sm.mappings)

    def test_source_location(self):
        loc = SourceLocation(line=5, column=2)
        d = loc.to_dict()
        assert d["line"] == 5
        assert d["column"] == 2

    def test_summary_format(self):
        sm = generate_source_map(MAPPED_SOURCE, source_file="demo.a2e")
        summary = sm.summary()
        assert "demo.a2e" in summary
        assert "fetch" in summary

    def test_property_mapping(self):
        sm = generate_source_map(MAPPED_SOURCE)
        mapping = sm.lookup_operation("fetch")
        # Should have property mappings for method, url
        assert "method" in mapping.properties or "url" in mapping.properties
