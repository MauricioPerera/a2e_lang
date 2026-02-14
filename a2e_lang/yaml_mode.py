"""YAML mode: simplified workflow format for small LLMs.

Parses YAML workflow definitions and compiles them to A2E JSONL.
Designed so that even 2B-parameter models can generate valid workflows
using syntax they already know from training data (GitHub Actions, K8s, etc).

Supported step types (6 core primitives):
  fetch     → ApiCall
  filter    → FilterData
  transform → TransformData
  branch    → Conditional
  merge     → MergeData
  store     → StoreData
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml


# ── Step type mapping ────────────────────────────────────────────────

STEP_TYPE_MAP = {
    "fetch":     "ApiCall",
    "filter":    "FilterData",
    "transform": "TransformData",
    "branch":    "Conditional",
    "merge":     "MergeData",
    "store":     "StoreData",
}

# Key synonyms — LLMs use different names for the same concept.
# We normalize before validation so we accept all common variants.
KEY_SYNONYMS: dict[str, str] = {
    # transform step
    "using":       "transform",
    "operation":   "transform",
    "sort_by":     "transform",
    "action":      "transform",
    "script":      "transform",
    "run":         "transform",
    "apply":       "transform",
    # merge step
    "inputs":      "sources",
    # I/O
    "from":        "input",
    "input_path":  "input",
    "source":      "input",
    "output_path": "output",
    "to":          "output",
    "target":      "output",
    # store
    "name":        "key",
    "store_key":   "key",
    # filter
    "filter":      "where",
    "conditions":  "where",
    # branch
    "if":          "condition",
    "when":        "condition",
    "else":        "otherwise",
}

# Required keys per step type (besides 'id' and 'type')
REQUIRED_KEYS: dict[str, list[str]] = {
    "fetch":     ["method", "url"],
    "filter":    ["input", "where"],
    "transform": ["input", "transform"],
    "branch":    ["condition", "then"],
    "merge":     ["sources"],
    "store":     ["input", "key"],
}


# ── Parse & validate ─────────────────────────────────────────────────

class YamlValidationError(Exception):
    """Raised when YAML workflow fails validation."""


def parse_yaml(source: str) -> dict:
    """Parse YAML source and validate structure. Returns parsed dict."""
    try:
        data = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise YamlValidationError(f"Invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise YamlValidationError("Root must be a YAML mapping")

    if "workflow" not in data:
        raise YamlValidationError("Missing 'workflow' key (workflow name)")

    if "steps" not in data or not isinstance(data["steps"], list):
        raise YamlValidationError("Missing 'steps' list")

    if len(data["steps"]) == 0:
        raise YamlValidationError("Workflow must have at least one step")

    seen_ids: set[str] = set()
    for i, step in enumerate(data["steps"]):
        _normalize_step(step)
        _validate_step(step, i, seen_ids)

    return data


def _normalize_step(step: dict) -> None:
    """Normalize key names in-place using synonym table.

    Also handles structural patterns LLMs commonly produce:
      - input1/input2 keys → sources list (for merge)
      - input as list → sources (for merge)
      - sort_by/using value → transform key
    """
    if not isinstance(step, dict):
        return

    # 1) Rename synonym keys
    for old_key, new_key in KEY_SYNONYMS.items():
        if old_key in step and new_key not in step:
            step[new_key] = step.pop(old_key)

    step_type = step.get("type", "")

    # 2) Merge: input1+input2 → sources
    if step_type == "merge" and "sources" not in step:
        numbered = {}
        for k in list(step.keys()):
            if k.startswith("input") and k != "input":
                numbered[k] = step.pop(k)
        if numbered:
            step["sources"] = list(numbered.values())

    # 3) Merge: input as list → sources
    if step_type == "merge" and "sources" not in step:
        inp = step.get("input")
        if isinstance(inp, list):
            step["sources"] = step.pop("input")

    # 4) Transform: if transform key holds a dict with 'type', flatten it
    if step_type == "transform" and "transform" in step:
        val = step["transform"]
        if isinstance(val, dict) and "type" in val:
            config = {k: v for k, v in val.items() if k != "type"}
            step["transform"] = val["type"]
            if config and "config" not in step:
                step["config"] = config


def _validate_step(step: dict, index: int, seen_ids: set[str]) -> None:
    """Validate a single step."""
    prefix = f"Step {index}"

    if not isinstance(step, dict):
        raise YamlValidationError(f"{prefix}: must be a mapping")

    if "id" not in step:
        raise YamlValidationError(f"{prefix}: missing 'id'")

    if "type" not in step:
        raise YamlValidationError(f"{prefix} ({step['id']}): missing 'type'")

    step_id = step["id"]
    step_type = step["type"]

    if step_id in seen_ids:
        raise YamlValidationError(f"{prefix}: duplicate id '{step_id}'")
    seen_ids.add(step_id)

    if step_type not in STEP_TYPE_MAP:
        raise YamlValidationError(
            f"{prefix} ({step_id}): unknown type '{step_type}'. "
            f"Valid: {', '.join(sorted(STEP_TYPE_MAP))}"
        )

    for key in REQUIRED_KEYS.get(step_type, []):
        if key not in step:
            raise YamlValidationError(
                f"{prefix} ({step_id}): type '{step_type}' requires '{key}'"
            )


# ── Where-clause parser ─────────────────────────────────────────────

_WHERE_RE = re.compile(
    r"(\w+)\s*(==|!=|>|<|>=|<=)\s*(.+)"
)


def _parse_where(where: str | list) -> list[dict]:
    """Parse where clause into condition list.

    Accepts:
      where: "price > 50"
      where: "status == active"
      where:
        - "price > 50"
        - "status == active"
    """
    items = where if isinstance(where, list) else [where]
    conditions = []
    for item in items:
        item = str(item).strip()
        m = _WHERE_RE.match(item)
        if not m:
            raise YamlValidationError(f"Invalid where clause: '{item}'")
        field, op, val = m.group(1), m.group(2), m.group(3).strip()
        # Coerce value
        val = _coerce_value(val)
        conditions.append({"field": field, "operator": op, "value": val})
    return conditions


def _parse_condition(cond_str: str) -> dict:
    """Parse branch condition string like '/workflow/temp > 30'."""
    cond_str = str(cond_str).strip()
    m = _WHERE_RE.match(cond_str)
    if m:
        path, op, val = m.group(1), m.group(2), m.group(3).strip()
        return {"path": path, "operator": op, "value": _coerce_value(val)}
    # Try path-based: /workflow/data > 30
    parts = cond_str.split()
    if len(parts) >= 3:
        return {
            "path": parts[0],
            "operator": parts[1],
            "value": _coerce_value(" ".join(parts[2:])),
        }
    return {"path": cond_str, "operator": "==", "value": True}


def _coerce_value(val: str) -> Any:
    """Coerce string value to int/float/bool/string."""
    # Remove quotes
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


# ── Compile to A2E JSONL ─────────────────────────────────────────────

def compile_yaml(data: dict) -> str:
    """Compile parsed YAML workflow to A2E JSONL (compact)."""
    workflow_name = str(data["workflow"])
    steps = data["steps"]
    operations = [_compile_step(s) for s in steps]
    exec_order = [s["id"] for s in steps]

    lines = [
        json.dumps({
            "operationUpdate": {
                "workflowId": workflow_name,
                "operations": operations,
            }
        }, separators=(",", ":")),
        json.dumps({
            "beginExecution": {
                "workflowId": workflow_name,
                "root": exec_order[0],
            }
        }, separators=(",", ":")),
    ]
    return "\n".join(lines)


def compile_yaml_pretty(data: dict) -> str:
    """Compile parsed YAML workflow to A2E JSONL (pretty)."""
    workflow_name = str(data["workflow"])
    steps = data["steps"]
    operations = [_compile_step(s) for s in steps]
    exec_order = [s["id"] for s in steps]

    lines = [
        json.dumps({
            "operationUpdate": {
                "workflowId": workflow_name,
                "operations": operations,
            }
        }, indent=2),
        json.dumps({
            "beginExecution": {
                "workflowId": workflow_name,
                "root": exec_order[0],
            }
        }, indent=2),
    ]
    return "\n\n".join(lines)


def _compile_step(step: dict) -> dict:
    """Compile a single step to A2E operation dict."""
    step_type = step["type"]
    a2e_type = STEP_TYPE_MAP[step_type]

    config: dict[str, Any] = {}

    if step_type == "fetch":
        config["method"] = step["method"]
        config["url"] = step["url"]
        if "headers" in step:
            headers = step["headers"]
            compiled_headers = {}
            for k, v in headers.items():
                v_str = str(v)
                if v_str.startswith("credential:"):
                    compiled_headers[k] = {
                        "credentialRef": {"id": v_str.split(":", 1)[1]}
                    }
                else:
                    compiled_headers[k] = v
            config["headers"] = compiled_headers
        if "body" in step:
            config["body"] = step["body"]
        if "output" in step:
            config["outputPath"] = step["output"]

    elif step_type == "filter":
        config["inputPath"] = step["input"]
        config["conditions"] = _parse_where(step["where"])
        if "output" in step:
            config["outputPath"] = step["output"]

    elif step_type == "transform":
        config["inputPath"] = step["input"]
        config["transform"] = step["transform"]
        # Collect extra keys as config (LLMs put field/order/etc at step level)
        extra_config = step.get("config", {})
        skip = {"id", "type", "input", "transform", "output", "config"}
        for k, v in step.items():
            if k not in skip:
                extra_config[k] = v
        if extra_config:
            config["config"] = extra_config
        if "output" in step:
            config["outputPath"] = step["output"]

    elif step_type == "branch":
        config["condition"] = _parse_condition(step["condition"])
        config["ifTrue"] = step["then"]
        if "else" in step:
            config["ifFalse"] = step["else"]
        elif "otherwise" in step:
            config["ifFalse"] = step["otherwise"]

    elif step_type == "merge":
        config["sources"] = step["sources"]
        config["strategy"] = step.get("strategy", "concat")
        if "output" in step:
            config["outputPath"] = step["output"]

    elif step_type == "store":
        config["inputPath"] = step["input"]
        config["storage"] = step.get("storage", "localStorage")
        config["key"] = step["key"]

    return {
        "id": step["id"],
        "operation": {a2e_type: config},
    }


# ── Public API ───────────────────────────────────────────────────────

def yaml_to_jsonl(source: str) -> str:
    """Parse YAML source, validate, compile to A2E JSONL."""
    data = parse_yaml(source)
    return compile_yaml(data)


def yaml_to_jsonl_pretty(source: str) -> str:
    """Parse YAML source, validate, compile to pretty A2E JSONL."""
    data = parse_yaml(source)
    return compile_yaml_pretty(data)
