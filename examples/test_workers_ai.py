"""
Test: LLM agent generates a2e-lang DSL code from natural language.

Flow:
  1. User describes what they want in plain language
  2. Workers AI (Hermes 2 Pro 7B) generates a2e-lang DSL
  3. We parse, validate, and compile it to A2E JSONL

Usage:
  set CLOUDFLARE_API_TOKEN=your-token
  python examples/test_workers_ai.py
"""

import json
import os
import sys
import time
import httpx

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2e_lang.parser import parse
from a2e_lang.validator import Validator
from a2e_lang.compiler import Compiler
from a2e_lang.errors import A2ELangError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ACCOUNT_ID = "091122c40cc6f8d0d421cbc90e2caca8"
MODEL = "@cf/google/gemma-2b-it-lora"
BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}"

# ---------------------------------------------------------------------------
# System prompt — teaches the LLM the a2e-lang DSL
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an A2E workflow generator. You write workflows in the a2e-lang DSL.

## Syntax rules

1. Start with: workflow "name"
2. Each operation: id = OperationType { ... }
3. Use `from /workflow/path` for input
4. Use `-> /workflow/path` for output
5. Use `where field op value` for filters
6. Use `if /path op value then id else id` for branching
7. Use `credential("name")` for auth headers
8. End with: run: op1 -> op2 -> op3

## Operation types

ApiCall: HTTP request
  method: "GET" or "POST"
  url: "https://..."
  headers: { Key: "value" }
  body: { key: "value" }
  -> /workflow/output

FilterData: filter arrays
  from /workflow/input
  where field == "value", field > 100
  -> /workflow/output

TransformData: transform data
  from /workflow/input
  transform: "sort" or "select" or "map" or "group"
  config: { field: "name", order: "asc" }
  -> /workflow/output

Conditional: branching
  if /workflow/path > 0 then op_a else op_b

StoreData: persist data
  from /workflow/input
  storage: "localStorage"
  key: "name"

MergeData: combine sources
  sources: [/workflow/a, /workflow/b]
  strategy: "concat" or "deepMerge"
  -> /workflow/output

Wait: pause execution
  duration: 5000

Loop: iterate over array
  from /workflow/input
  operations: [op_id]
  -> /workflow/output

## Example

workflow "user-pipeline"

fetch_users = ApiCall {
  method: "GET"
  url: "https://api.example.com/users"
  headers: { Authorization: credential("api-key") }
  -> /workflow/users
}

filter_active = FilterData {
  from /workflow/users
  where status == "active", points > 50
  -> /workflow/filtered
}

store = StoreData {
  from /workflow/filtered
  storage: "localStorage"
  key: "active-users"
}

run: fetch_users -> filter_active -> store

## Rules
- ONLY output the a2e-lang code, nothing else
- No markdown, no explanation, just the DSL code
- Use underscores in operation IDs (not hyphens)
- All ApiCall operations need -> output path
- All FilterData need from + where + -> output path
- Invent realistic URLs for the task"""

# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

SCENARIOS = [
    "Fetch a list of products from an e-commerce API, filter products that cost more than 50 dollars, sort them by price descending, and store the result.",
    "Get weather data from an API, check if temperature is above 30, if yes store a heat alert, if no store normal status.",
    "Fetch users and orders from two different APIs, merge them together, and store the combined data.",
]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def call_workers_ai(token: str, user_message: str) -> dict:
    """Call Workers AI and return response text + metrics."""
    t0 = time.perf_counter()
    response = httpx.post(
        BASE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        },
        timeout=60.0,
    )
    latency = time.perf_counter() - t0
    response.raise_for_status()
    data = response.json()
    result = data.get("result", {})

    # Extract text: support both simple format (response) and OpenAI format (choices)
    text = ""
    if isinstance(result, dict):
        text = result.get("response", "")
        if not text and "choices" in result:
            choices = result["choices"]
            if choices and isinstance(choices, list):
                text = choices[0].get("message", {}).get("content", "")

    # Extract usage from result or result.usage
    usage = {}
    if isinstance(result, dict):
        usage = result.get("usage", {})
        if not usage and "choices" in result:
            # Some models put usage at result level
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if key in result:
                    usage[key] = result[key]

    return {
        "text": text,
        "latency_s": latency,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def try_compile(dsl_source: str) -> tuple[bool, str]:
    """Try to parse, validate, and compile DSL source. Returns (success, output)."""
    try:
        workflow = parse(dsl_source)
    except A2ELangError as e:
        return False, f"PARSE ERROR: {e}"

    errors = Validator().validate(workflow)
    if errors:
        return False, f"VALIDATION ERRORS:\n" + "\n".join(f"  - {e}" for e in errors)

    jsonl = Compiler().compile_pretty(workflow)
    return True, jsonl


def main():
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("ERROR: Set CLOUDFLARE_API_TOKEN environment variable.")
        sys.exit(1)

    print("=" * 70)
    print("a2e-lang + Workers AI — LLM Agent Generates Workflows")
    print("=" * 70)
    print(f"Model: {MODEL}")
    print()

    results = {"success": 0, "parse_fail": 0, "validation_fail": 0}
    metrics = []  # per-scenario metrics

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n{'='*70}")
        print(f"SCENARIO {i}/{len(SCENARIOS)}")
        print(f"{'='*70}")
        print(f"User request: {scenario}")
        print()

        # 1. Call LLM
        print("[1] Calling Workers AI...")
        try:
            ai_result = call_workers_ai(token, scenario)
        except Exception as e:
            print(f"    API ERROR: {e}")
            continue

        raw_response = ai_result["text"]
        m = {
            "scenario": i,
            "latency_s": ai_result["latency_s"],
            "prompt_tokens": ai_result["prompt_tokens"],
            "completion_tokens": ai_result["completion_tokens"],
            "total_tokens": ai_result["total_tokens"],
            "compiled": False,
        }

        print(f"    Latency:      {m['latency_s']:.2f}s")
        print(f"    Prompt tokens: {m['prompt_tokens']}")
        print(f"    Completion:    {m['completion_tokens']}")
        print(f"    Total tokens:  {m['total_tokens']}")
        if m["completion_tokens"] > 0:
            tps = m["completion_tokens"] / m["latency_s"]
            m["tokens_per_sec"] = tps
            print(f"    Throughput:    {tps:.1f} tok/s")

        # Clean up response (remove markdown fences if present)
        dsl_source = raw_response.strip()
        if dsl_source.startswith("```"):
            lines = dsl_source.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            dsl_source = "\n".join(lines)

        dsl_chars = len(dsl_source)
        m["dsl_chars"] = dsl_chars

        print(f"\n[2] LLM generated DSL ({dsl_chars} chars):")
        print("-" * 40)
        print(dsl_source)
        print("-" * 40)

        # 2. Parse + Validate + Compile
        print("\n[3] Compiling...")
        t0 = time.perf_counter()
        success, output = try_compile(dsl_source)
        compile_time = time.perf_counter() - t0
        m["compile_time_ms"] = compile_time * 1000

        if success:
            results["success"] += 1
            m["compiled"] = True
            print(f"    COMPILE OK ({compile_time*1000:.1f}ms)")
            print()
            data = json.loads(output.split("\n\n")[0])
            ops = data["operationUpdate"]["operations"]
            m["num_operations"] = len(ops)
            jsonl_compact = Compiler().compile(parse(dsl_source))
            m["jsonl_chars"] = len(jsonl_compact)
            m["compression"] = m["jsonl_chars"] / m["dsl_chars"] if m["dsl_chars"] else 0
            print(f"    Workflow: {data['operationUpdate']['workflowId']}")
            print(f"    Operations: {len(ops)}")
            for op in ops:
                op_type = list(op["operation"].keys())[0]
                print(f"      - {op['id']} ({op_type})")
            print(f"    DSL size:  {dsl_chars} chars")
            print(f"    JSONL size: {m['jsonl_chars']} chars")
            print(f"    Ratio:     DSL is {m['compression']:.1f}x the JSONL size")
        else:
            if "PARSE" in output:
                results["parse_fail"] += 1
            else:
                results["validation_fail"] += 1
            print(f"    {output}")

        metrics.append(m)

    # Summary
    total = len(SCENARIOS)
    ok = [m for m in metrics if m["compiled"]]

    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"  Total scenarios:     {total}")
    print(f"  Compiled OK:         {results['success']}/{total}")
    print(f"  Parse failures:      {results['parse_fail']}/{total}")
    print(f"  Validation failures: {results['validation_fail']}/{total}")
    print(f"  Success rate:        {results['success']/total*100:.0f}%")

    if metrics:
        print(f"\n--- Token Usage ---")
        total_prompt = sum(m["prompt_tokens"] for m in metrics)
        total_completion = sum(m["completion_tokens"] for m in metrics)
        total_all = sum(m["total_tokens"] for m in metrics)
        avg_latency = sum(m["latency_s"] for m in metrics) / len(metrics)
        print(f"  Total prompt tokens:     {total_prompt:,}")
        print(f"  Total completion tokens: {total_completion:,}")
        print(f"  Total tokens:            {total_all:,}")
        print(f"  Avg latency per call:    {avg_latency:.2f}s")
        if total_completion > 0:
            total_time = sum(m["latency_s"] for m in metrics)
            print(f"  Avg throughput:          {total_completion/total_time:.1f} tok/s")

        # System prompt overhead
        sys_tokens = len(SYSTEM_PROMPT.split())  # rough estimate
        print(f"\n--- System Prompt ---")
        print(f"  System prompt chars:     {len(SYSTEM_PROMPT):,}")
        print(f"  Prompt tokens (1st call): {metrics[0]['prompt_tokens']:,}")
        print(f"  Completion tokens (avg):  {total_completion // len(metrics):,}")
        prompt_pct = metrics[0]["prompt_tokens"] / metrics[0]["total_tokens"] * 100 if metrics[0]["total_tokens"] else 0
        print(f"  Prompt % of total:        {prompt_pct:.0f}%")

    if ok:
        print(f"\n--- Compilation ---")
        avg_compile = sum(m["compile_time_ms"] for m in ok) / len(ok)
        avg_ops = sum(m["num_operations"] for m in ok) / len(ok)
        avg_dsl = sum(m["dsl_chars"] for m in ok) / len(ok)
        avg_jsonl = sum(m["jsonl_chars"] for m in ok) / len(ok)
        avg_ratio = sum(m["compression"] for m in ok) / len(ok)
        print(f"  Avg compile time:        {avg_compile:.1f}ms")
        print(f"  Avg operations/workflow: {avg_ops:.1f}")
        print(f"  Avg DSL size:            {avg_dsl:.0f} chars")
        print(f"  Avg JSONL size:          {avg_jsonl:.0f} chars")
        print(f"  Avg JSONL/DSL ratio:     {avg_ratio:.2f}x")

    print(f"{'='*70}")


if __name__ == "__main__":
    main()
