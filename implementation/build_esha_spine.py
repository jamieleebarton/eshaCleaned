from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

import build_product_to_best_esha_full_map as full_map
import cluster_spine_common as common
import self_heal_policy as policy


OUT_CSV = common.ESHA_SPINE_CSV
OUT_JSON = common.OUT_DIR / "esha_spine_summary.json"

BROAD_HEADS = {
    "base", "dish", "drink", "food", "fruit", "meal", "sauce", "snack",
    "vegetables", "beans", "bar", "mix",
}


def inferred_buckets(head_norm: str, description: str, family: str) -> set[str]:
    text = common.norm_text(description)
    out: set[str] = set()
    if head_norm in {"pasta", "noodles", "macaroni"}:
        out.add("dry_pasta")
    if head_norm == "pasta dish":
        out |= {"pasta_dinner", "prepared_meal"}
    if head_norm in {"beans", "baked beans", "refried beans", "pork and beans"}:
        out |= {"canned_bottled_beans", "vegetable_lentil_mixes"}
    if head_norm == "popcorn":
        out.add("popcorn_nuts_seeds")
    if head_norm in {"butter", "butter substitute", "spread"}:
        out.add("butter_spread")
    if head_norm in {"salad dressing", "dressing"}:
        out.add("salad_dressing")
    if head_norm in {"dip", "salsa", "hummus"}:
        out.add("dip_salsa")
    if head_norm in {"meal", "dish", "burrito", "wrap", "sandwich", "pizza"}:
        out.add("prepared_meal")
    if head_norm == "pizza":
        out.add("pizza")
    if head_norm in {"milk", "almond milk", "oat milk", "soy milk", "coconut milk"}:
        out.add("plant_milk" if "almond" in text or "oat" in text or "soy" in text or "coconut" in text else "milk")
    if head_norm in {"cream substitute", "coffee"} or "creamer" in text:
        out.add("milk_additives")
    if head_norm in {"cake", "cookie", "cookies", "muffin", "baking mix"}:
        out.add("baking_mix")
    if family in {"legume"}:
        out.add("canned_bottled_beans")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT_CSV)
    args = parser.parse_args()

    print("building candidate profiles for full ESHA spine", flush=True)
    candidates, _category_to_codes, _family_to_codes, _idf = full_map.build_candidates()
    rows: list[dict[str, object]] = []
    for code, cand in sorted(candidates.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else kv[0]):
        head = common.esha_head(cand.description)
        head_norm = common.norm_head(head)
        tokens = set(cand.tokens) | set(cand.meaningful_terms) | set(cand.identity_terms)
        subtypes = common.subtype_keys(tokens, common.norm_text(cand.description))
        category_buckets = {policy.category_bucket(c) or "" for c in cand.categories}
        category_buckets.discard("")
        category_buckets |= inferred_buckets(head_norm, cand.description, cand.family)
        rows.append(
            {
                "esha_code": code,
                "esha_description": cand.description,
                "esha_head": head,
                "esha_head_norm": head_norm,
                "esha_family": cand.family,
                "identity_terms": common.terms_join(cand.identity_terms),
                "meaningful_terms": common.terms_join(cand.meaningful_terms),
                "all_terms": common.terms_join(tokens, limit=120),
                "subtype_keys": " ".join(sorted(subtypes)),
                "allowed_category_buckets": "|".join(sorted(category_buckets)),
                "category_support": int(cand.category_support),
                "observed_categories": " | ".join(sorted(cand.categories)[:30]),
                "needs_fix": int(bool(cand.needs_fix)),
                "broad_head": int(head_norm in BROAD_HEADS),
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(args.output, index=False)
    summary = {
        "output": str(args.output),
        "esha_codes": int(len(out)),
        "heads": int(out["esha_head_norm"].nunique()),
        "families": out["esha_family"].value_counts().head(30).to_dict(),
        "top_heads": out["esha_head_norm"].value_counts().head(40).to_dict(),
        "needs_fix_codes": int((out["needs_fix"] == 1).sum()),
        "broad_head_codes": int((out["broad_head"] == 1).sum()),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
