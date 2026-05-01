#!/usr/bin/env python3
"""Re-run a specific list of fdc_ids through the LLM with the current prompt.

Used to test prompt changes against a small handful of cases without rebuilding
the whole 100-row sample. Writes to a NEW file — never touches existing JSONLs.

Usage:
  NEBIUS_API_KEY=... python3 retail_mapper/v2/rerun_specific_fdcs.py \
      --fdc 2149580 --fdc 2082527 --fdc 2522991 ... \
      --out retail_mapper/v2/granularity_test.live.jsonl
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_CSV = V2 / "retail_leaf_v2_enriched_v2.csv"

csv.field_size_limit(sys.maxsize)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fdc", action="append", required=True,
                        help="fdc_id to rerun. Can be repeated.")
    parser.add_argument("--from-file", type=str, default=None,
                        help="Optional file with fdc_ids one per line (in addition to --fdc args).")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, required=True,
                        help="Output JSONL — will be created or appended to (resume-safe).")
    parser.add_argument("--model", default="deepseek-ai/DeepSeek-V3.2")
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    parser.add_argument("--retry-attempts", type=int, default=4)
    args = parser.parse_args()

    if args.out.exists():
        print(f"out file {args.out} already exists; will append (resume mode)", file=sys.stderr)

    fdcs = list(args.fdc)
    if args.from_file:
        with open(args.from_file) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    fdcs.append(line)

    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("NEBIUS_API_KEY not set")

    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)

    # Pull rows from CSV
    needed = set(map(str, fdcs))
    rows: dict[str, dict] = {}
    with args.csv.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("fdc_id") in needed:
                rows[row["fdc_id"]] = row
                if len(rows) == len(needed):
                    break
    missing = needed - set(rows)
    if missing:
        print(f"warning: {len(missing)} fdc_ids not found in CSV: {sorted(missing)[:5]}...", file=sys.stderr)

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
    client = OpenAI(api_key=api_key, base_url="https://api.studio.nebius.com/v1/")

    outputs = list(existing)
    todo = [(fdc, rows[fdc]) for fdc in fdcs if fdc in rows and fdc not in completed]
    print(f"running {len(todo)} cases (skipping {len(fdcs) - len(todo)} already completed/missing)", file=sys.stderr)

    for idx, (fdc, row) in enumerate(todo, 1):
        msgs = [
            {"role": "system", "content": m.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "source_row": m.compact_source_row(row),
            }, indent=2, sort_keys=True)},
        ]
        raw = ""
        parsed = {}
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
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for o in outputs:
                fh.write(json.dumps(o, sort_keys=True) + "\n")
        pid = (parsed.get("product_identity") or "?") if isinstance(parsed, dict) else "?"
        print(f"  [{idx}/{len(todo)}]  fdc={fdc}  identity={pid!r}")
        time.sleep(args.pause_seconds)

    print(f"\ndone. Wrote {len(outputs)} total rows to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
