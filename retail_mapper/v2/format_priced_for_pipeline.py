#!/usr/bin/env python3
"""Format priced_products rows as input for retail_mapper/v2/run_full_csv_batch.py.

The v2 pipeline's LLM call (cmd_build in run_full_csv_batch.py) reads each row
through llm_taxonomy_cleanup.compact_source_row(), which only uses fields
listed in SOURCE_FIELDS. In LEAN_EVIDENCE_MODE (default ON) the prompt drops
ngram/role-tagger fields, so the minimum useful columns are:

  fdc_id              - synthetic (priced UPC + offset)
  gtin_upc            - the priced UPC
  title               - priced_products.name
  branded_food_category - synthesized from Walmart categoryPath leaf

We DON'T need ingredients data, semantic_*, role_candidates_json, etc. — they
all degrade gracefully to empty.
"""
from __future__ import annotations
import csv, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
IN_CSV  = ROOT / "retail_mapper" / "v2" / "priced_extension_sample_raw.csv"
OUT_CSV = ROOT / "retail_mapper" / "v2" / "priced_extension_sample.csv"

# The pipeline expects these columns (compact_source_row reads from SOURCE_FIELDS;
# missing fields default to empty string).
PIPELINE_COLUMNS = [
    "fdc_id", "gtin_upc", "title", "branded_food_category",
    "current_esha", "current_esha_desc",
    "retail_leaf",
    "ing_full",
    "semantic_retail_type", "semantic_category_path", "semantic_product_identity",
    "semantic_canonical_path", "semantic_canonical_label", "semantic_review_flags",
    "source_parser_primary_food", "source_parser_form", "source_parser_flavor",
    "product_form_guess", "modifier_guesses", "ingredient_guesses",
    "ing_top5", "ing_categories",
    "title_ngrams_json", "role_candidates_json",
    "llm_evidence_block",
]

# Walmart categoryPath looks like:
#   "Home Page/Food/Pantry/Spices/Cumin"
# USDA BFC looks like:
#   "Pre-Packaged Fruit & Vegetables", "Spices, Herbs, Seasonings", "Butter & Spread"
# We can't perfectly map without a lookup table, but the LLM only uses the BFC
# as a hint — the title is the primary signal. Pass the leaf segment of the
# Walmart path as a stand-in BFC.
def synth_bfc(walmart_path: str, fallback: str) -> str:
    if walmart_path:
        parts = [p.strip() for p in walmart_path.split("/") if p.strip()]
        if parts:
            return parts[-1]
    if fallback:
        return fallback
    return ""

def synth_fdc(upc: str) -> str:
    """Synthesize a unique fdc_id from UPC. Use 9_000_000_000 prefix to keep
    these distinguishable from real FDC ids (which are < ~3M)."""
    digits = "".join(c for c in (upc or "") if c.isdigit())
    if not digits:
        return ""
    return str(9_000_000_000 + int(digits))

def main() -> int:
    n_in = n_out = 0
    with IN_CSV.open() as src, OUT_CSV.open("w", newline="") as dst:
        rdr = csv.DictReader(src)
        wtr = csv.DictWriter(dst, fieldnames=PIPELINE_COLUMNS)
        wtr.writeheader()
        for r in rdr:
            n_in += 1
            upc = (r.get("upc") or "").strip()
            title = (r.get("name") or "").strip()
            walmart_path = (r.get("category_path_walmart") or "").strip()
            simple_path = (r.get("category_path") or "").strip()
            if not title:
                continue
            row = {c: "" for c in PIPELINE_COLUMNS}
            row["fdc_id"] = synth_fdc(upc) or f"priced_{n_in}"
            row["gtin_upc"] = upc
            row["title"] = title.upper()  # consensus audit titles are uppercase
            row["branded_food_category"] = synth_bfc(walmart_path, simple_path)
            wtr.writerow(row)
            n_out += 1
    print(f"  read  {n_in} rows from {IN_CSV.name}")
    print(f"  wrote {n_out} rows to   {OUT_CSV.name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
