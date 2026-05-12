from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_MAP = OUT_DIR / "product_to_best_esha_full_map.csv"
SUMMARY_OUT = OUT_DIR / "esha_code_branded_food_category_report.csv"
DETAIL_OUT = OUT_DIR / "esha_code_branded_food_category_detail.csv"
FLAGS_OUT = OUT_DIR / "esha_code_branded_food_category_flags.csv"
SUMMARY_JSON = OUT_DIR / "esha_code_branded_food_category_report_summary.json"


def _clean_category(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return "<missing>"
    return text


def _join_counts(counts: pd.Series, limit: int | None = None) -> str:
    items = counts.sort_values(ascending=False)
    if limit is not None:
        items = items.head(limit)
    return " | ".join(f"{idx}:{int(val)}" for idx, val in items.items())


def _flag_categories(categories: list[str]) -> str:
    text = " || ".join(categories).lower()
    flags: list[str] = []
    category_groups = {
        "yogurt": ("yogurt",),
        "dessert": ("dessert", "ice cream", "frozen yogurt", "gelato", "pudding", "custard"),
        "beverage": ("juice", "drink", "beverage", "water", "soda", "tea", "coffee"),
        "meat": ("bacon", "sausage", "ribs", "meat", "poultry", "chicken", "turkey", "pepperoni", "salami", "cold cuts"),
        "beans": ("beans", "lentil"),
        "dressing": ("dressing", "mayonnaise"),
        "bakery": ("bread", "buns", "bagel", "pastries", "muffins", "croissants", "cookies", "cakes", "cupcakes"),
        "candy": ("candy", "chocolate", "confectionery", "gum", "mints"),
        "produce": ("fruit", "vegetables", "produce"),
        "seasoning": ("seasoning", "spices", "salts", "marinades", "tenderizers"),
    }
    for name, needles in category_groups.items():
        if any(needle in text for needle in needles):
            flags.append(name)
    return "|".join(flags)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--summary-out", type=Path, default=SUMMARY_OUT)
    parser.add_argument("--detail-out", type=Path, default=DETAIL_OUT)
    parser.add_argument("--flags-out", type=Path, default=FLAGS_OUT)
    args = parser.parse_args()

    df = pd.read_csv(args.map, dtype=str, keep_default_na=False, low_memory=False)
    assigned = df[df["best_esha_code"].astype(str).str.strip() != ""].copy()
    assigned["branded_food_category_clean"] = assigned["branded_food_category"].map(_clean_category)
    assigned["best_esha_code"] = assigned["best_esha_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    group_cols = [
        "best_esha_code",
        "best_esha_description",
        "best_esha_head",
        "best_esha_family",
        "branded_food_category_clean",
    ]
    detail = (
        assigned.groupby(group_cols, dropna=False)
        .size()
        .reset_index(name="product_count")
        .sort_values(["best_esha_code", "product_count", "branded_food_category_clean"], ascending=[True, False, True])
    )
    detail["category_share_within_code"] = (
        detail["product_count"] / detail.groupby("best_esha_code")["product_count"].transform("sum")
    ).round(6)

    summary_rows: list[dict[str, object]] = []
    for code, group in detail.groupby("best_esha_code", sort=False):
        first = group.iloc[0]
        counts = group.set_index("branded_food_category_clean")["product_count"]
        categories = list(group["branded_food_category_clean"])
        summary_rows.append(
            {
                "best_esha_code": code,
                "best_esha_description": first["best_esha_description"],
                "best_esha_head": first["best_esha_head"],
                "best_esha_family": first["best_esha_family"],
                "product_count": int(group["product_count"].sum()),
                "branded_food_category_count": int(len(group)),
                "top_branded_food_categories": _join_counts(counts, limit=12),
                "all_branded_food_categories": _join_counts(counts),
                "category_flags": _flag_categories(categories),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["product_count", "branded_food_category_count", "best_esha_code"],
        ascending=[False, False, True],
    )

    flags = summary[
        (summary["branded_food_category_count"] >= 8)
        | summary["category_flags"].str.contains(r"\|", regex=True, na=False)
    ].copy()

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_out, index=False)
    detail.to_csv(args.detail_out, index=False)
    flags.to_csv(args.flags_out, index=False)

    payload = {
        "input_map": str(args.map),
        "assigned_rows": int(len(assigned)),
        "esha_codes": int(len(summary)),
        "detail_rows": int(len(detail)),
        "flagged_codes": int(len(flags)),
        "summary_out": str(args.summary_out),
        "detail_out": str(args.detail_out),
        "flags_out": str(args.flags_out),
        "top_codes_by_product_count": summary.head(20)[
            ["best_esha_code", "best_esha_description", "product_count", "branded_food_category_count"]
        ].to_dict("records"),
    }
    SUMMARY_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
