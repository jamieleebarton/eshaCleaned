from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import self_heal_common as sh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-facts", type=Path, default=sh.SELF_HEAL_DIR / "product_facts.csv")
    parser.add_argument("--esha-facts", type=Path, default=sh.SELF_HEAL_DIR / "esha_facts.csv")
    parser.add_argument("--output", type=Path, default=sh.SELF_HEAL_DIR / "category_head_compatibility.csv")
    args = parser.parse_args()

    sh.SELF_HEAL_DIR.mkdir(parents=True, exist_ok=True)
    facts = pd.read_csv(args.product_facts, dtype=str, keep_default_na=False, low_memory=False)
    esha = pd.read_csv(args.esha_facts, dtype=str, keep_default_na=False, low_memory=False)
    esha_map = sh.esha_fact_map(esha)

    rows = []
    for lane, heads in sh.LANE_HEADS.items():
        for head in heads:
            rows.append(
                {
                    "category_lane": lane,
                    "allowed_esha_head": head,
                    "source": "rule",
                    "support_count": "",
                    "example_categories": "",
                }
            )

    if {"best_esha_code", "category_lane", "target_heads"}.issubset(facts.columns):
        for _, row in facts.iterrows():
            code = str(row.get("best_esha_code") or "").split(".")[0]
            if not code:
                continue
            e = esha_map.get(code)
            if e is None:
                continue
            head = str(e["esha_head"])
            if not sh.head_compatible(str(row.get("target_heads") or "").split("|"), head):
                continue
            rows.append(
                {
                    "category_lane": row["category_lane"],
                    "allowed_esha_head": head,
                    "source": "clean_current_assignment",
                    "support_count": "1",
                    "example_categories": row["branded_food_category"],
                }
            )

    compat = pd.DataFrame(rows)
    grouped = (
        compat.groupby(["category_lane", "allowed_esha_head", "source"], dropna=False)
        .agg(
            support_count=("support_count", lambda s: sum(int(v) for v in s if str(v).isdigit())),
            example_categories=("example_categories", lambda s: sh.top_values([str(v) for v in s if str(v)], 3)),
        )
        .reset_index()
        .sort_values(["category_lane", "source", "support_count"], ascending=[True, True, False])
    )
    grouped.to_csv(args.output, index=False)
    summary = {
        "product_facts": str(args.product_facts),
        "esha_facts": str(args.esha_facts),
        "output": str(args.output),
        "rows": int(len(grouped)),
        "rule_rows": int((grouped["source"] == "rule").sum()),
        "learned_rows": int((grouped["source"] == "clean_current_assignment").sum()),
    }
    sh.summarize_json(args.output.with_suffix(".summary.json"), summary)
    print(f"wrote {args.output} ({len(grouped):,})", flush=True)


if __name__ == "__main__":
    main()
