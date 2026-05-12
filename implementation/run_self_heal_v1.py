from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import self_heal_common as sh


def _ensure_self_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "best_esha_head" not in out.columns:
        insert_at = out.columns.get_loc("best_esha_description") + 1 if "best_esha_description" in out.columns else len(out.columns)
        out.insert(insert_at, "best_esha_head", "")
    for col in ("self_heal_status", "self_heal_reason", "self_heal_target_heads"):
        if col not in out.columns:
            out[col] = ""
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-map", type=Path, default=sh.DEFAULT_INPUT_MAP)
    parser.add_argument("--output-map", type=Path, default=sh.VSELF_CSV)
    parser.add_argument("--product-facts", type=Path, default=sh.SELF_HEAL_DIR / "product_facts.csv")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"loading current map: {args.input_map}", flush=True)
    current = sh.ingredient_clusters.load_current_map(args.input_map)
    if args.limit:
        current = current.head(args.limit).copy()
    out = _ensure_self_columns(current)

    print("building/loading product facts", flush=True)
    if args.product_facts.exists():
        facts = pd.read_csv(args.product_facts, dtype=str, keep_default_na=False, low_memory=False)
        if "policy_version" not in facts.columns or set(facts["policy_version"].astype(str).unique()) != {sh.SELF_HEAL_POLICY_VERSION}:
            print("  cached product facts are stale for current self-heal policy; rebuilding", flush=True)
            facts = sh.build_product_facts(current)
            facts.to_csv(args.product_facts, index=False)
    else:
        facts = sh.build_product_facts(current)
        facts.to_csv(args.product_facts, index=False)
    facts_by_fdc = sh.product_fact_map(facts)

    print("building feature rows", flush=True)
    products = sh.ingredient_clusters.load_products()
    features = sh.ingredient_clusters.build_product_features(products, current)
    features_by_fdc = {str(r["fdc_id"]): r for _, r in features.iterrows()}

    print("loading candidates/anchors", flush=True)
    candidates, _category_to_codes, _family_to_codes, idf = sh.full_map.build_candidates()
    anchors = sh.ingredient_clusters.load_esha_anchors()
    head_index = sh.build_head_index(candidates)
    pool_cache: dict[str, list[str]] = {}
    replacement_cache: dict[str, sh.Replacement | None] = {}

    decisions: list[dict[str, object]] = []
    proposals: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []

    for i, row in out.iterrows():
        if (i + 1) % 5000 == 0:
            print(f"  self-heal scan: {i + 1:,}/{len(out):,}", flush=True)
        fdc_id = str(row.get("fdc_id") or "")
        fact = facts_by_fdc.get(fdc_id)
        feature = features_by_fdc.get(fdc_id)
        if fact is None or feature is None:
            out.at[i, "self_heal_status"] = "missing_leaf"
            out.at[i, "self_heal_reason"] = "missing_product_facts"
            continue

        current_code = str(row.get("best_esha_code") or "").split(".")[0].strip()
        anchor = anchors.get(current_code) if current_code else None
        status, reason = sh.current_assignment_decision(feature, fact, anchor)
        target_heads = str(fact.get("target_heads") or "")
        out.at[i, "self_heal_target_heads"] = target_heads

        if status == "kept_compatible":
            if current_code and anchor:
                out.at[i, "best_esha_head"] = sh.esha_head(anchor.description)
            out.at[i, "self_heal_status"] = status
            out.at[i, "self_heal_reason"] = reason
            decisions.append(
                {
                    "fdc_id": fdc_id,
                    "gtin_upc": row.get("gtin_upc", ""),
                    "product_description": row.get("product_description", ""),
                    "branded_food_category": row.get("branded_food_category", ""),
                    "old_esha_code": current_code,
                    "old_esha_description": row.get("best_esha_description", ""),
                    "new_esha_code": current_code,
                    "new_esha_description": row.get("best_esha_description", ""),
                    "self_heal_status": status,
                    "self_heal_reason": reason,
                    "target_heads": target_heads,
                }
            )
            continue

        heads_key = str(fact.get("target_heads") or "")
        pool = pool_cache.get(heads_key)
        if pool is None:
            pool = sh.code_pool_for_heads(heads_key.split("|"), head_index, candidates)
            pool_cache[heads_key] = pool
        repair_key = "|".join(
            [
                str(fact.get("category_lane") or ""),
                str(fact.get("product_form") or ""),
                str(fact.get("product_role") or ""),
                str(fact.get("identity_terms") or ""),
                str(fact.get("ingredient_profile_signature") or ""),
                str(fact.get("ingredient_signature") or "")[:240],
                heads_key,
            ]
        )
        if repair_key in replacement_cache:
            replacement = replacement_cache[repair_key]
        else:
            replacement = sh.choose_replacement(fact, candidates, head_index, idf, pool=pool)
            replacement_cache[repair_key] = replacement
        base = {
            "fdc_id": fdc_id,
            "gtin_upc": row.get("gtin_upc", ""),
            "product_description": row.get("product_description", ""),
            "branded_food_category": row.get("branded_food_category", ""),
            "category_lane": fact.get("category_lane", ""),
            "product_form": fact.get("product_form", ""),
            "product_role": fact.get("product_role", ""),
            "identity_terms": fact.get("identity_terms", ""),
            "target_heads": target_heads,
            "old_esha_code": current_code,
            "old_esha_description": row.get("best_esha_description", ""),
            "old_esha_head": sh.esha_head(str(row.get("best_esha_description") or "")),
            "old_assignment_source": row.get("assignment_source", ""),
            "reject_reason": reason,
        }
        if replacement is None:
            for col in ("best_esha_code", "best_esha_description", "best_esha_head", "best_esha_family", "score"):
                if col in out.columns:
                    out.at[i, col] = ""
            if "n_candidates" in out.columns:
                out.at[i, "n_candidates"] = "0"
            out.at[i, "assignment_source"] = "self_heal_missing_leaf"
            out.at[i, "self_heal_status"] = "missing_leaf"
            out.at[i, "self_heal_reason"] = reason
            missing.append(base)
            decisions.append({**base, "new_esha_code": "", "new_esha_description": "", "self_heal_status": "missing_leaf", "self_heal_reason": reason})
            continue

        out.at[i, "best_esha_code"] = replacement.code
        out.at[i, "best_esha_description"] = replacement.description
        out.at[i, "best_esha_head"] = replacement.head
        out.at[i, "best_esha_family"] = replacement.family
        out.at[i, "score"] = str(replacement.score)
        out.at[i, "n_candidates"] = str(replacement.pool_size)
        out.at[i, "assignment_source"] = "self_heal_remapped_compatible"
        out.at[i, "self_heal_status"] = "remapped_compatible"
        out.at[i, "self_heal_reason"] = replacement.reason
        proposal = {
            **base,
            "new_esha_code": replacement.code,
            "new_esha_description": replacement.description,
            "new_esha_head": replacement.head,
            "new_esha_family": replacement.family,
            "self_heal_score": replacement.score,
            "candidate_pool_size": replacement.pool_size,
            "score_reason": replacement.reason,
            "self_heal_status": "remapped_compatible",
        }
        proposals.append(proposal)
        decisions.append(proposal)

    out.to_csv(args.output_map, index=False)
    decisions_df = pd.DataFrame(decisions)
    proposals_df = pd.DataFrame(proposals)
    missing_df = pd.DataFrame(missing)
    decisions_path = sh.SELF_HEAL_DIR / "self_heal_decisions.csv"
    proposals_path = sh.SELF_HEAL_DIR / "self_heal_remap_proposals.csv"
    missing_path = sh.SELF_HEAL_DIR / "self_heal_missing_leaf_queue.csv"
    decisions_df.to_csv(decisions_path, index=False)
    proposals_df.to_csv(proposals_path, index=False)
    missing_df.to_csv(missing_path, index=False)

    assigned_before = int((current["best_esha_code"].astype(str).str.strip() != "").sum())
    assigned_after = int((out["best_esha_code"].astype(str).str.strip() != "").sum())
    summary = {
        "input_map": str(args.input_map),
        "output_map": str(args.output_map),
        "rows": int(len(out)),
        "assigned_before": assigned_before,
        "assigned_after": assigned_after,
        "status_counts": out["self_heal_status"].value_counts().to_dict(),
        "assignment_sources": out["assignment_source"].value_counts().head(50).to_dict(),
        "proposal_rows": int(len(proposals_df)),
        "missing_leaf_rows": int(len(missing_df)),
        "top_reject_reasons": decisions_df["reject_reason"].value_counts().head(50).to_dict() if "reject_reason" in decisions_df else {},
        "top_proposed_heads": proposals_df["new_esha_head"].value_counts().head(50).to_dict() if "new_esha_head" in proposals_df else {},
    }
    sh.summarize_json(args.output_map.with_suffix(".summary.json"), summary)
    sh.summarize_json(sh.SELF_HEAL_DIR / "self_heal_summary.json", summary)
    print(f"wrote {args.output_map} ({len(out):,})", flush=True)
    print(f"assigned before={assigned_before:,} after={assigned_after:,}", flush=True)


if __name__ == "__main__":
    main()
