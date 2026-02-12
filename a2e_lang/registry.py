"""Workflow registry: publish and discover reusable workflows.

Provides a local file-based registry for sharing workflow definitions.
Workflows can be published with metadata (name, version, author, tags)
and discovered by name or tag search.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WorkflowEntry:
    """Entry in the workflow registry."""
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""
    published_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "tags": self.tags,
            "source": self.source,
            "published_at": self.published_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkflowEntry:
        return cls(
            name=d["name"],
            version=d.get("version", "1.0.0"),
            author=d.get("author", ""),
            description=d.get("description", ""),
            tags=d.get("tags", []),
            source=d.get("source", ""),
            published_at=d.get("published_at", 0),
        )

    def summary_line(self) -> str:
        tags = ", ".join(self.tags) if self.tags else "—"
        return f"{self.name} v{self.version} by {self.author or '?'} [{tags}]"


class WorkflowRegistry:
    """Local file-based workflow registry.

    Stores workflow metadata and source code in a directory structure:
      registry_dir/
        index.json          — registry index
        workflows/
          <name>.a2e        — workflow source files
    """

    def __init__(self, registry_dir: str | Path | None = None):
        if registry_dir is None:
            registry_dir = Path.home() / ".a2e" / "registry"
        self.root = Path(registry_dir)
        self._workflows_dir = self.root / "workflows"
        self._index_path = self.root / "index.json"
        self._entries: dict[str, WorkflowEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load registry index from disk."""
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                for entry_data in data.get("workflows", []):
                    entry = WorkflowEntry.from_dict(entry_data)
                    self._entries[entry.name] = entry
            except (json.JSONDecodeError, KeyError):
                self._entries = {}

    def _save(self) -> None:
        """Persist registry index to disk."""
        self.root.mkdir(parents=True, exist_ok=True)
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "workflows": [e.to_dict() for e in self._entries.values()],
        }
        self._index_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    def publish(
        self,
        name: str,
        source: str,
        *,
        version: str = "1.0.0",
        author: str = "",
        description: str = "",
        tags: list[str] | None = None,
    ) -> WorkflowEntry:
        """Publish a workflow to the registry."""
        entry = WorkflowEntry(
            name=name,
            version=version,
            author=author,
            description=description,
            tags=tags or [],
            source=source,
        )
        self._entries[name] = entry

        # Save source file
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        src_path = self._workflows_dir / f"{name}.a2e"
        src_path.write_text(source, encoding="utf-8")

        self._save()
        return entry

    def get(self, name: str) -> WorkflowEntry | None:
        """Get a workflow entry by name."""
        return self._entries.get(name)

    def get_source(self, name: str) -> str | None:
        """Get the source code for a published workflow."""
        entry = self._entries.get(name)
        if entry:
            return entry.source
        return None

    def search(self, query: str) -> list[WorkflowEntry]:
        """Search workflows by name or tag (case-insensitive)."""
        q = query.lower()
        results = []
        for entry in self._entries.values():
            if q in entry.name.lower():
                results.append(entry)
            elif any(q in t.lower() for t in entry.tags):
                results.append(entry)
            elif q in entry.description.lower():
                results.append(entry)
        return sorted(results, key=lambda e: e.name)

    def list_all(self) -> list[WorkflowEntry]:
        """List all published workflows."""
        return sorted(self._entries.values(), key=lambda e: e.name)

    def remove(self, name: str) -> bool:
        """Remove a workflow from the registry."""
        if name not in self._entries:
            return False
        del self._entries[name]
        src_path = self._workflows_dir / f"{name}.a2e"
        if src_path.exists():
            src_path.unlink()
        self._save()
        return True

    def summary(self) -> str:
        """Return a summary of the registry."""
        entries = self.list_all()
        if not entries:
            return "Registry is empty"
        lines = [f"Workflow Registry ({len(entries)} workflows):"]
        for entry in entries:
            lines.append(f"  • {entry.summary_line()}")
        return "\n".join(lines)
