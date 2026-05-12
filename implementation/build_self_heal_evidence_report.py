from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import self_heal_common as sh


DEFAULT_IDS = (
    "2401297",  # plain mashed potatoes -> was chicken meal
    "2096669",  # homestyle mashed potatoes -> was chicken meal
    "2544599",  # plain mashed potatoes -> was chicken meal
    "2059544",  # loaded mashed potatoes -> was chicken meal
    "2581028",  # light butter popcorn -> was snack/butter leakage
    "2615538",  # butter popcorn -> was snack/butter leakage
    "2055869",  # powdered mini donuts -> was cake leakage
    "2503091",  # cinnamon mini donuts -> was cake leakage
)


def _tokens_sample(tokens: set[str], limit: int = 80) -> str:
    return " ".join(sorted(tokens)[:limit])


def build_report(fdc_ids: set[str], input_map: Path) -> pd.DataFrame:
    products = sh.ingredient_clusters.load_products()
    current = sh.ingredient_clusters.load_current_map(input_map)
    current_cols = [
        "fdc_id",
        "best_esha_code",
        "best_esha_description",
        "best_esha_family",
        "score",
        "n_candidates",
        "assignment_source",
    ]
    rows = products[products["fdc_id"].astype(str).isin(fdc_ids)].merge(
        current[[c for c in current_cols if c in current.columns]].drop_duplicates("fdc_id"),
        on="fdc_id",
        how="left",
    )

    candidates, _category_to_codes, _family_to_codes, idf = sh.full_map.build_candidates()
    head_index = sh.build_head_index(candidates)
    anchors = sh.ingredient_clusters.load_esha_anchors()

    out: list[dict[str, object]] = []
    for _, row in rows.iterrows():
        desc = str(row.get("product_description") or "")
        category = str(row.get("branded_food_category") or "")
        title_tokens = set(sh.ingredient_clusters.title_tokens(desc))
        ingredient_tokens = set(sh.ingredient_clusters.tokenize_ingredients(str(row.get("ingredients") or "")))
        lane = sh.category_lane_for(desc, category, title_tokens)
        form = sh.product_form_for(desc, category, lane, title_tokens)
        role = sh.role_for(desc, lane, form, title_tokens)
        identity = sh.identity_terms_for(title_tokens, ingredient_tokens, form, role)
        target_heads = sh.target_heads_for(lane, form, role, title_tokens)
        fact = pd.Series(
            {
                "category_lane": lane,
                "product_form": form,
                "product_role": role,
                "identity_terms": " ".join(identity),
                "target_heads": "|".join(target_heads),
                "title_tokens": " ".join(sorted(title_tokens)),
                "ingredient_tokens": " ".join(sorted(ingredient_tokens)),
            }
        )
        feature = pd.Series(
            {
                "product_description": desc,
                "branded_food_category": category,
                "_title_tokens": tuple(title_tokens),
                "_ingredient_tokens": tuple(ingredient_tokens),
                "_product_family": sh.ingredient_clusters.product_family_for(desc, category, tuple(title_tokens)),
            }
        )
        current_code = str(row.get("best_esha_code") or "").split(".")[0].strip()
        anchor = anchors.get(current_code) if current_code else None
        status, reason = sh.current_assignment_decision(feature, fact, anchor)
        pool = sh.code_pool_for_heads(target_heads, head_index, candidates)
        replacement = sh.choose_replacement(fact, candidates, head_index, idf, pool=pool)
        out.append(
            {
                "fdc_id": row.get("fdc_id", ""),
                "gtin_upc": row.get("gtin_upc", ""),
                "product_description": desc,
                "branded_food_category": category,
                "brand_owner": row.get("brand_owner", ""),
                "brand_name": row.get("brand_name", ""),
                "title_tokens": " ".join(sorted(title_tokens)),
                "ingredient_tokens_sample": _tokens_sample(ingredient_tokens),
                "category_lane": lane,
                "product_form": form,
                "product_role": role,
                "identity_terms": " ".join(identity),
                "target_heads": "|".join(target_heads),
                "current_esha_code": current_code,
                "current_esha_description": row.get("best_esha_description", ""),
                "current_esha_head": sh.esha_head(str(row.get("best_esha_description") or "")),
                "current_assignment_source": row.get("assignment_source", ""),
                "current_decision": status,
                "current_reject_reason": reason,
                "candidate_pool_size": len(pool),
                "proposed_esha_code": "" if replacement is None else replacement.code,
                "proposed_esha_description": "" if replacement is None else replacement.description,
                "proposed_esha_head": "" if replacement is None else replacement.head,
                "proposed_score": "" if replacement is None else replacement.score,
                "proposed_reason": "" if replacement is None else replacement.reason,
            }
        )
    return pd.DataFrame(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-map", type=Path, default=sh.OUT_DIR / "product_to_best_esha_full_map.csv")
    parser.add_argument("--output", type=Path, default=sh.SELF_HEAL_DIR / "self_heal_evidence_report.csv")
    parser.add_argument("--fdc-id", action="append", default=[])
    args = parser.parse_args()

    fdc_ids = set(args.fdc_id or DEFAULT_IDS)
    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(fdc_ids, args.input_map)
    report.to_csv(args.output, index=False)
    print(f"wrote {args.output} ({len(report):,})")


if __name__ == "__main__":
    main()
