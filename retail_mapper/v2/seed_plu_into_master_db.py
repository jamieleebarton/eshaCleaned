#!/usr/bin/env python3
"""Seed PLU produce stubs into master_products.db AND append rows to
full_corpus_audit.csv so they show up in the audit alongside packaged SKUs.

Reads:
  - data/ifps_plu_seed.csv  (PLU code, description, canonical_path)

Writes:
  - INSERT into master_products.db.products (skips existing)
  - APPEND rows to retail_mapper/v2/full_corpus_audit.csv

Each PLU becomes a marker SKU. fdc_id is "PLU<code>" so it's distinct from
real USDA FDC IDs. brand_type='produce_plu' matches Hestia's existing 3
PLU rows, so this layers on top without conflict.

Idempotent — re-running just skips PLUs already present.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "data" / "ifps_plu_seed.csv"
DB = REPO / "data" / "master_products.db"
AUDIT = REPO / "retail_mapper" / "v2" / "full_corpus_audit.csv"

csv.field_size_limit(sys.maxsize)


def synthesize_title(description: str) -> str:
    """Render the PLU description as a retail-shelf-style title.
    'Banana, medium' → 'BANANAS'
    'Onion, Yellow, medium' → 'YELLOW ONIONS'
    """
    desc = description.strip()
    parts = [p.strip() for p in desc.split(",")]
    base = parts[0] if parts else desc
    modifiers = [p for p in parts[1:] if p.lower() not in
                 {"medium", "large", "small", "whole", "head", "bunch",
                  "fresh", "fresh bunch"}]
    title = " ".join(modifiers + [base]) if modifiers else base
    # Pluralize bare singular nouns for retail convention
    plurals = {
        "Banana": "Bananas", "Apple": "Apples", "Orange": "Oranges",
        "Lemon": "Lemons", "Lime": "Limes", "Pear": "Pears", "Peach": "Peaches",
        "Tomato": "Tomatoes", "Potato": "Potatoes", "Onion": "Onions",
        "Cucumber": "Cucumbers", "Carrot": "Carrots", "Pepper": "Peppers",
        "Bell Pepper": "Bell Peppers",
    }
    for sing, plur in plurals.items():
        if title == sing:
            title = plur
            break
        if title.endswith(" " + sing):
            title = title[: -len(sing)] + plur
            break
    return title.upper()


def insert_into_master_db(conn: sqlite3.Connection, plu: str, desc: str,
                           fdc_id: str) -> bool:
    """Insert one PLU row into master_products.db. Returns True if inserted,
    False if the row already exists."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM products WHERE gtin_upc = ?", (f"PLU{plu}",))
    if cur.fetchone():
        return False
    cur.execute("""
        INSERT INTO products (gtin_upc, fdc_id, description, brand_owner,
                              brand_name, branded_food_category,
                              brand_type, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"PLU{plu}",
        fdc_id,
        desc,
        "PLU Produce",
        "PLU",
        "Pre-Packaged Fruit & Vegetables",
        "produce_plu",
        "ifps_plu_seed",
    ))
    return True


def synthesize_audit_row(audit_columns: list[str], plu: str, desc: str,
                          canonical_path: str, title: str,
                          fdc_id: str) -> dict[str, str]:
    """Build a row matching the audit CSV's column schema, with the PLU
    fields populated and everything else blank/sensible-default."""
    row = {col: "" for col in audit_columns}
    row["fdc_id"] = fdc_id
    row["title"] = title
    row["branded_food_category"] = "Pre-Packaged Fruit & Vegetables"
    row["retail_type"] = "single"
    row["category_path_original"] = canonical_path
    row["category_path_fixed"] = canonical_path
    row["product_identity_original"] = title.title()
    row["product_identity_fixed"] = title.title()
    row["canonical_path"] = canonical_path
    row["canonical_label"] = title.title()
    row["match_source"] = "ifps_plu_seed"
    row["matched_key"] = f"PLU{plu}"
    return row


def main() -> None:
    if not SEED.exists():
        raise SystemExit(f"missing {SEED}")
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")

    print(f"  reading {SEED.name}")
    plus: list[tuple[str, str, str]] = []
    with SEED.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            plu = row["plu_code"].strip()
            desc = row["description"].strip()
            cp = row["canonical_path"].strip()
            if plu and desc and cp:
                plus.append((plu, desc, cp))
    print(f"  {len(plus)} PLU entries loaded")

    # Insert into master_products.db
    print(f"  opening {DB.name}")
    conn = sqlite3.connect(DB)
    n_inserted = 0
    n_skipped = 0
    # fdc_id sequence — reuse Hestia's PLU id range. Existing PLUs occupy
    # 169997..172233. Start ours above any seen ID to avoid collision.
    cur = conn.cursor()
    cur.execute("SELECT MAX(fdc_id) FROM products")
    max_fdc = cur.fetchone()[0] or 0
    next_fdc = max(int(max_fdc) + 1, 9000000)  # use 9M+ range for new PLU stubs
    plu_to_fdc: dict[str, str] = {}
    for plu, desc, _cp in plus:
        # If row already exists in the DB by gtin, get its fdc_id
        cur.execute("SELECT fdc_id FROM products WHERE gtin_upc = ?", (f"PLU{plu}",))
        existing = cur.fetchone()
        if existing:
            plu_to_fdc[plu] = str(existing[0])
            n_skipped += 1
            continue
        fdc_id = str(next_fdc)
        next_fdc += 1
        if insert_into_master_db(conn, plu, desc, fdc_id):
            plu_to_fdc[plu] = fdc_id
            n_inserted += 1
    conn.commit()
    print(f"  master_products.db: {n_inserted} inserted, {n_skipped} already present")

    # Append audit-CSV rows for the NEW (or re-confirmed) PLU rows so they
    # appear in the next downstream consumer of the audit CSV.
    print(f"  reading audit CSV header {AUDIT.name}")
    with AUDIT.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        audit_columns = list(rdr.fieldnames or [])
    # Index existing audit rows so we don't duplicate
    existing_fdc: set[str] = set()
    with AUDIT.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            existing_fdc.add(row.get("fdc_id", ""))

    new_rows: list[dict] = []
    for plu, desc, cp in plus:
        fdc_id = plu_to_fdc.get(plu)
        if not fdc_id or fdc_id in existing_fdc:
            continue
        title = synthesize_title(desc)
        new_rows.append(synthesize_audit_row(audit_columns, plu, desc, cp,
                                              title, fdc_id))

    if new_rows:
        print(f"  appending {len(new_rows)} PLU rows to {AUDIT.name}")
        with AUDIT.open("a", encoding="utf-8", newline="") as fh:
            wtr = csv.DictWriter(fh, fieldnames=audit_columns)
            for r in new_rows:
                wtr.writerow(r)
    else:
        print(f"  no new rows to append (all PLUs already in audit CSV)")

    conn.close()


if __name__ == "__main__":
    main()
