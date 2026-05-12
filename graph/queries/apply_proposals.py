"""Apply healed proposals to a v2 main-map CSV.

Reads:
  implementation/output/product_to_best_esha_full_map.csv  (current)
  graph/quarantine/healed_proposals_agreement.csv          (proposals)

Applies HIGH and MEDIUM confidence proposals:
  HIGH:   has_joint_signal AND joint_share >= 0.5 AND proposal_score >= 1.0
  MEDIUM: vote_score >= 0.5 AND proposal_score >= 0.5

Writes:
  implementation/output/product_to_best_esha_full_map.v2.csv (mutated)
  graph/quarantine/applied_diff.csv                          (full diff log)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.csv"
PROPOSALS_CSV = ROOT / "graph" / "quarantine" / "healed_proposals_agreement.csv"
OUT_CSV = ROOT / "implementation" / "output" / "product_to_best_esha_full_map.v2.csv"
DIFF_CSV = ROOT / "graph" / "quarantine" / "applied_diff.csv"
SUMMARY = ROOT / "graph" / "quarantine" / "applied_summary.json"

HIGH_JOINT_SHARE = 0.5
HIGH_PROPOSAL_SCORE = 1.0
MEDIUM_VOTE_SCORE = 0.3
MEDIUM_PROPOSAL_SCORE = 0.3


def main() -> None:
    print(f"reading {SRC_CSV.name}", flush=True)
    src = pd.read_csv(SRC_CSV, dtype=str, keep_default_na=False, low_memory=False)
    print(f"  rows: {len(src):,}", flush=True)

    print(f"reading {PROPOSALS_CSV.name}", flush=True)
    prop = pd.read_csv(PROPOSALS_CSV, dtype=str, keep_default_na=False, low_memory=False)
    prop["joint_share"] = pd.to_numeric(prop["joint_share"], errors="coerce")
    prop["vote_score"] = pd.to_numeric(prop["vote_score"], errors="coerce")
    prop["proposal_score"] = pd.to_numeric(prop["proposal_score"], errors="coerce")
    prop["has_joint_signal"] = prop["has_joint_signal"].astype(str).str.lower() == "true"
    prop = prop[prop["proposed_esha_code"] != ""].copy()
    print(f"  proposals with a target code: {len(prop):,}", flush=True)

    high_mask = (
        prop["has_joint_signal"]
        & (prop["joint_share"].fillna(0) >= HIGH_JOINT_SHARE)
        & (prop["proposal_score"].fillna(0) >= HIGH_PROPOSAL_SCORE)
    )
    medium_mask = (
        ~high_mask
        & (prop["vote_score"].fillna(0) >= MEDIUM_VOTE_SCORE)
        & (prop["proposal_score"].fillna(0) >= MEDIUM_PROPOSAL_SCORE)
    )
    prop["confidence_tier"] = "low"
    prop.loc[high_mask, "confidence_tier"] = "high"
    prop.loc[medium_mask, "confidence_tier"] = "medium"
    print("  confidence breakdown:", flush=True)
    print(prop["confidence_tier"].value_counts().to_string(), flush=True)

    apply = prop[prop["confidence_tier"].isin(["high", "medium"])].copy()
    print(f"  applying {len(apply):,} proposals (high+medium)", flush=True)

    apply_idx = apply.set_index("gtin_upc")
    src_indexed = src.set_index("gtin_upc")
    overlap = src_indexed.index.intersection(apply_idx.index)
    print(f"  rows in main map matched by gtin: {len(overlap):,}", flush=True)

    diff_rows = []
    src_indexed_copy = src_indexed.copy()
    for gtin in overlap:
        proposal = apply_idx.loc[gtin]
        if isinstance(proposal, pd.DataFrame):
            proposal = proposal.iloc[0]
        old_code = src_indexed_copy.at[gtin, "best_esha_code"]
        old_desc = src_indexed_copy.at[gtin, "best_esha_description"]
        old_family = src_indexed_copy.at[gtin, "best_esha_family"]
        new_code = str(proposal["proposed_esha_code"]).split(".")[0]
        new_desc = str(proposal["proposed_esha_description"])
        new_family = str(proposal["target_family"])
        if not new_code or new_code == "nan":
            continue
        src_indexed_copy.at[gtin, "best_esha_code"] = new_code
        src_indexed_copy.at[gtin, "best_esha_description"] = new_desc
        src_indexed_copy.at[gtin, "best_esha_family"] = new_family
        src_indexed_copy.at[gtin, "assignment_source"] = f"healed_v0.2_{proposal['confidence_tier']}"
        diff_rows.append({
            "gtin_upc": gtin,
            "old_esha_code": old_code,
            "old_esha_description": old_desc,
            "old_esha_family": old_family,
            "new_esha_code": new_code,
            "new_esha_description": new_desc,
            "new_esha_family": new_family,
            "tier": proposal["confidence_tier"],
            "vote_provenance": proposal["vote_provenance"],
        })

    diff_df = pd.DataFrame(diff_rows)
    diff_df.to_csv(DIFF_CSV, index=False)
    print(f"  wrote {DIFF_CSV.relative_to(ROOT)}  ({len(diff_df):,} changed rows)", flush=True)

    out = src_indexed_copy.reset_index()
    out = out[src.columns.tolist()]
    out.to_csv(OUT_CSV, index=False)
    print(f"  wrote {OUT_CSV.relative_to(ROOT)}", flush=True)

    summary = {
        "source_rows": int(len(src)),
        "proposals_total": int(len(prop)),
        "proposals_high": int((prop["confidence_tier"] == "high").sum()),
        "proposals_medium": int((prop["confidence_tier"] == "medium").sum()),
        "proposals_low": int((prop["confidence_tier"] == "low").sum()),
        "applied_changes": int(len(diff_df)),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
