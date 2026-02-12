"""Source maps: DSL → JSONL mapping for runtime debugging.

Generates a mapping from DSL source locations (line/column) to the
corresponding JSONL output positions. This enables precise error
attribution from runtime failures back to the original DSL source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .ast_nodes import Operation, Workflow
from .parser import parse


@dataclass
class SourceLocation:
    """A location in the DSL source."""
    line: int
    column: int = 0
    end_line: int | None = None
    end_column: int | None = None

    def to_dict(self) -> dict:
        d = {"line": self.line, "column": self.column}
        if self.end_line:
            d["end_line"] = self.end_line
        if self.end_column:
            d["end_column"] = self.end_column
        return d


@dataclass
class Mapping:
    """Maps a JSONL element to its DSL source location."""
    jsonl_line: int         # Line in the JSONL output (0-indexed)
    operation_id: str
    operation_type: str
    source: SourceLocation
    properties: dict[str, SourceLocation] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "jsonl_line": self.jsonl_line,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "source": self.source.to_dict(),
        }
        if self.properties:
            d["properties"] = {k: v.to_dict() for k, v in self.properties.items()}
        return d


@dataclass
class SourceMap:
    """Complete source map for a compiled workflow."""
    source_file: str = ""
    workflow_name: str = ""
    mappings: list[Mapping] = field(default_factory=list)
    _op_index: dict[str, Mapping] = field(default_factory=dict, repr=False)

    def add_mapping(self, mapping: Mapping) -> None:
        """Add a mapping entry."""
        self.mappings.append(mapping)
        self._op_index[mapping.operation_id] = mapping

    def lookup_operation(self, operation_id: str) -> Mapping | None:
        """Find the source location for an operation by ID."""
        return self._op_index.get(operation_id)

    def lookup_jsonl_line(self, line: int) -> Mapping | None:
        """Find the source location for a JSONL output line."""
        for m in self.mappings:
            if m.jsonl_line == line:
                return m
        return None

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "source_file": self.source_file,
            "workflow_name": self.workflow_name,
            "mappings": [m.to_dict() for m in self.mappings],
        }

    def to_json(self, pretty: bool = False) -> str:
        indent = 2 if pretty else None
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> SourceMap:
        sm = cls(
            source_file=d.get("source_file", ""),
            workflow_name=d.get("workflow_name", ""),
        )
        for md in d.get("mappings", []):
            src = SourceLocation(**md["source"])
            props = {}
            for k, v in md.get("properties", {}).items():
                props[k] = SourceLocation(**v)
            mapping = Mapping(
                jsonl_line=md["jsonl_line"],
                operation_id=md["operation_id"],
                operation_type=md["operation_type"],
                source=src,
                properties=props,
            )
            sm.add_mapping(mapping)
        return sm

    def summary(self) -> str:
        lines = [
            f"Source Map: {self.source_file or '(inline)'}",
            f"Workflow: {self.workflow_name}",
            f"Mappings: {len(self.mappings)}",
            "─" * 50,
        ]
        for m in self.mappings:
            lines.append(
                f"  JSONL:{m.jsonl_line} → DSL:{m.source.line} "
                f"  {m.operation_id} ({m.operation_type})"
            )
        return "\n".join(lines)


def generate_source_map(
    source: str,
    source_file: str = "",
) -> SourceMap:
    """Generate a source map from DSL source code.

    Parses the DSL and creates a mapping from each operation to its
    source location. The JSONL line index corresponds to the order
    operations appear in the compiled output (one line per operation
    in the JSONL format).
    """
    workflow = parse(source)
    sm = SourceMap(
        source_file=source_file,
        workflow_name=workflow.name,
    )

    source_lines = source.splitlines()

    for jsonl_idx, op in enumerate(workflow.operations):
        # Find the DSL line where this operation is defined
        dsl_line = _find_operation_line(source_lines, op)

        src_loc = SourceLocation(line=dsl_line, column=0)

        # Map individual properties
        prop_locs: dict[str, SourceLocation] = {}
        for prop in op.properties:
            prop_line = _find_property_line(source_lines, prop.key, dsl_line)
            if prop_line:
                prop_locs[prop.key] = SourceLocation(line=prop_line, column=0)

        mapping = Mapping(
            jsonl_line=jsonl_idx,
            operation_id=op.id,
            operation_type=op.op_type,
            source=src_loc,
            properties=prop_locs,
        )
        sm.add_mapping(mapping)

    return sm


def _find_operation_line(lines: list[str], op: Operation) -> int:
    """Find the DSL line number where an operation is defined."""
    # Look for pattern: op_id = OpType {
    pattern_exact = f"{op.id} ="
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(pattern_exact):
            return i + 1  # 1-indexed
    return 1  # fallback


def _find_property_line(
    lines: list[str],
    key: str,
    start_from: int,
) -> int | None:
    """Find the line number of a property definition."""
    pattern = f"{key}:"
    for i in range(start_from - 1, min(start_from + 20, len(lines))):
        stripped = lines[i].strip()
        if stripped.startswith(pattern):
            return i + 1  # 1-indexed
    return None
