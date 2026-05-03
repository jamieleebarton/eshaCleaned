#!/usr/bin/env python3
"""Audit whether consensus retail paths are in the right store location.

This is a focused failure-pattern inventory for consensus_full_corpus_audit.csv.
It complements the broad BFC co-occurrence reports by capturing concrete,
inspectable route mistakes and policy splits.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from taxonomy_finalizer import path_defects


V2 = Path(__file__).resolve().parent
SRC = V2 / "consensus_full_corpus_audit.csv"
OUT_CSV = V2 / "consensus_right_place_issue_inventory.csv"
OUT_SUMMARY = V2 / "consensus_right_place_audit_summary.json"
OUT_MD = V2 / "consensus_right_place_audit.md"

VALID_DEPARTMENTS = {
    "Baby & Toddler",
    "Bakery",
    "Beverage",
    "Dairy",
    "Frozen",
    "Meal",
    "Meat & Seafood",
    "Other",
    "Pantry",
    "Produce",
    "Snack",
    "Sports & Wellness",
}

COOKIE_CRACKER_BFCS = {
    "biscuits/cookies",
    "biscuits/cookies (shelf stable)",
    "cookies & biscuits",
    "crackers & biscotti",
}

BEVERAGE_BFCS = {
    "Alcohol",
    "Coffee",
    "Juice",
    "Milk Additives",
    "Other Drinks",
    "Powdered Drinks",
    "Tea",
}

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


def split_path(path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*>\s*", path or "") if part.strip()]


def path_starts(row: dict[str, str], *prefixes: str) -> bool:
    path = row.get("retail_leaf_path", "") or ""
    return any(path.startswith(prefix) for prefix in prefixes)


def canonical_starts(row: dict[str, str], *prefixes: str) -> bool:
    path = row.get("canonical_path", "") or ""
    return any(path.startswith(prefix) for prefix in prefixes)


def title_has(row: dict[str, str], pattern: str) -> bool:
    return bool(re.search(pattern, row.get("title", "") or "", re.I))


def bfc(row: dict[str, str]) -> str:
    return (row.get("branded_food_category") or "").strip()


def bfc_lower(row: dict[str, str]) -> str:
    return bfc(row).lower()


def first_title_phrase(row: dict[str, str]) -> str:
    return (row.get("title", "") or "").split(",", 1)[0]


def first_phrase_has(row: dict[str, str], pattern: str) -> bool:
    return bool(re.search(pattern, first_title_phrase(row), re.I))


def looks_like_cookie_flavored_cookie(row: dict[str, str]) -> bool:
    phrase = first_title_phrase(row)
    return bool(
        re.search(r"\bcookies?\b", phrase, re.I)
        and re.search(r"\b(birthday\s+cake|cake\s+batter|short\s*cake|ice\s+cream\s+cake)\b", phrase, re.I)
    )


def is_true_biscotti_product(row: dict[str, str]) -> bool:
    return title_has(row, r"\bbiscotti|biscottini\b") and bfc_lower(row) in COOKIE_CRACKER_BFCS


RULES: list[IssueRule] = [
    IssueRule(
        issue_family="sandwich_cookie_or_cracker_routed_as_meal_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route sandwich cookies/biscuits to Bakery > Cookies and sandwich crackers to Snack > Crackers; do not use Meal > Sandwiches.",
        rationale="Sandwich describes cookie/cracker construction here, not a prepared deli sandwich.",
        predicate=lambda r: (
            bfc_lower(r) in COOKIE_CRACKER_BFCS
            and path_starts(r, "Meal > Sandwiches")
            and title_has(r, r"\b(cookie|cookies|biscuit|biscuits|cracker|crackers|creme|sandwich)\b")
        ),
    ),
    IssueRule(
        issue_family="frozen_appetizer_sandwich_not_frozen",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Keep frozen sandwiches/pockets/sliders under a Frozen sandwich/appetizer shelf.",
        rationale="The sandwich identity is right, but the Frozen department was lost.",
        predicate=lambda r: (
            bfc(r) == "Frozen Appetizers & Hors D'oeuvres"
            and path_starts(r, "Meal > Sandwiches")
        ),
    ),
    IssueRule(
        issue_family="soup_chowder_or_bisque_routed_as_seafood",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route seafood soups, chowders, and bisques to Pantry > Soup/Chowder shelves; keep seafood as variant/component.",
        rationale="Clam, crab, lobster, or shrimp is an ingredient, not the retail shelf.",
        predicate=lambda r: (
            bfc(r) in {"Other Soups", "Canned Soup"}
            and path_starts(r, "Meat & Seafood")
            and title_has(r, r"\b(soup|chowder|bisque|gumbo|broth|base)\b")
        ),
    ),
    IssueRule(
        issue_family="dip_salsa_or_cocktail_sauce_routed_as_seafood",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route crab/shrimp/clam dips and cocktail sauces to Pantry > Dips & Spreads or Pantry > Sauces & Salsas.",
        rationale="Seafood is flavor/component evidence, while the shopper-facing product is a dip or sauce.",
        predicate=lambda r: (
            bfc(r) in {"Dips & Salsa", "Dips & Spreads"}
            and path_starts(r, "Meat & Seafood")
            and title_has(r, r"\b(dip|salsa|cocktail\s+sauce|sauce)\b")
        ),
    ),
    IssueRule(
        issue_family="seasoning_marinade_routed_as_meat_or_seafood",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route seafood rubs, boils, pastes, and marinades to Pantry > Spices & Seasonings or sauces/marinades.",
        rationale="The target protein named in the seasoning is stealing the retail category.",
        predicate=lambda r: (
            bfc(r) == "Seasoning Mixes, Salts, Marinades & Tenderizers"
            and path_starts(r, "Meat & Seafood")
            and title_has(r, r"\b(seasoning|rub|marinade|boil|paste|sauce\s+mix|tenderizer)\b")
        ),
    ),
    IssueRule(
        issue_family="cheese_slices_routed_as_meal_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route sandwich slices and processed cheese food to Dairy > Cheese, not Meal > Sandwiches.",
        rationale="Sandwich is a use/form cue for cheese slices, not the product category.",
        predicate=lambda r: (
            bfc(r) == "Cheese"
            and path_starts(r, "Meal > Sandwiches")
        ),
    ),
    IssueRule(
        issue_family="pickle_sandwich_slices_routed_as_meal_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route sandwich slices/bread-and-butter slices to Pantry pickle/relish shelves.",
        rationale="Sandwich modifies pickle slice use case; it is not a prepared sandwich.",
        predicate=lambda r: (
            bfc(r) == "Pickles, Olives, Peppers & Relishes"
            and path_starts(r, "Meal > Sandwiches")
        ),
    ),
    IssueRule(
        issue_family="salad_kit_not_on_produce_salad_kit_shelf",
        severity="high",
        confidence="medium",
        action_type="policy_fix_candidate",
        likely_fix="Adopt one salad-kit home, preferably Produce > Salad Kits for produce BFC rows and a deliberate Meal variant only when policy says so.",
        rationale="Salad kit is the shopper-facing identity; components like croutons, pasta, and pickles should not own the path.",
        predicate=lambda r: (
            title_has(r, r"\bsalad\s+kit\b")
            and not path_starts(r, "Produce > Salad Kits")
        ),
    ),
    IssueRule(
        issue_family="prepackaged_produce_salad_split_to_meal",
        severity="medium",
        confidence="medium",
        action_type="policy_decision",
        likely_fix="Decide whether packaged produce salads stay under Produce > Salad Kits/Packaged Salads rather than Meal > Salads.",
        rationale="The path is a salad, but the branded category says packaged produce; this is a shopper-department policy split.",
        predicate=lambda r: (
            bfc(r) == "Pre-Packaged Fruit & Vegetables"
            and path_starts(r, "Meal > Salads")
        ),
    ),
    IssueRule(
        issue_family="pickle_bfc_salad_source_conflict",
        severity="medium",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Keep true salads in Meal/Produce salad shelves, but mark the Pickles/Olives BFC as dirty source evidence for these rows.",
        rationale="The path is usually right; the branded_food_category is often wrong for fresh salads in this bucket.",
        predicate=lambda r: (
            bfc(r) == "Pickles, Olives, Peppers & Relishes"
            and path_starts(r, "Meal > Salads")
            and title_has(r, r"\bsalad\b")
        ),
    ),
    IssueRule(
        issue_family="salad_topping_routed_as_finished_salad",
        severity="medium",
        confidence="medium",
        action_type="policy_fix_candidate",
        likely_fix="Route salad toppers, tortilla strips, croutons, nuts, and dressing add-ins to Pantry/Snack topping shelves, not Meal > Salads.",
        rationale="These rows are salad components, not complete salads.",
        predicate=lambda r: (
            bfc(r) == "Salad Dressing & Mayonnaise"
            and path_starts(r, "Meal > Salads")
            and title_has(r, r"\b(topping|toppings|toppins|topper|croutons?|strips?|nuggets?)\b")
        ),
    ),
    IssueRule(
        issue_family="baking_decoration_or_topping_routed_as_candy",
        severity="medium",
        confidence="medium",
        action_type="policy_decision",
        likely_fix="Decide whether baking decorations, edible confetti, melts, peels, and dessert toppings stay in Pantry baking/topping shelves even when candy-like.",
        rationale="The product may look like candy, but the source category/use case says baking decoration or dessert topping.",
        predicate=lambda r: (
            bfc(r) == "Baking Decorations & Dessert Toppings"
            and path_starts(r, "Snack > Candy", "Snack > Chocolate Candy")
        ),
    ),
    IssueRule(
        issue_family="candy_bfc_routed_outside_snack_candy",
        severity="medium",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Review whether the BFC is dirty or whether ice cream/cracker/sandwich words hijacked true candy.",
        rationale="Candy BFC is overwhelmingly Snack; non-Snack rows are small but suspicious.",
        predicate=lambda r: (
            bfc(r) == "Candy"
            and not path_starts(r, "Snack > Candy", "Snack > Chocolate Candy")
        ),
    ),
    IssueRule(
        issue_family="mexican_dinner_mix_left_in_baking_mixes",
        severity="high",
        confidence="medium",
        action_type="deterministic_fix_candidate",
        likely_fix="Route Mexican dinner/meal products to meal kits, tortillas, beans, sides, or other Mexican pantry shelves instead of Baking Mixes.",
        rationale="Baking Mixes is still acting as a generic Mix bucket for non-baking Mexican dinner products.",
        predicate=lambda r: (
            bfc(r) == "Mexican Dinner Mixes"
            and path_starts(r, "Pantry > Baking Mixes")
        ),
    ),
    IssueRule(
        issue_family="vegetable_lentil_mix_left_in_baking_mixes",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route beans, lentils, grains, sea vegetables, and potato sides out of Pantry > Baking Mixes.",
        rationale="Vegetable/lentil/grain products are not baking mixes unless title explicitly says baking mix.",
        predicate=lambda r: (
            bfc(r) == "Vegetable and Lentil Mixes"
            and path_starts(r, "Pantry > Baking Mixes")
        ),
    ),
    IssueRule(
        issue_family="beverage_bfc_left_in_baking_mixes",
        severity="high",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Review BFC/title conflict; drink mixes belong in Beverage unless the title is truly a cake/baking mix.",
        rationale="Baking Mixes can still swallow beverage-flavored mixes.",
        predicate=lambda r: (
            bfc(r) in BEVERAGE_BFCS
            and path_starts(r, "Pantry > Baking Mixes")
        ),
    ),
    IssueRule(
        issue_family="alcohol_bfc_routed_outside_beverage",
        severity="high",
        confidence="medium",
        action_type="source_conflict_review",
        likely_fix="Review the row; Alcohol BFC should usually resolve to Beverage/cocktail mixer territory unless BFC is dirty.",
        rationale="Alcohol branded category outside Beverage is a strong department conflict.",
        predicate=lambda r: bfc(r) == "Alcohol" and not path_starts(r, "Beverage"),
    ),
    IssueRule(
        issue_family="prepared_sandwich_routed_to_bakery_carrier",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route prepared hot dogs/subs/sandwiches to Meal > Sandwiches; keep bun/roll as a form/component.",
        rationale="A bakery carrier word won over the prepared-sandwich source category.",
        predicate=lambda r: (
            bfc(r) in {"Prepared Subs & Sandwiches", "Prepared Sandwiches", "Sandwiches/Filled Rolls/Wraps"}
            and path_starts(r, "Bakery")
        ),
    ),
    IssueRule(
        issue_family="biscotti_product_routed_as_meal_sandwich",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route sandwich biscotti products to Bakery > Biscotti, not Meal > Sandwiches.",
        rationale="Sandwich is a biscotti form/fill cue, not a prepared meal sandwich.",
        predicate=lambda r: is_true_biscotti_product(r) and path_starts(r, "Meal > Sandwiches"),
    ),
    IssueRule(
        issue_family="cracker_title_still_under_bakery_cookies",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route obvious cracker rows still under Bakery > Cookies to Snack > Crackers.",
        rationale="A few abbreviated cracker titles still survived on the cookie shelf.",
        predicate=lambda r: (
            path_starts(r, "Bakery > Cookies")
            and title_has(r, r"\b(crackers?|crckrs)\b")
        ),
    ),
    IssueRule(
        issue_family="cake_or_cupcake_product_routed_as_cookie",
        severity="medium",
        confidence="review",
        action_type="manual_review",
        likely_fix="Review cake/cupcake/madeleine/Jaffa rows under Bakery > Cookies; true cakes should move to Bakery > Cakes, cookie-flavored cookies can stay.",
        rationale="Cookies-and-cream or cake flavor can be a modifier, but cake as product identity should not be a cookie.",
        predicate=lambda r: (
            path_starts(r, "Bakery > Cookies")
            and first_phrase_has(r, r"\b(cake|cakes|cupcake|cupcakes|madeleine|madeleines|jaffa\s+cakes?)\b")
            and not looks_like_cookie_flavored_cookie(r)
        ),
    ),
    IssueRule(
        issue_family="plant_milk_redundant_plant_based_modifier",
        severity="medium",
        confidence="high",
        action_type="normalization_fix_candidate",
        likely_fix="Drop Plant Based from modifier tails when the canonical path is already Beverage > Plant Milk.",
        rationale="Plant Based repeats the parent concept and creates duplicate paths.",
        predicate=lambda r: (
            path_starts(r, "Beverage > Plant Milk")
            and bool(re.search(r"\s>\sPlant Based(?:\s>|$)", r.get("retail_leaf_path", "") or ""))
        ),
    ),
    IssueRule(
        issue_family="beverage_or_creamer_hijacked_to_bakery_flavor",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route coffee, latte, cold brew, and creamers to Beverage; keep churro/biscotti/cinnamon roll as flavor modifiers.",
        rationale="A bakery flavor token became the product category.",
        predicate=lambda r: (
            bfc(r) in BEVERAGE_BFCS
            and path_starts(r, "Bakery")
            and title_has(r, r"\b(coffee|latte|cold\s*brew|creamer|espresso|cappuccino|iced\s+coffee)\b")
        ),
    ),
    IssueRule(
        issue_family="coffee_creamer_not_on_creamer_shelf",
        severity="high",
        confidence="high",
        action_type="deterministic_fix_candidate",
        likely_fix="Route title-level coffee creamers to Beverage > Coffee Creamer.",
        rationale="Coffee creamer should not live under plant milk, bakery, or generic mix shelves.",
        predicate=lambda r: (
            bfc(r) == "Milk Additives"
            and title_has(r, r"\bcreamer\b")
            and not path_starts(r, "Beverage > Coffee Creamer", "Beverage > Creamers")
        ),
    ),
    IssueRule(
        issue_family="churro_flavor_hijacked_non_bakery_product",
        severity="high",
        confidence="medium",
        action_type="deterministic_fix_candidate",
        likely_fix="Only route actual churros to Bakery > Pastry > Churros; keep churro as flavor for drinks, cereal, bars, candy, etc.",
        rationale="Churro is often a flavor line rather than product identity.",
        predicate=lambda r: (
            path_starts(r, "Bakery > Pastry > Churros")
            and bfc_lower(r)
            not in {
                "biscuits/cookies",
                "cookies & biscuits",
                "croissants, sweet rolls, muffins & other pastries",
                "sweet bakery products",
                "cakes, cupcakes, snack cakes",
            }
        ),
    ),
    IssueRule(
        issue_family="ice_cream_title_left_under_bakery_review",
        severity="low",
        confidence="review",
        action_type="manual_review",
        likely_fix="Review residual ice-cream-title rows under Bakery; many are cookie flavors, but true frozen desserts should move to Frozen.",
        rationale="Explicit ice cream words under Bakery deserve spot checking after the main frozen-dessert fixes.",
        predicate=lambda r: title_has(r, r"\bice\s+cream\b") and path_starts(r, "Bakery"),
    ),
    IssueRule(
        issue_family="ice_cream_bfc_routed_outside_frozen_review",
        severity="medium",
        confidence="review",
        action_type="manual_review",
        likely_fix="Review Ice Cream & Frozen Yogurt BFC rows outside Frozen for dirty BFC versus missed frozen product.",
        rationale="Most ice cream BFC rows should be Frozen, but the source BFC can be dirty.",
        predicate=lambda r: bfc(r) == "Ice Cream & Frozen Yogurt" and not path_starts(r, "Frozen"),
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
        "consensus_source": row.get("consensus_source", ""),
        "consensus_reason": row.get("consensus_reason", ""),
    }


def structural_metrics(rows: Iterable[dict[str, str]]) -> dict[str, object]:
    rows = list(rows)
    fdc_counts = Counter((row.get("fdc_id") or "").strip() for row in rows)
    defect_counts: Counter[str] = Counter()
    invalid_department = 0
    empty_leaf = 0
    for row in rows:
        for defect in path_defects(row):
            defect_counts[defect] += 1
        leaf = row.get("retail_leaf_path", "") or ""
        if not leaf.strip():
            empty_leaf += 1
        parts = split_path(leaf)
        if parts and parts[0] not in VALID_DEPARTMENTS:
            invalid_department += 1
    return {
        "rows": len(rows),
        "unique_fdc_ids": len(fdc_counts),
        "duplicate_fdc_extra_rows": sum(count - 1 for count in fdc_counts.values() if count > 1),
        "empty_retail_leaf_path_rows": empty_leaf,
        "invalid_department_rows": invalid_department,
        "path_defect_rows": sum(defect_counts.values()),
        "path_defects": dict(defect_counts.most_common()),
    }


def markdown_table_rows(rows: list[dict[str, str]]) -> list[str]:
    out = ["| fdc_id | BFC | path | title |", "|---|---|---|---|"]
    for row in rows:
        title = (row["title"] or "").replace("|", "\\|")[:140]
        bfc_value = (row["branded_food_category"] or "").replace("|", "\\|")[:80]
        path = (row["retail_leaf_path"] or "").replace("|", "\\|")[:120]
        out.append(f"| {row['fdc_id']} | {bfc_value} | {path} | {title} |")
    return out


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run build_consensus_full_corpus_audit.py first")

    with SRC.open(newline="", encoding="utf-8", errors="replace") as handle:
        rows = list(csv.DictReader(handle))

    issue_rows: list[dict[str, str]] = []
    issue_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        for rule in RULES:
            if not rule.predicate(row):
                continue
            out = row_for_issue(row, rule)
            issue_rows.append(out)
            issue_counts[rule.issue_family] += 1
            severity_counts[rule.severity] += 1
            action_counts[rule.action_type] += 1
            if len(examples[rule.issue_family]) < 8:
                examples[rule.issue_family].append(out)

    fields = list(row_for_issue({}, RULES[0]).keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(issue_rows)

    unique_issue_fdcs = {row["fdc_id"] for row in issue_rows if row["fdc_id"]}
    high_conf_fdcs = {
        row["fdc_id"]
        for row in issue_rows
        if row["fdc_id"] and row["severity"] == "high" and row["confidence"] == "high"
    }
    deterministic_fdcs = {
        row["fdc_id"]
        for row in issue_rows
        if row["fdc_id"] and row["action_type"] == "deterministic_fix_candidate"
    }

    summary = {
        "source": str(SRC),
        "outputs": {
            "csv": str(OUT_CSV),
            "json": str(OUT_SUMMARY),
            "markdown": str(OUT_MD),
        },
        "structural_metrics": structural_metrics(rows),
        "issue_rows": len(issue_rows),
        "unique_issue_fdc_ids": len(unique_issue_fdcs),
        "high_high_confidence_unique_fdc_ids": len(high_conf_fdcs),
        "deterministic_fix_unique_fdc_ids": len(deterministic_fdcs),
        "issue_counts": dict(issue_counts.most_common()),
        "severity_counts": dict(severity_counts.most_common()),
        "action_counts": dict(action_counts.most_common()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Consensus Right-Place Audit",
        "",
        f"Source: `{SRC.name}`",
        f"Rows: `{len(rows):,}`",
        f"Unique issue FDC ids: `{len(unique_issue_fdcs):,}`",
        f"High severity + high confidence FDC ids: `{len(high_conf_fdcs):,}`",
        f"Deterministic-fix FDC ids: `{len(deterministic_fdcs):,}`",
        "",
        "## Structural Metrics",
        "",
    ]
    metrics = summary["structural_metrics"]
    for key in (
        "unique_fdc_ids",
        "duplicate_fdc_extra_rows",
        "empty_retail_leaf_path_rows",
        "invalid_department_rows",
        "path_defect_rows",
    ):
        lines.append(f"- `{key}`: `{metrics[key]:,}`")

    lines.extend(["", "## Issue Counts", ""])
    for family, count in issue_counts.most_common():
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
        ])
        lines.extend(markdown_table_rows(examples[family]))
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "rows": len(rows),
        "unique_issue_fdc_ids": len(unique_issue_fdcs),
        "high_high_confidence_unique_fdc_ids": len(high_conf_fdcs),
        "deterministic_fix_unique_fdc_ids": len(deterministic_fdcs),
        "top_issues": dict(issue_counts.most_common(15)),
        "outputs": summary["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
