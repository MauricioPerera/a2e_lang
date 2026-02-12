"""a2e-lang — DSL compiler for the A2E protocol."""

from .ast_nodes import (
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
from .compiler import Compiler
from .compiler_spec import SpecCompiler
from .decompiler import Decompiler
from .engine import ExecutionEngine, ExecutionResult
from .errors import A2ELangError, CompileError, ParseError, ValidationError
from .graph import generate_mermaid
from .logging import ExecutionLogger, PipelineLog
from .orchestrator import Orchestrator, OrchestrationResult, ChainMode
from .parser import parse
from .plugins import (
    PluginSpec,
    register_plugin,
    unregister_plugin,
    get_plugin,
    list_plugins,
    is_valid_op_type,
    get_all_op_types,
)
from .prompts import format_prompt, get_template, list_templates
from .recovery import recover, parse_with_recovery
from .registry import WorkflowRegistry, WorkflowEntry
from .resilience import RetryPolicy, CircuitBreaker, execute_with_retry
from .scoring import score_syntax
from .simulator import Simulator, SimulationResult
from .sourcemap import SourceMap, generate_source_map
from .tokens import calculate_budget
from .validator import Validator
from .webhook import WebhookServer

__all__ = [
    "parse",
    "Compiler",
    "SpecCompiler",
    "Decompiler",
    "Validator",
    "Simulator",
    "SimulationResult",
    "generate_mermaid",
    "recover",
    "parse_with_recovery",
    "calculate_budget",
    "format_prompt",
    "get_template",
    "list_templates",
    "score_syntax",
    "ExecutionEngine",
    "ExecutionResult",
    "ExecutionLogger",
    "PipelineLog",
    "RetryPolicy",
    "CircuitBreaker",
    "execute_with_retry",
    "WebhookServer",
    "PluginSpec",
    "register_plugin",
    "unregister_plugin",
    "get_plugin",
    "list_plugins",
    "is_valid_op_type",
    "get_all_op_types",
    "WorkflowRegistry",
    "WorkflowEntry",
    "Orchestrator",
    "OrchestrationResult",
    "ChainMode",
    "SourceMap",
    "generate_source_map",
    "Workflow",
    "Operation",
    "Property",
    "Condition",
    "IfClause",
    "Path",
    "Credential",
    "ObjectValue",
    "ArrayValue",
    "A2ELangError",
    "ParseError",
    "ValidationError",
    "CompileError",
]
