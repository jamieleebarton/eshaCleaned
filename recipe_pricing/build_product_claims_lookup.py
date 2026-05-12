#!/usr/bin/env python3
"""Build a per-UPC claims lookup so the calculator can filter products
by user facets at query time.

Claims are extracted in api_cache_taxonomy_v2.csv (field `claims` —
pipe-separated). priced_products_v2.db has UPCs that match. We index
claims by UPC and emit a sidecar CSV the calculator loads.

Output: recipe_pricing/product_claims.csv
  columns: upc, claims (pipe-separated)
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT = ROOT / "recipe_pricing" / "product_claims.csv"


def parse_upc_from_fdc_id(fdc_id: str) -> str:
    """api_cache fdc_id is like 'WM-78742259208' or 'KR-1234567'.
    We strip the prefix to get the UPC string."""
    fdc_id = (fdc_id or "").strip()
    m = re.match(r"^(?:WM|KR)-(.+)$", fdc_id)
    if m:
        return m.group(1)
    return fdc_id


def main() -> int:
    # api_cache and priced_products use different ID systems but share product
    # names. Join on name (case-insensitive, trim whitespace).
    print("indexing priced_products by name...", file=sys.stderr)
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("SELECT upc, name FROM priced_products WHERE name IS NOT NULL")
    name_to_upcs: dict[str, list[str]] = {}
    for upc, name in cur.fetchall():
        if not name:
            continue
        key = name.strip().lower()
        name_to_upcs.setdefault(key, []).append(upc)
    print(f"  {sum(len(v) for v in name_to_upcs.values()):,} priced_products rows under {len(name_to_upcs):,} unique names", file=sys.stderr)

    # Walk api_cache rows; for each row with claims, find matching upcs by name
    print("matching api_cache claims to priced_products by name...", file=sys.stderr)
    n_rows = 0
    n_with_claims = 0
    n_matched_upcs = 0
    seen_upc_claims: dict[str, str] = {}
    with API.open() as fin:
        reader = csv.DictReader(fin)
        for row in reader:
            n_rows += 1
            claims = (row.get("claims") or "").strip()
            if not claims:
                continue
            n_with_claims += 1
            title = (row.get("title") or "").strip().lower()
            if not title:
                continue
            for upc in name_to_upcs.get(title, []):
                # Don't overwrite — keep the longest claims string (most info)
                existing = seen_upc_claims.get(upc, "")
                if len(claims) > len(existing):
                    seen_upc_claims[upc] = claims
                n_matched_upcs += 1

    with OUT.open("w", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=["upc", "claims"])
        writer.writeheader()
        for upc, claims in seen_upc_claims.items():
            writer.writerow({"upc": upc, "claims": claims})

    print(f"\napi_cache rows scanned:       {n_rows:,}", file=sys.stderr)
    print(f"with claims:                   {n_with_claims:,}", file=sys.stderr)
    print(f"upcs claimed-tagged:           {len(seen_upc_claims):,}", file=sys.stderr)
    print(f"  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
