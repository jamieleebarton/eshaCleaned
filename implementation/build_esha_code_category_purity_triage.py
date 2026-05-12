from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

import self_heal_policy as policy


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_DETAIL = OUT_DIR / "esha_code_branded_food_category_detail.csv"
DEFAULT_MAP = OUT_DIR / "product_to_best_esha_full_map.csv"
OUT_CSV = OUT_DIR / "esha_code_category_purity_triage.csv"
OUT_JSON = OUT_DIR / "esha_code_category_purity_triage_summary.json"


def category_lane(category: str) -> str:
    c = str(category or "").lower()
    if c in {"", "nan", "<missing>"}:
        return "missing"
    bucket = policy.category_bucket(c)
    if bucket:
        return bucket
    rules: list[tuple[str, tuple[str, ...]]] = [
        ("yogurt", ("yogurt",)),
        ("ice_cream_frozen_dessert", ("ice cream", "frozen yogurt", "frozen dessert", "gelato")),
        ("butter_spread", ("butter & spread",)),
        ("nut_butter", ("nut & seed butters",)),
        ("oil", ("oil",)),
        ("sauce_condiment", ("dressing", "mayonnaise", "sauce", "ketchup", "mustard", "bbq", "salsa", "dips", "spreads", "jelly", "jam", "honey", "syrup", "molasses", "condiments")),
        ("cookie_cracker", ("cookies", "biscuits", "crackers", "biscotti")),
        ("cake_dessert", ("cake", "cupcake", "dessert", "pudding", "custard", "gelatin", "gels", "toppings")),
        ("bread_pastry", ("bread", "buns", "bagel", "pastries", "muffins", "croissants", "sweet rolls", "dough", "crusts")),
        ("candy_chocolate", ("candy", "chocolate", "confectionery", "gum", "mints")),
        ("bar_cereal", ("cereal", "granola", "muesli", "energy", "protein", "muscle recovery")),
        ("snack", ("snack", "chips", "pretzels", "popcorn", "peanuts", "seeds")),
        ("fruit_produce", ("fruit", "pre-packaged fruit")),
        ("vegetable_produce", ("vegetable", "tomatoes", "potatoes", "french fries")),
        ("beans_legumes", ("beans", "lentil")),
        ("juice_beverage", ("juice", "nectars", "fruit drinks", "water enhancer")),
        ("drink", ("drink", "beverage", "water", "plant based water", "soda", "tea", "coffee", "sport drinks", "alcohol")),
        ("milk_creamer", ("milk", "cream", "creamer", "cream substitutes")),
        ("cheese", ("cheese",)),
        ("meat", ("meat", "poultry", "chicken", "turkey", "bacon", "sausage", "ribs", "pepperoni", "salami", "cold cuts", "hotdogs", "brats")),
        ("fish_seafood", ("fish", "seafood", "tuna", "shellfish")),
        ("soup", ("soup",)),
        ("prepared_meal", ("frozen dinners", "entrees", "prepared meals", "wraps", "burritos", "pizza", "sushi", "other deli", "sandwiches", "variety packs")),
        ("seasoning", ("seasoning", "spices", "salts", "marinades", "tenderizers", "extracts", "herbs")),
        ("flour_baking", ("flour", "corn meal", "baking", "mixes/supplies", "baking needs")),
        ("pasta_rice_grain", ("pasta", "noodles", "rice", "grains", "flavored rice")),
        ("baby_health_supplement", ("baby", "infant", "vitamins", "supplements", "health care", "weight control")),
    ]
    for lane, needles in rules:
        if any(needle in c for needle in needles):
            return lane
    return "other"


def expected_lanes(head: str, description: str) -> set[str]:
    h = str(head or "").lower()
    d = str(description or "").lower()
    text = f"{h} {d}"
    pairs: list[tuple[set[str], tuple[str, ...]]] = [
        ({"cookie_cracker", "cake_dessert"}, ("cookie", "cookies")),
        ({"cookie_cracker"}, ("cracker", "biscuit")),
        ({"cake_dessert", "flour_baking"}, ("cake", "cupcake", "brownie")),
        ({"cake_dessert", "ice_cream_frozen_dessert"}, ("ice cream", "frozen dessert")),
        ({"bread_pastry"}, ("bread", "bagel", "bun", "roll", "muffin", "croissant", "pastry", "doughnut")),
        ({"candy_chocolate"}, ("candy", "chocolate", "gum")),
        ({"bar_cereal", "snack"}, ("bar", "cereal", "oatmeal", "granola", "oats")),
        ({"snack"}, ("snack", "chips", "pretzel", "popcorn", "nuts", "seeds", "trail mix")),
        ({"fruit_produce", "juice_beverage"}, ("apple", "banana", "fruit", "mango", "strawberry", "blueberry", "raisin", "coconut")),
        ({"vegetable_produce"}, ("vegetable", "tomato", "pumpkin", "asparagus", "broccoli", "corn", "peas", "potato")),
        ({"beans_legumes", "vegetable_produce", "prepared_meal"}, ("green bean", "green beans", "beans, green", "beans green")),
        ({"beans_legumes", "prepared_meal"}, ("beans", "bean", "lentil")),
        ({"juice_beverage", "drink"}, ("juice", "drink", "smoothie", "beverage")),
        ({"drink"}, ("water", "tea", "coffee", "soda")),
        ({"milk_creamer"}, ("milk", "yogurt", "cream substitute", "cream", "creamer")),
        ({"cheese"}, ("cheese",)),
        ({"meat", "prepared_meal"}, ("bacon", "sausage", "turkey", "chicken", "pork", "beef", "ham", "lunchmeat", "salami")),
        ({"fish_seafood", "prepared_meal"}, ("fish", "seafood", "shrimp", "tuna")),
        ({"prepared_meal"}, ("dish", "meal", "pizza", "sandwich", "wrap", "burrito", "pasta dish")),
        ({"soup", "prepared_meal"}, ("soup", "chili", "stew")),
        ({"sauce_condiment"}, ("sauce", "dressing", "salsa", "dip", "hummus", "jelly", "jam", "syrup", "spread", "mayonnaise")),
        ({"sauce_condiment"}, ("catsup", "ketchup", "mustard")),
        ({"seasoning"}, ("seasoning", "spice", "salt", "pepper")),
        ({"oil"}, ("oil",)),
        ({"butter_spread", "milk_creamer"}, ("butter",)),
        ({"nut_butter", "sauce_condiment"}, ("peanut butter", "nut butter")),
        ({"flour_baking"}, ("flour", "baking powder", "baking soda", "baking mix")),
        ({"pasta_rice_grain", "prepared_meal"}, ("pasta", "rice", "noodles")),
    ]
    lanes: set[str] = set()
    for expected, needles in pairs:
        if any(needle in text for needle in needles):
            lanes |= expected
    return lanes or {"other"}


def join_counts(items: pd.Series) -> str:
    return " | ".join(f"{idx}:{int(val)}" for idx, val in items.items())


def entropy(counts: pd.Series) -> float:
    total = counts.sum()
    if total <= 0:
        return 0.0
    return float(-sum((v / total) * math.log2(v / total) for v in counts if v))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", type=Path, default=DEFAULT_DETAIL)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--output", type=Path, default=OUT_CSV)
    args = parser.parse_args()

    detail = pd.read_csv(args.detail, dtype=str, keep_default_na=False, low_memory=False)
    detail["product_count_num"] = detail["product_count"].astype(int)
    detail["category_lane"] = detail["branded_food_category_clean"].map(category_lane)
    detail["policy_category_bucket"] = detail["branded_food_category_clean"].map(lambda c: policy.category_bucket(c) or "")
    detail["policy_head_allowed"] = detail.apply(
        lambda r: policy.category_allows_head(
            category=str(r.get("branded_food_category_clean") or ""),
            product_description="",
            title_tokens=(),
            candidate_head=str(r.get("best_esha_head") or ""),
        )[0],
        axis=1,
    )

    rows: list[dict[str, object]] = []
    for code, group in detail.groupby("best_esha_code", sort=False):
        first = group.iloc[0]
        total = int(group["product_count_num"].sum())
        raw_counts = group.set_index("branded_food_category_clean")["product_count_num"].sort_values(ascending=False)
        lane_counts = group.groupby("category_lane")["product_count_num"].sum().sort_values(ascending=False)
        dominant_category = raw_counts.index[0]
        dominant_category_count = int(raw_counts.iloc[0])
        dominant_lane = lane_counts.index[0]
        dominant_lane_count = int(lane_counts.iloc[0])
        expected = expected_lanes(str(first["best_esha_head"]), str(first["best_esha_description"]))
        compatible = group[group["category_lane"].isin(expected)]["product_count_num"].sum()
        incompatible = total - int(compatible)
        incompatible_counts = (
            group[~group["category_lane"].isin(expected)]
            .groupby("category_lane")["product_count_num"]
            .sum()
            .sort_values(ascending=False)
        )
        policy_incompatible = int(group[~group["policy_head_allowed"]]["product_count_num"].sum())
        policy_incompatible_counts = (
            group[~group["policy_head_allowed"]]
            .groupby("branded_food_category_clean")["product_count_num"]
            .sum()
            .sort_values(ascending=False)
        )
        raw_off_counts = group[~group["category_lane"].isin(expected)].set_index("branded_food_category_clean")["product_count_num"].sort_values(ascending=False)
        dominant_share = dominant_category_count / total if total else 0.0
        dominant_lane_share = dominant_lane_count / total if total else 0.0
        incompatible_share = incompatible / total if total else 0.0
        severity = round((incompatible * 2.0) + (total * (1.0 - dominant_lane_share)) + (len(group) * 4.0), 3)
        rows.append(
            {
                "best_esha_code": code,
                "best_esha_description": first["best_esha_description"],
                "best_esha_head": first["best_esha_head"],
                "best_esha_family": first["best_esha_family"],
                "product_count": total,
                "raw_category_count": int(len(group)),
                "lane_count": int(len(lane_counts)),
                "dominant_category": dominant_category,
                "dominant_category_count": dominant_category_count,
                "dominant_category_share": round(dominant_share, 6),
                "dominant_lane": dominant_lane,
                "dominant_lane_count": dominant_lane_count,
                "dominant_lane_share": round(dominant_lane_share, 6),
                "category_entropy": round(entropy(raw_counts), 6),
                "expected_lanes": "|".join(sorted(expected)),
                "incompatible_rows": incompatible,
                "incompatible_share": round(incompatible_share, 6),
                "policy_incompatible_rows": policy_incompatible,
                "policy_incompatible_share": round(policy_incompatible / total if total else 0.0, 6),
                "severity_score": severity,
                "lane_counts": join_counts(lane_counts),
                "incompatible_lane_counts": join_counts(incompatible_counts),
                "top_categories": join_counts(raw_counts.head(15)),
                "top_incompatible_categories": join_counts(raw_off_counts.head(15)),
                "top_policy_incompatible_categories": join_counts(policy_incompatible_counts.head(15)),
            }
        )

    triage = pd.DataFrame(rows)
    triage = triage.sort_values(
        ["severity_score", "incompatible_rows", "raw_category_count", "product_count"],
        ascending=False,
    )
    triage.to_csv(args.output, index=False)

    payload = {
        "detail": str(args.detail),
        "output": str(args.output),
        "codes": int(len(triage)),
        "codes_with_incompatible_rows": int((triage["incompatible_rows"] > 0).sum()),
        "codes_with_policy_incompatible_rows": int((triage["policy_incompatible_rows"] > 0).sum()),
        "codes_with_raw_category_count_ge_10": int((triage["raw_category_count"] >= 10).sum()),
        "top_25": triage.head(25)[
            [
                "best_esha_code",
                "best_esha_description",
                "product_count",
                "raw_category_count",
                "dominant_category_share",
                "incompatible_rows",
                "severity_score",
            ]
        ].to_dict("records"),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
