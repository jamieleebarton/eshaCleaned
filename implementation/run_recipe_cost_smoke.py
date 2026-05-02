#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import surface_lab_calculator as lab_sources
from surface_lab_calculator import calculate_lab, configure_data_sources, normalize_key


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION = ROOT / "implementation"
OUT_DIR = IMPLEMENTATION / "output"
LOCAL_CLEAN_ROOT = ROOT.parent / "clean"

DEFAULT_RECIPES_CSV = LOCAL_CLEAN_ROOT / "recipe_pricing" / "output" / "recipes_final.csv"
DEFAULT_RECIPE_QA_DB = LOCAL_CLEAN_ROOT / "data" / "recipe_qa.db"
REPO_RETAIL_BRIDGE_CSV = OUT_DIR / "retail_canonical_surface_bridge.csv"
TMP_RETAIL_BRIDGE_CSV = Path("/tmp/hestia_native_artifacts/retail_canonical_surface_bridge.csv")
DEFAULT_RETAIL_BRIDGE_CSV = REPO_RETAIL_BRIDGE_CSV if REPO_RETAIL_BRIDGE_CSV.exists() else TMP_RETAIL_BRIDGE_CSV
DEFAULT_OUT_JSON = OUT_DIR / "recipe_cost_smoke.json"
DEFAULT_OUT_MD = OUT_DIR / "recipe_cost_smoke.md"

DEFAULT_RECIPE_IDS = ("59578", "59579", "113871", "113875", "113880")

NO_PURCHASE_KEYS = {
    "water",
    "boiling water",
    "cold water",
    "hot water",
    "ice water",
    "iced water",
    "tap water",
    "warm water",
    "water bottled generic",
}

NO_PURCHASE_WATER_QUALIFIERS = {
    "boiling",
    "cold",
    "hot",
    "ice",
    "iced",
    "tap",
    "very",
    "warm",
}
NO_PURCHASE_QUANTITY_TOKENS = {
    "cup",
    "cups",
    "dash",
    "fl",
    "fluid",
    "g",
    "gallon",
    "gallons",
    "gram",
    "grams",
    "lb",
    "lbs",
    "liter",
    "liters",
    "ml",
    "ounce",
    "ounces",
    "oz",
    "pint",
    "pints",
    "qt",
    "quart",
    "quarts",
    "tablespoon",
    "tablespoons",
    "tbsp",
    "teaspoon",
    "teaspoons",
    "tsp",
}


@dataclass(frozen=True)
class RetailOffer:
    retail_source: str
    upc: str
    name: str
    grams: float
    cents: float
    cpg: float
    search_term: str
    canonical_surface: str
    canonical_shopping_item: str


def _float_or_zero(value: str) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def _normalized_package_grams(*, name: str, search_term: str, canonical_surface: str, grams: float) -> float:
    text = normalize_key(f"{name} {search_term} {canonical_surface}")
    tokens = set(text.split())
    if not (tokens & {"egg", "eggs"}):
        return grams
    if tokens & {"beater", "beaters", "liquid", "substitute", "white", "whites", "yolk", "yolks"}:
        return grams

    count = 0
    for token in text.split():
        if token.isdigit():
            value = int(token)
            if value in {6, 12, 18, 24, 30, 36, 60}:
                count = value
                break
    if "dozen" in tokens:
        count = 12
    if count:
        return float(count * 50)
    if grams < 300 or grams > 1500:
        return 600.0
    return grams


def _is_no_purchase_surface(value: str) -> bool:
    key = normalize_key(value)
    if key in NO_PURCHASE_KEYS:
        return True
    tokens = {
        token
        for token in key.split()
        if not token.isdigit() and token not in NO_PURCHASE_QUANTITY_TOKENS
    }
    return bool(tokens) and "water" in tokens and tokens <= (NO_PURCHASE_WATER_QUALIFIERS | {"water"})


def _money(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:.2f}"


def _short(value: str, limit: int = 72) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _load_retail_offers(path: Path) -> dict[tuple[str, str], RetailOffer]:
    offers: dict[tuple[str, str], RetailOffer] = {}
    if not path.exists():
        return offers
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            if (row.get("canonical_match_status") or "").strip() != "assigned":
                continue
            source = (row.get("retail_source") or "").strip()
            upc = (row.get("upc") or "").strip()
            name = (row.get("name") or "").strip()
            grams = _float_or_zero(row.get("grams", ""))
            cents = _float_or_zero(row.get("cents", ""))
            cpg = _float_or_zero(row.get("cpg", ""))
            if not source or not name or grams <= 0 or cents <= 0:
                continue
            grams = _normalized_package_grams(
                name=name,
                search_term=(row.get("search_term") or "").strip(),
                canonical_surface=(row.get("canonical_surface") or "").strip(),
                grams=grams,
            )
            if cpg <= 0:
                cpg = cents / 100.0 / grams
            else:
                cpg = cents / 100.0 / grams
            offer = RetailOffer(
                retail_source=source,
                upc=upc,
                name=name,
                grams=grams,
                cents=cents,
                cpg=cpg,
                search_term=(row.get("search_term") or "").strip(),
                canonical_surface=(row.get("canonical_surface") or "").strip(),
                canonical_shopping_item=(row.get("canonical_shopping_item") or "").strip(),
            )
            source_key = f"retail_surface_bridge:{source}"
            if upc:
                offers.setdefault((source_key, upc), offer)
            offers.setdefault((source_key, normalize_key(name)), offer)
    return offers


def _offer_for_product(product: dict[str, Any], offers: dict[tuple[str, str], RetailOffer]) -> RetailOffer | None:
    source = (product.get("source") or "").strip()
    upc = (product.get("gtin_upc") or "").strip()
    if upc:
        offer = offers.get((source, upc))
        if offer:
            return offer
    return offers.get((source, normalize_key(product.get("description") or "")))


def _price_offer(offer: RetailOffer, needed_grams: float) -> dict[str, Any]:
    packages = max(1, math.ceil(needed_grams / offer.grams)) if needed_grams > 0 else 0
    checkout_usd = packages * offer.cents / 100.0
    used_usd = needed_grams * offer.cpg
    return {
        "retail_source": offer.retail_source,
        "upc": offer.upc,
        "name": offer.name,
        "package_grams": offer.grams,
        "package_usd": offer.cents / 100.0,
        "packages": packages,
        "checkout_usd": checkout_usd,
        "used_usd": used_usd,
        "search_term": offer.search_term,
        "canonical_surface": offer.canonical_surface,
        "canonical_shopping_item": offer.canonical_shopping_item,
    }


def _ranked_offers(
    products: list[dict[str, Any]],
    offers: dict[tuple[str, str], RetailOffer],
    source: str,
    needed_grams: float,
) -> list[dict[str, Any]]:
    wanted_source = f"retail_surface_bridge:{source}"
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for product in products:
        product_source = (product.get("source") or "")
        if product_source == wanted_source:
            offer = _offer_for_product(product, offers)
        elif product_source.startswith("audit_path_lookup"):
            # Step D source: UPC came from master_products via audit
            # canonical_path. Re-key the offer lookup against the requested
            # retail source so Walmart/Kroger pricing still attaches.
            upc = (product.get("gtin_upc") or "").strip()
            offer = offers.get((wanted_source, upc)) if upc else None
            if not offer:
                offer = offers.get(
                    (wanted_source, normalize_key(product.get("description") or ""))
                )
        else:
            continue
        if not offer:
            continue
        dedupe_key = (offer.upc, normalize_key(offer.name))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        priced = _price_offer(offer, needed_grams)
        priced["decision_reason"] = product.get("reason", "")
        candidates.append(priced)
    return sorted(
        candidates,
        key=lambda row: (
            row["checkout_usd"],
            row["used_usd"],
            row["package_usd"],
            normalize_key(row["name"]),
        ),
    )


def _best_offer(
    products: list[dict[str, Any]],
    offers: dict[tuple[str, str], RetailOffer],
    source: str,
    needed_grams: float,
) -> dict[str, Any] | None:
    ranked = _ranked_offers(products, offers, source, needed_grams)
    return ranked[0] if ranked else None


def _shopping_needed_grams(
    *,
    display: str,
    item: str,
    lab: dict[str, Any],
    recipe_grams: float,
) -> tuple[float, str]:
    """Return retail purchase grams when recipe grams are for a prepared form."""
    if recipe_grams <= 0:
        return recipe_grams, ""
    text = normalize_key(" ".join([display, item]))
    target = normalize_key(" ".join([lab.get("shopping_canonical") or "", lab.get("canonical_name") or ""]))
    text_tokens = set(text.split())
    target_tokens = set(target.split())
    if "cooked" in text_tokens and "rice" in target_tokens and not (text_tokens & {"dry", "dried", "raw", "uncooked"}):
        return recipe_grams / 3.0, "retail grams adjusted: cooked rice -> dry rice using 3x cooked yield"
    return recipe_grams, ""


def _load_recipes(path: Path, recipe_ids: set[str], max_recipes: int) -> list[dict[str, str]]:
    recipes: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            recipe_id = (row.get("recipeNum") or "").strip()
            if recipe_ids and recipe_id not in recipe_ids:
                continue
            raw_items = (row.get("shopping_items_dict") or "").strip()
            if not raw_items or raw_items == "{}":
                continue
            recipes.append(row)
            if not recipe_ids and len(recipes) >= max_recipes:
                break
    return recipes


def _parse_shopping_items(raw: str) -> dict[str, float]:
    parsed = ast.literal_eval(raw)
    if not isinstance(parsed, dict):
        return {}
    items: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            grams = float(value)
        except (TypeError, ValueError):
            continue
        if grams > 0:
            items[str(key)] = grams
    return items


def _load_original_ingredients(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "select recipe_id, ingredients_json from recipe_cleaned where ingredients_json is not null"
        ).fetchall()
    for recipe_id, raw_json in rows:
        try:
            parsed = json.loads(raw_json or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue
        lines: list[dict[str, Any]] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            display = str(entry.get("display") or "").strip()
            item = str(entry.get("item") or "").strip()
            try:
                grams = float(entry.get("grams") or 0)
            except (TypeError, ValueError):
                grams = 0.0
            if display or item:
                lines.append({"display": display, "item": item, "grams": grams})
        if lines:
            out[str(recipe_id)] = lines
    return out


def _line_note(lab: dict[str, Any], walmart: dict[str, Any] | None, kroger: dict[str, Any] | None) -> str:
    if lab.get("nutrition_state") == "nutrition_unknown":
        return "resolver gap: no nutrition/shopping target; not a store availability claim"
    if lab.get("shopping_state") == "shopping_gap":
        return "shopping gap: no candidate store product selected"
    if walmart or kroger:
        return "accepted retail bridge"
    products = lab.get("products") or []
    if products:
        sources = sorted({(product.get("source") or "") for product in products})
        return "candidate products exist but no priced Walmart/Kroger bridge item: " + ", ".join(source for source in sources if source)
    return ""


def _nutrition_anchor_text(line: dict[str, Any]) -> str:
    if line.get("nutrition_source") == "sr28_direct" and line.get("sr28_fdc_id"):
        return f"SR28:{line['sr28_fdc_id']}"
    if line.get("nutrition_source") == "fndds_direct" and line.get("fndds_code"):
        return f"FNDDS:{line['fndds_code']}"
    if line.get("esha_code"):
        return f"ESHA:{line['esha_code']} {_short(line.get('esha_description', ''), 42)}".strip()
    if line.get("sr28_fdc_id"):
        return f"SR28:{line['sr28_fdc_id']}"
    if line.get("fndds_code"):
        return f"FNDDS:{line['fndds_code']}"
    return ""


def run_smoke(
    *,
    recipes_csv: Path,
    recipe_qa_db: Path,
    surface_csv: Path | None,
    product_esha_map_csv: Path | None,
    retail_bridge_csv: Path,
    recipe_ids: list[str],
    max_recipes: int,
    buy_water: bool,
) -> dict[str, Any]:
    configure_data_sources(
        surface_csv=surface_csv,
        product_esha_map_csv=product_esha_map_csv,
        retail_surface_bridge_csv=retail_bridge_csv,
    )
    offers = _load_retail_offers(retail_bridge_csv)
    recipes = _load_recipes(recipes_csv, set(recipe_ids), max_recipes)
    original_by_recipe = _load_original_ingredients(recipe_qa_db)
    output: dict[str, Any] = {
        "recipes_csv": str(recipes_csv),
        "recipe_qa_db": str(recipe_qa_db),
        "surface_csv": str(lab_sources.SURFACE_CSV),
        "product_esha_map_csv": str(lab_sources.PRODUCT_ESHA_MAP_CSV),
        "retail_bridge_csv": str(retail_bridge_csv),
        "recipe_ids": recipe_ids,
        "offer_count": len(offers),
        "recipes": [],
    }

    for recipe in recipes:
        shopping_items = _parse_shopping_items(recipe.get("shopping_items_dict") or "")
        recipe_num = (recipe.get("recipeNum") or "").strip()
        raw_lines = original_by_recipe.get(recipe_num, [])
        normalized_pairs = list(shopping_items.items())
        if raw_lines:
            line_inputs: list[dict[str, Any]] = []
            for index, raw_line in enumerate(raw_lines):
                normalized_label, normalized_grams = normalized_pairs[index] if index < len(normalized_pairs) else ("", 0.0)
                raw_grams = float(raw_line.get("grams") or 0.0)
                line_inputs.append(
                    {
                        "display": raw_line.get("display") or raw_line.get("item") or normalized_label,
                        "item": raw_line.get("item") or raw_line.get("display") or normalized_label,
                        "grams": raw_grams if raw_grams > 0 else normalized_grams,
                        "normalized_label": normalized_label,
                    }
                )
        else:
            line_inputs = [
                {"display": label, "item": label, "grams": grams, "normalized_label": label}
                for label, grams in normalized_pairs
            ]
        recipe_out: dict[str, Any] = {
            "recipe_num": recipe_num,
            "recipe_name": (recipe.get("recipeName") or "").strip(),
            "line_count": len(line_inputs),
            "original_ingredient_source": str(recipe_qa_db) if raw_lines else "",
            "lines": [],
            "totals": {
                "purchasable_grams": 0.0,
                "walmart_covered_grams": 0.0,
                "kroger_covered_grams": 0.0,
                "walmart_checkout_usd": 0.0,
                "walmart_used_usd": 0.0,
                "kroger_checkout_usd": 0.0,
                "kroger_used_usd": 0.0,
            },
        }
        for line_input in line_inputs:
            display = str(line_input.get("display") or "")
            item = str(line_input.get("item") or display)
            normalized_label = str(line_input.get("normalized_label") or "")
            grams = float(line_input.get("grams") or 0.0)
            lab = asdict(calculate_lab(display=display, item=item, grams=grams))
            no_purchase = (
                not buy_water
                and (
                    _is_no_purchase_surface(item)
                    or _is_no_purchase_surface(display)
                    or _is_no_purchase_surface(lab.get("shopping_canonical") or "")
                    or _is_no_purchase_surface(lab.get("canonical_name") or "")
                )
            )
            products = lab.get("products") or []
            shopping_grams, quantity_note = _shopping_needed_grams(
                display=display,
                item=item,
                lab=lab,
                recipe_grams=grams,
            )
            walmart_options = [] if no_purchase else _ranked_offers(products, offers, "walmart", shopping_grams)
            kroger_options = [] if no_purchase else _ranked_offers(products, offers, "kroger", shopping_grams)
            walmart = walmart_options[0] if walmart_options else None
            kroger = kroger_options[0] if kroger_options else None
            rejected = lab.get("rejected_products") or []
            note = "no purchase: water/household ingredient" if no_purchase else _line_note(lab, walmart, kroger)
            if quantity_note:
                note = f"{note}; {quantity_note}" if note else quantity_note
            line = {
                "input": display,
                "original_item": item,
                "normalized_shopping_item": normalized_label,
                "grams": grams,
                "shopping_grams": shopping_grams,
                "canonical_name": lab.get("canonical_name", ""),
                "shopping_canonical": lab.get("shopping_canonical", ""),
                "esha_code": lab.get("esha_code", ""),
                "esha_description": lab.get("esha_description", ""),
                "sr28_fdc_id": lab.get("sr28_fdc_id", ""),
                "fndds_code": lab.get("fndds_code", ""),
                "nutrition_state": lab.get("nutrition_state", ""),
                "nutrition_source": lab.get("nutrition_source", ""),
                "shopping_state": "not_purchased" if no_purchase else lab.get("shopping_state", ""),
                "walmart": walmart,
                "kroger": kroger,
                "walmart_options": walmart_options[:5],
                "kroger_options": kroger_options[:5],
                "note": note,
                "accepted_examples": [
                    {
                        "source": product.get("source", ""),
                        "name": product.get("description", ""),
                        "reason": product.get("reason", ""),
                    }
                    for product in products[:3]
                ],
                "rejected_examples": [
                    {
                        "source": product.get("source", ""),
                        "name": product.get("description", ""),
                        "reason": product.get("reason", ""),
                    }
                    for product in rejected[:3]
                ],
                "path": lab.get("path", []),
            }
            recipe_out["lines"].append(line)
            if not no_purchase:
                recipe_out["totals"]["purchasable_grams"] += grams
            if walmart:
                recipe_out["totals"]["walmart_covered_grams"] += grams
                recipe_out["totals"]["walmart_checkout_usd"] += walmart["checkout_usd"]
                recipe_out["totals"]["walmart_used_usd"] += walmart["used_usd"]
            if kroger:
                recipe_out["totals"]["kroger_covered_grams"] += grams
                recipe_out["totals"]["kroger_checkout_usd"] += kroger["checkout_usd"]
                recipe_out["totals"]["kroger_used_usd"] += kroger["used_usd"]

        purchasable = recipe_out["totals"]["purchasable_grams"]
        recipe_out["totals"]["walmart_coverage_pct"] = (
            recipe_out["totals"]["walmart_covered_grams"] / purchasable if purchasable else 0.0
        )
        recipe_out["totals"]["kroger_coverage_pct"] = (
            recipe_out["totals"]["kroger_covered_grams"] / purchasable if purchasable else 0.0
        )
        output["recipes"].append(recipe_out)
    return output


def _line_product_text(line: dict[str, Any], source: str) -> str:
    offer = line.get(source)
    if not offer:
        return ""
    return (
        f"{_short(offer['name'])} "
        f"({_money(offer['package_usd'])}/{offer['package_grams']:.0f}g, "
        f"{offer['packages']} pkg)"
    )


def _option_text(options: list[dict[str, Any]], limit: int = 3) -> str:
    if not options:
        return ""
    rendered = []
    for offer in options[:limit]:
        rendered.append(
            f"{_short(offer['name'], 48)} "
            f"({_money(offer['package_usd'])}/{offer['package_grams']:.0f}g, "
            f"{offer['packages']} pkg, checkout {_money(offer['checkout_usd'])})"
        )
    return " ; ".join(rendered)


def _md_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines: list[str] = [
        "# Recipe Cost Smoke",
        "",
        f"- recipes_csv: `{report['recipes_csv']}`",
        f"- recipe_qa_db: `{report.get('recipe_qa_db', '')}`",
        f"- surface_csv: `{report.get('surface_csv', '')}`",
        f"- product_esha_map_csv: `{report.get('product_esha_map_csv', '')}`",
        f"- retail_bridge_csv: `{report['retail_bridge_csv']}`",
        f"- bridge offers loaded: `{report['offer_count']}`",
        "",
        "## Summary",
        "",
        "| recipe | lines | Walmart checkout | Walmart used | Walmart grams covered | Kroger checkout | Kroger used | Kroger grams covered |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for recipe in report["recipes"]:
        totals = recipe["totals"]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{recipe['recipe_num']} {recipe['recipe_name']}",
                    str(recipe["line_count"]),
                    _money(totals["walmart_checkout_usd"]),
                    _money(totals["walmart_used_usd"]),
                    f"{totals['walmart_coverage_pct']:.0%}",
                    _money(totals["kroger_checkout_usd"]),
                    _money(totals["kroger_used_usd"]),
                    f"{totals['kroger_coverage_pct']:.0%}",
                ]
            )
            + " |"
        )

    for recipe in report["recipes"]:
        lines.extend(
            [
                "",
                f"## {recipe['recipe_num']} {recipe['recipe_name']}",
                "",
                f"- original ingredient source: `{recipe.get('original_ingredient_source') or 'not found; using normalized shopping items'}`",
                "",
                "| original recipe text | parsed item | normalized shopping item | recipe grams | retail grams | calculator target | nutrition anchor | Walmart buy | Kroger buy | diagnosis |",
                "| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |",
            ]
        )
        for line in recipe["lines"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(_short(line["input"], 54)),
                        _md_cell(_short(line.get("original_item", ""), 34)),
                        _md_cell(_short(line.get("normalized_shopping_item", ""), 42)),
                        f"{line['grams']:.1f}",
                        f"{line.get('shopping_grams', line['grams']):.1f}",
                        _md_cell(_short(line.get("shopping_canonical") or line.get("canonical_name") or "", 42)),
                        _md_cell(_short(_nutrition_anchor_text(line), 52)),
                        _md_cell(_line_product_text(line, "walmart")),
                        _md_cell(_line_product_text(line, "kroger")),
                        _md_cell(_short(line.get("note", ""), 60)),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "### Retail Package Options",
                "",
                "| original recipe text | Walmart top options | Kroger top options |",
                "| --- | --- | --- |",
            ]
        )
        for line in recipe["lines"]:
            if not line.get("walmart_options") and not line.get("kroger_options"):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(_short(line["input"], 54)),
                        _md_cell(_option_text(line.get("walmart_options") or [])),
                        _md_cell(_option_text(line.get("kroger_options") or [])),
                    ]
                )
                + " |"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run recipe-level pricing smoke checks through surface_lab_calculator.")
    parser.add_argument("--recipes-csv", type=Path, default=DEFAULT_RECIPES_CSV)
    parser.add_argument("--recipe-qa-db", type=Path, default=DEFAULT_RECIPE_QA_DB)
    parser.add_argument("--surface-csv", type=Path)
    parser.add_argument("--product-esha-map", type=Path)
    parser.add_argument("--retail-bridge-csv", type=Path, default=DEFAULT_RETAIL_BRIDGE_CSV)
    parser.add_argument("--recipe-id", action="append", dest="recipe_ids", help="Recipe id to include; repeatable")
    parser.add_argument("--max-recipes", type=int, default=3, help="Used only when no --recipe-id values are supplied")
    parser.add_argument("--buy-water", action="store_true", help="Treat water as a priced retail purchase")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = parser.parse_args()

    recipe_ids = args.recipe_ids or list(DEFAULT_RECIPE_IDS)
    report = run_smoke(
        recipes_csv=args.recipes_csv,
        recipe_qa_db=args.recipe_qa_db,
        surface_csv=args.surface_csv,
        product_esha_map_csv=args.product_esha_map,
        retail_bridge_csv=args.retail_bridge_csv,
        recipe_ids=recipe_ids,
        max_recipes=args.max_recipes,
        buy_water=args.buy_water,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, args.out_md)
    print(json.dumps({"recipes": len(report["recipes"]), "out_json": str(args.out_json), "out_md": str(args.out_md)}, indent=2))


if __name__ == "__main__":
    main()
