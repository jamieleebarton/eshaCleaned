#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "implementation"
OUT_DIR = IMPLEMENTATION / "output" / "sparse_cascade_planner"

sys.path.insert(0, str(IMPLEMENTATION))

from build_hestia_esha_native_artifacts import (  # noqa: E402
    IDENTITY_VERSION,
    _add_meta,
    _finalize_meta,
    _resolution_json,
    _resolve_item,
    _with_grams,
)
from esha_nutrition import nutrition_for_esha  # noqa: E402
from surface_lab_calculator import normalize_key  # noqa: E402


DEFAULT_RECIPE_QA_DB = ROOT / "data" / "recipe_qa.db"
DEFAULT_PACKAGE_DB = OUT_DIR / "food_packages_calculator_native.db"
DEFAULT_OUT_CSV = OUT_DIR / "recipe_qa_calculator_native.csv"
DEFAULT_OUT_SUMMARY = OUT_DIR / "recipe_qa_calculator_native.summary.json"
DEFAULT_OUT_META = OUT_DIR / "ingredient_meta.json"
DEFAULT_OUT_LINES = OUT_DIR / "recipe_qa_calculator_native_lines.jsonl"
FNDDS_SR_LINKS = ROOT / "data" / "fndds" / "FNDDSSRLinks.csv"

FIELDNAMES = [
    "recipeNum",
    "recipeName",
    "fndds_grams_dict",
    "calculator_native_grams_dict",
    "fndds_projection_grams_dict",
    "esha_grams_dict",
    "sr28_grams_dict",
    "shopping_items_dict",
    "total_mass_g",
    "total_estimated_cost",
    "calories_total_kcal",
    "protein_total_g",
    "carbs_total_g",
    "fat_total_g",
    "fiber_total_g",
    "food_groups.vegetables_g",
    "food_groups.fruit_g",
    "food_groups.dairy_g",
    "food_groups.grains_g",
    "food_groups.protein_g",
    "food_groups.fats_g",
    "food_groups.other_g",
    "servings.min",
    "servings.max",
    "category_number",
    "verdict",
    "ok_breakfast",
    "ok_lunch",
    "ok_dinner",
    "role",
    "main_template",
    "side_template",
    "prep_minutes",
    "cook_minutes",
    "difficulty",
    "sodium_total_mg",
    "potassium_total_mg",
    "nutrition_source",
    "nutrition_source_note",
    "nutrition_resolved_pct",
    "calculator_identity_version",
    "calculator_resolved_line_count",
    "calculator_unresolved_line_count",
    "calculator_resolved_grams_pct",
    "calculator_unresolved_lines_json",
    "calculator_line_resolutions_json",
]

FOOD_GROUP_BY_PREFIX = {
    **{p: "dairy" for p in ("11", "12", "13", "14")},
    **{p: "protein" for p in ("20", "21", "22", "23", "24", "25", "26", "27", "28", "31", "32", "33", "34", "41", "42", "43")},
    **{p: "grains" for p in ("50", "51", "52", "53", "54", "55", "56", "57", "58", "59")},
    **{p: "fruits" for p in ("61", "62", "63", "64", "65", "66", "67")},
    **{p: "vegetables" for p in ("71", "72", "73", "74", "75", "76", "77", "78")},
    **{p: "fats" for p in ("81", "82", "83", "89")},
    **{p: "other" for p in ("91", "92", "93", "94", "95", "99")},
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_ingredients(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _load_overrides(db_path: Path) -> dict[int, dict[str, dict[str, str]]]:
    out: dict[int, dict[str, dict[str, str]]] = defaultdict(dict)
    with sqlite3.connect(str(db_path)) as conn:
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='recipe_item_overrides'"
        ).fetchone()[0]
        if not exists:
            return out
        for recipe_id, ambiguous, display, specific, base, prep_state in conn.execute(
            """
            SELECT recipe_id, ambiguous_item, display, llm_specific_product, base_product, prep_state
            FROM recipe_item_overrides
            """
        ):
            label = (specific or base or "").strip()
            if not label:
                continue
            payload = {
                "label": label,
                "ambiguous_item": ambiguous or "",
                "display": display or "",
                "prep_state": prep_state or "",
            }
            rid = int(recipe_id)
            if display:
                out[rid][f"display:{normalize_key(display)}"] = payload
            if ambiguous:
                out[rid][f"item:{normalize_key(ambiguous)}"] = payload
    return out


def _override_for(
    overrides: dict[int, dict[str, dict[str, str]]],
    recipe_id: int,
    display: str,
    item: str,
) -> dict[str, str] | None:
    recipe_overrides = overrides.get(recipe_id) or {}
    return recipe_overrides.get(f"display:{normalize_key(display)}") or recipe_overrides.get(f"item:{normalize_key(item)}")


def _has_display_token(display_key: str, *tokens: str) -> bool:
    display_tokens = set(display_key.split())
    return any(token in display_tokens for token in tokens)


def _recipe_resolution_label(display: str, item: str, grams: float) -> str:
    label = (item or display or "").strip()
    item_key = normalize_key(item)
    display_key = normalize_key(display)
    if item_key == "ginger":
        if _has_display_token(display_key, "pickled", "sushi", "gari"):
            return "pickled ginger"
        if _has_display_token(display_key, "syrup"):
            return "ginger syrup"
        if _has_display_token(display_key, "ground", "powder", "powdered", "dried", "dry"):
            return "ground ginger"
        if _has_display_token(
            display_key,
            "chopped",
            "crushed",
            "fresh",
            "grated",
            "inch",
            "minced",
            "ounce",
            "ounces",
            "oz",
            "peeled",
            "piece",
            "pieces",
            "root",
            "shredded",
            "slice",
            "sliced",
            "slices",
        ):
            return "fresh ginger"
        if _has_display_token(display_key, "teaspoon", "teaspoons", "tsp") and grams <= 4:
            return "ground ginger"
        if grams >= 5:
            return "fresh ginger"
    return label


def _load_sr28_to_fndds(path: Path = FNDDS_SR_LINKS) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            sr = (row.get("SR code") or "").strip()
            fndds = (row.get("Food code") or "").strip()
            if sr and fndds:
                out.setdefault(sr, fndds)
    return out


def _fndds_projection(line: Any, sr28_to_fndds: dict[str, str]) -> str:
    if line.fndds_code:
        return line.fndds_code
    if line.esha_code:
        esha = nutrition_for_esha(line.esha_code) or {}
        proxy = str(esha.get("fndds_proxy") or "").strip()
        if proxy:
            return proxy
    if line.sr28_code:
        return sr28_to_fndds.get(line.sr28_code, "")
    return ""


def _group_for_fndds(code: str) -> str:
    return FOOD_GROUP_BY_PREFIX.get((code or "")[:2], "other")


def _load_package_price_per_gram(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with sqlite3.connect(str(path)) as conn:
        rows = conn.execute(
            """
            SELECT fndds_code, package_weight_grams, walmart_price_cents, kroger_price_cents
            FROM packages
            WHERE package_weight_grams > 0
              AND (COALESCE(walmart_price_cents, 0) > 0 OR COALESCE(kroger_price_cents, 0) > 0)
            """
        ).fetchall()
    for key, grams, walmart_cents, kroger_cents in rows:
        prices = [p for p in (walmart_cents, kroger_cents) if p and p > 0]
        if not prices:
            continue
        cpg = min(prices) / 100.0 / float(grams)
        if key not in out or cpg < out[key]:
            out[str(key)] = cpg
    return out


def _recipe_rows(db_path: Path):
    query = """
        SELECT
            c.recipe_id,
            c.title,
            c.ingredients_json,
            c.prep_minutes,
            c.cook_minutes,
            c.difficulty,
            v.verdict,
            v.ok_breakfast,
            v.ok_lunch,
            v.ok_dinner,
            v.role,
            v.new_category,
            v.main_template,
            v.side_template
        FROM recipe_cleaned c
        LEFT JOIN recipe_verdicts v ON v.recipe_id = c.recipe_id
        ORDER BY c.recipe_id
    """
    with sqlite3.connect(str(db_path)) as conn:
        for row in conn.execute(query):
            yield row


def build_recipes(
    *,
    recipe_qa_db: Path,
    package_db: Path,
    out_csv: Path,
    out_summary: Path,
    out_meta: Path,
    out_lines: Path,
    limit_recipes: int,
    min_resolved_grams_pct: float,
    default_servings: float,
    allow_sr28_fallback: bool,
    allow_fndds_fallback: bool,
    require_priced_ingredients: bool,
    include_line_json: bool,
    write_lines_jsonl: bool,
) -> dict[str, Any]:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    overrides = _load_overrides(recipe_qa_db)
    sr28_to_fndds = _load_sr28_to_fndds()
    price_per_gram = _load_package_price_per_gram(package_db)

    resolution_cache: dict[str, Any] = {}
    meta: dict[str, dict[str, Any]] = {}
    stats: Counter[str] = Counter()
    gate_reasons: Counter[str] = Counter()
    key_sources: Counter[str] = Counter()
    nutrition_sources: Counter[str] = Counter()
    unresolved_inputs: Counter[str] = Counter()
    unpriced_recipe_keys: Counter[str] = Counter()

    tmp_csv = out_csv.with_suffix(out_csv.suffix + ".tmp")
    tmp_lines = out_lines.with_suffix(out_lines.suffix + ".tmp")
    line_handle = tmp_lines.open("w", encoding="utf-8") if write_lines_jsonl else None
    try:
        with tmp_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()

            for (
                recipe_id,
                title,
                ingredients_json,
                prep_minutes,
                cook_minutes,
                difficulty,
                verdict,
                ok_breakfast,
                ok_lunch,
                ok_dinner,
                role,
                new_category,
                main_template,
                side_template,
            ) in _recipe_rows(recipe_qa_db):
                if limit_recipes and stats["recipes_seen"] >= limit_recipes:
                    break
                stats["recipes_seen"] += 1
                ingredients = _parse_ingredients(ingredients_json)
                if not ingredients:
                    stats["skip_no_ingredients"] += 1
                    continue

                shopping_items: dict[str, float] = defaultdict(float)
                line_records: list[dict[str, Any]] = []
                unresolved_records: list[dict[str, Any]] = []
                native_grams: dict[str, float] = defaultdict(float)
                projection_grams: dict[str, float] = defaultdict(float)
                esha_grams: dict[str, float] = defaultdict(float)
                sr28_grams: dict[str, float] = defaultdict(float)
                food_groups: dict[str, float] = defaultdict(float)
                nutrition_totals = {"kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbs_g": 0.0}
                recipe_meta_lines: list[Any] = []
                total_grams = 0.0
                resolved_grams = 0.0
                nutrition_grams = 0.0
                priced_cost = 0.0
                default_cost = 0.0

                for index, entry in enumerate(ingredients, start=1):
                    display = str(entry.get("display") or entry.get("item") or "").strip()
                    item = str(entry.get("item") or display).strip()
                    grams = _as_float(entry.get("grams"))
                    if grams <= 0:
                        stats["skip_bad_line_grams"] += 1
                        continue
                    override = _override_for(overrides, int(recipe_id), display, item)
                    label = (override or {}).get("label") or _recipe_resolution_label(display, item, grams)
                    label = label.strip()
                    if not label:
                        stats["skip_blank_line_label"] += 1
                        continue

                    total_grams += grams
                    shopping_items[label] += grams
                    cache_key = normalize_key(label)
                    cached = resolution_cache.get(cache_key)
                    if cached is None:
                        cached = _resolve_item(
                            label,
                            100.0,
                            allow_sr28_fallback=allow_sr28_fallback,
                            allow_fndds_fallback=allow_fndds_fallback,
                        )
                        resolution_cache[cache_key] = cached
                    line = _with_grams(cached, grams)
                    record = _resolution_json(line)
                    record.update(
                        {
                            "recipe_id": int(recipe_id),
                            "line_index": index,
                            "display": display,
                            "item": item,
                            "override_label": (override or {}).get("label", ""),
                        }
                    )
                    line_records.append(record)
                    stats["lines"] += 1
                    gate_reasons[line.gate_reason] += 1
                    key_sources[line.key_source] += 1
                    nutrition_sources[line.nutrition_source] += 1

                    projection = _fndds_projection(line, sr28_to_fndds)
                    if line.ingredient_key:
                        native_grams[line.ingredient_key] += grams
                        resolved_grams += grams
                        recipe_meta_lines.append(line)
                        if projection:
                            projection_grams[projection] += grams
                            food_groups[_group_for_fndds(projection)] += grams
                        if line.ingredient_key.startswith("ESHA:"):
                            esha_grams[line.ingredient_key[5:]] += grams
                        elif line.ingredient_key.startswith("SR28:"):
                            sr28_grams[line.ingredient_key[5:]] += grams
                        cpg = price_per_gram.get(line.ingredient_key)
                        if cpg is not None:
                            priced_cost += grams * cpg
                        else:
                            default_cost += grams * 0.003
                    elif line.key_source in {"non_food", "excluded_non_purchasable"}:
                        resolved_grams += grams
                        stats["excluded_lines"] += 1
                    else:
                        unresolved_records.append(record)
                        unresolved_inputs[label] += 1

                    if line.nutrition is not None:
                        nutrition_grams += grams
                        nutrition_totals["kcal"] += line.nutrition.kcal
                        nutrition_totals["protein_g"] += line.nutrition.protein_g
                        nutrition_totals["fat_g"] += line.nutrition.fat_g
                        nutrition_totals["carbs_g"] += line.nutrition.carbs_g

                    if line_handle is not None:
                        line_handle.write(json.dumps(record, sort_keys=True) + "\n")

                if not native_grams:
                    stats["skip_no_native_grams"] += 1
                    continue
                resolved_pct = resolved_grams / total_grams * 100.0 if total_grams else 0.0
                if resolved_pct < min_resolved_grams_pct:
                    stats["skip_low_resolved_pct"] += 1
                    continue

                native_dict = {k: round(v, 4) for k, v in sorted(native_grams.items()) if v > 0}
                unpriced_keys = [key for key in native_dict if key not in price_per_gram]
                if require_priced_ingredients and unpriced_keys:
                    stats["skip_unpriced_ingredients"] += 1
                    stats["unpriced_ingredient_key_instances"] += len(unpriced_keys)
                    for key in unpriced_keys:
                        unpriced_recipe_keys[key] += 1
                    continue

                for line in recipe_meta_lines:
                    _add_meta(meta, line)

                projection_dict = {k: round(v, 4) for k, v in sorted(projection_grams.items()) if v > 0}
                cost = priced_cost + default_cost
                row = {
                    "recipeNum": str(recipe_id),
                    "recipeName": title or "",
                    "fndds_grams_dict": repr(native_dict),
                    "calculator_native_grams_dict": repr(native_dict),
                    "fndds_projection_grams_dict": repr(projection_dict),
                    "esha_grams_dict": repr({k: round(v, 4) for k, v in sorted(esha_grams.items()) if v > 0}),
                    "sr28_grams_dict": repr({k: round(v, 4) for k, v in sorted(sr28_grams.items()) if v > 0}),
                    "shopping_items_dict": repr({k: round(v, 4) for k, v in sorted(shopping_items.items()) if v > 0}),
                    "total_mass_g": f"{sum(native_dict.values()):.4f}",
                    "total_estimated_cost": f"{cost:.4f}",
                    "calories_total_kcal": f"{nutrition_totals['kcal']:.4f}",
                    "protein_total_g": f"{nutrition_totals['protein_g']:.4f}",
                    "carbs_total_g": f"{nutrition_totals['carbs_g']:.4f}",
                    "fat_total_g": f"{nutrition_totals['fat_g']:.4f}",
                    "fiber_total_g": "0.0000",
                    "food_groups.vegetables_g": f"{food_groups['vegetables']:.4f}",
                    "food_groups.fruit_g": f"{food_groups['fruits']:.4f}",
                    "food_groups.dairy_g": f"{food_groups['dairy']:.4f}",
                    "food_groups.grains_g": f"{food_groups['grains']:.4f}",
                    "food_groups.protein_g": f"{food_groups['protein']:.4f}",
                    "food_groups.fats_g": f"{food_groups['fats']:.4f}",
                    "food_groups.other_g": f"{food_groups['other']:.4f}",
                    "servings.min": f"{default_servings:g}",
                    "servings.max": f"{default_servings:g}",
                    "category_number": new_category or role or "",
                    "verdict": verdict or "",
                    "ok_breakfast": str(ok_breakfast if ok_breakfast is not None else 1),
                    "ok_lunch": str(ok_lunch if ok_lunch is not None else 1),
                    "ok_dinner": str(ok_dinner if ok_dinner is not None else 1),
                    "role": role or "",
                    "main_template": main_template or "",
                    "side_template": side_template or "",
                    "prep_minutes": str(prep_minutes or ""),
                    "cook_minutes": str(cook_minutes or ""),
                    "difficulty": difficulty or "",
                    "sodium_total_mg": "0.0000",
                    "potassium_total_mg": "0.0000",
                    "nutrition_source": "recipe_qa_calculator_native",
                    "nutrition_source_note": (
                        f"{IDENTITY_VERSION}; nutrition_grams_pct="
                        f"{(nutrition_grams / total_grams * 100.0) if total_grams else 0.0:.2f}; "
                        f"default_cost_usd={default_cost:.4f}"
                    ),
                    "nutrition_resolved_pct": f"{(nutrition_grams / total_grams * 100.0) if total_grams else 0.0:.2f}",
                    "calculator_identity_version": IDENTITY_VERSION,
                    "calculator_resolved_line_count": str(len(line_records) - len(unresolved_records)),
                    "calculator_unresolved_line_count": str(len(unresolved_records)),
                    "calculator_resolved_grams_pct": f"{resolved_pct:.2f}",
                    "calculator_unresolved_lines_json": (
                        json.dumps(unresolved_records, sort_keys=True, separators=(",", ":")) if unresolved_records else ""
                    ),
                    "calculator_line_resolutions_json": (
                        json.dumps(line_records, sort_keys=True, separators=(",", ":")) if include_line_json else ""
                    ),
                }
                writer.writerow(row)
                stats["recipes_written"] += 1
                if default_cost:
                    stats["recipes_with_default_cost"] += 1

    finally:
        if line_handle is not None:
            line_handle.close()

    tmp_csv.replace(out_csv)
    if write_lines_jsonl:
        tmp_lines.replace(out_lines)
    elif tmp_lines.exists():
        tmp_lines.unlink()
    elif out_lines.exists():
        out_lines.unlink()

    finalized_meta = _finalize_meta(meta)
    out_meta.write_text(json.dumps(finalized_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "recipe_qa_db": str(recipe_qa_db),
        "package_db": str(package_db),
        "out_csv": str(out_csv),
        "out_meta": str(out_meta),
        "out_lines": str(out_lines) if write_lines_jsonl else "",
        "identity_version": IDENTITY_VERSION,
        "limit_recipes": limit_recipes,
        "min_resolved_grams_pct": min_resolved_grams_pct,
        "default_servings": default_servings,
        "allow_sr28_fallback": allow_sr28_fallback,
        "allow_fndds_fallback": allow_fndds_fallback,
        "require_priced_ingredients": require_priced_ingredients,
        "stats": dict(stats),
        "top_gate_reasons": gate_reasons.most_common(50),
        "key_sources": dict(key_sources),
        "nutrition_sources": dict(nutrition_sources),
        "ingredient_key_count": len(finalized_meta),
        "price_key_count": len(price_per_gram),
        "top_unresolved_inputs": unresolved_inputs.most_common(50),
        "top_unpriced_recipe_keys": unpriced_recipe_keys.most_common(50),
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Hestia-compatible native recipe rows from recipe_qa.db.")
    parser.add_argument("--recipe-qa-db", type=Path, default=DEFAULT_RECIPE_QA_DB)
    parser.add_argument("--package-db", type=Path, default=DEFAULT_PACKAGE_DB)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    parser.add_argument("--out-meta", type=Path, default=DEFAULT_OUT_META)
    parser.add_argument("--out-lines", type=Path, default=DEFAULT_OUT_LINES)
    parser.add_argument("--limit-recipes", type=int, default=0)
    parser.add_argument("--min-resolved-grams-pct", type=float, default=70.0)
    parser.add_argument("--default-servings", type=float, default=4.0)
    parser.add_argument("--strict-esha-only", action="store_true")
    parser.add_argument("--allow-fndds-fallback", action="store_true")
    parser.add_argument(
        "--allow-default-priced-ingredients",
        action="store_true",
        help="Allow recipes with ingredient keys missing from the package DB. Off by default.",
    )
    parser.add_argument("--include-line-json", action="store_true")
    parser.add_argument("--write-lines-jsonl", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_recipes(
        recipe_qa_db=args.recipe_qa_db.expanduser(),
        package_db=args.package_db.expanduser(),
        out_csv=args.out_csv.expanduser(),
        out_summary=args.out_summary.expanduser(),
        out_meta=args.out_meta.expanduser(),
        out_lines=args.out_lines.expanduser(),
        limit_recipes=args.limit_recipes,
        min_resolved_grams_pct=args.min_resolved_grams_pct,
        default_servings=args.default_servings,
        allow_sr28_fallback=not args.strict_esha_only,
        allow_fndds_fallback=args.allow_fndds_fallback,
        require_priced_ingredients=not args.allow_default_priced_ingredients,
        include_line_json=args.include_line_json,
        write_lines_jsonl=args.write_lines_jsonl,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
