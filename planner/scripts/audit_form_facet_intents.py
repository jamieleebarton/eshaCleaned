#!/usr/bin/env python3
"""Audit selected planner recipes for line-level form/facet violations.

This joins:
  plan weeks[*].recipe_ids
  plan weeks[*].ingredient_purchases
  recipes_unified.csv line text/facets/grams
  concept_resolution.json recipe concept -> priced concept

It catches problems that concept-only cart checks cannot see, such as a
blueberry bagel line priced with plain bagels or ham recipes using lunch meat.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from planner.concept_routing import (  # noqa: E402
    choose_recipe_canonical_path,
    encode_recipe_line_htc,
    load_form_path_authority,
    load_htc_to_path,
    load_item_overrides,
    load_title_maps,
    valid_htc_form,
)
from planner.form_facet_audit import all_package_names, gram_bridge_findings, line_sku_findings

UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
RES_PATH = ROOT / "planner" / "data" / "concept_resolution.json"


def selected_recipe_ids(plan: dict) -> set[str]:
    ids: set[str] = set()
    for week in plan.get("weeks", []) or []:
        for rid in week.get("recipe_ids", []) or []:
            if rid:
                ids.add(str(rid))
    return ids


def load_recipe_lines(rids: set[str]) -> dict[str, list[dict]]:
    htc_to_path = load_htc_to_path()
    title_to_path, _ = load_title_maps()
    item_overrides = load_item_overrides()
    form_path_authority = load_form_path_authority()
    by_recipe: dict[str, list[dict]] = defaultdict(list)
    htc_encode_cache: dict[tuple[str, str, str], str] = {}
    intent_encode_cache: dict[tuple[str, str], str] = {}

    with UNIFIED.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rid = (row.get("recipe_id") or "").strip()
            if rid not in rids:
                continue
            item = (row.get("ingredient_item") or "").strip().lower()
            htc = (row.get("htc_code") or "").strip().lstrip("~")
            display = row.get("display") or ""
            title_path = title_to_path.get(item, "")
            cp = choose_recipe_canonical_path(
                item=item,
                display=display,
                source_htc=htc,
                title_path=title_path,
                item_overrides=item_overrides,
                htc_to_path=htc_to_path,
                form_path_authority=form_path_authority,
                intent_cache=intent_encode_cache,
            )
            if not cp or cp.startswith("Non-Food"):
                continue
            htc = encode_recipe_line_htc(item, display, cp, htc, htc_encode_cache)
            if not valid_htc_form(htc):
                continue
            line = dict(row)
            line["line_index"] = len(by_recipe[rid]) + 1
            line["recipe_concept_key"] = f"{cp}|{htc}"
            by_recipe[rid].append(line)
    return by_recipe


def purchase_map_for_week(week: dict) -> dict[str, dict]:
    return {
        row.get("concept_key", ""): row
        for row in week.get("ingredient_purchases", []) or []
        if row.get("concept_key")
    }


def audit_plan(plan_path: Path) -> tuple[list[dict], dict]:
    plan = json.loads(plan_path.read_text())
    res = json.loads(RES_PATH.read_text())
    rids = selected_recipe_ids(plan)
    lines_by_recipe = load_recipe_lines(rids)
    findings: list[dict] = []
    counters = Counter()

    for week in plan.get("weeks", []) or []:
        week_no = week.get("week", "")
        purchases = purchase_map_for_week(week)
        for rid in week.get("recipe_ids", []) or []:
            rid_s = str(rid)
            for line in lines_by_recipe.get(rid_s, []):
                counters["lines_scanned"] += 1
                recipe_key = line["recipe_concept_key"]
                resolution = res.get(recipe_key, {})
                priced_key = resolution.get("priced_key") or ""
                for finding in gram_bridge_findings(line):
                    counters[finding.issue_type] += 1
                    findings.append({
                        "week": week_no,
                        "recipe_id": rid_s,
                        "recipe_title": line.get("recipe_title", ""),
                        "line_index": line.get("line_index", ""),
                        "display": line.get("display", ""),
                        "ingredient_item": line.get("ingredient_item", ""),
                        "grams_resolved": line.get("grams_resolved", ""),
                        "recipe_concept_key": recipe_key,
                        "priced_concept_key": priced_key,
                        "selected_sku": "",
                        "issue_type": finding.issue_type,
                        "severity": finding.severity,
                        "message": finding.message,
                        "expected": finding.expected,
                        "actual": finding.actual,
                    })
                if not priced_key:
                    continue
                purchase = purchases.get(priced_key)
                if not purchase:
                    continue
                package_names = all_package_names(purchase)
                for finding in line_sku_findings(line, priced_key, package_names):
                    counters[finding.issue_type] += 1
                    findings.append({
                        "week": week_no,
                        "recipe_id": rid_s,
                        "recipe_title": line.get("recipe_title", ""),
                        "line_index": line.get("line_index", ""),
                        "display": line.get("display", ""),
                        "ingredient_item": line.get("ingredient_item", ""),
                        "grams_resolved": line.get("grams_resolved", ""),
                        "recipe_concept_key": recipe_key,
                        "priced_concept_key": priced_key,
                        "selected_sku": " | ".join(package_names),
                        "issue_type": finding.issue_type,
                        "severity": finding.severity,
                        "message": finding.message,
                        "expected": finding.expected,
                        "actual": finding.actual,
                    })

    summary = {
        "plan": str(plan_path),
        "recipes_selected": len(rids),
        "lines_scanned": counters["lines_scanned"],
        "finding_count": len(findings),
        "by_issue_type": dict(sorted((k, v) for k, v in counters.items() if k != "lines_scanned")),
    }
    return findings, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--out-csv", type=Path)
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args()

    findings, summary = audit_plan(args.plan_json)
    out_csv = args.out_csv or args.plan_json.with_suffix(".form_facet_audit.csv")
    out_json = args.out_json or args.plan_json.with_suffix(".form_facet_audit.json")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if findings:
        with out_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(findings[0].keys()))
            w.writeheader()
            w.writerows(findings)
    elif out_csv.exists():
        out_csv.unlink()
    out_json.write_text(json.dumps(summary, indent=2))

    print(
        f"{args.plan_json}: {summary['finding_count']} findings "
        f"across {summary['lines_scanned']} selected-recipe lines"
    )
    print(f"by issue: {summary['by_issue_type']}")
    print(f"-> {out_json}")
    if findings:
        print(f"-> {out_csv}")


if __name__ == "__main__":
    main()
