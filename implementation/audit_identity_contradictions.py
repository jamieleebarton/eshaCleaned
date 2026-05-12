from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
DEFAULT_INPUT = OUT_DIR / "product_to_best_esha_full_map.vIdentity.csv"
DEFAULT_REPORT = OUT_DIR / "identity_contradiction_audit.csv"
DEFAULT_SUMMARY = OUT_DIR / "identity_contradiction_audit.summary.json"


BAKERY_HEADS = {
    "bagel",
    "biscuit",
    "bread",
    "cake",
    "cookie",
    "cracker",
    "muffin",
    "pancakes",
    "waffles",
}

COMPOSED_HEADS = {
    "bar",
    "burrito",
    "dish",
    "fajita",
    "fettuccine",
    "meal",
    "pasta dish",
    "pizza",
    "salad",
    "sandwich",
    "snack",
    "stir fry",
    "wrap",
}

BEVERAGE_CATEGORIES = (
    "juice",
    "drink",
    "beverage",
    "coffee",
    "tea",
    "sport drinks",
    "water enhancer",
    "plant based milk",
)

FRUIT_WORDS = {
    "apple",
    "apricot",
    "banana",
    "blueberry",
    "cherry",
    "coconut",
    "cranberry",
    "date",
    "fig",
    "grape",
    "lemon",
    "lime",
    "mango",
    "orange",
    "papaya",
    "peach",
    "pear",
    "pineapple",
    "plum",
    "prune",
    "raisin",
    "raspberry",
    "strawberry",
}

VEGETABLE_WORDS = {
    "asparagus",
    "bean",
    "beet",
    "broccoli",
    "carrot",
    "corn",
    "garlic",
    "green bean",
    "kale",
    "mushroom",
    "pea",
    "pepper",
    "potato",
    "pumpkin",
    "spinach",
    "tomato",
    "zucchini",
}

SPECIES = ("beef", "pork", "turkey", "chicken", "lamb", "veal")


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def head(row: dict[str, str]) -> str:
    return norm(row.get("best_esha_head"))


def desc(row: dict[str, str]) -> str:
    return norm(row.get("best_esha_description"))


def title(row: dict[str, str]) -> str:
    return norm(row.get("product_description"))


def cat(row: dict[str, str]) -> str:
    return norm(row.get("branded_food_category"))


def has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def any_word(text: str, words: set[str] | tuple[str, ...]) -> bool:
    return any(has_word(text, w) for w in words)


def species_in(text: str) -> set[str]:
    return {s for s in SPECIES if has_word(text, s)}


def fruit_in(text: str) -> set[str]:
    return {f for f in FRUIT_WORDS if has_word(text, f)}


def veg_in(text: str) -> set[str]:
    return {v for v in VEGETABLE_WORDS if has_word(text, v)}


def is_assigned(row: dict[str, str]) -> bool:
    return bool(str(row.get("best_esha_code") or "").strip())


Rule = tuple[str, str, Callable[[dict[str, str]], bool]]


def rules() -> list[Rule]:
    return [
        (
            "cookie_biscuit_category_to_plain_biscuit",
            "Cookies/Biscuits retail category assigned to plain Biscuit when product title does not say biscuit.",
            lambda r: (
                "cookies & biscuits" in cat(r)
                or "biscuits/cookies" in cat(r)
                or "biscuits chocolate" in cat(r)
            )
            and "biscuit" not in title(r)
            and head(r) == "biscuit",
        ),
        (
            "cookie_title_to_plain_biscuit",
            "Cookie product assigned to plain Biscuit.",
            lambda r: any(x in title(r) for x in ("cookie", "cookies", "oreo", "snickerdoodle"))
            and head(r) == "biscuit",
        ),
        (
            "cracker_title_to_plain_biscuit",
            "Cracker product assigned to plain Biscuit.",
            lambda r: any(x in title(r) for x in ("cracker", "crackers", "cheez-it", "cheez it", "goldfish"))
            and head(r) == "biscuit",
        ),
        (
            "turkey_bacon_to_non_turkey_bacon",
            "Product says turkey bacon but ESHA description does not contain turkey bacon.",
            lambda r: "turkey bacon" in title(r) and ("turkey" not in desc(r) or "bacon" not in desc(r)),
        ),
        (
            "pepperoni_to_bacon",
            "Pepperoni/salami/cold-cut product assigned to Bacon.",
            lambda r: any(x in title(r) for x in ("pepperoni", "salami")) and head(r) == "bacon",
        ),
        (
            "single_species_meat_mismatch",
            "Single-species meat product assigned to a different meat species.",
            lambda r: len(species_in(title(r))) == 1
            and len(species_in(desc(r))) >= 1
            and not (species_in(title(r)) & species_in(desc(r))),
        ),
        (
            "fruit_juice_or_drink_to_bakery_head",
            "Beverage/juice product assigned to bread/bakery head.",
            lambda r: (any(x in cat(r) for x in BEVERAGE_CATEGORIES) or any(x in title(r) for x in ("juice", "drink", "beverage")))
            and head(r) in BAKERY_HEADS,
        ),
        (
            "beverage_category_to_solid_composed_head",
            "Beverage category assigned to composed solid food head.",
            lambda r: any(x in cat(r) for x in BEVERAGE_CATEGORIES) and head(r) in (BAKERY_HEADS | COMPOSED_HEADS),
        ),
        (
            "dried_fruit_to_bakery_or_bar",
            "Dried/freeze-dried fruit assigned to bakery/bar/cereal/snack form.",
            lambda r: (fruit_in(title(r)) and any(x in title(r) for x in ("dried", "freeze", "dehydrated", "prune", "raisin")))
            and head(r) in (BAKERY_HEADS | {"bar", "cereal", "chips", "snack"}),
        ),
        (
            "whole_fruit_snack_to_bakery_or_chips",
            "Whole fruit in Wholesome Snacks assigned to bakery/chips/bar.",
            lambda r: "wholesome snacks" in cat(r)
            and fruit_in(title(r))
            and not any(x in title(r) for x in ("bar", "muffin", "cookie", "cake", "chips", "juice", "snack mix"))
            and head(r) in (BAKERY_HEADS | {"bar", "chips", "snack"}),
        ),
        (
            "produce_vegetable_identity_mismatch",
            "Produce vegetable product assigned to a different vegetable identity.",
            lambda r: ("pre-packaged fruit" in cat(r) or "vegetable" in cat(r))
            and veg_in(title(r))
            and veg_in(desc(r))
            and not (veg_in(title(r)) & veg_in(desc(r))),
        ),
        (
            "produce_fruit_to_legume_or_vegetable",
            "Produce fruit product assigned to bean/legume or unrelated vegetable.",
            lambda r: ("pre-packaged fruit" in cat(r) or "wholesome snacks" in cat(r))
            and fruit_in(title(r))
            and any(x in desc(r) for x in ("bean", "beans", "legume", "beet", "carrot"))
            and not (fruit_in(title(r)) & fruit_in(desc(r))),
        ),
        (
            "salad_dressing_to_plain_mustard_or_sauce",
            "Dressing product assigned to plain Mustard/Sauce instead of Salad Dressing.",
            lambda r: ("dressing" in title(r) or "salad dressing" in cat(r)) and head(r) in {"mustard", "sauce"},
        ),
        (
            "sandwich_to_non_sandwich",
            "Sandwich product assigned to non-sandwich head.",
            lambda r: "sandwich" in title(r) and head(r) != "sandwich" and head(r) != "breakfast sandwich",
        ),
        (
            "chicken_strip_to_wrong_composed_head",
            "Chicken strip product assigned to bar/burrito/sandwich/snack/composed dish without meal context.",
            lambda r: "chicken strip" in title(r)
            and head(r) in {"bar", "burrito", "sandwich", "snack", "dish", "meal", "pizza"}
            and not any(x in cat(r) for x in ("frozen dinners", "entrees", "meals", "pizza"))
            and not any(x in title(r) for x in ("sandwich", "pizza", "meal", "salad", "wrap", "pasta")),
        ),
        (
            "dry_pasta_category_to_prepared_dish",
            "Pasta by shape/type category assigned to prepared dish/meal/pizza.",
            lambda r: "pasta by shape" in cat(r)
            and head(r) in {"dish", "meal", "pasta dish", "pizza", "fettuccine"}
            and not any(x in title(r) for x in ("alfredo", "with", "sauce", "meal", "dinner", "pizza")),
        ),
        (
            "plain_mashed_potatoes_to_meal",
            "Plain mashed potatoes assigned to full meal with extra components.",
            lambda r: "mashed potato" in title(r)
            and not any(x in title(r) for x in ("chicken", "beef", "turkey", "pork", "meal", "dinner", "bowl"))
            and head(r) in {"meal", "dish", "pizza"},
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--sample-limit", type=int, default=250)
    args = parser.parse_args()

    rule_defs = rules()
    counts: Counter[str] = Counter()
    samples: dict[str, int] = Counter()
    report_rows: list[dict[str, str]] = []
    total = 0
    assigned = 0

    with args.input.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if not is_assigned(row):
                continue
            assigned += 1
            for name, explanation, predicate in rule_defs:
                if predicate(row):
                    counts[name] += 1
                    if samples[name] < args.sample_limit:
                        samples[name] += 1
                        report_rows.append(
                            {
                                "rule": name,
                                "explanation": explanation,
                                "gtin_upc": row.get("gtin_upc", ""),
                                "fdc_id": row.get("fdc_id", ""),
                                "product_description": row.get("product_description", ""),
                                "branded_food_category": row.get("branded_food_category", ""),
                                "brand_owner": row.get("brand_owner", ""),
                                "brand_name": row.get("brand_name", ""),
                                "best_esha_code": row.get("best_esha_code", ""),
                                "best_esha_description": row.get("best_esha_description", ""),
                                "best_esha_head": row.get("best_esha_head", ""),
                                "assignment_source": row.get("assignment_source", ""),
                                "score": row.get("score", ""),
                            }
                        )

    fields = [
        "rule",
        "explanation",
        "gtin_upc",
        "fdc_id",
        "product_description",
        "branded_food_category",
        "brand_owner",
        "brand_name",
        "best_esha_code",
        "best_esha_description",
        "best_esha_head",
        "assignment_source",
        "score",
    ]
    with args.report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report_rows)

    summary = {
        "input": str(args.input),
        "report": str(args.report),
        "total_rows": total,
        "assigned_rows": assigned,
        "flagged_rows_sampled": len(report_rows),
        "rule_counts": dict(counts.most_common()),
        "rules_with_hits": sum(1 for v in counts.values() if v),
        "rules_total": len(rule_defs),
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
