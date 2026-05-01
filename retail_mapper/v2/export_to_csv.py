#!/usr/bin/env python3
"""Export the live LLM JSONL → wide CSV with normalized records.

Reads the live JSONL produced by run_full_csv_parallel.py, applies
normalize_record() to each row, and writes a wide CSV that's easy to
consume in spreadsheets, scripts, or downstream alignment tools.

Each row in the CSV is one fdc_id with:
  - source identifiers (fdc_id, gtin_upc, brand_owner, brand_name)
  - source title and branded_food_category
  - LLM classification (product_identity, category_path, etc.)
  - all top-level facets joined by " | "
  - components count and joined component identities
  - QA fields (confidence, review_flags, rationale, parse_error)
  - LLM usage stats (token counts) for cost auditing

Usage:
    python3 retail_mapper/v2/export_to_csv.py
    # writes retail_mapper/v2/full_corpus.csv

    python3 retail_mapper/v2/export_to_csv.py \
      --live retail_mapper/v2/full_corpus.live.jsonl \
      --csv  retail_mapper/v2/retail_leaf_v2_enriched_v2.csv \
      --out  retail_mapper/v2/full_corpus.csv \
      --no-normalize     # skip normalizer, keep raw LLM record verbatim
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_LIVE = V2 / "full_corpus.live.jsonl"
DEFAULT_CSV  = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_OUT  = V2 / "full_corpus.csv"

csv.field_size_limit(sys.maxsize)


def load_module():
    sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)
    return m


def join_list(v) -> str:
    if not v:
        return ""
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)
    return str(v)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--csv",  type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out",  type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-normalize", action="store_true",
                        help="Skip normalize_record(); keep raw LLM record")
    parser.add_argument("--no-source-join", action="store_true",
                        help="Skip joining source CSV fields (gtin, brand)")
    args = parser.parse_args()

    if not args.live.exists():
        raise SystemExit(f"no live file at {args.live}")
    m = load_module()

    # 1) Optionally read the source CSV and index extra fields by fdc_id
    src_extras: dict[str, dict] = {}
    if not args.no_source_join and args.csv.exists():
        print(f"  reading source CSV for brand/gtin join: {args.csv}")
        # Scan the CSV once, only keeping rows whose fdc_id appears in live JSONL
        live_fdc: set[str] = set()
        with args.live.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line: continue
                try:
                    d = json.loads(line)
                    f = str(d.get("fdc_id",""))
                    if f: live_fdc.add(f)
                except: pass
        with args.csv.open(encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                fdc = row.get("fdc_id","")
                if fdc in live_fdc:
                    src_extras[fdc] = {
                        "gtin_upc":     row.get("gtin_upc",""),
                        "brand_owner":  row.get("brand_owner",""),
                        "brand_name":   row.get("brand_name",""),
                        "current_esha": row.get("current_esha",""),
                        "current_esha_desc": row.get("current_esha_desc",""),
                        "ing_top5":     row.get("ing_top5",""),
                    }
        print(f"  joined {len(src_extras):,} source rows")

    # 2) Walk the live JSONL and write the CSV
    columns = [
        "fdc_id",
        "gtin_upc",
        "brand_owner",
        "brand_name",
        "title",
        "branded_food_category",
        "current_esha",
        "current_esha_desc",
        "ing_top5",
        "retail_type",
        "category_path",
        "product_identity",
        "canonical_path",
        "canonical_label",
        "variant",
        "flavor",
        "form_texture_cut",
        "processing_storage",
        "claims",
        "components_count",
        "components",
        "confidence",
        "mint_required",
        "review_flags",
        "rationale",
        "parse_error",
        "api_error",
        "prompt_tokens",
        "completion_tokens",
        "cache_hit_tokens",
        "cache_miss_tokens",
    ]

    rows_written = 0
    parse_err = 0
    api_err = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.live.open(encoding="utf-8") as src, \
         args.out.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=columns)
        writer.writeheader()
        for line in src:
            line = line.strip()
            if not line: continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            fdc = str(o.get("fdc_id",""))
            title = o.get("title","")
            bfc = o.get("branded_food_category","")
            rec = o.get("record", {}) or {}
            usage = o.get("usage", {}) or {}

            row_parse_err = ""
            row_api_err = ""
            if "_parse_error" in rec:
                row_parse_err = rec["_parse_error"]; parse_err += 1
                rec = {}
            if "_api_error" in rec:
                row_api_err = rec["_api_error"]; api_err += 1
                rec = {}

            if not args.no_normalize and rec:
                try:
                    rec = m.normalize_record(rec, {"title": title, "branded_food_category": bfc})
                except Exception as exc:
                    row_parse_err = f"normalize_error: {exc}"
                    rec = {}

            comps = rec.get("components", []) or []
            comp_ids = [c.get("identity","") for c in comps if isinstance(c, dict)]

            extras = src_extras.get(fdc, {})

            writer.writerow({
                "fdc_id":       fdc,
                "gtin_upc":     extras.get("gtin_upc",""),
                "brand_owner":  extras.get("brand_owner",""),
                "brand_name":   extras.get("brand_name",""),
                "title":        title,
                "branded_food_category": bfc,
                "current_esha":      extras.get("current_esha",""),
                "current_esha_desc": extras.get("current_esha_desc",""),
                "ing_top5":     extras.get("ing_top5",""),
                "retail_type":  rec.get("retail_type",""),
                "category_path":rec.get("category_path",""),
                "product_identity":  rec.get("product_identity",""),
                "canonical_path":    rec.get("canonical_path",""),
                "canonical_label":   rec.get("canonical_label",""),
                "variant":           join_list(rec.get("variant", [])),
                "flavor":            join_list(rec.get("flavor", [])),
                "form_texture_cut":  join_list(rec.get("form_texture_cut", [])),
                "processing_storage":join_list(rec.get("processing_storage", [])),
                "claims":            join_list(rec.get("claims", [])),
                "components_count":  len(comps),
                "components":        join_list(comp_ids),
                "confidence":        rec.get("confidence",""),
                "mint_required":     rec.get("mint_required",""),
                "review_flags":      join_list(rec.get("review_flags", [])),
                "rationale":         (rec.get("rationale","") or "")[:500],
                "parse_error":       row_parse_err,
                "api_error":         row_api_err,
                "prompt_tokens":     usage.get("prompt_tokens",""),
                "completion_tokens": usage.get("completion_tokens",""),
                "cache_hit_tokens":  usage.get("prompt_cache_hit_tokens",""),
                "cache_miss_tokens": usage.get("prompt_cache_miss_tokens",""),
            })
            rows_written += 1
            if rows_written % 50000 == 0:
                print(f"  wrote {rows_written:,} rows…", flush=True)

    print(f"  wrote {rows_written:,} rows -> {args.out}")
    print(f"  size: {args.out.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  parse_errors: {parse_err}  api_errors: {api_err}")
    print(f"  normalizer applied: {not args.no_normalize}")
    print(f"  source-CSV brand/gtin join: {bool(src_extras)}")


if __name__ == "__main__":
    main()
