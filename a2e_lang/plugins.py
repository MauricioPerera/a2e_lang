"""Plugin system: register custom operation types.

Allows extending a2e-lang with user-defined operation types. Plugins
provide a name, required properties, an optional handler, and a
description for LSP integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .ast_nodes import Operation
from .engine import ExecutionContext, register_handler as _register_engine_handler


@dataclass(frozen=True)
class PluginSpec:
    """Specification for a custom operation type."""
    name: str
    required_properties: frozenset[str] = frozenset()
    optional_properties: frozenset[str] = frozenset()
    description: str = ""
    handler: Callable[[Operation, ExecutionContext], Any] | None = None


_PLUGINS: dict[str, PluginSpec] = {}


def register_plugin(spec: PluginSpec) -> None:
    """Register a custom operation type plugin.

    Raises:
        ValueError: If a plugin with the same name is already registered.
    """
    if spec.name in _PLUGINS:
        raise ValueError(f"Plugin '{spec.name}' is already registered")
    _PLUGINS[spec.name] = spec

    # Register handler with the execution engine
    if spec.handler:
        _register_engine_handler(spec.name, spec.handler)


def unregister_plugin(name: str) -> None:
    """Remove a registered plugin."""
    _PLUGINS.pop(name, None)


def get_plugin(name: str) -> PluginSpec | None:
    """Get a registered plugin by name."""
    return _PLUGINS.get(name)


def list_plugins() -> list[PluginSpec]:
    """List all registered plugins."""
    return sorted(_PLUGINS.values(), key=lambda p: p.name)


def is_valid_op_type(name: str) -> bool:
    """Check if name is a built-in or plugin operation type."""
    from .validator import VALID_OP_TYPES
    return name in VALID_OP_TYPES or name in _PLUGINS


def get_all_op_types() -> set[str]:
    """Get all valid operation types (built-in + plugins)."""
    from .validator import VALID_OP_TYPES
    return VALID_OP_TYPES | set(_PLUGINS.keys())


def clear_plugins() -> None:
    """Remove all registered plugins (useful for testing)."""
    _PLUGINS.clear()
