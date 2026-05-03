#!/usr/bin/env python3
"""Apply Kimi's code-verify decisions to the audit.

For each "wrong" verdict, we have a plain-English suggested concept. We
write a per-fdc correction file that flags the wrong code AND records the
suggested concept (a human or a downstream tool can re-resolve to a
proper code by searching FNDDS/SR28/ESHA description databases for the
suggested concept).

This script does NOT auto-resolve to new codes (that requires the FNDDS/
SR28/ESHA description tables loaded). It produces:
  retail_mapper/v2/code_corrections.csv — one row per (fdc_id, code_type)
    that should be reviewed.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

V2 = Path(__file__).resolve().parent
DECISIONS = V2 / "code_verify_decisions.jsonl"
OUT = V2 / "code_corrections.csv"


def main() -> None:
    if not DECISIONS.exists():
        print(f"missing {DECISIONS}", file=sys.stderr); sys.exit(1)

    n_wrong = 0
    n_correct = 0
    n_unclear = 0
    rows = []
    with DECISIONS.open() as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            verdict = d.get("verdict", "")
            if verdict == "correct":
                n_correct += 1
                continue
            if verdict == "unclear":
                n_unclear += 1
                continue
            n_wrong += 1
            members = d.get("_member_fdcs", [])
            for fdc in members:
                rows.append({
                    "fdc_id": fdc,
                    "code_type": d["code_type"],
                    "current_code": d["code"],
                    "current_desc": d["code_desc"],
                    "suggested_concept": d.get("suggested", ""),
                    "title": d["title"],
                })

    cols = ["fdc_id", "code_type", "current_code", "current_desc",
            "suggested_concept", "title"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"verdicts: correct={n_correct:,}  wrong={n_wrong:,}  unclear={n_unclear:,}")
    print(f"wrote {len(rows):,} per-fdc corrections to {OUT}")


if __name__ == "__main__":
    main()
