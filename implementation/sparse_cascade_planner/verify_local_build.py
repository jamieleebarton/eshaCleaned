#!/usr/bin/env python3
"""Verify the local sparse-cascade build and write coverage/blocker reports."""

from __future__ import annotations

import ast
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "implementation" / "output" / "sparse_cascade_planner"
RECIPES_CSV = OUT_DIR / "recipe_qa_calculator_native.csv"
PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
INGREDIENT_META = OUT_DIR / "ingredient_meta.json"
PACKAGE_SUMMARY = OUT_DIR / "food_packages_calculator_native.summary.json"
RECIPE_SUMMARY = OUT_DIR / "recipe_qa_calculator_native.summary.json"
TENSOR_SUMMARY = OUT_DIR / "tensor_cache" / "tensor_cache.summary.json"
PLAN_SMOKE = OUT_DIR / "local_sparse_plan.smoke.json"
OUT_JSON = OUT_DIR / "local_sparse_build_verification.json"
OUT_MD = OUT_DIR / "local_sparse_build_verification.md"


PRODUCT_PATTERN_ALLOWED_KEYS = {
    "Banana Nut Muffin": {"ESHA:18966", "FNDDS:58610005"},
    "BANANA NUT MUFFIN": {"ESHA:18966", "FNDDS:58610005"},
    "Crispy Chicken Breast Strips": set(),
}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def package_keys_and_bad_patterns(db_path: Path) -> tuple[set[str], Dict[str, dict[str, Any]]]:
    conn = sqlite3.connect(str(db_path))
    try:
        priced_keys = {str(row[0]) for row in conn.execute("SELECT DISTINCT fndds_code FROM packages")}
        pattern_checks: Dict[str, dict[str, Any]] = {}
        for pattern, allowed_keys in PRODUCT_PATTERN_ALLOWED_KEYS.items():
            rows = conn.execute(
                """
                SELECT fndds_code, food_description, package_size_display, product_meta
                FROM packages
                WHERE product_meta LIKE ?
                LIMIT 20
                """,
                (f"%{pattern}%",),
            ).fetchall()
            hits = [
                {
                    "ingredient_key": row[0],
                    "description": row[1],
                    "package_size": row[2],
                    "product_meta": row[3],
                }
                for row in rows
            ]
            bad_hits = [hit for hit in hits if hit["ingredient_key"] not in allowed_keys]
            pattern_checks[pattern] = {
                "allowed_keys": sorted(allowed_keys),
                "total_hits": len(hits),
                "allowed_hits": len(hits) - len(bad_hits),
                "bad_hits": bad_hits,
            }
    finally:
        conn.close()
    return priced_keys, pattern_checks


def read_ingredient_meta(path: Path) -> Dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def dict_from_cell(value: str) -> dict[str, float]:
    if not value:
        return {}
    try:
        parsed = ast.literal_eval(value)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, float] = {}
    for key, grams in parsed.items():
        try:
            amount = float(grams)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            out[str(key)] = amount
    return out


def recipe_coverage(recipes_csv: Path, priced_keys: set[str], meta: Dict[str, dict[str, Any]]) -> Dict[str, Any]:
    csv.field_size_limit(sys.maxsize)
    total_grams_by_key: defaultdict[str, float] = defaultdict(float)
    recipe_count_by_key: Counter[str] = Counter()
    stats = Counter()

    with recipes_csv.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stats["recipe_rows"] += 1
            grams_dict = dict_from_cell(row.get("fndds_grams_dict") or "")
            if not grams_dict:
                stats["empty_ingredient_dict"] += 1
                continue
            for key, grams in grams_dict.items():
                total_grams_by_key[key] += grams
                recipe_count_by_key[key] += 1
                stats["ingredient_grams_total"] += grams
                if key in priced_keys:
                    stats["ingredient_grams_priced"] += grams
                else:
                    stats["ingredient_grams_default_priced"] += grams

    unpriced = []
    for key, grams in total_grams_by_key.items():
        if key in priced_keys:
            continue
        info = meta.get(key) or {}
        unpriced.append(
            {
                "ingredient_key": key,
                "description": (
                    info.get("description")
                    or info.get("food_description")
                    or info.get("esha_description")
                    or info.get("sr28_description")
                    or info.get("fndds_description")
                    or ""
                ),
                "recipe_count": int(recipe_count_by_key[key]),
                "total_kg": round(grams / 1000.0, 3),
                "source": info.get("source") or info.get("key_source") or "",
            }
        )
    unpriced.sort(key=lambda row: (row["total_kg"], row["recipe_count"]), reverse=True)

    total_grams = float(stats["ingredient_grams_total"])
    priced_grams = float(stats["ingredient_grams_priced"])
    return {
        "recipe_rows": int(stats["recipe_rows"]),
        "unique_ingredient_keys_in_recipes": len(total_grams_by_key),
        "priced_keys_used_by_recipes": sum(1 for key in total_grams_by_key if key in priced_keys),
        "unpriced_keys_used_by_recipes": sum(1 for key in total_grams_by_key if key not in priced_keys),
        "total_ingredient_kg": round(total_grams / 1000.0, 3),
        "priced_ingredient_kg": round(priced_grams / 1000.0, 3),
        "priced_grams_pct": round((priced_grams / total_grams * 100.0) if total_grams else 0.0, 3),
        "top_unpriced_by_kg": unpriced[:50],
    }


def plan_gate(plan: Dict[str, Any]) -> Dict[str, Any]:
    weeks = plan.get("weeks") or []
    meals = plan.get("meals") or []
    expected_meals = 21 * int((plan.get("settings") or {}).get("weeks") or len(weeks) or 0)
    failures: list[str] = []
    if len(meals) != expected_meals:
        failures.append(f"expected {expected_meals} meals, got {len(meals)}")
    for week in weeks:
        if float(week.get("total_cost") or 0) <= 0:
            failures.append(f"week {week.get('week')} has non-positive cost")
        cal = float(week.get("cal_compliance") or 0)
        prot = float(week.get("prot_compliance") or 0)
        if not 0.85 <= cal <= 1.15:
            failures.append(f"week {week.get('week')} calorie compliance out of range: {cal}")
        if not 0.75 <= prot <= 1.35:
            failures.append(f"week {week.get('week')} protein compliance out of range: {prot}")
    return {
        "passed": not failures,
        "failures": failures,
        "meal_count": len(meals),
        "weeks": weeks,
    }


def build_markdown(report: Dict[str, Any]) -> str:
    package_summary = report["package_summary"]
    recipe_summary = report["recipe_summary"]
    tensor_summary = report["tensor_summary"]
    coverage = report["coverage"]
    plan = report["plan_gate"]
    bad_checks = report["bad_product_checks"]

    lines = [
        "# Local Sparse Cascade Build Verification",
        "",
        "## Summary",
        f"- Recipe-QA source recipes seen: {recipe_summary.get('stats', {}).get('recipes_seen')}",
        f"- Tensor-ready recipe rows: {recipe_summary.get('stats', {}).get('recipes_written')}",
        f"- Planner tensor recipes: {tensor_summary.get('tensor_recipes')}",
        f"- Tensor ingredient keys: {tensor_summary.get('ingredient_keys')}",
        f"- Package rows: {package_summary.get('package_rows')}",
        f"- Package ingredient keys: {package_summary.get('ingredient_keys')}",
        f"- Plan gate passed: {plan.get('passed')}",
        "",
        "## Pricing Coverage",
        f"- Recipe ingredient keys used: {coverage.get('unique_ingredient_keys_in_recipes')}",
        f"- Keys with store packages: {coverage.get('priced_keys_used_by_recipes')}",
        f"- Keys on explicit $3/kg default: {coverage.get('unpriced_keys_used_by_recipes')}",
        f"- Gram-weighted package coverage: {coverage.get('priced_grams_pct')}%",
        "",
        "## Product Leak Checks",
    ]
    for pattern, check in bad_checks.items():
        lines.append(
            f"- `{pattern}`: {len(check.get('bad_hits') or [])} bad hits "
            f"({check.get('allowed_hits')} allowed / {check.get('total_hits')} total)"
        )
    lines.extend(["", "## Top Unpriced Ingredients"])
    for row in coverage.get("top_unpriced_by_kg", [])[:20]:
        lines.append(
            f"- `{row['ingredient_key']}` {row['description']} "
            f"({row['total_kg']} kg across {row['recipe_count']} recipes)"
        )
    if plan.get("failures"):
        lines.extend(["", "## Plan Failures"])
        for failure in plan["failures"]:
            lines.append(f"- {failure}")
    return "\n".join(lines) + "\n"


def main() -> int:
    for path in [RECIPES_CSV, PACKAGE_DB, INGREDIENT_META, PACKAGE_SUMMARY, RECIPE_SUMMARY, TENSOR_SUMMARY, PLAN_SMOKE]:
        if not path.exists():
            raise FileNotFoundError(path)

    priced_keys, bad_hits = package_keys_and_bad_patterns(PACKAGE_DB)
    meta = read_ingredient_meta(INGREDIENT_META)
    report = {
        "package_summary": load_json(PACKAGE_SUMMARY).get("packages") or load_json(PACKAGE_SUMMARY),
        "recipe_summary": load_json(RECIPE_SUMMARY),
        "tensor_summary": load_json(TENSOR_SUMMARY),
        "coverage": recipe_coverage(RECIPES_CSV, priced_keys, meta),
        "bad_product_checks": bad_hits,
        "plan_gate": plan_gate(load_json(PLAN_SMOKE)),
    }
    unpriced_count = int(report["coverage"].get("unpriced_keys_used_by_recipes") or 0)
    if unpriced_count:
        report["plan_gate"]["passed"] = False
        report["plan_gate"].setdefault("failures", []).append(
            f"{unpriced_count} ingredient keys in recipes have no store package; default pricing is disallowed"
        )
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps({"out_json": str(OUT_JSON), "out_md": str(OUT_MD), "plan_passed": report["plan_gate"]["passed"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
