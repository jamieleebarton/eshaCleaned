#!/usr/bin/env python3
"""Step 1 of FIX_PLAN.md — read-only baseline dumper for `accept_via_audit`.

Runs `calculate_lab` against each line of a curated recipe set, capturing the
FULL list of rejected products with their reasons. Saves to JSON. The dump is
the empirical baseline that Step 3 verification compares against.

Defaults: the four investigation samples
  - 36094  Macaroni Pastitsio with Feta Cheese    (canonical=macaroni)
  - 95150  Frugal Gourmet Chicken                  (canonical=chicken drumstick)
  - 129624 Chinese Garlic Spareribs                (canonical=green onion)
  - 115199 Affordable Tomato and Macaroni Soup     (canonical=tomato juice)
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

import surface_lab_calculator as lab_sources
from surface_lab_calculator import calculate_lab, configure_data_sources


ROOT = Path(__file__).resolve().parent.parent
LOCAL_CLEAN_ROOT = ROOT.parent / "clean"
DEFAULT_RECIPES_CSV = LOCAL_CLEAN_ROOT / "recipe_pricing" / "output" / "recipes_final.csv"
DEFAULT_RECIPE_QA_DB = LOCAL_CLEAN_ROOT / "data" / "recipe_qa.db"
DEFAULT_RETAIL_BRIDGE_CSV = ROOT / "implementation" / "output" / "retail_canonical_surface_bridge.csv"

DEFAULT_RECIPE_IDS = ("36094", "95150", "129624", "115199")


def _load_recipe(recipes_csv: Path, recipe_id: str) -> dict[str, str] | None:
    with recipes_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if (row.get("recipeNum") or "").strip() == recipe_id:
                return row
    return None


def _load_qa_lines(recipe_qa_db: Path, recipe_id: str) -> list[dict[str, Any]]:
    if not recipe_qa_db.exists():
        return []
    with sqlite3.connect(recipe_qa_db) as conn:
        row = conn.execute(
            "select ingredients_json from recipe_cleaned where recipe_id=?",
            (recipe_id,),
        ).fetchone()
    if not row or not row[0]:
        return []
    try:
        parsed = json.loads(row[0])
    except json.JSONDecodeError:
        return []
    out: list[dict[str, Any]] = []
    if isinstance(parsed, list):
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            display = str(entry.get("display") or "").strip()
            item = str(entry.get("item") or display).strip()
            try:
                grams = float(entry.get("grams") or 0)
            except (TypeError, ValueError):
                grams = 0.0
            if display or item:
                out.append({"display": display, "item": item, "grams": grams})
    return out


def _parse_shopping_items(raw: str) -> list[tuple[str, float]]:
    if not raw:
        return []
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(parsed, dict):
        return []
    out: list[tuple[str, float]] = []
    for key, value in parsed.items():
        try:
            grams = float(value)
        except (TypeError, ValueError):
            continue
        if grams > 0:
            out.append((str(key), grams))
    return out


def dump_recipe(recipes_csv: Path, recipe_qa_db: Path, recipe_id: str) -> dict[str, Any]:
    recipe = _load_recipe(recipes_csv, recipe_id)
    if recipe is None:
        return {"recipe_id": recipe_id, "error": "not_found_in_recipes_csv"}
    qa_lines = _load_qa_lines(recipe_qa_db, recipe_id)
    shopping_pairs = _parse_shopping_items(recipe.get("shopping_items_dict") or "")
    if qa_lines:
        line_inputs = []
        for index, raw in enumerate(qa_lines):
            normalized_label, normalized_grams = (
                shopping_pairs[index] if index < len(shopping_pairs) else ("", 0.0)
            )
            grams = float(raw.get("grams") or 0)
            line_inputs.append(
                {
                    "display": raw.get("display") or raw.get("item") or normalized_label,
                    "item": raw.get("item") or raw.get("display") or normalized_label,
                    "grams": grams if grams > 0 else normalized_grams,
                    "normalized_label": normalized_label,
                }
            )
    else:
        line_inputs = [
            {"display": label, "item": label, "grams": grams, "normalized_label": label}
            for label, grams in shopping_pairs
        ]

    out_lines: list[dict[str, Any]] = []
    for inp in line_inputs:
        lab = asdict(
            calculate_lab(
                display=str(inp.get("display") or ""),
                item=str(inp.get("item") or ""),
                grams=float(inp.get("grams") or 0.0),
            )
        )
        accepted_n = len(lab.get("products") or [])
        rejected_n = len(lab.get("rejected_products") or [])
        out_lines.append(
            {
                "input": inp.get("display") or inp.get("item"),
                "item": inp.get("item"),
                "normalized_label": inp.get("normalized_label"),
                "grams": inp.get("grams"),
                "canonical_name": lab.get("canonical_name"),
                "shopping_canonical": lab.get("shopping_canonical"),
                "fndds_code": lab.get("fndds_code"),
                "esha_code": lab.get("esha_code"),
                "shopping_state": lab.get("shopping_state"),
                "nutrition_state": lab.get("nutrition_state"),
                "path": lab.get("path") or [],
                "accepted_count": accepted_n,
                "rejected_count": rejected_n,
                "accepted_products": [
                    {
                        "source": p.get("source"),
                        "gtin_upc": p.get("gtin_upc"),
                        "description": p.get("description"),
                        "brand_name": p.get("brand_name"),
                        "category": p.get("category"),
                        "reason": p.get("reason"),
                    }
                    for p in (lab.get("products") or [])
                ],
                "rejected_products": [
                    {
                        "source": p.get("source"),
                        "gtin_upc": p.get("gtin_upc"),
                        "description": p.get("description"),
                        "brand_name": p.get("brand_name"),
                        "category": p.get("category"),
                        "reason": p.get("reason"),
                    }
                    for p in (lab.get("rejected_products") or [])
                ],
            }
        )

    return {
        "recipe_id": recipe_id,
        "recipe_name": (recipe.get("recipeName") or "").strip(),
        "line_count": len(out_lines),
        "lines": out_lines,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump full rejected_products with reason strings for FIX_PLAN.md Step 1 baseline."
    )
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--recipe-qa-db", type=Path, default=DEFAULT_RECIPE_QA_DB)
    parser.add_argument("--retail-bridge-csv", type=Path, default=DEFAULT_RETAIL_BRIDGE_CSV)
    parser.add_argument(
        "--recipe-id",
        action="append",
        dest="recipe_ids",
        help="Recipe id to include; repeatable.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("/Users/jamiebarton/Desktop/Hestia/api/data/universe_calc.debug.json"),
    )
    args = parser.parse_args()

    configure_data_sources(retail_surface_bridge_csv=args.retail_bridge_csv)
    recipe_ids = args.recipe_ids or list(DEFAULT_RECIPE_IDS)

    out: dict[str, Any] = {
        "recipes_csv": str(args.recipes_csv),
        "recipe_qa_db": str(args.recipe_qa_db),
        "retail_bridge_csv": str(args.retail_bridge_csv),
        "surface_csv": str(lab_sources.SURFACE_CSV),
        "recipe_ids": recipe_ids,
        "recipes": [],
    }
    for rid in recipe_ids:
        out["recipes"].append(dump_recipe(args.recipes_csv, args.recipe_qa_db, rid))

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Print a compact summary to stderr.
    summary = []
    for r in out["recipes"]:
        if "error" in r:
            summary.append(f"{r['recipe_id']}=ERROR:{r['error']}")
            continue
        line_summary = [
            f"{ln.get('canonical_name')}: a={ln['accepted_count']} r={ln['rejected_count']}"
            for ln in r["lines"]
        ]
        summary.append(f"{r['recipe_id']} {r['recipe_name']}: " + "; ".join(line_summary))
    print("\n".join(summary))
    print(f"\nout: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
