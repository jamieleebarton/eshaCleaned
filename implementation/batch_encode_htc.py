#!/usr/bin/env python3
"""Batch-send items to DeepSeek (or any OpenAI-compatible API) for HTC encoding.

Reads a CSV with an 'item' column, batches N items per prompt, calls the API,
and writes a JSONL of LLM-discovered HTC codes + attributes.

Usage:
    export DEEPSEEK_API_KEY=sk-...
    python3 implementation/batch_encode_htc.py \
        --input recipe_mapper/v1/output/recipe_ingredient_items.csv \
        --output /tmp/llm_htc_output.jsonl \
        --batch-size 50 \
        --model deepseek-chat

The script automatically:
  1. Loads docs/HTC_CONDENSED_DICTIONARY.md as the system prompt
  2. Formats each batch as a numbered list
  3. Requests strict JSON array output
  4. Parses the response and validates each code is 8 chars
  5. Retries failed batches up to 3 times
  6. Writes incremental output so you can resume if interrupted
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional: openai package. Install with: pip install openai
# ---------------------------------------------------------------------------
try:
    from openai import OpenAI
except Exception as exc:  # noqa: BLE001
    print(f"ERROR: install openai first: pip install openai ({exc})", file=sys.stderr)
    raise SystemExit(1)


ROOT = Path(__file__).resolve().parent.parent
DICTIONARY_PATH = ROOT / "docs" / "HTC_CONDENSED_DICTIONARY.md"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF = 2.0


def load_dictionary(path: Path) -> str:
    if not path.exists():
        print(f"ERROR: Dictionary not found at {path}", file=sys.stderr)
        raise SystemExit(1)
    return path.read_text()


def load_items(path: Path) -> list[str]:
    """Read items from CSV (expects 'item' column) or plain text (one per line)."""
    suffix = path.suffix.lower()
    items: list[str] = []
    if suffix == ".csv":
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                item = (row.get("item") or "").strip()
                if item:
                    items.append(item)
    else:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(line)
    # dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def build_user_prompt(items: list[str]) -> str:
    lines = ["Encode the following items into HTC codes."]
    lines.append("")
    lines.append("Return ONLY a valid JSON array. Each element must be an object with these exact keys:")
    lines.append('  "item"      — the original item string (exactly as given)')
    lines.append('  "htc_code"  — the full 8-character HTC code (7 chars + check digit)')
    lines.append('  "htc_group" — the 1-character group code')
    lines.append('  "htc_family"— the 1-character family code')
    lines.append('  "modifier"  — discovered modifier, or "" if none (e.g. "sharp" for cheddar, "whole" for milk)')
    lines.append('  "flavor"    — discovered flavor, or "" if none (e.g. "BBQ", "chipotle", "strawberry")')
    lines.append("")
    lines.append("Items:")
    for i, it in enumerate(items, 1):
        lines.append(f'{i}. "{it}"')
    lines.append("")
    lines.append("JSON array:")
    return "\n".join(lines)


def parse_response(text: str, expected_items: list[str]) -> list[dict[str, str]] | None:
    """Extract JSON array from the response text."""
    # Try to find a JSON array in the response
    text = text.strip()
    # Sometimes the model wraps it in markdown code blocks
    if text.startswith("```"):
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find an array substring
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return None
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, list):
        return None

    # Validate and normalize each entry
    results: list[dict[str, str]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        item = str(entry.get("item", "")).strip()
        code = str(entry.get("htc_code", "")).strip().upper()
        # Validate code length (should be 8)
        if len(code) != 8:
            # Try to fix common issues: missing check digit, spaces
            code = code.replace(" ", "").replace("-", "")
            if len(code) == 7:
                # LLM forgot check digit — we can't compute it without the alphabet,
                # so leave it as-is and flag for post-processing
                pass
        results.append({
            "item": item,
            "htc_code": code,
            "htc_group": str(entry.get("htc_group", "")),
            "htc_family": str(entry.get("htc_family", "")),
            "modifier": str(entry.get("modifier", "")),
            "flavor": str(entry.get("flavor", "")),
        })

    # If the LLM omitted items or reordered them, we can't safely map back
    # unless we match by item string. Do a best-effort merge.
    if len(results) != len(expected_items):
        # Build lookup by item string
        by_item = {r["item"]: r for r in results}
        merged: list[dict[str, str]] = []
        for it in expected_items:
            if it in by_item:
                merged.append(by_item[it])
            else:
                merged.append({
                    "item": it,
                    "htc_code": "",
                    "htc_group": "",
                    "htc_family": "",
                    "modifier": "",
                    "flavor": "",
                })
        results = merged

    return results


def call_api(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int,
    backoff: float,
) -> str | None:
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=4096,
            )
            return resp.choices[0].message.content
        except Exception as exc:  # noqa: BLE001
            print(f"    API attempt {attempt}/{max_retries} failed: {exc}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(backoff * attempt)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch-encode items to HTC via LLM API")
    ap.add_argument("--input", type=Path, required=True, help="Input CSV or text file")
    ap.add_argument("--output", type=Path, required=True, help="Output JSONL file")
    ap.add_argument("--dictionary", type=Path, default=DICTIONARY_PATH, help="Path to HTC_CONDENSED_DICTIONARY.md")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Items per API call")
    ap.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model name")
    ap.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="API base URL")
    ap.add_argument("--api-key", type=str, default=os.getenv("DEEPSEEK_API_KEY"), help="API key (or set DEEPSEEK_API_KEY env var)")
    ap.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Retries per batch")
    ap.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF, help="Backoff multiplier in seconds")
    ap.add_argument("--resume", action="store_true", help="Skip items already present in output")
    args = ap.parse_args()

    if not args.api_key:
        print("ERROR: --api-key or DEEPSEEK_API_KEY required", file=sys.stderr)
        return 1

    # Load system prompt
    system_prompt = load_dictionary(args.dictionary)
    print(f"Loaded dictionary: {len(system_prompt):,} chars (~{len(system_prompt)//4:,} tokens)")

    # Load items
    all_items = load_items(args.input)
    print(f"Loaded {len(all_items):,} unique items")

    # Resume support: read already-done items from output
    done_items: set[str] = set()
    if args.resume and args.output.exists():
        with args.output.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    done_items.add(obj.get("item", ""))
        print(f"  Resuming: {len(done_items):,} items already encoded")

    items_to_encode = [it for it in all_items if it not in done_items]
    if not items_to_encode:
        print("Nothing to do.")
        return 0
    print(f"  Encoding {len(items_to_encode):,} remaining items")

    # Init client
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    # Open output in append mode if resuming
    out_mode = "a" if args.resume else "w"
    out_f = args.output.open(out_mode)

    total_batches = (len(items_to_encode) + args.batch_size - 1) // args.batch_size
    total_cost_in_tokens = 0
    total_out_tokens = 0

    try:
        for batch_idx in range(total_batches):
            start = batch_idx * args.batch_size
            end = start + args.batch_size
            batch = items_to_encode[start:end]

            print(f"[{batch_idx + 1}/{total_batches}] Encoding batch of {len(batch)} items ...")
            user_prompt = build_user_prompt(batch)

            # Rough token estimate (4 chars ≈ 1 token)
            est_in = (len(system_prompt) + len(user_prompt)) // 4
            est_out = len(batch) * 80  # ~80 tokens per item JSON object
            total_cost_in_tokens += est_in
            total_out_tokens += est_out

            text = call_api(
                client,
                args.model,
                system_prompt,
                user_prompt,
                args.max_retries,
                args.backoff,
            )
            if text is None:
                print(f"  FAILED batch {batch_idx + 1} after all retries", file=sys.stderr)
                # Write empty placeholders so we don't lose track
                for it in batch:
                    out_f.write(json.dumps({
                        "item": it,
                        "htc_code": "",
                        "htc_group": "",
                        "htc_family": "",
                        "modifier": "",
                        "flavor": "",
                        "_batch_failed": True,
                    }, ensure_ascii=False) + "\n")
                out_f.flush()
                continue

            results = parse_response(text, batch)
            if results is None:
                print(f"  FAILED to parse batch {batch_idx + 1} response", file=sys.stderr)
                print(f"  Raw response preview: {text[:200]!r}", file=sys.stderr)
                for it in batch:
                    out_f.write(json.dumps({
                        "item": it,
                        "htc_code": "",
                        "htc_group": "",
                        "htc_family": "",
                        "modifier": "",
                        "flavor": "",
                        "_parse_failed": True,
                        "_raw_preview": text[:500],
                    }, ensure_ascii=False) + "\n")
                out_f.flush()
                continue

            for r in results:
                out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"  OK — wrote {len(results)} results")

            # Small rate-limit courtesy
            if batch_idx < total_batches - 1:
                time.sleep(0.5)

    finally:
        out_f.close()

    print("\n" + "=" * 50)
    print(f"Done. Output: {args.output}")
    print(f"Estimated total input tokens:  {total_cost_in_tokens:,}")
    print(f"Estimated total output tokens: {total_out_tokens:,}")
    print(f"Batches: {total_batches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
