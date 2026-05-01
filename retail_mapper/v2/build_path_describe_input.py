#!/usr/bin/env python3
"""Build per-SKU input for the two-pass DeepSeek path-describe pipeline.

Reads `correction_quality_report.csv` (the suspect list from
audit_correction_quality.py). For each row whose family is mismatched,
gather full evidence (title + ingredients + branded category + brand) and
write one JSON line per SKU.

Output: retail_mapper/v2/path_describe_input.jsonl

Pass-1 prompt (in call_deepseek_path_describe.py) will ask DeepSeek to
emit a canonical_path string in our top-down convention, given the
evidence + a short description of allowed top-levels.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SUSPECTS = V2 / "correction_quality_report.csv"
AUDIT = V2 / "full_corpus_audit.csv"
DB = REPO / "data" / "master_products.db"
OUT = V2 / "path_describe_input.jsonl"

csv.field_size_limit(sys.maxsize)


def main() -> None:
    if not SUSPECTS.exists():
        raise SystemExit(f"missing {SUSPECTS}")
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")

    # Get fdc_ids of suspect rows (family_mismatch only)
    suspects: dict[str, dict] = {}
    with SUSPECTS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if "family_mismatch" not in r["issue"]:
                continue
            suspects[r["fdc_id"]] = {
                "current_path": r["current_path"],
                "expected_family": r["expected_family"],
                "actual_family": r["actual_family"],
                "fndds_code": r["new_code"],
                "fndds_desc": r["new_desc"],
            }
    print(f"  family-mismatched rows: {len(suspects):,}")

    # Index audit for title + BFC
    audit: dict[str, dict] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            if fdc in suspects:
                audit[fdc] = {
                    "title": r.get("title", "")[:140],
                    "branded_food_category": r.get("branded_food_category", "")[:60],
                }

    # Pull ingredients + brand from master DB
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    fdcs = list(suspects.keys())
    master: dict[str, dict] = {}
    for i in range(0, len(fdcs), 500):
        batch = fdcs[i:i + 500]
        ph = ",".join("?" * len(batch))
        c.execute(f"""SELECT fdc_id, ingredients_clean, ingredients,
                              brand_name, brand_owner
                      FROM products WHERE fdc_id IN ({ph})""", batch)
        for fdc, ic, ir, bn, bo in c.fetchall():
            master[str(fdc)] = {
                "ingredients": (ic or ir or "")[:400],
                "brand_name": (bn or "")[:40],
                "brand_owner": (bo or "")[:40],
            }
    conn.close()
    print(f"  master DB matches: {len(master):,}")

    # Write JSONL
    n = 0
    with OUT.open("w", encoding="utf-8") as fh_out:
        for fdc, susp in suspects.items():
            a = audit.get(fdc, {})
            m = master.get(fdc, {})
            rec = {
                "fdc_id": fdc,
                "title": a.get("title", ""),
                "branded_food_category": a.get("branded_food_category", ""),
                "brand_name": m.get("brand_name", ""),
                "ingredients": m.get("ingredients", ""),
                "current_path": susp["current_path"],
                "current_fndds": susp["fndds_code"],
                "current_fndds_desc": susp["fndds_desc"],
            }
            fh_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"  wrote {n:,} SKUs to {OUT.name}")


if __name__ == "__main__":
    main()
