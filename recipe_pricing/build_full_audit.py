#!/usr/bin/env python3
"""Build a comprehensive audit CSV for spot-checking the four-corpus
classification. One row per recipe ingredient with everything needed
to verify the join end-to-end.

Output columns:
  item, recipe_count, grams_total
  htc_code, htc_sku_code, htc_group, htc_family, htc_food
  canonical_path, canonical_label, product_identity_fixed
  variant, flavor, form_texture_cut, processing_storage, claims, modifier
  match_method, match_confidence
  walmart_hits, walmart_sample_titles
  nutrition_hits, nutrition_top_sr28_code, nutrition_top_sr28_desc,
                  nutrition_top_fndds_code, nutrition_top_fndds_desc
  fdc_retail_hits, fdc_retail_sample_title
  join_status (both / walmart_only / nutrition_only / unmatched / non_food)
  non_food, food_slot_resolved, low_confidence, needs_review
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ING = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
DEFAULT_RIH = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv"
DEFAULT_WMT = ROOT / "recipe_pricing" / "output" / "api_cache_taxonomy_v2.csv"
DEFAULT_NUT = ROOT / "recipe_pricing" / "output" / "sr28_fndds_taxonomy_v2.csv"
DEFAULT_NUT_INPUT = ROOT / "recipe_pricing" / "data" / "nutrition_db_for_llm.csv"
DEFAULT_RETAIL = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_OUT = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_full_audit.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingredient", type=Path, default=DEFAULT_ING)
    ap.add_argument("--legacy-ing", type=Path, default=DEFAULT_RIH)
    ap.add_argument("--walmart", type=Path, default=DEFAULT_WMT)
    ap.add_argument("--nutrition", type=Path, default=DEFAULT_NUT)
    ap.add_argument("--nutrition-input", type=Path, default=DEFAULT_NUT_INPUT)
    ap.add_argument("--retail", type=Path, default=DEFAULT_RETAIL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    # Pull recipe_count and grams_total from legacy ingredient file
    recipe_meta: dict[str, dict] = {}
    print(f"reading legacy ingredient meta ({args.legacy_ing}) ...", file=sys.stderr)
    if args.legacy_ing.exists():
        with args.legacy_ing.open() as f:
            for row in csv.DictReader(f):
                recipe_meta[row["item"]] = {
                    "recipe_count": int(row.get("recipe_count") or 0),
                    "grams_total": int(float(row.get("grams_total") or 0)),
                }

    # Index Walmart/Kroger by htc_code
    print(f"indexing walmart/kroger ({args.walmart}) ...", file=sys.stderr)
    wmt_by_code: dict[str, list[str]] = defaultdict(list)
    wmt_count: Counter = Counter()
    with args.walmart.open() as f:
        for row in csv.DictReader(f):
            c = row["htc_code"]
            wmt_count[c] += 1
            if len(wmt_by_code[c]) < 3:
                wmt_by_code[c].append(row.get("title", "")[:80])

    # Index nutrition DB by htc_code
    print(f"indexing nutrition db ({args.nutrition}) ...", file=sys.stderr)
    nut_by_code: dict[str, list[dict]] = defaultdict(list)
    nut_count: Counter = Counter()
    with args.nutrition.open() as f:
        for row in csv.DictReader(f):
            c = row["htc_code"]
            nut_count[c] += 1
            if len(nut_by_code[c]) < 5:
                nut_by_code[c].append({
                    "fdc_id": row["fdc_id"],
                    "title": row.get("title", "")[:80],
                    "source": row.get("source", ""),
                })

    # Cross-walk: nutrition_db_for_llm.csv has source/fdc_id by SR28-/FNDDS- prefix
    # Already encoded in fdc_id; just split on prefix to identify SR28 vs FNDDS code.

    # Index FDC retail audit by htc_code (using the regex-encoder consensus_htc_tagged
    # is the canonical retail tagged file)
    print(f"indexing fdc retail audit ({args.retail}) ...", file=sys.stderr)
    retail_by_code: dict[str, dict] = defaultdict(lambda: {"count": 0, "sample": ""})
    retail_count: Counter = Counter()
    consensus_htc = args.retail.parent.parent.parent / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv"
    if consensus_htc.exists():
        with consensus_htc.open() as f:
            for row in csv.DictReader(f):
                c = row.get("htc_code") or ""
                if not c:
                    continue
                retail_count[c] += 1
                if not retail_by_code[c]["sample"]:
                    retail_by_code[c]["sample"] = row.get("title", "")[:80]

    # Stream ingredients and emit the audit row per item.
    print(f"writing audit ({args.out}) ...", file=sys.stderr)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_total = 0
    status_counter: Counter = Counter()
    out_cols = [
        "item", "recipe_count", "grams_total",
        "htc_code", "htc_sku_code",
        "htc_group", "htc_family", "htc_food",
        "canonical_path", "retail_leaf_path", "retail_leaf_source",
        "canonical_label", "product_identity_fixed", "htc_full_code",
        "variant", "flavor", "form_texture_cut", "processing_storage",
        "claims", "modifier",
        "match_method", "match_confidence",
        "walmart_hits", "walmart_sample_titles",
        "nutrition_hits", "nutrition_sample_titles",
        "fdc_retail_hits", "fdc_retail_sample",
        "join_status",
        "non_food", "food_slot_resolved", "low_confidence", "needs_review",
    ]

    with args.ingredient.open() as inp, args.out.open("w", newline="") as out:
        r = csv.DictReader(inp)
        w = csv.DictWriter(out, fieldnames=out_cols)
        w.writeheader()
        for row in r:
            n_total += 1
            item = row.get("title", "").strip()
            meta = recipe_meta.get(item, {})
            code = row.get("htc_code", "")
            grp = row.get("htc_group", "")
            food = row.get("htc_food", "")
            mm = row.get("match_method", "")
            mc = float(row.get("match_confidence") or 0)

            non_food = grp == "N"
            food_slot_resolved = food and food != "00"

            wh = wmt_count.get(code, 0)
            nh = nut_count.get(code, 0)
            rh = retail_count.get(code, 0)

            if non_food:
                status = "non_food"
            elif wh > 0 and nh > 0:
                status = "both"
            elif wh > 0:
                status = "walmart_only"
            elif nh > 0:
                status = "nutrition_only"
            else:
                status = "unmatched"
            status_counter[status] += 1

            low_conf = mc < 0.85 and mm in ("fuzzy", "unmatched")
            needs_review = (status == "unmatched") or (mm == "unmatched") or low_conf

            w.writerow({
                "item": item,
                "recipe_count": meta.get("recipe_count", 0),
                "grams_total": meta.get("grams_total", 0),
                "htc_code": code,
                "htc_sku_code": row.get("htc_sku_code", code),
                "htc_group": grp,
                "htc_family": row.get("htc_family", ""),
                "htc_food": food,
                "canonical_path": row.get("canonical_path", ""),
                "retail_leaf_path": row.get("retail_leaf_path", ""),
                "retail_leaf_source": row.get("retail_leaf_source", ""),
                "htc_full_code": row.get("htc_full_code", ""),
                "canonical_label": row.get("canonical_label", ""),
                "product_identity_fixed": row.get("product_identity_fixed", ""),
                "variant": row.get("variant", ""),
                "flavor": row.get("flavor", ""),
                "form_texture_cut": row.get("form_texture_cut", ""),
                "processing_storage": row.get("processing_storage", ""),
                "claims": row.get("claims", ""),
                "modifier": row.get("modifier", ""),
                "match_method": mm,
                "match_confidence": f"{mc:.2f}",
                "walmart_hits": wh,
                "walmart_sample_titles": " | ".join(wmt_by_code.get(code, [])[:3]),
                "nutrition_hits": nh,
                "nutrition_sample_titles": " | ".join(
                    f"{x['fdc_id']}:{x['title']}" for x in nut_by_code.get(code, [])[:3]
                ),
                "fdc_retail_hits": rh,
                "fdc_retail_sample": retail_by_code[code]["sample"] if rh else "",
                "join_status": status,
                "non_food": "Y" if non_food else "",
                "food_slot_resolved": "Y" if food_slot_resolved else "",
                "low_confidence": "Y" if low_conf else "",
                "needs_review": "Y" if needs_review else "",
            })

    print(f"\nwrote {n_total:,} rows -> {args.out}")
    print("\njoin_status distribution:")
    for s, n in status_counter.most_common():
        print(f"  {s}: {n:,} ({n/n_total*100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
