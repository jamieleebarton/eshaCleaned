from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
NO_VALID_CSV = OUT_DIR / "head_remap_no_valid_esha.csv"
OUT_QUEUE = OUT_DIR / "head_remap_missing_leaf_queue.csv"
OUT_SUMMARY = OUT_DIR / "head_remap_missing_leaf_summary.json"


def top_examples(values: pd.Series, limit: int = 5) -> str:
    seen: list[str] = []
    for value in values.astype(str):
        clean = value.strip()
        if clean and clean not in seen:
            seen.append(clean)
        if len(seen) >= limit:
            break
    return " || ".join(seen)


def main() -> None:
    no_valid = pd.read_csv(NO_VALID_CSV, dtype=str, keep_default_na=False, low_memory=False)
    if no_valid.empty:
        OUT_QUEUE.write_text("", encoding="utf-8")
        OUT_SUMMARY.write_text(json.dumps({"rows": 0}, indent=2) + "\n", encoding="utf-8")
        return

    grouped = (
        no_valid.groupby(["quarantine_reason", "candidate_heads", "branded_food_category"], dropna=False)
        .agg(
            n_products=("gtin_upc", "count"),
            examples=("product_description", top_examples),
            top_brands=("brand_name", top_examples),
        )
        .reset_index()
        .sort_values(["n_products", "quarantine_reason"], ascending=[False, True])
    )
    grouped.to_csv(OUT_QUEUE, index=False)

    summary = {
        "input_rows": int(len(no_valid)),
        "queue_rows": int(len(grouped)),
        "top_quarantine_reasons": no_valid["quarantine_reason"].value_counts().head(30).to_dict(),
        "top_candidate_heads": no_valid["candidate_heads"].value_counts().head(30).to_dict(),
        "top_categories": no_valid["branded_food_category"].value_counts().head(30).to_dict(),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT_QUEUE.relative_to(ROOT)} ({len(grouped):,} rows)")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
