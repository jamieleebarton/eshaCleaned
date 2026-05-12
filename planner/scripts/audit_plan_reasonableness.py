#!/usr/bin/env python3
"""Plan-level purchase/price sanity audit for multi_week_ours JSON.

This is intentionally lightweight: it does not recalculate the planner, it
checks the actual emitted cart rows for missing SKUs, known bad classes,
package-size oddities, and price reasonableness signals.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "recipe_pricing"))

from recipe_pricing.verify_plan_bad_skus import find_hits
from recipe_pricing.fix_size_display_grams import choose_expected_grams, parse_count, parse_pack


RANDOM_WEIGHT_AVG_UNIT_RE = re.compile(
    r"\b("
    r"jalapenos?|jalape(?:n|ñ)os?|serranos?|peppers?|chiles?|chilies?|"
    r"ginger(?:\s+root)?|shallots?|carrots?"
    r")\b",
    re.I,
)
COUNT_OR_PACK_RE = re.compile(r"\b\d+\s*(?:ct|count|pk|pack|packs)\b", re.I)


def iter_purchases(plan: dict):
    for week in plan.get("weeks", []) or []:
        for row in week.get("ingredient_purchases", []) or []:
            yield week.get("week"), row


def all_selected_packages(row: dict) -> list[dict]:
    packages = row.get("selected_packages") or []
    if packages:
        return packages
    return [{
        "n_packages": row.get("n_packages", 0),
        "name": row.get("selected_sku", ""),
        "upc": row.get("selected_upc", ""),
        "grams": row.get("selected_package_grams", 0),
        "cents": row.get("selected_package_cents", 0),
        "display": row.get("selected_package_display", ""),
    }]


def _is_random_weight_average_unit(concept: str, name: str, display: str,
                                   grams: float, expected_g: float) -> bool:
    if not concept.lower().startswith("produce >"):
        return False
    if not re.fullmatch(r"\s*1\s*(?:lb|lbs|pound|pounds)\s*", display or "", re.I):
        return False
    if grams <= 0 or expected_g <= 0 or grams > expected_g * 0.35:
        return False
    return bool(RANDOM_WEIGHT_AVG_UNIT_RE.search(f"{concept} {name}"))


def package_flag_details(concept: str, pkg: dict) -> list[dict]:
    details: list[dict] = []
    name = pkg.get("name", "") or ""
    grams = float(pkg.get("grams", 0) or 0)
    cents = float(pkg.get("cents", 0) or 0)
    display = pkg.get("display", "") or ""
    expected_g, source = choose_expected_grams(name, display)

    if not name:
        details.append({"flag": "missing_sku", "severity": "error"})
    if grams <= 0:
        details.append({"flag": "missing_package_grams", "severity": "error"})
    is_household_free = "not purchased" in name.lower()
    if cents <= 0 and not is_household_free:
        details.append({"flag": "zero_price", "severity": "error"})
    if grams > 0 and cents > 0:
        cpg = cents / grams
        if cpg < 0.025 and not re.search(r"\b(water|juice|soda|tea|broth)\b", name, re.I):
            details.append({"flag": "very_low_cpg", "severity": "warning"})
        if cpg > 25 and not re.search(
            r"\b(spices?|seasonings?|extracts?|yeast|gelatin|herbs?)\b",
            concept,
            re.I,
        ):
            details.append({"flag": "very_high_cpg", "severity": "warning"})

    if expected_g and grams > 0:
        ratio = grams / expected_g
        count_n = parse_count(f"{name} {display}") or 0
        pack_n = parse_pack(f"{name} {display}") or 0
        expected_multipliers = {1}
        if count_n:
            expected_multipliers.add(count_n)
        if pack_n:
            expected_multipliers.add(pack_n)
        meta = {
            "expected_g": round(expected_g, 1),
            "source": source,
            "ratio": round(ratio, 3),
        }
        if ratio >= 4.5 and all(abs(ratio - m) > max(0.35, m * 0.1) for m in expected_multipliers):
            details.append({
                "flag": "package_grams_over_declared_size",
                "severity": "error",
                **meta,
            })
        if ratio <= 0.2:
            if _is_random_weight_average_unit(concept, name, display, grams, expected_g):
                details.append({
                    "flag": "random_weight_average_unit",
                    "severity": "info",
                    **meta,
                })
            elif COUNT_OR_PACK_RE.search(display):
                details.append({
                    "flag": "count_with_net_weight_package",
                    "severity": "info",
                    **meta,
                })
            else:
                details.append({
                    "flag": "package_grams_under_declared_size",
                    "severity": "error",
                    **meta,
                })
    return details


def package_flags(concept: str, pkg: dict) -> list[str]:
    return [
        d["flag"] for d in package_flag_details(concept, pkg)
        if d.get("severity") != "info"
    ]


def summarize(plan_path: Path) -> dict:
    plan = json.loads(plan_path.read_text())
    cfg = plan.get("config", {})
    totals = plan.get("totals", {})
    people = int(cfg.get("people") or 1)
    weeks_n = int(cfg.get("weeks") or len(plan.get("weeks", [])) or 1)

    purchase_rows = list(iter_purchases(plan))
    bad_hits = find_hits(plan)
    blank_rows = []
    mixed_rows = 0
    pkg_flag_rows = []
    pkg_info_rows = []
    line_costs = []
    concept_counts = Counter()

    for week_no, row in purchase_rows:
        concept = row.get("concept_key", "")
        concept_counts[concept.split("|")[0]] += 1
        if not row.get("selected_sku"):
            blank_rows.append({"week": week_no, "concept_key": concept})
        if len(row.get("selected_packages") or []) > 1:
            mixed_rows += 1
        for pkg in all_selected_packages(row):
            details = package_flag_details(concept, pkg)
            flags = [
                d["flag"] for d in details
                if d.get("severity") != "info"
            ]
            info = [
                d["flag"] for d in details
                if d.get("severity") == "info"
            ]
            grams = float(pkg.get("grams", 0) or 0)
            cents = float(pkg.get("cents", 0) or 0)
            if grams > 0 and cents > 0:
                line_costs.append({
                    "week": week_no,
                    "concept_key": concept,
                    "name": pkg.get("name", ""),
                    "grams": round(grams, 1),
                    "cents": int(cents),
                    "cpg": round(cents / grams, 4),
                })
            if flags:
                pkg_flag_rows.append({
                    "week": week_no,
                    "concept_key": concept,
                    "name": pkg.get("name", ""),
                    "grams": round(grams, 1),
                    "cents": int(cents),
                    "display": pkg.get("display", ""),
                    "flags": flags,
                    "details": details,
                })
            if info:
                pkg_info_rows.append({
                    "week": week_no,
                    "concept_key": concept,
                    "name": pkg.get("name", ""),
                    "grams": round(grams, 1),
                    "cents": int(cents),
                    "display": pkg.get("display", ""),
                    "flags": info,
                    "details": details,
                })

    line_costs.sort(key=lambda r: r["cpg"])
    expensive = sorted(line_costs, key=lambda r: r["cents"], reverse=True)

    total_cost = float(totals.get("total_whole_cart_cost") or totals.get("total_cost") or 0.0)
    return {
        "plan": str(plan_path),
        "config": cfg,
        "totals": totals,
        "derived": {
            "per_person_day": round(total_cost / max(1, weeks_n * 7 * people), 2),
            "purchase_rows": len(purchase_rows),
            "blank_selected_sku_rows": len(blank_rows),
            "mixed_package_rows": mixed_rows,
            "known_bad_sku_hits": len(bad_hits),
            "package_flag_rows": len(pkg_flag_rows),
            "package_info_rows": len(pkg_info_rows),
        },
        "bad_hits": bad_hits[:25],
        "blank_rows": blank_rows[:25],
        "package_flags": pkg_flag_rows[:40],
        "package_info": pkg_info_rows[:40],
        "cheapest_cpg": line_costs[:15],
        "highest_package_prices": expensive[:15],
        "top_concepts": concept_counts.most_common(20),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    summary = summarize(args.plan_json)
    out = args.out
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2))

    cfg = summary["config"]
    totals = summary["totals"]
    d = summary["derived"]
    print(
        f"{cfg.get('mode')} {cfg.get('people')}p {cfg.get('cal')}cal "
        f"leftovers={cfg.get('leftover_pct')} -> "
        f"${totals.get('total_whole_cart_cost', totals.get('total_cost'))} total, "
        f"${d['per_person_day']}/person/day"
    )
    print(
        f"purchases={d['purchase_rows']} blank_sku={d['blank_selected_sku_rows']} "
        f"bad_sku={d['known_bad_sku_hits']} package_flags={d['package_flag_rows']} "
        f"mixed={d['mixed_package_rows']}"
    )
    if summary["bad_hits"]:
        print("bad SKU examples:")
        for hit in summary["bad_hits"][:5]:
            print(f"  W{hit['week']} {hit['selected_sku']} [{hit['concept_key']}]")
    if summary["package_flags"]:
        print("package flag examples:")
        for row in summary["package_flags"][:8]:
            print(f"  W{row['week']} {row['flags']} {row['name'][:80]} [{row['concept_key']}]")
    if out:
        print(f"-> {out}")


if __name__ == "__main__":
    main()
