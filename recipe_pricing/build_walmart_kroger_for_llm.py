#!/usr/bin/env python3
"""Adapt the Walmart/Kroger API cache into the row shape that the retail
v2 LLM batch driver (run_full_csv_batch.py) expects.

The retail driver reads rows with the 27-column SOURCE_FIELDS schema. Most
of those are optional — compact_source_row() drops empty fields before
sending to DeepSeek. The minimum useful contract is:

    fdc_id                 — unique row id (synthetic for Walmart/Kroger)
    gtin_upc               — UPC if available
    title                  — the product name
    branded_food_category  — closest BFC proxy (we use search_term)

After this script runs, feed the output CSV to the existing batch driver:

    python3 retail_mapper/v2/run_full_csv_batch.py build \
        --csv  recipe_pricing/data/walmart_kroger_for_llm.csv \
        --out  recipe_pricing/data/walmart_kroger_batch_input.jsonl

The driver then submits the JSONL to Nebius batch the same way it did the
462k FDC retail corpus.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
DEFAULT_OUTPUT = ROOT / "recipe_pricing" / "data" / "walmart_kroger_for_llm.csv"

OUTPUT_FIELDS = [
    "fdc_id",
    "gtin_upc",
    "title",
    "branded_food_category",
    "source",
    "grams",
    "cents",
    "search_term",
]


def synthetic_fdc_id(source: str, upc: str, name: str) -> str:
    prefix = "WM" if source.lower() == "walmart" else "KR"
    if upc and upc.strip():
        return f"{prefix}-{upc.strip()}"
    digest = hashlib.md5(name.encode("utf-8", "replace")).hexdigest()[:10]
    return f"{prefix}-N{digest}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    csv.field_size_limit(sys.maxsize)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # The raw API cache duplicates each product across every search_term it
    # was returned for (a Kroger UPC may appear 100+ times). Dedupe on
    # (source, upc, normalized name) so the LLM sees each unique product
    # ONCE. Aggregate the search_terms that surfaced it as a comma-joined
    # hint — they're the FNDDS food categories that drove the API to return
    # this product, so they're the strongest BFC proxy we have.
    n_raw = 0
    n_skipped = 0
    by_key: dict[tuple[str, str, str], dict] = {}
    seen_search_terms: dict[tuple[str, str, str], list[str]] = {}
    with args.input.open(encoding="utf-8", errors="replace", newline="") as src:
        for row in csv.DictReader(src):
            n_raw += 1
            source = (row.get("source") or "").strip()
            upc = (row.get("upc") or "").strip()
            name = (row.get("name") or "").strip()
            search_term = (row.get("search_term") or "").strip()
            grams = (row.get("grams") or "").strip()
            cents = (row.get("cents") or "").strip()
            if not name:
                n_skipped += 1
                continue
            key = (source, upc, name.lower())
            if key not in by_key:
                by_key[key] = {
                    "source": source, "upc": upc, "name": name,
                    "grams": grams, "cents": cents,
                }
                seen_search_terms[key] = []
            if search_term and search_term not in seen_search_terms[key]:
                seen_search_terms[key].append(search_term)

    n = 0
    seen_ids: dict[str, int] = {}
    with args.output.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for key, data in by_key.items():
            n += 1
            terms = seen_search_terms[key]
            # Prefer the most-specific single term (shortest / most concrete);
            # join remaining as comma-separated hint.
            primary_term = terms[0] if terms else ""
            joined_terms = ", ".join(terms[:5])
            fid = synthetic_fdc_id(data["source"], data["upc"], data["name"])
            seen_ids[fid] = seen_ids.get(fid, 0) + 1
            if seen_ids[fid] > 1:
                fid = f"{fid}#{seen_ids[fid]}"
            writer.writerow({
                "fdc_id": fid,
                "gtin_upc": data["upc"],
                "title": data["name"],
                "branded_food_category": primary_term,
                "source": data["source"],
                "grams": data["grams"],
                "cents": data["cents"],
                "search_term": joined_terms,
            })

    print(f"raw rows scanned: {n_raw:,}  (skipped {n_skipped:,} with no name)")
    print(f"unique products written: {n:,}  ({n/n_raw*100:.1f}% of raw)")
    print(f"output -> {args.output}")
    print(f"size: {args.output.stat().st_size / 1024 / 1024:.1f} MB")
    print()
    print("Next steps (uses the same driver as the FDC retail batch):")
    print(f"  python3 retail_mapper/v2/run_full_csv_batch.py build \\")
    print(f"      --csv {args.output} \\")
    print(f"      --out recipe_pricing/data/walmart_kroger_batch_input.jsonl")
    print(f"  python3 retail_mapper/v2/run_full_csv_batch.py estimate \\")
    print(f"      --batch recipe_pricing/data/walmart_kroger_batch_input.jsonl")
    print(f"  NEBIUS_API_KEY=... python3 retail_mapper/v2/run_full_csv_batch.py submit \\")
    print(f"      --batch recipe_pricing/data/walmart_kroger_batch_input.jsonl \\")
    print(f"      --description 'Walmart/Kroger api_cache taxonomy'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
