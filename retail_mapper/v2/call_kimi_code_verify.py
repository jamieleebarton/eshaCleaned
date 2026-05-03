#!/usr/bin/env python3
"""For each flagged code mismatch, ask Kimi whether the (title, code, desc)
mapping is conceptually correct. If wrong, get a plain-English description
of what the right concept should be.

Input:  retail_mapper/v2/code_concept_mismatch_report.csv
Output: retail_mapper/v2/code_verify_decisions.jsonl
  Each line: {fdc_id, title, code_type, code, code_desc, verdict, suggested_concept}
  verdict: "correct" | "wrong" | "unclear"

We dedupe by (code_type, code, title-prefix) to keep cost low.
Kimi is invoked via the local CLI in --print mode.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path(__file__).resolve().parent
SRC = V2 / "code_concept_mismatch_report.csv"
OUT = V2 / "code_verify_decisions.jsonl"

csv.field_size_limit(sys.maxsize)


def _title_key(t: str) -> str:
    t = (t or "").lower().split(",")[0]
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:40]


def _build_groups() -> list[dict]:
    """Group mismatches by (code_type, code, title-prefix). One Kimi call per group."""
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr); sys.exit(1)
    groups: dict[tuple, dict] = {}
    with SRC.open() as fh:
        for r in csv.DictReader(fh):
            k = (r["code_type"], r["code"], _title_key(r["title"]))
            if k in groups:
                groups[k]["_member_fdcs"].append(r["fdc_id"])
            else:
                groups[k] = {
                    "title": r["title"],
                    "canonical_path": r["canonical_path"],
                    "code_type": r["code_type"],
                    "code": r["code"],
                    "code_desc": r["code_desc"],
                    "mismatch_reason": r["mismatch_reason"],
                    "_member_fdcs": [r["fdc_id"]],
                }
    return list(groups.values())


def _query_kimi(items: list[dict]) -> str:
    """One Kimi call covers up to ~50 items. Returns Kimi's stdout."""
    payload = "\n".join(
        f"[{i}] title={it['title'][:80]!r}  code={it['code_type']}={it['code']}  desc={it['code_desc'][:80]!r}"
        for i, it in enumerate(items)
    )
    prompt = f"""You verify whether a food-database code (FNDDS/SR28/ESHA) conceptually
matches a SKU title. For each item below, return JSON of the form:
[{{"i": <index>, "verdict": "correct"|"wrong"|"unclear", "suggested": "<short
concept if wrong, else empty string>"}}]

VERDICT RULES:
- "correct" if the code's description IS conceptually a reasonable match for the title
  (allow some looseness — a brand "ROASTED CASHEWS" matched to "Nuts, cashews, dry
  roasted" is correct even if the brand uses different wording).
- "wrong" if the code is a clearly different food/state (e.g., title is "RAW CASHEWS"
  but code is "Nuts, cashews, dry roasted" — wrong because raw vs roasted).
- "unclear" if the title is ambiguous or the code could go either way.

For "wrong" verdicts, "suggested" should be a 3-8 word plain-English description of
the right concept (e.g., "Nuts, cashews, raw, unsalted").

Items:
{payload}

Return JSON array only, no other text.
"""
    proc = subprocess.run(
        ["kimi", "--print", "--quiet", "-p", prompt],
        capture_output=True, text=True, timeout=180,
    )
    return proc.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap number of groups")
    ap.add_argument("--batch-size", type=int, default=20)
    args = ap.parse_args()

    groups = _build_groups()
    print(f"Loaded {len(groups):,} unique (code_type, code, title) groups")

    # Already-decided
    done_keys = set()
    if OUT.exists():
        with OUT.open() as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    done_keys.add((d["code_type"], d["code"], _title_key(d["title"])))
                except json.JSONDecodeError:
                    continue
    todo = [g for g in groups if (g["code_type"], g["code"], _title_key(g["title"])) not in done_keys]
    if args.limit:
        todo = todo[:args.limit]
    print(f"todo: {len(todo):,}  done: {len(done_keys):,}")

    n_done = 0
    with OUT.open("a") as fh:
        for batch_start in range(0, len(todo), args.batch_size):
            batch = todo[batch_start:batch_start + args.batch_size]
            try:
                resp = _query_kimi(batch)
            except subprocess.TimeoutExpired:
                print(f"  batch {batch_start}: timeout, skipping")
                continue
            # Extract JSON array from response
            m = re.search(r"\[\s*\{.*?\}\s*\]", resp, re.DOTALL)
            if not m:
                print(f"  batch {batch_start}: no JSON in response, skipping")
                continue
            try:
                decisions = json.loads(m.group(0))
            except json.JSONDecodeError as e:
                print(f"  batch {batch_start}: JSON parse error: {e}")
                continue
            for d in decisions:
                idx = d.get("i")
                if not isinstance(idx, int) or idx >= len(batch):
                    continue
                item = batch[idx]
                rec = {
                    **item,
                    "verdict": d.get("verdict", "unclear"),
                    "suggested": d.get("suggested", ""),
                }
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                n_done += 1
            print(f"  [{batch_start + len(batch):>5,}/{len(todo):,}]  done={n_done:,}")


if __name__ == "__main__":
    main()
