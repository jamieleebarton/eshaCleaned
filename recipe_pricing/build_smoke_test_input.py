#!/usr/bin/env python3
"""Build a 25-row smoke-test CSV for run_full_csv_parallel.py.

Mixes:
  5 Walmart products that ALSO exist in FDC (we have the curated answer)
  5 Kroger  products that exist in FDC after dropping the check digit
  5 Walmart products NOT in FDC (truly novel)
  5 Kroger  products NOT in FDC
  10 recipe ingredients (clean strings — no brand)

Each row carries an extra column `_smoke_category` and `_known_fdc_id` so the
result analyzer can compare DeepSeek's answer to FDC's curated answer where
applicable. Those columns are ignored by the LLM driver (compact_source_row
only forwards SOURCE_FIELDS).
"""
from __future__ import annotations

import csv
import glob
import hashlib
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
API_CACHE = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
RECIPE_ITEMS = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_items.csv"
OUT_PATH = ROOT / "recipe_pricing" / "data" / "smoke_test_input.csv"

OUT_FIELDS = [
    "fdc_id", "gtin_upc", "title", "branded_food_category",
    "source", "_smoke_category", "_known_fdc_id",
]

RECIPE_PICKS = [
    "garlic",
    "almond milk",
    "kielbasa",
    "lit'l smokies sausages",
    "extra virgin olive oil",
    "sharp cheddar cheese",
    "ground cumin",
    "blueberries",
    "kosher salt",
    "rice vinegar",
]


def upc_keys(u: str) -> set[str]:
    s = u.strip()
    if not s:
        return set()
    out = {s}
    stripped = s.lstrip("0")
    out.add(stripped)
    if len(s) > 1: out.add(s[:-1])
    if len(stripped) > 1: out.add(stripped[:-1])
    for L in (11, 12, 13, 14):
        out.add(stripped.zfill(L))
        if len(stripped) > 1:
            out.add(stripped[:-1].zfill(L))
    return out


def main() -> int:
    # Build fdc UPC -> fdc_id index
    fdc_idx: dict[str, str] = {}
    for path in glob.glob(str(ROOT / "fixy_done" / "*.csv")):
        try:
            with open(path) as f:
                r = csv.DictReader(f)
                if "gtin_upc" not in (r.fieldnames or []):
                    continue
                for row in r:
                    upc = (row.get("gtin_upc") or "").strip()
                    fid = (row.get("fdc_id") or "").strip()
                    if upc and fid:
                        for k in upc_keys(upc):
                            fdc_idx.setdefault(k, fid)
        except Exception:
            pass

    print(f"FDC UPC variants indexed: {len(fdc_idx):,}", file=sys.stderr)

    def find_fdc(upc: str) -> str | None:
        for k in upc_keys(upc):
            if k in fdc_idx:
                return fdc_idx[k]
        return None

    # Walk api_cache_products.csv once. Bucket products into the four categories
    # and stop after we have 5 of each.
    wmt_known: list[dict] = []
    wmt_novel: list[dict] = []
    kr_known: list[dict] = []
    kr_novel: list[dict] = []
    seen_upcs: set[tuple[str, str]] = set()

    with open(API_CACHE) as f:
        for row in csv.DictReader(f):
            source = row["source"]
            upc = (row["upc"] or "").strip()
            name = (row["name"] or "").strip()
            search_term = (row["search_term"] or "").strip()
            if not name:
                continue
            key = (source, upc)
            if upc and key in seen_upcs:
                continue
            seen_upcs.add(key)

            fid = find_fdc(upc) if upc else None
            bucket = None
            if source == "walmart":
                bucket = wmt_known if fid else wmt_novel
            elif source == "kroger":
                bucket = kr_known if fid else kr_novel
            if bucket is None or len(bucket) >= 5:
                continue
            bucket.append({
                "fdc_id": (f"WM-{upc}" if source == "walmart" else f"KR-{upc}") if upc else f"{source[:2].upper()}-N{hashlib.md5(name.encode()).hexdigest()[:8]}",
                "gtin_upc": upc,
                "title": name,
                "branded_food_category": search_term,
                "source": source,
                "_smoke_category": f"{source}_{'fdc_known' if fid else 'novel'}",
                "_known_fdc_id": fid or "",
            })
            if all(len(b) >= 5 for b in (wmt_known, wmt_novel, kr_known, kr_novel)):
                break

    # Recipe ingredients
    recipe_rows: list[dict] = []
    items_in_corpus: dict[str, dict] = {}
    with open(RECIPE_ITEMS) as f:
        for row in csv.DictReader(f):
            items_in_corpus[row["item"]] = row
    for ing in RECIPE_PICKS:
        meta = items_in_corpus.get(ing) or {}
        recipe_rows.append({
            "fdc_id": f"RI-{hashlib.md5(ing.encode()).hexdigest()[:8]}",
            "gtin_upc": "",
            "title": ing,
            "branded_food_category": "",
            "source": "recipe",
            "_smoke_category": "recipe_ingredient",
            "_known_fdc_id": "",
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_rows = wmt_known + wmt_novel + kr_known + kr_novel + recipe_rows
    with OUT_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    print(f"wrote {len(all_rows)} rows -> {OUT_PATH}")
    print(f"  walmart fdc-known: {len(wmt_known)}")
    print(f"  walmart novel:     {len(wmt_novel)}")
    print(f"  kroger  fdc-known: {len(kr_known)}")
    print(f"  kroger  novel:     {len(kr_novel)}")
    print(f"  recipe ingredients:{len(recipe_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
