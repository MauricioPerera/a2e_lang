"""Test: YAML mode — small LLMs generate workflows in YAML format.

Compares YAML mode vs DSL mode across multiple models.
YAML leverages knowledge models already have from training data.

Usage:
  set CLOUDFLARE_API_TOKEN=your-token
  python examples/test_yaml_mode.py
"""

import json
import os
import sys
import time
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2e_lang.yaml_mode import yaml_to_jsonl, YamlValidationError

# ── Config ───────────────────────────────────────────────────────────

ACCOUNT_ID = "091122c40cc6f8d0d421cbc90e2caca8"
MODELS = [
    "@cf/google/gemma-2b-it-lora",
    "@hf/nousresearch/hermes-2-pro-mistral-7b",
    "@cf/ibm-granite/granite-4.0-h-micro",
]

# ── System prompt — drastically simpler than DSL mode ────────────────

SYSTEM_PROMPT = """Generate YAML workflows. Output ONLY valid YAML, no explanation.

Step types: fetch, filter, transform, merge, store

Example:
workflow: user-pipeline
steps:
  - id: get_users
    type: fetch
    method: GET
    url: https://api.example.com/users
    output: /workflow/users

  - id: active_only
    type: filter
    input: /workflow/users
    where: "status == active"
    output: /workflow/active

  - id: save
    type: store
    input: /workflow/active
    key: active-users"""

# ── Scenarios (same as DSL test) ─────────────────────────────────────

SCENARIOS = [
    "Fetch a list of products from an e-commerce API, filter products that cost more than 50 dollars, sort them by price descending, and store the result.",
    "Get weather data from an API, check if temperature is above 30, if yes store a heat alert, if no store normal status.",
    "Fetch users and orders from two different APIs, merge them together, and store the combined data.",
]

# ── API call ─────────────────────────────────────────────────────────

def call_workers_ai(token: str, model: str, user_message: str) -> dict:
    """Call Workers AI and return response + metrics."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{model}"
    t0 = time.perf_counter()
    response = httpx.post(
        url,
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
            "temperature": 0.2,
        },
        timeout=90.0,
    )
    latency = time.perf_counter() - t0
    response.raise_for_status()
    data = response.json()
    result = data.get("result", {})

    # Extract text: support both simple (response) and OpenAI (choices) format
    text = ""
    if isinstance(result, dict):
        text = result.get("response", "")
        if not text and "choices" in result:
            choices = result["choices"]
            if choices and isinstance(choices, list):
                text = choices[0].get("message", {}).get("content", "")

    # Extract usage
    usage = {}
    if isinstance(result, dict):
        usage = result.get("usage", {})

    return {
        "text": text,
        "latency_s": latency,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def extract_yaml(text: str) -> str:
    """Extract YAML from response, stripping markdown fences if present."""
    text = text.strip()
    # Strip ```yaml ... ``` fences
    if "```" in text:
        lines = text.split("\n")
        in_block = False
        yaml_lines = []
        for line in lines:
            if line.strip().startswith("```yaml") or line.strip() == "```yml":
                in_block = True
                continue
            if line.strip() == "```":
                if in_block:
                    break
                continue
            if in_block:
                yaml_lines.append(line)
        if yaml_lines:
            return "\n".join(yaml_lines)
    # If starts with 'workflow:' it's already clean YAML
    if text.startswith("workflow:") or text.startswith("workflow :"):
        return text
    # Try to find 'workflow:' anywhere in the text
    idx = text.find("workflow:")
    if idx == -1:
        idx = text.find("workflow :")
    if idx >= 0:
        return text[idx:]
    return text


def try_compile(yaml_source: str) -> tuple[bool, str, str]:
    """Try to compile YAML source. Returns (success, jsonl_or_error, error_type)."""
    try:
        jsonl = yaml_to_jsonl(yaml_source)
        return True, jsonl, ""
    except YamlValidationError as exc:
        return False, str(exc), "validation"
    except Exception as exc:
        return False, str(exc), "error"


# ── Main ─────────────────────────────────────────────────────────────

def run_model(token: str, model: str) -> dict:
    """Run all scenarios for a given model. Returns summary dict."""
    model_short = model.split("/")[-1]
    print(f"\n{'='*70}")
    print(f"  MODEL: {model_short}")
    print(f"{'='*70}")

    results = {"model": model, "ok": 0, "fail_parse": 0, "fail_val": 0,
               "total_latency": 0, "total_prompt": 0, "total_completion": 0,
               "total_tokens": 0, "scenarios": []}

    for i, scenario in enumerate(SCENARIOS):
        print(f"\n--- Scenario {i+1}/{len(SCENARIOS)} ---")
        print(f"  Request: {scenario[:80]}...")

        try:
            resp = call_workers_ai(token, model, scenario)
        except Exception as exc:
            print(f"  API ERROR: {exc}")
            results["fail_parse"] += 1
            continue

        raw_text = resp["text"]
        yaml_source = extract_yaml(raw_text)
        results["total_latency"] += resp["latency_s"]
        results["total_prompt"] += resp["prompt_tokens"]
        results["total_completion"] += resp["completion_tokens"]
        results["total_tokens"] += resp["total_tokens"]

        print(f"  Latency: {resp['latency_s']:.1f}s | Tokens: {resp['total_tokens']}")
        print(f"  Response ({len(raw_text)} chars):")
        # Show first 400 chars
        preview = yaml_source[:400]
        for line in preview.split("\n"):
            print(f"    {line}")
        if len(yaml_source) > 400:
            print(f"    ... ({len(yaml_source)} chars total)")

        ok, output, err_type = try_compile(yaml_source)
        if ok:
            results["ok"] += 1
            # Parse JSONL to count ops
            first_line = json.loads(output.split("\n")[0])
            ops = first_line["operationUpdate"]["operations"]
            print(f"  COMPILE OK ({len(ops)} operations)")
        else:
            if err_type == "validation":
                results["fail_val"] += 1
            else:
                results["fail_parse"] += 1
            print(f"  FAIL: {output[:120]}")

        results["scenarios"].append({
            "ok": ok,
            "latency": resp["latency_s"],
            "tokens": resp["total_tokens"],
        })

    return results


def main():
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        print("Set CLOUDFLARE_API_TOKEN env var")
        sys.exit(1)

    print("="*70)
    print("  a2e-lang YAML Mode — Multi-Model Benchmark")
    print(f"  System prompt: {len(SYSTEM_PROMPT)} chars (vs ~2,026 for DSL mode)")
    print(f"  Scenarios: {len(SCENARIOS)}")
    print("="*70)

    all_results = []
    for model in MODELS:
        result = run_model(token, model)
        all_results.append(result)

    # ── Summary table ─────────────────────────────────────────────
    n = len(SCENARIOS)
    print(f"\n{'='*70}")
    print("  COMPARATIVE RESULTS — YAML Mode")
    print(f"{'='*70}")
    print(f"  {'Model':<28} {'OK':>4} {'Rate':>6} {'Latency':>8} {'Tokens':>7}")
    print(f"  {'-'*28} {'----':>4} {'------':>6} {'--------':>8} {'-------':>7}")
    for r in all_results:
        name = r["model"].split("/")[-1][:28]
        rate = f"{r['ok']}/{n}"
        pct = f"{100*r['ok']/n:.0f}%"
        avg_lat = f"{r['total_latency']/n:.1f}s" if n else "N/A"
        print(f"  {name:<28} {rate:>4} {pct:>6} {avg_lat:>8} {r['total_tokens']:>7}")

    print(f"\n  System prompt tokens: ~{len(SYSTEM_PROMPT)//4} (estimated)")
    print(f"  DSL mode system prompt: ~506 tokens")
    print(f"  Reduction: {100*(1 - len(SYSTEM_PROMPT)/2026):.0f}%")
    print("="*70)


if __name__ == "__main__":
    main()
