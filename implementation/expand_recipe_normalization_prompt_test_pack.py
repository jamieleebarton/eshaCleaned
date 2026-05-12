#!/usr/bin/env python3
"""Expand the recipe-normalization prompt stress fixture.

The base fixture is made of real recipes from recipe_qa.db. This expander adds
missing high-risk cases found after reviewing the failure inventory. A small
synthetic recipe is included for exact parser/product surfaces that do not
exist as complete recipe rows in recipe_qa.db, such as "Nabisco 100% bran" and
bare parser fragments.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/Users/jamiebarton/Desktop/clean/data/recipe_qa.db")
DEFAULT_PACK = ROOT / "implementation" / "output" / "recipe_normalization_prompt_test_pack.jsonl"
DEFAULT_INDEX = ROOT / "implementation" / "output" / "recipe_normalization_prompt_test_pack_index.csv"


REAL_STRESS_ADDITIONS = [
    {
        "recipe_id": 41,
        "line_index": 3,
        "case": "shared_sense_pepper",
        "focus": "red pepper is bell/chile produce context, not black pepper spice",
    },
    {
        "recipe_id": 41,
        "line_index": 13,
        "case": "shared_sense_pepper",
        "focus": "black pepper is spice, not bell pepper/chile produce",
    },
    {
        "recipe_id": 39,
        "line_index": 2,
        "case": "shared_sense_chili",
        "focus": "green chili peppers are chile peppers, not chili powder or prepared chili",
    },
    {
        "recipe_id": 39,
        "line_index": 6,
        "case": "shared_sense_pepper",
        "focus": "whole peppercorns are spice seed form, not bell pepper",
    },
    {
        "recipe_id": 39,
        "line_index": 8,
        "case": "shared_sense_coriander",
        "focus": "coriander seeds are seed spice, not cilantro leaf",
    },
    {
        "recipe_id": 39,
        "line_index": 12,
        "case": "shared_sense_coriander",
        "focus": "cilantro leaves are herb leaf, not coriander seed spice",
    },
    {
        "recipe_id": 54,
        "line_index": 12,
        "case": "head_noun_trap",
        "focus": "cream cheese must stay cream cheese, not generic cheese or cream",
    },
    {
        "recipe_id": 139,
        "line_index": 9,
        "case": "head_noun_trap",
        "focus": "coconut milk must stay coconut milk, not dairy milk or coconut",
    },
    {
        "recipe_id": 158,
        "line_index": 6,
        "case": "parenthetical_examples",
        "focus": "orange liqueur examples Cointreau and Grand Marnier must be preserved as examples/options, not machine identity",
    },
    {
        "recipe_id": 71,
        "line_index": 0,
        "case": "bone_in_yield",
        "focus": "bone-in chicken pieces require yield policy and must preserve thighs/drumsticks examples",
    },
    {
        "recipe_id": 71,
        "line_index": 0,
        "case": "parenthetical_examples",
        "focus": "parenthetical examples thighs and drumsticks must be preserved",
    },
    {
        "recipe_id": 352979,
        "line_index": 8,
        "case": "parsed_item_hides_display_options",
        "focus": "parsed item is only topping, but display contains corn flakes/cracker crumbs/cheddar alternatives",
    },
    {
        "recipe_id": 3222,
        "line_index": 8,
        "case": "blend_identity_preservation",
        "focus": "6-cheese Mexican blend must stay a cheese blend identity; do not collapse to generic cheese or a single cheese",
    },
    {
        "recipe_id": 24789,
        "line_index": 8,
        "case": "blend_identity_preservation",
        "focus": "3-cheese gourmet cheddar blend must preserve the 3-cheese blend identity and visible alternative",
    },
    {
        "recipe_id": 11737,
        "line_index": 0,
        "case": "true_alternative_bean_mix",
        "focus": "7 bean mix or 15 bean mix is an explicit alternative, but both are equivalent dried mixed bean soup mix variants for base calculation",
    },
    {
        "recipe_id": 11737,
        "line_index": 0,
        "case": "blend_identity_preservation",
        "focus": "7 bean mix / 15 bean mix must stay a bean mix identity; do not collapse to pinto beans or a single bean",
    },
    {
        "recipe_id": 19546,
        "line_index": 0,
        "case": "blend_identity_preservation",
        "focus": "16-bean mix must stay 16-bean mix; product matching can calculate if a matching product exists",
    },
    {
        "recipe_id": 4627,
        "line_index": 14,
        "case": "true_alternative_cheese_blend",
        "focus": "Monterey Jack cheese or Mexican blend cheese is an explicit alternative; do not silently choose one",
    },
]

OBSOLETE_CASES = {"blend_composition_unknown", "known_concept_not_wrong_proxy"}


SYNTHETIC_RECIPE = {
    "recipe_id": "synthetic_recipe_edge_cases_001",
    "title": "Synthetic Recipe Normalization Edge Cases",
    "cases": [
        "percent_purity_bran_brand",
        "percent_purity_bran_ambiguous",
        "percent_purity_fruit_juice_unknown",
        "percent_purity_pumpkin",
        "protein_powder_percent_flavor",
        "parser_fragment",
        "section_header",
        "section_scoped_ingredient",
        "head_noun_trap",
        "shared_sense_chili",
    ],
    "stress_lines": [
        {
            "line_index": 0,
            "display": "1 cup Nabisco 100% bran",
            "item": "Nabisco 100% bran",
            "grams": 60,
            "case": "percent_purity_bran_brand",
            "focus": "remove Nabisco brand but preserve 100% bran purity/identity; do not map to bread",
        },
        {
            "line_index": 1,
            "display": "1 cup 100% bran",
            "item": "100% bran",
            "grams": 60,
            "case": "percent_purity_bran_ambiguous",
            "focus": "bare 100% bran is ambiguous between bran cereal and crude bran; preserve purity and block without context",
        },
        {
            "line_index": 2,
            "display": "1 cup 100% fruit juice",
            "item": "100% fruit juice",
            "grams": 240,
            "case": "percent_purity_fruit_juice_unknown",
            "focus": "preserve 100% juice claim and block because fruit identity is unknown",
        },
        {
            "line_index": 3,
            "display": "1 can organic 100% pumpkin",
            "item": "organic 100% pumpkin",
            "grams": 425,
            "case": "percent_purity_pumpkin",
            "focus": "100% pumpkin means canned pumpkin/puree identity with organic/purity claims",
        },
        {
            "line_index": 4,
            "display": "1 scoop gold standard 100% whey protein powder, extreme milk chocolate flavor",
            "item": "100% whey protein powder",
            "grams": 30,
            "case": "protein_powder_percent_flavor",
            "focus": "protein powder must preserve whey/isolate percent-style claim and chocolate flavor without fake SKU",
        },
        {
            "line_index": 5,
            "display": "or",
            "item": "or",
            "grams": 0,
            "case": "parser_fragment",
            "focus": "bare parser fragment is not a consumed ingredient",
        },
        {
            "line_index": 6,
            "display": "cooked and",
            "item": "cooked and",
            "grams": 0,
            "case": "parser_fragment",
            "focus": "dangling prep suffix is not a consumed ingredient",
        },
        {
            "line_index": 7,
            "display": "For sauce:",
            "item": "for sauce",
            "grams": 0,
            "case": "section_header",
            "focus": "section header is not a consumed ingredient",
        },
        {
            "line_index": 8,
            "display": "1 cup tomato sauce",
            "item": "tomato sauce",
            "grams": 240,
            "case": "section_scoped_ingredient",
            "focus": "real ingredient following For sauce header should remain consumed/matchable with section=sauce",
        },
        {
            "line_index": 9,
            "display": "Topping:",
            "item": "topping",
            "grams": 0,
            "case": "section_header",
            "focus": "section header is not a consumed ingredient",
        },
        {
            "line_index": 10,
            "display": "4 ounces milk chocolate, chopped",
            "item": "milk chocolate",
            "grams": 113,
            "case": "head_noun_trap",
            "focus": "milk chocolate must stay milk chocolate, not milk or chocolate alone",
        },
        {
            "line_index": 11,
            "display": "1/2 cup peanut butter",
            "item": "peanut butter",
            "grams": 128,
            "case": "head_noun_trap",
            "focus": "peanut butter must stay peanut butter, not butter or peanuts alone",
        },
        {
            "line_index": 12,
            "display": "1 teaspoon chili powder",
            "item": "chili powder",
            "grams": 3,
            "case": "shared_sense_chili",
            "focus": "chili powder is spice blend, not chile pepper or prepared chili",
        },
        {
            "line_index": 13,
            "display": "1 cup prepared chili",
            "item": "chili",
            "grams": 240,
            "case": "shared_sense_chili",
            "focus": "prepared chili is dish/soup/stew sense, not chili powder or chile pepper",
        },
    ],
    "ingredients": [
        {"display": "1 cup Nabisco 100% bran", "item": "Nabisco 100% bran", "grams": 60},
        {"display": "1 cup 100% bran", "item": "100% bran", "grams": 60},
        {"display": "1 cup 100% fruit juice", "item": "100% fruit juice", "grams": 240},
        {"display": "1 can organic 100% pumpkin", "item": "organic 100% pumpkin", "grams": 425},
        {
            "display": "1 scoop gold standard 100% whey protein powder, extreme milk chocolate flavor",
            "item": "100% whey protein powder",
            "grams": 30,
        },
        {"display": "or", "item": "or", "grams": 0},
        {"display": "cooked and", "item": "cooked and", "grams": 0},
        {"display": "For sauce:", "item": "for sauce", "grams": 0},
        {"display": "1 cup tomato sauce", "item": "tomato sauce", "grams": 240},
        {"display": "Topping:", "item": "topping", "grams": 0},
        {"display": "4 ounces milk chocolate, chopped", "item": "milk chocolate", "grams": 113},
        {"display": "1/2 cup peanut butter", "item": "peanut butter", "grams": 128},
        {"display": "1 teaspoon chili powder", "item": "chili powder", "grams": 3},
        {"display": "1 cup prepared chili", "item": "chili", "grams": 240},
    ],
}


def load_pack(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows[str(row["recipe_id"])] = row
    return rows


def load_recipe_from_db(db_path: Path, recipe_id: int) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT recipe_id, recipe_name, ingredients_json FROM recipe_verdicts WHERE recipe_id=?",
            (recipe_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise SystemExit(f"recipe_id {recipe_id} not found in {db_path}")
    rid, title, ingredients_json = row
    ingredients = json.loads(ingredients_json)
    if not isinstance(ingredients, list):
        raise SystemExit(f"recipe_id {recipe_id} ingredients_json is not a list")
    return {
        "recipe_id": rid,
        "title": title,
        "cases": [],
        "stress_lines": [],
        "ingredients": ingredients,
    }


def stress_key(stress: dict[str, Any]) -> tuple[str, str]:
    return (str(stress.get("line_index")), str(stress.get("case")))


def add_stress(row: dict[str, Any], stress: dict[str, Any]) -> None:
    existing = {stress_key(item) for item in row.get("stress_lines", [])}
    if stress_key(stress) not in existing:
        row.setdefault("stress_lines", []).append(stress)
    cases = sorted({item.get("case") for item in row.get("stress_lines", []) if item.get("case")})
    row["cases"] = cases
    row["stress_lines"] = sorted(row.get("stress_lines", []), key=lambda item: (int(item.get("line_index", 0)), item.get("case", "")))


def expand_pack(db_path: Path, pack_path: Path) -> list[dict[str, Any]]:
    rows = load_pack(pack_path)
    for key, row in list(rows.items()):
        row["stress_lines"] = [
            stress for stress in row.get("stress_lines", [])
            if stress.get("case") not in OBSOLETE_CASES
        ]
        row["cases"] = sorted({stress.get("case") for stress in row["stress_lines"] if stress.get("case")})
        if not row["stress_lines"] and key != str(SYNTHETIC_RECIPE["recipe_id"]):
            rows.pop(key)
    for addition in REAL_STRESS_ADDITIONS:
        rid = int(addition["recipe_id"])
        key = str(rid)
        row = rows.get(key) or load_recipe_from_db(db_path, rid)
        ingredients = row["ingredients"]
        line_index = int(addition["line_index"])
        ingredient = ingredients[line_index]
        stress = {
            "line_index": line_index,
            "display": ingredient.get("display", ""),
            "item": ingredient.get("item", ""),
            "grams": ingredient.get("grams"),
            "case": addition["case"],
            "focus": addition["focus"],
        }
        add_stress(row, stress)
        rows[key] = row

    rows[str(SYNTHETIC_RECIPE["recipe_id"])] = SYNTHETIC_RECIPE
    return sorted(rows.values(), key=lambda row: (isinstance(row["recipe_id"], str), str(row["recipe_id"])))


def write_pack(rows: list[dict[str, Any]], pack_path: Path) -> None:
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    with pack_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_index(rows: list[dict[str, Any]], index_path: Path) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["recipe_id", "title", "cases", "stress_line_count", "stress_examples"],
        )
        writer.writeheader()
        for row in rows:
            examples = []
            for stress in row.get("stress_lines", [])[:5]:
                examples.append(
                    f"[{stress.get('case')}] {stress.get('display')} -> item={stress.get('item')} grams={stress.get('grams')}"
                )
            writer.writerow(
                {
                    "recipe_id": row.get("recipe_id"),
                    "title": row.get("title"),
                    "cases": "|".join(row.get("cases", [])),
                    "stress_line_count": len(row.get("stress_lines", [])),
                    "stress_examples": " || ".join(examples),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()

    rows = expand_pack(args.db, args.pack)
    write_pack(rows, args.pack)
    write_index(rows, args.index)
    stress_count = sum(len(row.get("stress_lines", [])) for row in rows)
    cases = sorted({stress["case"] for row in rows for stress in row.get("stress_lines", [])})
    print(json.dumps({"recipes": len(rows), "stress_lines": stress_count, "cases": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
