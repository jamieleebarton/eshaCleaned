#!/usr/bin/env python3
"""Build the JSONL input for DeepSeek FNDDS re-classification.

Groups the 146K disagreements in `fndds_disagreements.csv` by (ours_code,
master_code). For each pattern, gathers up to 15 representative SKUs with
full evidence (title, branded_food_category, ingredients, brand, current
canonical_path). Writes one JSON line per cluster.

Output: retail_mapper/v2/fndds_cluster_input.jsonl

Read-only.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DISAGREEMENTS = V2 / "fndds_disagreements.csv"
AUDIT = V2 / "full_corpus_audit.csv"
DB = REPO / "data" / "master_products.db"
OUT = V2 / "fndds_cluster_input.jsonl"

SAMPLES_PER_CLUSTER = 15

csv.field_size_limit(sys.maxsize)


def main() -> None:
    if not DISAGREEMENTS.exists():
        raise SystemExit(f"missing {DISAGREEMENTS}")
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")
    if not DB.exists():
        raise SystemExit(f"missing {DB}")

    # 1. Load disagreement rows; group by (ours_code, master_code)
    print(f"  reading {DISAGREEMENTS.name}")
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with DISAGREEMENTS.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["ours_code"], row["master_code"])
            by_pair[key].append(row)
    print(f"    {sum(len(v) for v in by_pair.values()):,} disagreements across "
          f"{len(by_pair):,} (ours_code, master_code) pairs")

    # 2. Index audit CSV for branded_food_category lookups
    print(f"  indexing {AUDIT.name} for BFC + path...")
    audit_lookup: dict[str, dict] = {}
    needed_fdcs: set[str] = {r["fdc_id"] for rows in by_pair.values() for r in rows}
    with AUDIT.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fdc = row.get("fdc_id", "")
            if fdc in needed_fdcs:
                audit_lookup[fdc] = {
                    "branded_food_category": row.get("branded_food_category", ""),
                    "canonical_path": row.get("canonical_path", ""),
                }
    print(f"    {len(audit_lookup):,} fdc_ids matched")

    # 3. Pull ingredients + brand from master_products.db
    print(f"  loading master_products.db ingredients/brand for {len(needed_fdcs):,} fdc_ids...")
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    chunks = list(needed_fdcs)
    master_lookup: dict[str, dict] = {}
    for i in range(0, len(chunks), 500):
        batch = chunks[i:i + 500]
        placeholders = ",".join("?" * len(batch))
        c.execute(f"""
            SELECT fdc_id, ingredients_clean, ingredients, brand_name, brand_owner
            FROM products
            WHERE fdc_id IN ({placeholders})
        """, batch)
        for fdc, ic, ir, bn, bo in c.fetchall():
            master_lookup[str(fdc)] = {
                "ingredients_clean": ic or "",
                "ingredients_raw": ir or "",
                "brand_name": bn or "",
                "brand_owner": bo or "",
            }
    conn.close()
    print(f"    {len(master_lookup):,} fdc_ids found in master DB")

    # 4. For each cluster, take 15 representative SKUs (sorted by fdc for
    #    determinism so reruns produce stable input)
    print(f"  sampling up to {SAMPLES_PER_CLUSTER} SKUs per cluster...")
    n_written = 0
    with OUT.open("w", encoding="utf-8") as fh_out:
        # sort pairs by descending cluster size so the LLM tackles the
        # high-impact patterns first
        sorted_pairs = sorted(by_pair.items(), key=lambda kv: -len(kv[1]))
        for (ours_code, master_code), rows in sorted_pairs:
            ours_desc = rows[0]["ours_desc"]
            master_desc = rows[0]["master_desc"]
            n_total = len(rows)
            # Pick the first SAMPLES_PER_CLUSTER alphabetically by fdc_id
            samples_rows = sorted(rows, key=lambda r: r["fdc_id"])[:SAMPLES_PER_CLUSTER]
            samples: list[dict] = []
            for r in samples_rows:
                fdc = r["fdc_id"]
                m = master_lookup.get(fdc, {})
                a = audit_lookup.get(fdc, {})
                # Truncate ingredients to keep token cost down
                ing = (m.get("ingredients_clean") or m.get("ingredients_raw") or "")[:400]
                samples.append({
                    "fdc_id": fdc,
                    "title": r["title"][:120],
                    "branded_food_category": a.get("branded_food_category", "")[:60],
                    "brand_name": m.get("brand_name", "")[:40],
                    "ingredients": ing,
                    "current_canonical_path": a.get("canonical_path", r.get("canonical_path", ""))[:120],
                })
            cluster = {
                "ours_code": ours_code,
                "ours_desc": ours_desc,
                "master_code": master_code,
                "master_desc": master_desc,
                "n_total_skus": n_total,
                "samples": samples,
            }
            fh_out.write(json.dumps(cluster, ensure_ascii=False) + "\n")
            n_written += 1
    print(f"  wrote {n_written:,} clusters to {OUT.name}")
    # Quick stats
    sizes = sorted([len(v) for v in by_pair.values()], reverse=True)
    print(f"  cluster size distribution: max={sizes[0]:,}, "
          f"top-10 covers {sum(sizes[:10]):,} rows ({100*sum(sizes[:10])/sum(sizes):.0f}%), "
          f"top-100 covers {sum(sizes[:100]):,} rows ({100*sum(sizes[:100])/sum(sizes):.0f}%)")


if __name__ == "__main__":
    main()
