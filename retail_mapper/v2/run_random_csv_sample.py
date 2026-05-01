#!/usr/bin/env python3
"""Honest test: random rows from the enriched CSV, no gold, raw LLM output.

Usage:
    NEBIUS_API_KEY=... python3 retail_mapper/v2/run_random_csv_sample.py \
        --n 100 \
        --out retail_mapper/v2/random_csv_sample.live.jsonl

What it does:
  1. Reads the enriched CSV.
  2. Picks N random rows (with seedable randomness for reproducibility).
  3. Builds the user payload with the EXACT same compact_source_row and
     SYSTEM_PROMPT used in production. No gold cases. No prompt examples
     tuned to specific brands.
  4. Calls DeepSeek-V3.2 once per row.
  5. Writes raw + parsed records to a NEW JSONL.
  6. Reports distinct product_identities and category_paths emitted, and
     any invalid retail_types.

The point: no overfitting, no opinionated gold, no hand-picked brands.
Whatever the model says, that's what we measure.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_CSV = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"
DEFAULT_BASE_URL = "https://api.studio.nebius.com/v1/"
DEFAULT_API_KEY_ENV = "NEBIUS_API_KEY"

csv.field_size_limit(sys.maxsize)


def load_module():
    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)
    return m


def reservoir_sample(csv_path: Path, n: int, seed: int, bfc_filter: str | None) -> list[dict]:
    """Reservoir-sample N rows uniformly from the CSV without loading it all.

    If bfc_filter is given, only rows whose branded_food_category contains
    that substring (case-insensitive) are eligible.
    """
    rng = random.Random(seed)
    reservoir: list[dict] = []
    seen = 0
    with csv_path.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("title"):
                continue
            if bfc_filter and bfc_filter.lower() not in (row.get("branded_food_category") or "").lower():
                continue
            seen += 1
            if len(reservoir) < n:
                reservoir.append(row)
            else:
                j = rng.randint(0, seen - 1)
                if j < n:
                    reservoir[j] = row
    print(f"reservoir-sampled {len(reservoir)} from {seen} eligible rows", file=sys.stderr)
    return reservoir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--bfc-filter", type=str, default=None,
                        help="Optional case-insensitive BFC substring filter (e.g. 'snack').")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="API base URL. Default Nebius. For DeepSeek official: https://api.deepseek.com")
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV,
                        help="Env var holding the API key. Default NEBIUS_API_KEY. Use DEEPSEEK_API_KEY for DeepSeek.")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output JSONL — must NOT exist (this script never overwrites).")
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    parser.add_argument("--retry-attempts", type=int, default=4)
    args = parser.parse_args()

    if args.out.exists():
        # Don't clobber. Resume by appending past completed cases.
        print(f"out file {args.out} already exists; will resume (skip cases already in it)", file=sys.stderr)

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"{args.api_key_env} not set")

    m = load_module()
    rows = reservoir_sample(args.csv, args.n, args.seed, args.bfc_filter)
    if not rows:
        print("no rows matched filter", file=sys.stderr); raise SystemExit(1)

    # Resume support
    completed: set[str] = set()
    existing: list[dict] = []
    if args.out.exists():
        with args.out.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                completed.add(str(d.get("fdc_id", "")))
                existing.append(d)

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=args.base_url)

    outputs = list(existing)
    for idx, row in enumerate(rows, 1):
        fdc = str(row.get("fdc_id") or "")
        if fdc in completed:
            continue
        msgs = [
            {"role": "system", "content": m.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "source_row": m.compact_source_row(row),
            }, indent=2, sort_keys=True)},
        ]
        for attempt in range(args.retry_attempts + 1):
            try:
                resp = client.chat.completions.create(
                    model=args.model,
                    messages=msgs,
                    temperature=0.0,
                    max_tokens=1200,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or ""
                try:
                    parsed = m.extract_json_object(raw)
                except ValueError as exc:
                    parsed = {"_parse_error": str(exc), "_raw_preview": raw[:200]}
                break
            except Exception as exc:
                if attempt >= args.retry_attempts:
                    raw = ""
                    parsed = {"_api_error": f"{type(exc).__name__}: {exc}"}
                    break
                time.sleep(2.0 * (2 ** attempt))
        outputs.append({
            "fdc_id": fdc,
            "title": row.get("title", ""),
            "branded_food_category": row.get("branded_food_category", ""),
            "raw": raw,
            "record": parsed,
        })
        # Persist after each — resumable + crash-resistant
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for o in outputs:
                fh.write(json.dumps(o, sort_keys=True) + "\n")
        print(f"  [{idx}/{len(rows)}]  fdc={fdc:>10s}  identity={(parsed.get('product_identity') or '?')!r}")
        time.sleep(args.pause_seconds)

    # Summary
    pids = Counter()
    cats = Counter()
    invalid_rt = []
    for o in outputs:
        rec = o.get("record", {})
        if "_parse_error" in rec or "_api_error" in rec:
            continue
        pid = rec.get("product_identity", "")
        cat = rec.get("category_path", "")
        rt = rec.get("retail_type", "")
        if pid:
            pids[pid] += 1
        if cat:
            cats[cat] += 1
        if rt not in m.RETAIL_TYPES:
            invalid_rt.append(f"{o.get('fdc_id')}: retail_type={rt!r}  title={o.get('title','')[:60]}")

    print()
    print("=" * 100)
    print(f"RESULTS  ({len(outputs)} rows; bfc_filter={args.bfc_filter!r})")
    print("=" * 100)
    print(f"distinct product_identities: {len(pids)}")
    print(f"distinct category_paths:     {len(cats)}")
    print(f"invalid retail_types:        {len(invalid_rt)}")
    print()
    print("Top 30 product_identities (frequency):")
    for pid, count in pids.most_common(30):
        print(f"  {count:>4d}  {pid}")
    print()
    if invalid_rt:
        print("Invalid retail_types:")
        for line in invalid_rt[:20]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
