#!/usr/bin/env python3
"""Pull a real-world stress test from the enriched CSV.

Builds two pseudo-gold JSONLs (no expected record — we don't grade against
my opinion, only count distinct identities the model emits):

  - llm_taxonomy_bars_explosion_cases.jsonl   ~100 bar SKUs
  - llm_taxonomy_candy_explosion_cases.jsonl  ~100 candy SKUs

Each entry is a real CSV row, so when build_requests_from_gold runs it'll
read the row directly (no fixture map needed) and graft full evidence.

The expected block is a placeholder — we won't score core/exact. We just
count distinct product_identities the model produces on these SKUs.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CSV_PATH = V2 / "retail_leaf_v2_enriched_v2.csv"

csv.field_size_limit(sys.maxsize)

# Module for build helpers
sp = importlib.util.spec_from_file_location("ltc", V2 / "llm_taxonomy_cleanup.py")
ltc = importlib.util.module_from_spec(sp); sys.modules["ltc"] = ltc
sp.loader.exec_module(ltc)


def make_placeholder_expected(fdc_id: str) -> dict:
    """Minimal valid expected record so validate_gold doesn't reject."""
    rec = {
        "fdc_id": fdc_id,
        "retail_type": "single",
        "category_path": "Other > Needs Review",
        "product_identity": "Unknown Product",
        "variant": [], "flavor": [], "form_texture_cut": [],
        "processing_storage": [], "claims": [], "components": [],
        "confidence": 0.0, "mint_required": False,
        "review_flags": ["explosion_test_placeholder"],
        "rationale": "explosion test — gold is a placeholder, not used for scoring",
    }
    rec["canonical_path"] = ltc.build_canonical_path(rec["category_path"], rec["product_identity"])
    rec["canonical_label"] = ltc.build_canonical_label(rec["product_identity"], rec)
    rec["tree_paths"] = ltc.build_tree_paths(rec)
    return rec


# Bar BFC patterns — broadened from earlier-too-narrow filter.
# Bars live in many BFCs in the real CSV: granola, protein, breakfast,
# snack bars, cereal & granola, energy, meal replacement, fruit bars.
BAR_BFC_ANY = [
    "granola bar", "snack bar", "protein bar", "breakfast bar",
    "energy bar", "cereal bar", "meal replacement", "fruit bar",
    "wholesome snack", "snacks/refrigerated",
    "cereal", "snack",  # broad fallbacks; filtered by title containing "bar"
]
BAR_TITLE_INCLUDE = ["bar"]  # require literal "bar" in the title
BAR_TITLE_EXCLUDE = ["soap", "shampoo", "detergent", "candy bar", "chocolate bar",
                     "ice cream bar", "yogurt bar", "lara bar"]  # candy bars handled in candy file

# Candy BFC patterns
CANDY_BFC = [
    "chocolate candy", "non chocolate candy",
    "candy & confection", "confection",
]
CANDY_TITLE_EXCLUDE = ["soap", "ice cream", "yogurt", "cookies"]


def is_bar(title: str, bfc: str) -> bool:
    # Require "bar" or "bars" in title
    has_bar = any(t in title for t in BAR_TITLE_INCLUDE) or "bars" in title
    if not has_bar:
        return False
    if any(x in title for x in BAR_TITLE_EXCLUDE):
        return False
    # BFC must match at least one
    if not any(b in bfc for b in BAR_BFC_ANY):
        return False
    return True


def is_candy(title: str, bfc: str) -> bool:
    if any(x in title for x in CANDY_TITLE_EXCLUDE):
        return False
    if not any(x in bfc for x in CANDY_BFC):
        return False
    return True


def main() -> None:
    bars: list[dict] = []
    candy: list[dict] = []
    seen_bar_titles: set[str] = set()
    seen_candy_titles: set[str] = set()

    with CSV_PATH.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            title = (row.get("title") or "").lower()
            bfc = (row.get("branded_food_category") or "").lower()
            if not title or not row.get("ing_full"):
                continue
            # Bars
            if len(bars) < 100 and is_bar(title, bfc) and title not in seen_bar_titles:
                seen_bar_titles.add(title)
                fdc = row.get("fdc_id") or ""
                bars.append({
                    "name": f"explosion_bar_{len(bars)+1}_{fdc}",
                    "source": {
                        "fdc_id": fdc,
                        "title": row.get("title", ""),
                        "branded_food_category": row.get("branded_food_category", ""),
                    },
                    "expected": make_placeholder_expected(fdc),
                })
            # Candy
            if len(candy) < 100 and is_candy(title, bfc) and title not in seen_candy_titles:
                seen_candy_titles.add(title)
                fdc = row.get("fdc_id") or ""
                candy.append({
                    "name": f"explosion_candy_{len(candy)+1}_{fdc}",
                    "source": {
                        "fdc_id": fdc,
                        "title": row.get("title", ""),
                        "branded_food_category": row.get("branded_food_category", ""),
                    },
                    "expected": make_placeholder_expected(fdc),
                })
            if len(bars) >= 100 and len(candy) >= 100:
                break

    bars_path = V2 / "llm_taxonomy_bars_explosion_cases.jsonl"
    candy_path = V2 / "llm_taxonomy_candy_explosion_cases.jsonl"
    with bars_path.open("w", encoding="utf-8") as fh:
        for b in bars:
            fh.write(json.dumps(b, sort_keys=True) + "\n")
    with candy_path.open("w", encoding="utf-8") as fh:
        for c in candy:
            fh.write(json.dumps(c, sort_keys=True) + "\n")
    print(f"wrote {len(bars)} bar cases -> {bars_path}")
    print(f"wrote {len(candy)} candy cases -> {candy_path}")
    print()
    print("=== Sample bars (first 10) ===")
    for b in bars[:10]:
        print(f"  {b['source']['fdc_id']:>10s}  bfc={b['source']['branded_food_category']:30s}  {b['source']['title']}")
    print()
    print("=== Sample candy (first 10) ===")
    for c in candy[:10]:
        print(f"  {c['source']['fdc_id']:>10s}  bfc={c['source']['branded_food_category']:30s}  {c['source']['title']}")


if __name__ == "__main__":
    main()
