#!/usr/bin/env python3
"""Enrich priced_products_v2.db with the consensus PID + canonical_path.

For every priced product whose UPC bridges to a master_products gtin_upc
(zero-stripped match), look up its fdc_id, then pull the consensus's
product_identity_fixed, canonical_path, fndds_code, sr28_code.

Adds columns:
  consensus_pid          — the deduplicated food identity ('Apple Juice')
  consensus_canonical    — full path ('Beverage > Juice > Apple Juice')
  consensus_fndds        — overrides the in-row htc-encoder fndds
  consensus_sr28         — same
  consensus_modifier     — flavor/variant from consensus
  consensus_flavor       —
  bridge_status          — 'bridged' | 'no_master' | 'no_consensus'
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
MASTER = ROOT / "data" / "master_products.db"
PRICED = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
CON = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"


def main() -> int:
    print("loading master_products bridge (gtin → fdc)...")
    mc = sqlite3.connect(str(MASTER))
    gtin_to_fdc: dict[str, int] = {}
    for u, f in mc.execute("SELECT gtin_upc, fdc_id FROM products WHERE fdc_id IS NOT NULL"):
        if u:
            gtin_to_fdc[u.lstrip("0")] = f
    print(f"  {len(gtin_to_fdc):,} GTIN → fdc_id mappings")

    print("loading consensus by fdc_id...")
    fdc_to_con: dict[int, dict] = {}
    with CON.open() as f:
        for row in csv.DictReader(f):
            try:
                fdc = int(row["fdc_id"])
            except (ValueError, TypeError):
                continue
            fdc_to_con[fdc] = {
                "pid": row.get("product_identity_fixed", ""),
                "canonical": row.get("canonical_path", ""),
                "fndds": row.get("fndds_code", ""),
                "sr28": row.get("sr28_code", ""),
                "modifier": row.get("modifier", ""),
                "flavor": row.get("flavor", ""),
            }
    print(f"  {len(fdc_to_con):,} consensus rows")

    print(f"enriching priced_products_v2.db...")
    prc = sqlite3.connect(str(PRICED))
    cur = prc.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(priced_products)")}
    for col, ddl in [
        ("consensus_pid",       "ALTER TABLE priced_products ADD COLUMN consensus_pid TEXT"),
        ("consensus_canonical", "ALTER TABLE priced_products ADD COLUMN consensus_canonical TEXT"),
        ("consensus_fndds",     "ALTER TABLE priced_products ADD COLUMN consensus_fndds TEXT"),
        ("consensus_sr28",      "ALTER TABLE priced_products ADD COLUMN consensus_sr28 TEXT"),
        ("consensus_modifier",  "ALTER TABLE priced_products ADD COLUMN consensus_modifier TEXT"),
        ("consensus_flavor",    "ALTER TABLE priced_products ADD COLUMN consensus_flavor TEXT"),
        ("bridge_status",       "ALTER TABLE priced_products ADD COLUMN bridge_status TEXT"),
    ]:
        if col not in cols:
            cur.execute(ddl)
    prc.commit()

    rows = cur.execute("SELECT rowid, upc FROM priced_products").fetchall()
    n = bridged = no_master = no_consensus = 0
    updates = []
    for rowid, upc in rows:
        n += 1
        if not upc:
            updates.append(("", "", "", "", "", "", "no_master", rowid))
            no_master += 1
            continue
        fdc = gtin_to_fdc.get(upc.lstrip("0"))
        if fdc is None:
            updates.append(("", "", "", "", "", "", "no_master", rowid))
            no_master += 1
            continue
        con = fdc_to_con.get(fdc)
        if con is None:
            updates.append(("", "", "", "", "", "", "no_consensus", rowid))
            no_consensus += 1
            continue
        updates.append((
            con["pid"], con["canonical"], con["fndds"], con["sr28"],
            con["modifier"], con["flavor"], "bridged", rowid,
        ))
        bridged += 1

    cur.executemany("""
        UPDATE priced_products
        SET consensus_pid=?, consensus_canonical=?, consensus_fndds=?,
            consensus_sr28=?, consensus_modifier=?, consensus_flavor=?,
            bridge_status=? WHERE rowid=?
    """, updates)
    prc.commit()

    cur.execute("CREATE INDEX IF NOT EXISTS idx_pp_consensus_pid ON priced_products(consensus_pid)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pp_bridge ON priced_products(bridge_status)")
    prc.commit()

    print()
    print(f"  total priced products:    {n:,}")
    print(f"  bridged to consensus:     {bridged:,}  ({bridged/n:.1%})")
    print(f"  no master fdc match:      {no_master:,}")
    print(f"  no consensus row:         {no_consensus:,}")

    # Show coverage by HTC group (food only)
    print(f"\n=== bridge rate by HTC group ===")
    for r in cur.execute("""
        SELECT htc_group,
               COUNT(*) AS total,
               SUM(CASE WHEN bridge_status='bridged' THEN 1 ELSE 0 END) AS bridged
        FROM priced_products
        WHERE htc_group NOT IN ('0','N')
        GROUP BY htc_group ORDER BY total DESC
    """):
        rate = r[2] / r[1] if r[1] else 0
        print(f"  {r[0]}: {r[2]:>6,} / {r[1]:>6,}  ({rate:.0%})")

    # Sample bridged rows
    print(f"\n=== sample bridged rows (the new join chain) ===")
    for r in cur.execute("""
        SELECT upc, substr(name,1,40), htc_code, consensus_pid, consensus_canonical
        FROM priced_products
        WHERE bridge_status='bridged'
        ORDER BY RANDOM() LIMIT 8
    """):
        print(f"  {r[0]}  {r[1]:<42}  htc={r[2]:<10}  pid={r[3]:<22}  path={r[4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
