#!/usr/bin/env python3
"""Build a concrete taxonomy issue inventory from Codex's rebuilt corpus.

This is deliberately narrower than the BFC outlier queue. It does not try to
label every suspicious row as wrong. It captures repeated, inspectable failure
patterns with examples and a suggested fix direction.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "codex_full_corpus_audit.csv"
OUT_CSV = V2 / "codex_taxonomy_issue_inventory.csv"
OUT_SUMMARY = V2 / "codex_taxonomy_issue_inventory_summary.json"
OUT_MD = V2 / "codex_taxonomy_issue_inventory.md"

csv.field_size_limit(sys.maxsize)


@dataclass(frozen=True)
class IssueRule:
    issue_family: str
    severity: str
    confidence: str
    action_type: str
    likely_fix: str
    rationale: str
    predicate: Callable[[dict[str, str]], bool]


def first_path(path: str, depth: int) -> str:
    return " > ".join([p.strip() for p in (path or "").split(" > ") if p.strip()][:depth])


def title_has(row: dict[str, str], pattern: str) -> bool:
    return bool(re.search(pattern, row.get("title", "") or "", re.I))


def path_starts(row: dict[str, str], *prefixes: str) -> bool:
    path = row.get("canonical_path", "") or ""
    return path.startswith(prefixes)


def bfc(row: dict[str, str]) -> str:
    return (row.get("branded_food_category") or "").strip()


def bfc_lower(row: dict[str, str]) -> str:
    return bfc(row).lower()


def identity_has(row: dict[str, str], pattern: str) -> bool:
    return bool(re.search(pattern, row.get("product_identity_fixed", "") or "", re.I))


def reference_text(row: dict[str, str]) -> str:
    return " ".join([
        row.get("fndds_desc", "") or "",
        row.get("sr28_desc", "") or "",
        row.get("esha_desc", "") or "",
        row.get("matched_key", "") or "",
    ])


BAKERY_BFCS = {
    "biscuits/cookies",
    "cookies & biscuits",
    "croissants, sweet rolls, muffins & other pastries",
    "sweet bakery products",
    "cakes, cupcakes, snack cakes",
}

COOKIE_CRACKER_BFCS = {
    "biscuits/cookies",
    "cookies & biscuits",
    "crackers & biscotti",
}


RULES: list[IssueRule] = [
    IssueRule(
        issue_family="bread_carrier_routed_as_meal_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Breads & Buns rows whose title is bread/bun/roll should stay in Bakery carrier shelves, not Meal > Sandwiches.",
        rationale="A retail bread carrier was interpreted as a prepared sandwich because of words like sandwich, hamburger, or roll.",
        predicate=lambda r: (
            bfc(r) == "Breads & Buns"
            and path_starts(r, "Meal > Sandwiches")
            and title_has(r, r"\b(bread|buns?|rolls?|bagels?|english\s+muffins?|pita|flatbread|hamburger|hot\s*dog)\b")
        ),
    ),
    IssueRule(
        issue_family="prepared_sandwich_identity_is_carrier",
        severity="medium",
        confidence="high",
        action_type="identity_fix_candidate",
        likely_fix="Keep under Meal > Sandwiches, but replace carrier identities like Sandwich Rolls/Croissants/Slider Buns with Sandwich/Sub/Slider/etc.",
        rationale="The department is right, but the product identity is the bread carrier instead of the prepared sandwich.",
        predicate=lambda r: (
            bfc_lower(r) in {
                "prepared subs & sandwiches",
                "prepared sandwiches",
                "sandwiches/filled rolls/wraps",
            }
            and path_starts(r, "Meal > Sandwiches")
            and identity_has(r, r"\b(buns?|rolls?|croissants?|baguette|ciabatta|flatbread|english\s+muffins?)\b")
        ),
    ),
    IssueRule(
        issue_family="charcuterie_roll_routed_as_bakery_roll",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route meat/cheese roll-up snacks to Meat & Seafood > Charcuterie or a snack/meat roll-up shelf, not Bakery > Rolls.",
        rationale="Roll means rolled meat/cheese, not bread.",
        predicate=lambda r: (
            bfc(r) in {"Pepperoni, Salami & Cold Cuts", "Cooked & Prepared"}
            and path_starts(r, "Bakery > Rolls")
            and title_has(r, r"\broll")
        ),
    ),
    IssueRule(
        issue_family="beverage_or_creamer_hijacked_to_bakery_flavor",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route coffee, latte, cold brew, and coffee creamer products to Beverage/Coffee Creamer; keep churro/cinnamon roll/biscotti as modifiers.",
        rationale="A bakery flavor token became the product category.",
        predicate=lambda r: (
            bfc(r) in {"Other Drinks", "Milk Additives", "Coffee", "Powdered Drinks"}
            and path_starts(r, "Bakery > Pastry", "Bakery > Biscotti")
            and title_has(r, r"\b(coffee|latte|cold\s*brew|creamer|espresso|cappuccino|nitro)\b")
        ),
    ),
    IssueRule(
        issue_family="coffee_creamer_not_on_creamer_shelf",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route title-level coffee creamers to Beverage > Coffee Creamer or Beverage > Creamers.",
        rationale="Coffee creamer should not live under bakery flavors, generic mixes, or plant milk identity shelves.",
        predicate=lambda r: (
            title_has(r, r"\bcoffee\s+creamer\b|\bcreamer\b")
            and bfc(r) == "Milk Additives"
            and not path_starts(r, "Beverage > Coffee Creamer", "Beverage > Creamers")
        ),
    ),
    IssueRule(
        issue_family="churro_flavor_word_became_churro_product",
        severity="high",
        confidence="medium",
        action_type="deterministic_fix_candidate",
        likely_fix="Use the BFC/title product type as category and keep Churro/Cinnamon Churro as flavor modifier unless product is actually churros.",
        rationale="Churro is often a flavor line for cereal, coffee, candy, bars, cheesecake, or mix.",
        predicate=lambda r: (
            path_starts(r, "Bakery > Pastry > Churros")
            and bfc_lower(r) not in BAKERY_BFCS
        ),
    ),
    IssueRule(
        issue_family="snack_bar_routed_as_meal_or_ingredient",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route snack/energy/granola/cereal bars to Snack > Bars; keep sandwich/PB&J/salmon/apple pie as modifiers.",
        rationale="The word sandwich or an ingredient token stole the route away from the bar product.",
        predicate=lambda r: (
            bfc_lower(r) in {"snack, energy & granola bars", "cereal/muesli bars"}
            and title_has(r, r"\bbars?\b")
            and first_path(r.get("canonical_path", ""), 1) not in {"Snack", "Frozen"}
        ),
    ),
    IssueRule(
        issue_family="vegetable_lentil_item_still_in_baking_mixes",
        severity="high",
        confidence="medium",
        action_type="deterministic_fix_candidate",
        likely_fix="Route legumes, grains, dried vegetables, kelp/sea vegetables, and potato sides out of Pantry > Baking Mixes unless clearly a baking mix.",
        rationale="Baking Mixes is still catching vegetable/lentil/grain products.",
        predicate=lambda r: (
            bfc(r) == "Vegetable and Lentil Mixes"
            and path_starts(r, "Pantry > Baking Mixes")
        ),
    ),
    IssueRule(
        issue_family="nut_seed_butter_routed_to_dairy_butter",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route nut/seed/granola/oat butters to Pantry nut butter/spread shelves; reserve Dairy > Butter for dairy butter.",
        rationale="The word butter is being treated as dairy even when the branded category is nut/seed butter.",
        predicate=lambda r: bfc(r) == "Nut & Seed Butters" and path_starts(r, "Dairy > Butter"),
    ),
    IssueRule(
        issue_family="canned_vegetable_routed_to_fresh_produce",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route Canned Vegetables BFC rows to Pantry canned/pickled vegetable shelves unless title evidence proves fresh produce.",
        rationale="Canned/shelf-stable vegetables are being routed as fresh produce because the vegetable identity overrode the storage/category context.",
        predicate=lambda r: bfc(r) == "Canned Vegetables" and path_starts(r, "Produce > Vegetables"),
    ),
    IssueRule(
        issue_family="frozen_vegetable_routed_to_canned_pantry",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route Frozen Vegetables rows away from Pantry > Canned Vegetables; use a frozen vegetable shelf or an explicit frozen-storage policy.",
        rationale="Frozen vegetables should not be classified as canned pantry vegetables.",
        predicate=lambda r: bfc(r) == "Frozen Vegetables" and path_starts(r, "Pantry > Canned Vegetables"),
    ),
    IssueRule(
        issue_family="frozen_appetizer_routed_to_non_frozen_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route frozen breakfast/appetizer sandwich forms under Frozen, not generic Meal > Sandwiches.",
        rationale="Frozen branded categories are losing storage context when the title contains sandwich, pancake sandwich, griddle cake, or similar carrier words.",
        predicate=lambda r: (
            bfc(r) == "Frozen Appetizers & Hors D'oeuvres"
            and path_starts(r, "Meal > Sandwiches")
        ),
    ),
    IssueRule(
        issue_family="cookie_cracker_sandwich_routed_as_meal",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Keep sandwich cookies, sandwich cremes, sandwich biscuits, and sandwich crackers on cookie/cracker shelves, not Meal > Sandwiches.",
        rationale="The word sandwich describes a cookie/cracker construction, not a prepared deli sandwich.",
        predicate=lambda r: (
            bfc_lower(r) in COOKIE_CRACKER_BFCS
            and path_starts(r, "Meal > Sandwiches")
        ),
    ),
    IssueRule(
        issue_family="soup_or_chowder_routed_as_seafood",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route clam/crab/lobster chowders and seafood soups to soup/chowder shelves; keep seafood as a variant/component.",
        rationale="A named ingredient in soup/chowder is stealing the product identity.",
        predicate=lambda r: (
            bfc(r) in {"Other Soups", "Canned Soup"}
            and path_starts(r, "Meat & Seafood")
            and title_has(r, r"\b(soup|chowder|bisque|gumbo)\b")
        ),
    ),
    IssueRule(
        issue_family="dip_or_salsa_routed_as_seafood",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route crab/shrimp/artichoke dips to Pantry > Dips & Spreads or Pantry > Dips & Salsa; seafood belongs as a variant/component.",
        rationale="A seafood ingredient is being classified as the retail item instead of the dip.",
        predicate=lambda r: (
            bfc(r) in {"Dips & Salsa", "Dips & Spreads"}
            and path_starts(r, "Meat & Seafood")
            and title_has(r, r"\b(dip|salsa)\b")
        ),
    ),
    IssueRule(
        issue_family="pickles_relishes_routed_as_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route sandwich stuffers, bread-and-butter pickles, olives, peppers, and relishes to Pantry pickle/relish shelves.",
        rationale="The word sandwich in a condiment/pickle title is being interpreted as a prepared sandwich.",
        predicate=lambda r: bfc(r) == "Pickles, Olives, Peppers & Relishes" and path_starts(r, "Meal > Sandwiches"),
    ),
    IssueRule(
        issue_family="salad_kit_not_on_salad_kit_shelf",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route title-level salad kits to Produce > Salad Kits or the chosen Meal > Salad Kits policy shelf, not ingredient/component shelves.",
        rationale="Salad kit is the shopper-facing product identity; croutons, dressing, pasta, or flatbread are components/modifiers.",
        predicate=lambda r: (
            title_has(r, r"\bsalad\s+kit\b")
            and not path_starts(r, "Produce > Salad Kits", "Meal > Salad Kits")
        ),
    ),
    IssueRule(
        issue_family="plant_milk_redundant_plant_based_modifier",
        severity="medium",
        confidence="high",
        action_type="normalization_fix_candidate",
        likely_fix="Drop Plant Based from the modifier path when the canonical path is already Beverage > Plant Milk.",
        rationale="Plant Based repeats the parent concept and creates paths like Beverage > Plant Milk > Almond Milk > Plant Based.",
        predicate=lambda r: (
            path_starts(r, "Beverage > Plant Milk")
            and "Plant Based" in (r.get("retail_leaf_path", "") or "")
        ),
    ),
    IssueRule(
        issue_family="biscotti_product_not_single_biscotti_shelf",
        severity="medium",
        confidence="high",
        action_type="normalization_fix_candidate",
        likely_fix="Route true biscotti/biscottini products to the one canonical biscotti shelf; keep biscotti flavor-only rows in the host product category.",
        rationale="True biscotti products should have one discoverable path.",
        predicate=lambda r: (
            bfc_lower(r) in COOKIE_CRACKER_BFCS
            and title_has(r, r"\bbiscotti|biscottini\b")
            and not path_starts(r, "Bakery > Biscotti")
        ),
    ),
    IssueRule(
        issue_family="baking_decoration_routed_as_snack_candy",
        severity="medium",
        confidence="medium",
        action_type="policy_decision",
        likely_fix="Decide whether edible decorations, candy melts, baking bars, sprinkles, and dessert toppings should remain Pantry baking decorations even when candy-like.",
        rationale="The product may be candy-like, but the branded category and shopper use case are baking decoration/topping.",
        predicate=lambda r: (
            bfc(r) == "Baking Decorations & Dessert Toppings"
            and path_starts(r, "Snack > Candy", "Snack > Chocolate Candy", "Snack > Candied Fruit")
        ),
    ),
    IssueRule(
        issue_family="frozen_storage_department_policy_split",
        severity="medium",
        confidence="medium",
        action_type="policy_decision",
        likely_fix="Choose whether frozen vegetable/fruit BFCs should live under Frozen or under Produce with frozen as storage metadata.",
        rationale="The corpus currently mixes storage-as-department and product-family-as-department for frozen produce.",
        predicate=lambda r: (
            bfc(r) in {"Frozen Vegetables", "Frozen Fruit"}
            and not path_starts(r, "Frozen")
        ),
    ),
    IssueRule(
        issue_family="alcohol_bfc_not_beverage",
        severity="medium",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Review whether BFC is dirty or whether cocktail/drink context should force Beverage.",
        rationale="Alcohol BFC should usually be Beverage, but several titles look like candy/supplements/meat/seasoning.",
        predicate=lambda r: bfc_lower(r) == "alcohol" and not path_starts(r, "Beverage"),
    ),
    IssueRule(
        issue_family="ice_cream_bfc_title_conflict_non_frozen",
        severity="medium",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Review BFC/title conflict; do not blindly force to Frozen when title says yogurt, cheese, dried fruit, soft drink, or cereal.",
        rationale="BFC says Ice Cream & Frozen Yogurt but title/product evidence says a different product family.",
        predicate=lambda r: bfc(r) == "Ice Cream & Frozen Yogurt" and not path_starts(r, "Frozen"),
    ),
    IssueRule(
        issue_family="ice_cream_title_left_under_bakery",
        severity="medium",
        confidence="review",
        action_type="manual_review",
        likely_fix="Decide whether each is a true bakery flavor product or a frozen dessert missed by rules.",
        rationale="Residual explicit ice-cream title rows under Bakery after the frozen dessert repair.",
        predicate=lambda r: title_has(r, r"\bice\s+cream\b") and path_starts(r, "Bakery"),
    ),
    IssueRule(
        issue_family="salad_kit_policy_split",
        severity="medium",
        confidence="medium",
        action_type="policy_decision",
        likely_fix="Decide whether all salad kits belong under Produce > Salad Kits or whether protein/meal kits belong under Meal > Salad Kits.",
        rationale="The taxonomy currently splits salad kits between Produce and Meal.",
        predicate=lambda r: title_has(r, r"\bsalad\s+kit\b") and not path_starts(r, "Produce > Salad Kits"),
    ),
    IssueRule(
        issue_family="pickles_bfc_contains_finished_salads",
        severity="medium",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Review BFC/title conflict. Title says salad; BFC says pickles/olives/peppers/relishes.",
        rationale="This looks like dirty branded_food_category data rather than a simple path bug.",
        predicate=lambda r: bfc(r) == "Pickles, Olives, Peppers & Relishes" and path_starts(r, "Meal > Salads"),
    ),
    IssueRule(
        issue_family="biscotti_fragmentation_residual",
        severity="low",
        confidence="review",
        action_type="manual_review",
        likely_fix="Verify whether non-Bakery > Biscotti rows are true biscotti products or flavor inclusions in ice cream/sandwiches.",
        rationale="Biscotti is mostly consolidated, but a few rows remain outside the one shelf.",
        predicate=lambda r: (
            (title_has(r, r"\bbiscotti|biscottini\b") or identity_has(r, r"\bbiscotti\b"))
            and not path_starts(r, "Bakery > Biscotti")
        ),
    ),
]


def row_for_issue(row: dict[str, str], rule: IssueRule) -> dict[str, str]:
    return {
        "issue_family": rule.issue_family,
        "severity": rule.severity,
        "confidence": rule.confidence,
        "action_type": rule.action_type,
        "likely_fix": rule.likely_fix,
        "rationale": rule.rationale,
        "fdc_id": row.get("fdc_id", ""),
        "title": row.get("title", ""),
        "branded_food_category": row.get("branded_food_category", ""),
        "category_path_fixed": row.get("category_path_fixed", ""),
        "product_identity_fixed": row.get("product_identity_fixed", ""),
        "canonical_path": row.get("canonical_path", ""),
        "modifier": row.get("modifier", ""),
        "retail_leaf_path": row.get("retail_leaf_path", ""),
        "fndds_desc": row.get("fndds_desc", ""),
        "sr28_desc": row.get("sr28_desc", ""),
        "esha_desc": row.get("esha_desc", ""),
        "matched_key": row.get("matched_key", ""),
    }


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run build_codex_full_corpus_audit.py first")

    issue_rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    with SRC.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for rule in RULES:
                if not rule.predicate(row):
                    continue
                out = row_for_issue(row, rule)
                issue_rows.append(out)
                counts[rule.issue_family] += 1
                severity_counts[rule.severity] += 1
                action_counts[rule.action_type] += 1
                if len(examples[rule.issue_family]) < 8:
                    examples[rule.issue_family].append(out)

    fieldnames = list(issue_rows[0].keys()) if issue_rows else [
        "issue_family", "severity", "confidence", "action_type", "likely_fix",
        "rationale", "fdc_id", "title", "branded_food_category",
        "category_path_fixed", "product_identity_fixed", "canonical_path",
        "modifier", "retail_leaf_path", "fndds_desc", "sr28_desc",
        "esha_desc", "matched_key",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issue_rows)

    summary = {
        "source": str(SRC),
        "issue_rows": len(issue_rows),
        "unique_fdc_ids": len({row["fdc_id"] for row in issue_rows}),
        "issue_counts": dict(counts.most_common()),
        "severity_counts": dict(severity_counts.most_common()),
        "action_counts": dict(action_counts.most_common()),
        "outputs": {
            "csv": str(OUT_CSV),
            "json": str(OUT_SUMMARY),
            "markdown": str(OUT_MD),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Codex Taxonomy Issue Inventory",
        "",
        f"Source: `{SRC.name}`",
        f"Issue rows: `{len(issue_rows):,}`",
        f"Unique FDC ids: `{summary['unique_fdc_ids']:,}`",
        "",
        "This report is a concrete failure-pattern inventory, not a broad outlier score.",
        "",
        "## Issue Counts",
        "",
    ]
    for family, count in counts.most_common():
        rule = next(rule for rule in RULES if rule.issue_family == family)
        lines.extend([
            f"### {family}",
            "",
            f"- rows: `{count:,}`",
            f"- severity: `{rule.severity}`",
            f"- confidence: `{rule.confidence}`",
            f"- action: `{rule.action_type}`",
            f"- likely fix: {rule.likely_fix}",
            "",
            "| fdc_id | BFC | current path | title |",
            "|---|---|---|---|",
        ])
        for ex in examples[family]:
            title = (ex["title"] or "").replace("|", "\\|")[:140]
            bfc_value = (ex["branded_food_category"] or "").replace("|", "\\|")[:80]
            path = (ex["retail_leaf_path"] or "").replace("|", "\\|")[:120]
            lines.append(f"| {ex['fdc_id']} | {bfc_value} | {path} | {title} |")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "issue_rows": len(issue_rows),
        "unique_fdc_ids": summary["unique_fdc_ids"],
        "top_issues": dict(counts.most_common(10)),
        "outputs": summary["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
