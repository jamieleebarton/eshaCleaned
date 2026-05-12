#!/usr/bin/env python3
"""Calculate ingredient grams from Nebius recipe-normalization output.

This is recipe-side calculation only. It does not choose ESHA/SR28/FNDDS,
retail products, UPCs, or nutrient values.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from implementation.recipe_calculation_defaults import (
    lookup_retention,
    lookup_sodium,
    lookup_uptake,
    lookup_yield,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "implementation" / "output" / "recipe_normalization_nebius_candidate.jsonl"
DEFAULT_LINES = ROOT / "implementation" / "output" / "recipe_normalization_nebius_calculation_lines.csv"
DEFAULT_SUMMARY = ROOT / "implementation" / "output" / "recipe_normalization_nebius_calculation_summary.csv"
DEFAULT_MD = ROOT / "implementation" / "output" / "recipe_normalization_nebius_calculation_summary.md"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def should_apply_to_taste_default(ingredient: dict[str, Any], source_grams: float | None) -> bool:
    if source_grams is None or source_grams <= 0:
        return False
    role = text(ingredient.get("role"))
    if role != "consumed":
        return False
    haystack = " ".join(
        [
            text(ingredient.get("original_display")),
            text(ingredient.get("rewritten_ingredient")),
            text((ingredient.get("normalized") or {}).get("machine_name")),
            text((ingredient.get("normalized") or {}).get("product_identity")),
        ]
    ).lower()
    if "to taste" not in haystack:
        return False
    process_terms = {"pasta water", "boiling water", "frying", "dredging", "dusting", "coating", "garnish"}
    if any(term in haystack for term in process_terms):
        return False
    return True


def haystack_for(ingredient: dict[str, Any]) -> str:
    normalized = ingredient.get("normalized") if isinstance(ingredient.get("normalized"), dict) else {}
    return " ".join(
        [
            text(ingredient.get("original_display")),
            text(ingredient.get("original_item")),
            text(ingredient.get("rewritten_ingredient")),
            text(normalized.get("machine_name")),
            text(normalized.get("product_identity")),
            text(normalized.get("culinary_use")),
        ]
    ).lower()


def range_midpoint_grams(quantity: dict[str, Any], source_grams: float | None) -> float | None:
    if source_grams is None or source_grams <= 0:
        return None
    low = number(quantity.get("range_low"))
    high = number(quantity.get("range_high"))
    if low is None or high is None or high <= 0 or low > high:
        return None
    midpoint = (low + high) / 2.0
    return source_grams * midpoint / high


def calculation_default(
    ingredient: dict[str, Any],
    *,
    source_grams: float | None,
    raw_calc_status: str,
    raw_policy: str,
    quantity: dict[str, Any],
) -> tuple[str, str, float | None, str, Any]:
    """Return calculation status, policy, grams, applied-policy label, blockers.

    Dispatch is on the policy class (consumption.consumption_policy and
    matchability.status), never on substrings of the ingredient name.
    Substring lookups happen only inside a class via recipe_calculation_defaults.
    """
    consumption = ingredient.get("consumption") if isinstance(ingredient.get("consumption"), dict) else {}
    matchability = ingredient.get("matchability") if isinstance(ingredient.get("matchability"), dict) else {}
    blockers = consumption.get("blockers") or matchability.get("match_blockers") or []
    consumed_grams = number(consumption.get("consumed_grams"))
    haystack = haystack_for(ingredient)

    midpoint_grams = range_midpoint_grams(quantity, source_grams)
    if midpoint_grams is not None and text(ingredient.get("role")) == "consumed" and raw_policy != "selected_option_required":
        return (
            "CALCULATION_READY",
            "range_midpoint_default_applied",
            midpoint_grams,
            "range_midpoint_default_applied",
            [],
        )

    if raw_calc_status == "EXCLUDED":
        return raw_calc_status, raw_policy, consumed_grams, "", blockers

    if raw_calc_status != "BLOCKED":
        return raw_calc_status, raw_policy, consumed_grams, "", blockers

    if should_apply_to_taste_default(ingredient, source_grams):
        return (
            "CALCULATION_READY",
            "to_taste_source_grams_default_applied",
            source_grams,
            "to_taste_source_grams_default_applied",
            [],
        )

    if (
        text(matchability.get("status")) == "BLOCKED"
        and source_grams is not None
        and source_grams > 0
    ):
        return (
            "CALCULATION_READY",
            "identity_ambiguous_source_grams_default_applied",
            source_grams,
            "identity_ambiguous_source_grams_default_applied",
            [],
        )

    if raw_policy == "yield_policy_required" and source_grams is not None:
        factor, tag = lookup_yield(haystack)
        return ("CALCULATION_READY", tag, source_grams * factor, tag, [])

    if raw_policy == "retention_policy_required" and source_grams is not None:
        factor, tag = lookup_retention(haystack)
        return ("CALCULATION_READY", tag, source_grams * factor, tag, [])

    if raw_policy == "uptake_policy_required" and source_grams is not None:
        factor, tag = lookup_uptake(haystack)
        return ("CALCULATION_READY", tag, source_grams * factor, tag, [])

    if raw_policy == "sodium_absorption_policy_required" and source_grams is not None:
        factor, tag = lookup_sodium(haystack)
        return ("CALCULATION_READY", tag, source_grams * factor, tag, [])

    if raw_policy == "serving_selection_required":
        return (
            "EXCLUDED",
            "serving_accompaniment_excluded_applied",
            0.0,
            "serving_accompaniment_excluded_applied",
            blockers,
        )

    if raw_policy == "selected_option_required" and source_grams is not None:
        yield_factor, yield_tag = lookup_yield(haystack)
        if yield_tag != "yield_policy_default_50pct_applied":
            tag = f"selected_option_first_alternative_with_{yield_tag}"
            return ("CALCULATION_READY", tag, source_grams * yield_factor, tag, [])
        return (
            "CALCULATION_READY",
            "selected_option_first_alternative_applied",
            source_grams,
            "selected_option_first_alternative_applied",
            [],
        )

    return raw_calc_status, raw_policy, consumed_grams, "", blockers


def short(value: str, limit: int = 120) -> str:
    value = value.replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def ingredient_row(recipe: dict[str, Any], ingredient: dict[str, Any]) -> dict[str, str]:
    normalized = ingredient.get("normalized") if isinstance(ingredient.get("normalized"), dict) else {}
    matchability = ingredient.get("matchability") if isinstance(ingredient.get("matchability"), dict) else {}
    consumption = ingredient.get("consumption") if isinstance(ingredient.get("consumption"), dict) else {}
    quantity = ingredient.get("quantity") if isinstance(ingredient.get("quantity"), dict) else {}
    choice = ingredient.get("calculation_choice") if isinstance(ingredient.get("calculation_choice"), dict) else {}

    raw_calc_status = text(consumption.get("calculation_status"))
    raw_policy = text(consumption.get("consumption_policy"))
    source_grams = number(quantity.get("source_grams", ingredient.get("source_grams")))
    calc_status, consumption_policy, consumed_grams, policy_applied, blockers = calculation_default(
        ingredient,
        source_grams=source_grams,
        raw_calc_status=raw_calc_status,
        raw_policy=raw_policy,
        quantity=quantity,
    )

    calculated_grams = consumed_grams if calc_status == "CALCULATION_READY" else 0.0 if calc_status == "EXCLUDED" else None

    return {
        "recipe_id": text(recipe.get("recipe_id")),
        "title": text(recipe.get("title")),
        "line_index": text(ingredient.get("line_index")),
        "original_display": text(ingredient.get("original_display")),
        "rewritten_ingredient": text(ingredient.get("rewritten_ingredient")),
        "machine_name": text(normalized.get("machine_name")),
        "product_identity": text(normalized.get("product_identity")),
        "role": text(ingredient.get("role")),
        "match_status": text(matchability.get("status")),
        "raw_calculation_status": raw_calc_status,
        "consumption_policy": consumption_policy,
        "calculation_status": calc_status,
        "policy_applied": policy_applied,
        "calculation_choice": text(choice.get("selected_ingredient")),
        "requires_user_selection": text(choice.get("requires_user_selection")),
        "source_grams": fmt(source_grams),
        "calculated_grams": fmt(calculated_grams),
        "blockers": text(blockers),
    }


def build_rows(recipes: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    line_rows: list[dict[str, str]] = []
    summary_rows: list[dict[str, str]] = []
    for recipe in recipes:
        ingredients = recipe.get("ingredients") if isinstance(recipe.get("ingredients"), list) else []
        recipe_rows = [ingredient_row(recipe, ing) for ing in ingredients if isinstance(ing, dict)]
        line_rows.extend(recipe_rows)

        status_counts = Counter(row["calculation_status"] for row in recipe_rows)
        policy_counts = Counter(row["consumption_policy"] for row in recipe_rows)
        ready_grams = sum(number(row["calculated_grams"]) or 0.0 for row in recipe_rows if row["calculation_status"] == "CALCULATION_READY")
        excluded_source_grams = sum(number(row["source_grams"]) or 0.0 for row in recipe_rows if row["calculation_status"] == "EXCLUDED")
        blocked_source_grams = sum(number(row["source_grams"]) or 0.0 for row in recipe_rows if row["calculation_status"] == "BLOCKED")
        blockers = [
            f"L{row['line_index']} {row['rewritten_ingredient'] or row['original_display']}: {row['blockers']}"
            for row in recipe_rows
            if row["calculation_status"] == "BLOCKED"
        ]

        summary_rows.append(
            {
                "recipe_id": text(recipe.get("recipe_id")),
                "title": text(recipe.get("title")),
                "lines": str(len(recipe_rows)),
                "ready_lines": str(status_counts["CALCULATION_READY"]),
                "blocked_lines": str(status_counts["BLOCKED"]),
                "excluded_lines": str(status_counts["EXCLUDED"]),
                "calculated_grams": fmt(ready_grams),
                "blocked_source_grams": fmt(blocked_source_grams),
                "excluded_source_grams": fmt(excluded_source_grams),
                "calculatable": "yes" if status_counts["BLOCKED"] == 0 else "no",
                "policies": "; ".join(f"{k}={v}" for k, v in sorted(policy_counts.items()) if k),
                "blockers": " | ".join(short(blocker, 220) for blocker in blockers),
            }
        )
    return line_rows, summary_rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown(path: Path, summaries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# Nebius Recipe Calculation Summary\n\n")
        f.write("Recipe-side gram calculation from normalized Nebius output. This does not include nutrition-code matching.\n\n")
        f.write("| Recipe | Title | Ready | Blocked | Excluded | Calculated g | Blocked source g | Calculatable | Blockers |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|---|---|\n")
        for row in summaries:
            f.write(
                "| {recipe_id} | {title} | {ready} | {blocked} | {excluded} | {grams} | {blocked_grams} | {calculatable} | {blockers} |\n".format(
                    recipe_id=md_escape(short(row["recipe_id"], 24)),
                    title=md_escape(short(row["title"], 48)),
                    ready=md_escape(row["ready_lines"]),
                    blocked=md_escape(row["blocked_lines"]),
                    excluded=md_escape(row["excluded_lines"]),
                    grams=md_escape(row["calculated_grams"]),
                    blocked_grams=md_escape(row["blocked_source_grams"]),
                    calculatable=md_escape(row["calculatable"]),
                    blockers=md_escape(short(row["blockers"], 260)),
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--lines-out", type=Path, default=DEFAULT_LINES)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    line_rows, summary_rows = build_rows(load_jsonl(args.candidate))
    write_csv(args.lines_out, line_rows)
    write_csv(args.summary_out, summary_rows)
    write_markdown(args.md_out, summary_rows)
    print(
        json.dumps(
            {
                "recipes": len(summary_rows),
                "lines": len(line_rows),
                "fully_calculatable": sum(1 for row in summary_rows if row["calculatable"] == "yes"),
                "lines_out": str(args.lines_out),
                "summary_out": str(args.summary_out),
                "md_out": str(args.md_out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
