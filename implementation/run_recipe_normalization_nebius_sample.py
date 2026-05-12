#!/usr/bin/env python3
"""Run the recipe-normalization prompt against a JSONL sample via Nebius.

The model sees only recipe title and ingredient lines. Stress labels stay in
the source fixture and are used later by the validator.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import certifi

from validate_recipe_normalization_nebius_output import load_jsonl, validate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT = ROOT / "implementation" / "RECIPE_NORMALIZATION_NEBIUS_PROMPT_DRAFT.md"
DEFAULT_SOURCE = ROOT / "implementation" / "output" / "recipe_normalization_prompt_test_pack.jsonl"
DEFAULT_OUT = ROOT / "implementation" / "output" / "recipe_normalization_nebius_candidate.jsonl"
DEFAULT_FINDINGS = ROOT / "implementation" / "output" / "recipe_normalization_nebius_candidate_findings.jsonl"
DEFAULT_BASE_URL = "https://api.studio.nebius.com/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2-fast"


def read_api_key(use_stdin: bool) -> str:
    if use_stdin:
        raw = sys.stdin.readline()
    else:
        raw = os.environ.get("NEBIUS_API_KEY", "")
    return "".join(str(raw).split())


def recipe_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipe_id": recipe.get("recipe_id"),
        "title": recipe.get("title"),
        "ingredients": [
            {
                "line_index": idx,
                "display": ing.get("display"),
                "item": ing.get("item"),
                "grams": ing.get("grams"),
            }
            for idx, ing in enumerate(recipe.get("ingredients") or [])
            if isinstance(ing, dict)
        ],
    }


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response was not a JSON object")
    return value


def call_nebius(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    recipe: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(recipe_payload(recipe), ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Nebius HTTP {exc.code}: {detail}") from exc

    content = response_body["choices"][0]["message"]["content"]
    return extract_json_object(content)


def write_validation_findings(source_rows: list[dict[str, Any]], candidate_path: Path, findings_path: Path) -> int:
    candidate_rows = load_jsonl(candidate_path)
    findings = validate(source_rows, candidate_rows)
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    with findings_path.open("w", encoding="utf-8") as f:
        for finding in findings:
            f.write(json.dumps(finding.__dict__, ensure_ascii=False) + "\n")
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    print(json.dumps({"validation_errors": errors, "validation_warnings": warnings, "findings": len(findings)}, indent=2))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--findings-out", type=Path, default=DEFAULT_FINDINGS)
    parser.add_argument("--base-url", default=os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("NEBIUS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-key-stdin", action="store_true", help="Read the Nebius API key from stdin instead of the environment.")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--dry-run", action="store_true", help="Print the first request payload and do not call Nebius.")
    parser.add_argument("--validate", action="store_true", help="Validate candidate output after the run.")
    args = parser.parse_args()

    source_rows = load_jsonl(args.source)
    selected = source_rows[args.start : args.start + args.limit]
    prompt = args.prompt.read_text(encoding="utf-8")

    if args.dry_run:
        first = selected[0] if selected else {}
        print(json.dumps({"model": args.model, "prompt_path": str(args.prompt), "recipe": recipe_payload(first)}, indent=2, ensure_ascii=False))
        return

    api_key = read_api_key(args.api_key_stdin)
    if not api_key:
        raise SystemExit("NEBIUS_API_KEY is not set. Export it or use --api-key-stdin.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with args.out.open("w", encoding="utf-8") as f:
        for recipe in selected:
            recipe_id = recipe.get("recipe_id")
            try:
                result = call_nebius(
                    api_key=api_key,
                    base_url=args.base_url,
                    model=args.model,
                    prompt=prompt,
                    recipe=recipe,
                    timeout=args.timeout,
                )
                if str(result.get("recipe_id")) != str(recipe_id):
                    result["recipe_id"] = recipe_id
                    result.setdefault("runner_warnings", []).append("model recipe_id did not match source; overwritten by runner")
            except Exception as exc:  # noqa: BLE001 - keep batch output inspectable.
                result = {
                    "recipe_id": recipe_id,
                    "title": recipe.get("title"),
                    "ingredients": [],
                    "runner_error": str(exc),
                }
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            completed += 1
            print(json.dumps({"completed": completed, "recipe_id": recipe_id}, ensure_ascii=False))
            if args.sleep:
                time.sleep(args.sleep)

    if args.validate:
        errors = write_validation_findings(selected, args.out, args.findings_out)
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
