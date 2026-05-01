#!/usr/bin/env python3
"""Build DeepSeek input for the borderline-centroid cases.

Inputs:
  - retail_mapper/v2/iterative_deep_reroutes.csv (stage C only)
  - retail_mapper/v2/full_corpus_audit.csv (current paths)
  - data/master_products.db (ingredients + brand)

For each Stage C candidate, package: title, ingredients, BFC, brand,
current_path (where it sits now), proposed_path (centroid's pick).

Output: retail_mapper/v2/adjudication_input.jsonl
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CANDIDATES = V2 / "iterative_deep_reroutes.csv"
AUDIT = V2 / "full_corpus_audit.csv"
DB = REPO / "data" / "master_products.db"
OUT = V2 / "adjudication_input.jsonl"

csv.field_size_limit(sys.maxsize)


def main() -> None:
    # 1. Load Stage C candidates only (the risky ones)
    candidates: list[dict] = []
    with CANDIDATES.open() as fh:
        for r in csv.DictReader(fh):
            if r["stage"] != "C_relaxed":
                continue
            candidates.append({
                "fdc_id": r["fdc_id"],
                "title": r["title"],
                "current_path": r["old_path"],
                "centroid_proposed_path": r["new_path"],
                "current_sim": r["current_sim"],
                "proposed_sim": r["proposed_sim"],
                "improvement": r["improvement"],
            })
    print(f"  Stage C candidates: {len(candidates):,}")

    # 2. Index BFC from audit
    fdcs = {c["fdc_id"] for c in candidates}
    bfc_map: dict[str, str] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("fdc_id") in fdcs:
                bfc_map[r["fdc_id"]] = r.get("branded_food_category", "")[:60]

    # 3. Load ingredients + brand from master DB
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    master: dict[str, dict] = {}
    fdcs_list = list(fdcs)
    for i in range(0, len(fdcs_list), 500):
        batch = fdcs_list[i:i + 500]
        ph = ",".join("?" * len(batch))
        c.execute(f"""SELECT fdc_id, ingredients_clean, ingredients,
                              brand_name FROM products WHERE fdc_id IN ({ph})""", batch)
        for fdc, ic, ir, bn in c.fetchall():
            master[str(fdc)] = {
                "ingredients": (ic or ir or "")[:300],
                "brand_name": (bn or "")[:40],
            }
    conn.close()
    print(f"  master DB hits: {len(master):,}")

    # 4. Write JSONL
    n = 0
    with OUT.open("w", encoding="utf-8") as fh:
        for cand in candidates:
            fdc = cand["fdc_id"]
            m = master.get(fdc, {})
            rec = {
                "fdc_id": fdc,
                "title": cand["title"],
                "branded_food_category": bfc_map.get(fdc, ""),
                "brand_name": m.get("brand_name", ""),
                "ingredients": m.get("ingredients", ""),
                "current_path": cand["current_path"],
                "centroid_proposed_path": cand["centroid_proposed_path"],
                "current_sim_to_centroid": cand["current_sim"],
                "proposed_sim_to_centroid": cand["proposed_sim"],
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"  wrote {n:,} adjudication cases to {OUT.name}")


if __name__ == "__main__":
    main()
