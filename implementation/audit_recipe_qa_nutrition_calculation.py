from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

try:
    from resolver_context import DEFAULT_ARTIFACTS
except ModuleNotFoundError:
    from implementation.resolver_context import DEFAULT_ARTIFACTS

try:
    from map_recipe_lines_to_concepts import (
        approved_rule_for_surface,
        load_approved_normalization_rules,
        parse_line as parse_recipe_line,
    )
except ModuleNotFoundError:
    from implementation.map_recipe_lines_to_concepts import (
        approved_rule_for_surface,
        load_approved_normalization_rules,
        parse_line as parse_recipe_line,
    )

try:
    from build_normalized_item_bridge import NormalizedItemBridgeResolver
except ModuleNotFoundError:
    from implementation.build_normalized_item_bridge import NormalizedItemBridgeResolver


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DEFAULT_RECIPE_QA_DB = DEFAULT_ARTIFACTS.recipe_qa_db
DEFAULT_PRODUCTS_DB = DEFAULT_ARTIFACTS.master_products_db
DEFAULT_LINE_AUDIT_DB = ROOT / "output" / "recipe_calculation_audit_full.db"
DEFAULT_PRODUCT_AUDIT_CSV = DEFAULT_ARTIFACTS.product_contract_audit_csv
DEFAULT_PRODUCT_NUTRITION_STATE_DB = DEFAULT_ARTIFACTS.product_nutrition_state_db
DEFAULT_DENSITY_BRIDGE_CSV = DEFAULT_ARTIFACTS.reviewed_density_bridge_csv
DEFAULT_NUTRITION_ANCHORS_CSV = DEFAULT_ARTIFACTS.reviewed_nutrition_anchors_csv
DEFAULT_SR28_FALLBACK_CSV = DEFAULT_ARTIFACTS.reviewed_sr28_nutrition_fallbacks_csv
DEFAULT_EXTERNAL_CATALOG_CSV = DEFAULT_ARTIFACTS.reviewed_external_catalog_items_csv
DEFAULT_SR28_FOOD_CSV = PROJECT_ROOT / "data" / "sr28_csv" / "food.csv"
DEFAULT_SR28_NUTRIENT_CSV = PROJECT_ROOT / "data" / "sr28_csv" / "food_nutrient.csv"
DEFAULT_SR28_FOOD_PORTION_CSV = PROJECT_ROOT / "data" / "sr28_csv" / "food_portion.csv"
DEFAULT_SR28_MEASURE_UNIT_CSV = PROJECT_ROOT / "data" / "sr28_csv" / "measure_unit.csv"
DEFAULT_SR28_LEGACY_FOOD_CSV = PROJECT_ROOT / "data" / "sr28_csv" / "sr_legacy_food.csv"
DEFAULT_FNDDS_INGRED_CSV = PROJECT_ROOT / "data" / "fndds" / "FNDDSIngred.csv"
DEFAULT_FNDDS_NUTRIENT_CSV = PROJECT_ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
DEFAULT_OUTPUT_DB = ROOT / "output" / "recipe_qa_nutrition_calculation_audit.db"
DEFAULT_REPORT_JSON = ROOT / "output" / "recipe_qa_nutrition_calculation_audit.json"
DEFAULT_REPORT_MD = ROOT / "output" / "recipe_qa_nutrition_calculation_audit.md"
DEFAULT_TOP_FAILURES_CSV = ROOT / "output" / "recipe_qa_nutrition_top_failures.csv"
DEFAULT_LOW_RECIPES_CSV = ROOT / "output" / "recipe_qa_nutrition_low_recipes.csv"
DEFAULT_NORMALIZED_ITEM_BRIDGE_CSV = DEFAULT_ARTIFACTS.normalized_item_bridge_csv
DEFAULT_TO_TASTE_DEFAULTS_CSV = DEFAULT_ARTIFACTS.reviewed_to_taste_defaults_csv
DEFAULT_QUANTITY_POLICIES_CSV = DEFAULT_ARTIFACTS.reviewed_quantity_policies_csv
DEFAULT_HOUSEHOLD_UNIT_GRAMS_CSV = DEFAULT_ARTIFACTS.reviewed_household_unit_gram_rules_csv
DEFAULT_RECIPE_LINE_PATCHES_CSV = DEFAULT_ARTIFACTS.reviewed_recipe_line_patches_csv
TO_TASTE_BUCKETS = ("quantity_to_taste", "quantity_as_needed")
QUANTITY_POLICY_BUCKETS = ("quantity_missing", "manual_quantity_required", "quantity_to_taste", "quantity_as_needed")


NUTRIENTS = [
    "calories",
    "protein_g",
    "fat_g",
    "carbs_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
]

GRAM_UNITS = {"g", "gram", "grams", "grm"}
ML_UNITS = {"ml", "mlt", "milliliter", "milliliters", "millilitre", "millilitres"}
MASS_UNIT_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.349523125,
    "lb": 453.59237,
}
VOLUME_UNIT_ML = {
    "ml": 1.0,
    "l": 1000.0,
    "tsp": 4.92892159375,
    "tbsp": 14.78676478125,
    "fl oz": 29.5735295625,
    "cup": 236.5882365,
    "pint": 473.176473,
    "quart": 946.352946,
    "gallon": 3785.411784,
}
READY_NUTRITION_STATUSES = {
    "nutrition_ready_g",
    "nutrition_ready_ml_density",
    "nutrition_ready_sr28_anchor",
    "nutrition_ready_sr28_fallback",
    "nutrition_ready_fndds_anchor",
    "nutrition_ready_branded_fdc_proxy",
    "nutrition_ready_external_catalog",
    "nutrition_ready_split_to_taste_defaults",
}
SR28_NUTRIENT_IDS = {
    "1008": "calories",
    "2047": "calories",
    "1003": "protein_g",
    "1004": "fat_g",
    "1005": "carbs_g",
    "1079": "fiber_g",
    "2000": "sugar_g",
    "1063": "sugar_g",
    "1093": "sodium_mg",
}
FNDDS_NUTRIENT_COLUMNS = {
    "calories": "energy_kcal",
    "protein_g": "protein_g",
    "fat_g": "fat_g",
    "carbs_g": "carbs_g",
    "fiber_g": "fiber_g",
    "sugar_g": "sugar_g",
    "sodium_mg": "sodium_mg",
}
SR28_FALLBACK_ELIGIBLE_STATUSES = {
    "product_nutrition_zero_or_rounded",
    "product_nutrition_missing",
}
EXTERNAL_CATALOG_FALLBACK_BUCKETS = (
    "contract_not_passed",
    "product_not_candidate_covered",
    "product_contract_failed",
    "product_contract_missing",
    "product_nutrition_missing",
    "product_nutrition_zero_or_rounded",
    "product_unknown",
    "product_not_in_audit_scope",
    "serving_unit_not_grams",
    "serving_unit_not_supported",
)
PRODUCT_NUTRITION_CACHE_TABLES = ("product_nutrition", "external_catalog_nutrition")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_line(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u00a0", " ")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def normalize_concept_key(value: str | None) -> str:
    text = normalize_line(value)
    if not text:
        return ""
    parts = text.split("|")
    if len(parts) == 1:
        return parts[0].strip()
    parts = [part.strip() for part in (parts + ["", "", "", ""])[:4]]
    return "|".join(parts)


def normalize_concept_key_list(value: str | None) -> str:
    text = value or ""
    if ";" not in text:
        return normalize_concept_key(text)
    return ";".join(
        key for key in (normalize_concept_key(part) for part in text.split(";")) if key
    )


def parse_quantity_value(value: str | None) -> float | None:
    fraction_chars = {
        "¼": "1/4",
        "½": "1/2",
        "¾": "3/4",
        "⅓": "1/3",
        "⅔": "2/3",
        "⅛": "1/8",
        "⅜": "3/8",
        "⅝": "5/8",
        "⅞": "7/8",
    }
    raw = value or ""
    for char, replacement in fraction_chars.items():
        raw = raw.replace(char, f" {replacement}")
    text = unicodedata.normalize("NFKC", raw).strip().lower()
    if not text:
        return None
    text = text.replace("⁄", "/")
    text = re.sub(r"\b(?:about|approximately|approx\.?|around|scant|heaping|level)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(\d+)-(\d+/\d+)$", r"\1 \2", text)

    range_match = re.match(r"^(.+?)\s*(?:-|to|or)\s*(.+)$", text)
    if range_match:
        left = parse_quantity_value(range_match.group(1))
        right = parse_quantity_value(range_match.group(2))
        if left is not None and right is not None:
            return (left + right) / 2.0

    try:
        return float(text)
    except ValueError:
        pass

    parts = text.split()
    try:
        if len(parts) == 2:
            return float(Fraction(parts[0])) + float(Fraction(parts[1]))
        if len(parts) == 1:
            return float(Fraction(parts[0]))
    except (ValueError, ZeroDivisionError):
        return None
    return None


def normalize_household_unit(value: str | None) -> str:
    unit = normalize_line(value)
    unit = unit.strip(".")
    aliases = {
        "": "count",
        "ea": "count",
        "ea.": "count",
        "each": "count",
        "whole": "count",
        "pepper": "count",
        "peppers": "count",
        "potato": "count",
        "potatoes": "count",
        "g": "g",
        "grm": "g",
        "gram": "g",
        "grams": "g",
        "kg": "kg",
        "kgs": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "ml": "ml",
        "mlt": "ml",
        "milliliter": "ml",
        "milliliters": "ml",
        "millilitre": "ml",
        "millilitres": "ml",
        "l": "l",
        "liter": "l",
        "liters": "l",
        "litre": "l",
        "litres": "l",
        "c": "cup",
        "c.": "cup",
        "cup": "cup",
        "cups": "cup",
        "tbsp": "tbsp",
        "tbsp.": "tbsp",
        "tbs": "tbsp",
        "tbs.": "tbsp",
        "tablespoon": "tbsp",
        "tablespoons": "tbsp",
        "t": "tsp",
        "t.": "tsp",
        "tsp": "tsp",
        "tsp.": "tsp",
        "teaspoon": "tsp",
        "teaspoons": "tsp",
        "oz": "oz",
        "oz.": "oz",
        "ounce": "oz",
        "ounces": "oz",
        "fl oz": "fl oz",
        "fl. oz": "fl oz",
        "fl. oz.": "fl oz",
        "fluid ounce": "fl oz",
        "fluid ounces": "fl oz",
        "in": "inch",
        "in.": "inch",
        "inch": "inch",
        "inches": "inch",
        "pint": "pint",
        "pints": "pint",
        "quart": "quart",
        "quarts": "quart",
        "gallon": "gallon",
        "gallons": "gallon",
        "lb": "lb",
        "lb.": "lb",
        "lbs": "lb",
        "lbs.": "lb",
        "pound": "lb",
        "pounds": "lb",
        "slice": "slice",
        "slices": "slice",
        "clove": "clove",
        "cloves": "clove",
        "leaf": "count",
        "leaves": "count",
        "sprig": "sprig",
        "sprigs": "sprig",
        "stalk": "stalk",
        "stalks": "stalk",
        "ear": "ear",
        "ears": "ear",
        "rib": "rib",
        "ribs": "rib",
        "roll": "count",
        "rolls": "count",
        "bun": "count",
        "buns": "count",
        "head": "head",
        "heads": "head",
        "bunch": "bunch",
        "bunches": "bunch",
        "pita": "count",
        "pitas": "count",
        "round": "count",
        "rounds": "count",
        "piece": "piece",
        "pieces": "piece",
        "pkg": "package",
        "pkg.": "package",
        "package": "package",
        "packages": "package",
        "packet": "packet",
        "packets": "packet",
        "punnet": "punnet",
        "punnets": "punnet",
        "pod": "pod",
        "pods": "pod",
        "fillet": "fillet",
        "fillets": "fillet",
        "blossom": "blossom",
        "blossoms": "blossom",
        "can": "can",
        "cans": "can",
        "stick": "stick",
        "sticks": "stick",
        "small": "small",
        "medium": "medium",
        "large": "large",
        "ring": "ring",
        "rings": "ring",
        "strip": "strip",
        "strips": "strip",
        "pinch": "pinch",
        "pinches": "pinch",
        "dash": "dash",
        "dashes": "dash",
    }
    return aliases.get(unit, unit)


SR28_PORTION_FORM_ALIASES = {
    "chunk": {"chunk", "chunks", "chunked"},
    "crushed": {"crushed"},
    "sliced": {"slice", "slices", "sliced"},
    "chopped": {"chop", "chopped"},
    "diced": {"dice", "diced"},
    "shredded": {"shred", "shredded"},
    "drained": {"drained"},
    "strip": {"strip", "strips"},
}


def portion_forms(text: str) -> set[str]:
    normalized = normalize_line(text)
    forms: set[str] = set()
    for form, aliases in SR28_PORTION_FORM_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            forms.add(form)
    return forms


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = FILE")
    return conn


def close_with_checkpoint(conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def artifact_digest(path: Path, *, hash_contents: bool) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.exists():
        return {
            "path": str(resolved),
            "exists": False,
            "size": None,
            "mtime_ns": None,
            "sha256": None,
        }
    stat = resolved.stat()
    sha256 = None
    if hash_contents:
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
    return {
        "path": str(resolved),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256,
    }


def product_nutrition_dependency_state(
    *,
    product_audit_csv: Path,
    products_db: Path,
    density_bridge_csv: Path,
    nutrition_anchor_csv: Path,
    sr28_fallback_csv: Path,
    external_catalog_csv: Path,
    sr28_food_csv: Path,
    sr28_nutrient_csv: Path,
) -> tuple[str, list[dict[str, object]]]:
    csv_inputs = [
        product_audit_csv,
        density_bridge_csv,
        nutrition_anchor_csv,
        sr28_fallback_csv,
        external_catalog_csv,
        sr28_food_csv,
        DEFAULT_SR28_LEGACY_FOOD_CSV,
        DEFAULT_FNDDS_INGRED_CSV,
        DEFAULT_FNDDS_NUTRIENT_CSV,
        Path(__file__),
    ]
    large_inputs = [products_db, sr28_nutrient_csv]
    artifacts = [
        artifact_digest(path, hash_contents=True)
        for path in csv_inputs
    ] + [
        artifact_digest(path, hash_contents=False)
        for path in large_inputs
    ]
    payload = json.dumps(artifacts, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), artifacts


def product_nutrition_cache_metadata(cache_db: Path) -> dict[str, object] | None:
    if not cache_db.exists():
        return None
    conn = sqlite3.connect(cache_db)
    try:
        row = conn.execute(
            """
            SELECT dependency_fingerprint, generated_at, product_rows, external_rows, external_stats_json
            FROM product_nutrition_state_meta
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        conn.close()
        return None
    conn.close()
    if not row:
        return None
    return {
        "dependency_fingerprint": row[0],
        "generated_at": row[1],
        "product_rows": int(row[2] or 0),
        "external_rows": int(row[3] or 0),
        "external_stats": json.loads(row[4] or "{}"),
    }


def product_nutrition_cache_is_valid(cache_db: Path, dependency_fingerprint: str) -> bool:
    metadata = product_nutrition_cache_metadata(cache_db)
    if not metadata or metadata.get("dependency_fingerprint") != dependency_fingerprint:
        return False
    conn = sqlite3.connect(cache_db)
    try:
        for table in PRODUCT_NUTRITION_CACHE_TABLES:
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            if not count:
                return False
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if row_count <= 0:
                return False
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return True


def load_product_rows(products_db: Path) -> dict[tuple[str, str], list[dict[str, object]]]:
    conn = sqlite3.connect(products_db)
    conn.row_factory = sqlite3.Row
    products: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in conn.execute(
        """
        SELECT
            gtin_upc,
            description,
            brand_owner,
            branded_food_category,
            serving_size,
            serving_size_unit,
            calories,
            protein_g,
            fat_g,
            carbs_g,
            fiber_g,
            sugar_g,
            sodium_mg
        FROM products
        WHERE calories IS NOT NULL
        """
    ):
        key = (row["description"] or "", row["branded_food_category"] or "")
        products.setdefault(key, []).append(dict(row))
    conn.close()
    return products


def load_density_bridge(path: Path) -> dict[tuple[str, str], float]:
    densities: dict[tuple[str, str], float] = {}
    if not path.exists():
        return densities
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            try:
                density = float(row.get("density_g_per_ml") or 0)
            except ValueError:
                continue
            if density <= 0:
                continue
            scope_type = (row.get("scope_type") or "").strip()
            scope_key = (row.get("scope_key") or "").strip()
            if scope_type and scope_key:
                densities[(scope_type, scope_key)] = density
    return densities


def load_sr28_nutrients(path: Path) -> dict[str, dict[str, float]]:
    nutrients: dict[str, dict[str, float]] = {}
    if not path.exists():
        return nutrients
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            nutrient_id = row.get("nutrient_id") or ""
            field = SR28_NUTRIENT_IDS.get(nutrient_id)
            if not field:
                continue
            try:
                amount = float(row.get("amount") or "")
            except ValueError:
                continue
            record = nutrients.setdefault(row["fdc_id"], {})
            if field == "calories":
                if nutrient_id == "1008" or "calories" not in record:
                    record[field] = amount
                continue
            if field == "sugar_g":
                if nutrient_id == "2000" or "sugar_g" not in record:
                    record[field] = amount
                continue
            record[field] = amount
    return nutrients


def load_sr28_food_descriptions(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    id_to_description: dict[str, str] = {}
    description_to_ids: dict[str, list[str]] = {}
    if not path.exists():
        return id_to_description, description_to_ids
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            fdc_id = (row.get("fdc_id") or "").strip()
            description = (row.get("description") or "").strip()
            if not fdc_id or not description:
                continue
            id_to_description[fdc_id] = description
            description_to_ids.setdefault(normalize_line(description), []).append(fdc_id)
    return id_to_description, description_to_ids


def resolve_sr28_fallback_id(
    fdc_id: str,
    reviewed_description: str,
    id_to_description: dict[str, str],
    description_to_ids: dict[str, list[str]],
) -> str | None:
    actual_description = id_to_description.get(fdc_id, "")
    if not actual_description:
        return None
    if not reviewed_description:
        return fdc_id
    if normalize_line(actual_description) == normalize_line(reviewed_description):
        return fdc_id
    exact_ids = description_to_ids.get(normalize_line(reviewed_description), [])
    if len(exact_ids) == 1:
        return exact_ids[0]
    return None


def load_sr28_fallbacks(path: Path, sr28_food_csv: Path | None = None) -> dict[str, dict[str, str]]:
    fallbacks: dict[str, dict[str, str]] = {}
    if not path.exists():
        return fallbacks
    id_to_description: dict[str, str] = {}
    description_to_ids: dict[str, list[str]] = {}
    if sr28_food_csv:
        id_to_description, description_to_ids = load_sr28_food_descriptions(sr28_food_csv)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            concept_key = normalize_concept_key(row.get("concept_key"))
            fdc_id = (row.get("fdc_id") or "").strip()
            sr28_description = (row.get("sr28_description") or "").strip()
            if id_to_description:
                resolved_fdc_id = resolve_sr28_fallback_id(
                    fdc_id,
                    sr28_description,
                    id_to_description,
                    description_to_ids,
                )
                if not resolved_fdc_id:
                    continue
                fdc_id = resolved_fdc_id
                sr28_description = id_to_description.get(fdc_id, sr28_description)
            if concept_key and fdc_id:
                fallbacks[concept_key] = {
                    "fdc_id": fdc_id,
                    "sr28_description": sr28_description,
                    "nutrition_status": "nutrition_ready_sr28_fallback",
                    "nutrition_basis": "sr28_fallback_per_100g",
                }
    return fallbacks


def load_reviewed_nutrition_anchors(path: Path, sr28_food_csv: Path | None = None) -> dict[str, dict[str, str]]:
    anchors: dict[str, dict[str, str]] = {}
    if not path.exists():
        return anchors
    id_to_description: dict[str, str] = {}
    description_to_ids: dict[str, list[str]] = {}
    if sr28_food_csv:
        id_to_description, description_to_ids = load_sr28_food_descriptions(sr28_food_csv)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            if (row.get("source_system") or "").strip() != "SR28":
                continue
            concept_key = normalize_concept_key(row.get("concept_key"))
            fdc_id = (row.get("food_id") or "").strip()
            sr28_description = (row.get("description") or "").strip()
            if id_to_description:
                resolved_fdc_id = resolve_sr28_fallback_id(
                    fdc_id,
                    sr28_description,
                    id_to_description,
                    description_to_ids,
                )
                if not resolved_fdc_id:
                    continue
                fdc_id = resolved_fdc_id
                sr28_description = id_to_description.get(fdc_id, sr28_description)
            if concept_key and fdc_id:
                anchors[concept_key] = {
                    "fdc_id": fdc_id,
                    "sr28_description": sr28_description,
                    "nutrition_status": "nutrition_ready_sr28_anchor",
                    "nutrition_basis": "sr28_anchor_per_100g",
                }
    return anchors


def load_sr28_legacy_ndb_to_fdc(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path.exists():
        return mapping
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ndb = (row.get("NDB_number") or "").strip()
            fdc_id = (row.get("fdc_id") or "").strip()
            if ndb and fdc_id:
                mapping[ndb] = fdc_id
    return mapping


def load_fndds_ingredient_weights(path: Path) -> dict[str, list[dict[str, object]]]:
    by_food_code: dict[str, list[dict[str, object]]] = {}
    if not path.exists():
        return by_food_code
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            food_code = (row.get("Food code") or "").strip()
            ingredient_code = (row.get("Ingredient code") or "").strip()
            if not food_code or not ingredient_code:
                continue
            try:
                weight = float(row.get("Ingredient weight") or row.get("Amount") or 0)
            except ValueError:
                continue
            if weight <= 0:
                continue
            by_food_code.setdefault(food_code, []).append(
                {
                    "ingredient_code": ingredient_code,
                    "ingredient_description": (row.get("Ingredient description") or "").strip(),
                    "weight_g": weight,
                }
            )
    return by_food_code


def load_fndds_nutrients(path: Path) -> dict[str, dict[str, float]]:
    nutrients: dict[str, dict[str, float]] = {}
    if not path.exists():
        return nutrients
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            food_code = (row.get("fndds_code") or "").strip()
            if not food_code:
                continue
            values: dict[str, float] = {}
            for nutrient, column in FNDDS_NUTRIENT_COLUMNS.items():
                raw = (row.get(column) or "").strip()
                if raw == "":
                    continue
                try:
                    values[nutrient] = float(raw)
                except ValueError:
                    continue
            if values:
                nutrients[food_code] = values
    return nutrients


def fndds_product_nutrition_row(
    concept_key: str,
    fndds_anchor: dict[str, str],
    fndds_nutrients: dict[str, float],
) -> dict[str, object] | None:
    food_id = fndds_anchor["food_id"]
    if not food_id or not fndds_nutrients:
        return None
    per_gram = {}
    for nutrient in NUTRIENTS:
        value = fndds_nutrients.get(nutrient)
        per_gram[f"{nutrient}_per_g"] = float(value) / 100.0 if value is not None else None
    return {
        "concept_key": concept_key,
        "nutrition_status": "nutrition_ready_fndds_anchor",
        "policy": "fndds_nutrition_only",
        "gtin_upc": "",
        "selected_description": fndds_anchor["description"],
        "selected_category": "FNDDS",
        "serving_size": None,
        "serving_size_unit": "",
        "density_g_per_ml": None,
        "nutrition_basis": "fndds_per_100g",
        "sr28_fdc_id": f"FNDDS:{food_id}",
        "sr28_description": fndds_anchor["description"],
        **per_gram,
    }


def load_reviewed_fndds_nutrition_rows(
    path: Path,
    *,
    fndds_nutrient_csv: Path = DEFAULT_FNDDS_NUTRIENT_CSV,
) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    if not path.exists():
        return rows
    fndds_nutrients = load_fndds_nutrients(fndds_nutrient_csv)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            if (row.get("source_system") or "").strip() != "FNDDS":
                continue
            concept_key = normalize_concept_key(row.get("concept_key"))
            food_id = (row.get("food_id") or "").strip()
            description = (row.get("description") or "").strip()
            if not concept_key or not food_id or not description:
                continue
            nutrients = fndds_nutrients.get(food_id)
            if not nutrients:
                continue
            nutrition_row = fndds_product_nutrition_row(
                concept_key,
                {"food_id": food_id, "description": description},
                nutrients,
            )
            if nutrition_row:
                rows[concept_key] = nutrition_row
    return rows


def parse_optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def split_review_tokens(value: str | None) -> list[str]:
    return [token for token in (normalize_line(part) for part in (value or "").split(";")) if token]


def reviewed_token_gate_allows(row: dict[str, str], text: str) -> bool:
    normalized = normalize_line(text)
    required = split_review_tokens(row.get("allowed_description_tokens"))
    forbidden = split_review_tokens(row.get("forbidden_description_tokens"))
    if any(token in normalized for token in forbidden):
        return False
    return all(token in normalized for token in required)


def branded_product_nutrients_are_sane(product: dict[str, object]) -> bool:
    values = {nutrient: parse_optional_float(product.get(nutrient)) for nutrient in NUTRIENTS}
    calories = values["calories"]
    if calories is None or calories < 0 or calories > 900:
        return False
    for nutrient in ("protein_g", "fat_g", "carbs_g"):
        value = values[nutrient]
        if value is None or value < 0 or value > 100:
            return False
    for nutrient in ("fiber_g", "sugar_g"):
        value = values[nutrient]
        if value is not None and (value < 0 or value > 100):
            return False
    sodium = values["sodium_mg"]
    if sodium is not None and (sodium < 0 or sodium > 100000):
        return False
    carbs = values["carbs_g"]
    fiber = values["fiber_g"]
    sugar = values["sugar_g"]
    if fiber is not None and carbs is not None and fiber > carbs + 0.5:
        return False
    if sugar is not None and carbs is not None and sugar > carbs + 0.5:
        return False
    if values["protein_g"] + values["fat_g"] + values["carbs_g"] > 130:
        return False
    return True


def load_branded_products_by_food_id(products_db: Path, food_id: str) -> list[dict[str, object]]:
    if not products_db.exists() or not food_id:
        return []
    conn = sqlite3.connect(products_db)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
        if "fdc_id" not in columns and "gtin_upc" not in columns:
            return []
        select_columns = [
            "fdc_id" if "fdc_id" in columns else "'' AS fdc_id",
            "gtin_upc",
            "description",
            "brand_owner",
            "branded_food_category",
            "serving_size",
            "serving_size_unit",
            "calories",
            "protein_g",
            "fat_g",
            "carbs_g",
            "fiber_g",
            "sugar_g",
            "sodium_mg",
        ]
        where_parts = []
        params: list[str] = []
        if "fdc_id" in columns:
            where_parts.append("CAST(fdc_id AS TEXT) = ?")
            params.append(food_id)
        if "gtin_upc" in columns:
            where_parts.append("gtin_upc = ?")
            params.append(food_id)
        query = f"""
            SELECT {', '.join(select_columns)}
            FROM products
            WHERE {' OR '.join(where_parts)}
        """
        return [dict(row) for row in conn.execute(query, params)]
    finally:
        conn.close()


def branded_fdc_product_nutrition_row(
    concept_key: str,
    anchor: dict[str, str],
    product: dict[str, object],
    *,
    densities: dict[tuple[str, str], float] | None = None,
) -> dict[str, object] | None:
    if not branded_product_nutrients_are_sane(product):
        return None
    densities = densities or {}
    serving_unit = normalize_household_unit(str(product.get("serving_size_unit") or ""))
    density: float | None = None
    nutrient_divisor = 100.0
    nutrition_basis = "branded_fdc_per_100g"
    if serving_unit in {"ml", "l"}:
        density = densities.get(("concept", concept_key))
        if density is None:
            density = densities.get(("category", str(product.get("branded_food_category") or "")))
        if density is None or density <= 0:
            return None
        nutrient_divisor = 100.0 * density
        nutrition_basis = "branded_fdc_per_100ml_density_bridge"
    per_gram = {}
    for nutrient in NUTRIENTS:
        value = parse_optional_float(product.get(nutrient))
        per_gram[f"{nutrient}_per_g"] = value / nutrient_divisor if value is not None else None
    fdc_id = str(product.get("fdc_id") or anchor["food_id"])
    return {
        "concept_key": concept_key,
        "nutrition_status": "nutrition_ready_branded_fdc_proxy",
        "policy": "branded_fdc_nutrition_proxy",
        "gtin_upc": product.get("gtin_upc") or "",
        "selected_description": product.get("description") or anchor["description"],
        "selected_category": product.get("branded_food_category") or "BRANDED_FDC",
        "serving_size": parse_optional_float(product.get("serving_size")),
        "serving_size_unit": product.get("serving_size_unit") or "",
        "density_g_per_ml": density,
        "nutrition_basis": nutrition_basis,
        "sr28_fdc_id": f"BRANDED_FDC:{fdc_id}",
        "sr28_description": product.get("description") or anchor["description"],
        **per_gram,
    }


def load_reviewed_branded_nutrition_rows(
    path: Path,
    *,
    products_db: Path = DEFAULT_PRODUCTS_DB,
    density_bridge_csv: Path = DEFAULT_DENSITY_BRIDGE_CSV,
    densities: dict[tuple[str, str], float] | None = None,
) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    if not path.exists():
        return rows
    if densities is None:
        densities = load_density_bridge(density_bridge_csv)
    candidates: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            if (row.get("source_system") or "").strip() != "BRANDED_FDC":
                continue
            concept_key = normalize_concept_key(row.get("concept_key"))
            food_id = (row.get("food_id") or "").strip()
            description = (row.get("description") or "").strip()
            if concept_key and food_id and description:
                candidate = dict(row)
                candidate["concept_key"] = concept_key
                candidate["food_id"] = food_id
                candidate["description"] = description
                candidates.append(candidate)
    if not candidates:
        return rows
    for row in candidates:
        products = load_branded_products_by_food_id(products_db, row["food_id"])
        if not products:
            continue
        products.sort(
            key=lambda product: (
                normalize_line(product.get("description") or "") != normalize_line(row["description"]),
                product.get("description") or "",
            )
        )
        for product in products:
            evidence_text = " ".join(
                [
                    str(product.get("description") or ""),
                    str(product.get("brand_owner") or ""),
                    str(product.get("branded_food_category") or ""),
                ]
            )
            if normalize_line(product.get("description") or "") != normalize_line(row["description"]):
                continue
            if not reviewed_token_gate_allows(row, evidence_text):
                continue
            nutrition_row = branded_fdc_product_nutrition_row(row["concept_key"], row, product, densities=densities)
            if nutrition_row:
                rows[row["concept_key"]] = nutrition_row
                break
    return rows


def load_external_catalog_items(
    path: Path,
    sr28_nutrients: dict[str, dict[str, float]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    return load_external_catalog_items_with_food_csv(
        path,
        sr28_nutrients,
        DEFAULT_SR28_FOOD_CSV,
    )


ALCOHOL_PROXY_ALLOW_RE = re.compile(
    r"\b(?:"
    r"absinthe|ale|amaretto|baileys?|benedictine|beer|bourbon|brandy|cabernet|campari|champagne|chambord|"
    r"chardonnay|chartreuse|cider|cognac|cointreau|curacao|drambuie|frangelico|framboise|galliano|gin|"
    r"creme de cacao|creme de menthe|grappa|grand marnier|goldschlager|guinness|irish cream|kahlua|kirsch|liqueur|"
    r"limoncello|marnier|marsala|merlot|ouzo|pernod|port|prosecco|riesling|rum|sake|sambuca|"
    r"sauterne|sauvignon|schnapps?|scotch|sherry|stout|tequila|"
    r"triple sec|vermouth|vodka|whiskey|whisky|wine"
    r")\b",
    re.IGNORECASE,
)
ALCOHOL_PROXY_FORBID_RE = re.compile(
    r"\b(?:"
    r"batter|bread|crumb|crumbled|crumpet|cookie|cooky|crust|dressing|extract|flavoring|ginger ale|"
    r"ginger beer|kale|leaf|pepper|ranch|salsa|sauce|seasoning|syrup|vinegar|vinaigrette"
    r")\b",
    re.IGNORECASE,
)


def plausible_external_alcohol_row(row: dict[str, str]) -> bool:
    if (row.get("shopping_category") or "").strip() != "external_alcohol":
        return True
    text = normalize_line(" ".join([row.get("concept_key") or "", row.get("shopping_label") or ""]))
    if ALCOHOL_PROXY_FORBID_RE.search(text):
        return False
    return bool(ALCOHOL_PROXY_ALLOW_RE.search(text))


REJECTED_EXTERNAL_AUTO_PROXIES = {
    "beans|||": ("175249", "beans, white, mature seeds, cooked, boiled, with salt", "generic beans cannot silently use cooked white beans"),
    "beef||cube|": ("174777", "beef, flank, steak, separable lean only, trimmed to 0\" fat, select, raw", "beef cubes/stew meat cannot silently use flank steak"),
    "cake|||": ("175055", "cake, yellow, unenriched, dry mix", "generic cake cannot silently use dry yellow cake mix"),
    "cake||crumb|": ("175055", "cake, yellow, unenriched, dry mix", "cake crumbs cannot silently use dry yellow cake mix"),
    "cheese|2% milk|singles|": ("173452", "cheese, parmesan, dry grated, reduced fat", "cheese singles cannot silently use grated parmesan"),
    "cherries|||": ("173960", "cherries, sweet, canned, pitted, heavy syrup pack, solids and liquids", "generic cherries cannot silently use canned heavy-syrup cherries"),
    "chicken|||cooked": ("174506", "chicken, broiler, rotisserie, bbq, back meat only", "generic cooked chicken cannot silently use BBQ rotisserie back meat"),
    "cookie|||": ("174080", "cookie, chocolate, with icing or coating", "generic cookie cannot silently use chocolate iced cookie"),
    "cranberry||ground|": ("169805", "cranberry, low bush or lingenberry, raw (alaska native)", "ground cranberry cannot silently use raw whole cranberry"),
    "dip|||": ("174069", "dip, tostitos, salsa con queso, medium", "generic dip cannot silently use salsa con queso"),
    "dressing|||": ("171046", "dressing, honey mustard, fat-free", "generic dressing cannot silently use fat-free honey mustard dressing"),
    "fat|||": ("173572", "fat, goose", "generic fat cannot silently use goose fat"),
    "fennel||powder|": ("169385", "fennel, bulb, raw", "fennel powder cannot silently use raw fennel bulb"),
    "fish|||": ("175181", "fish, trout, brook, raw, new york state", "generic fish cannot silently use raw brook trout"),
    "horseradish|||fresh": ("173472", "horseradish, prepared", "fresh horseradish cannot silently use prepared horseradish"),
    "kefir|||": ("171301", "kefir, lowfat, strawberry, lifeway", "generic kefir cannot silently use strawberry lowfat kefir"),
    "melon|||": ("167629", "melon, banana (navajo)", "generic melon cannot silently use banana melon"),
    "papaya|||fresh": ("169927", "papaya, canned, heavy syrup, drained", "fresh papaya cannot silently use canned heavy-syrup papaya"),
    "spices|||": ("172231", "spices, turmeric, ground", "generic spices cannot silently use turmeric"),
    "squash|||": ("170539", "squash, winter, spaghetti, cooked, boiled, drained, or baked, with salt", "generic squash cannot silently use cooked spaghetti squash"),
    "syrup|||": ("170681", "syrup, nestle, chocolate", "generic syrup cannot silently use chocolate syrup"),
    "turkey|||": ("174613", "turkey, white, rotisserie, deli cut", "generic turkey cannot silently use deli rotisserie turkey"),
}
REVIEW_REQUIRED_EXTERNAL_AUTO_CONCEPT_KEYS = {
    concept_key: reason for concept_key, (_fdc_id, _description, reason) in REJECTED_EXTERNAL_AUTO_PROXIES.items()
}


def plausible_external_auto_row(row: dict[str, str]) -> bool:
    if (row.get("shopping_category") or "").strip() != "external_auto":
        return True
    concept_key = normalize_concept_key(row.get("concept_key"))
    rejected = REJECTED_EXTERNAL_AUTO_PROXIES.get(concept_key)
    if not rejected:
        return True
    rejected_fdc_id, rejected_description, _reason = rejected
    fdc_id = (row.get("fdc_id") or "").strip()
    description = normalize_line(row.get("sr28_description") or "")
    return fdc_id != rejected_fdc_id and description != normalize_line(rejected_description)


def load_external_catalog_items_with_food_csv(
    path: Path,
    sr28_nutrients: dict[str, dict[str, float]],
    sr28_food_csv: Path,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    by_concept: dict[str, dict[str, object]] = {}
    conflicted_concepts: set[str] = set()
    stats = Counter()
    if not path.exists():
        return [], dict(stats)
    id_to_description, description_to_ids = load_sr28_food_descriptions(sr28_food_csv)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("review_status") != "approved":
                continue
            concept_key = normalize_concept_key(row.get("concept_key"))
            fdc_id = (row.get("fdc_id") or "").strip()
            reviewed_description = (row.get("sr28_description") or "").strip()
            if not plausible_external_alcohol_row(row):
                stats["implausible_external_alcohol_skipped"] += 1
                continue
            if not plausible_external_auto_row(row):
                stats["implausible_external_auto_skipped"] += 1
                continue
            if not concept_key or not fdc_id:
                stats["missing_key_or_id"] += 1
                continue
            resolved_fdc_id = fdc_id
            actual_description = id_to_description.get(fdc_id, "")
            if reviewed_description and actual_description and normalize_line(actual_description) != normalize_line(reviewed_description):
                exact_ids = description_to_ids.get(normalize_line(reviewed_description), [])
                if len(exact_ids) == 1:
                    resolved_fdc_id = exact_ids[0]
                    stats["fdc_id_repaired_from_description"] += 1
                else:
                    stats["fdc_id_description_mismatch_skipped"] += 1
                    continue
            nutrients = sr28_nutrients.get(resolved_fdc_id)
            if not nutrients:
                stats["missing_nutrients_skipped"] += 1
                continue
            per_gram = {
                f"{nutrient}_per_g": (
                    float(nutrients[nutrient]) / 100.0
                    if nutrient in nutrients
                    else None
                )
                for nutrient in NUTRIENTS
            }
            output_row = {
                "concept_key": concept_key,
                "nutrition_status": "nutrition_ready_external_catalog",
                "shopping_label": (row.get("shopping_label") or "").strip(),
                "shopping_category": (row.get("shopping_category") or "").strip(),
                "sr28_fdc_id": resolved_fdc_id,
                "sr28_description": reviewed_description or id_to_description.get(resolved_fdc_id, ""),
                **per_gram,
            }
            existing = by_concept.get(concept_key)
            if existing:
                if (
                    existing.get("sr28_fdc_id") == output_row["sr28_fdc_id"]
                    and existing.get("sr28_description") == output_row["sr28_description"]
                ):
                    stats["duplicate_same_external_row_skipped"] += 1
                    continue
                by_concept.pop(concept_key, None)
                conflicted_concepts.add(concept_key)
                stats["duplicate_conflict_skipped"] += 1
                continue
            if concept_key in conflicted_concepts:
                stats["duplicate_conflict_skipped"] += 1
                continue
            by_concept[concept_key] = output_row
    stats["loaded"] = len(by_concept)
    return list(by_concept.values()), dict(stats)


def density_for(
    concept_key: str,
    selected_category: str,
    densities: dict[tuple[str, str], float],
) -> float | None:
    concept_density = densities.get(("concept", concept_key))
    if concept_density:
        return concept_density
    return densities.get(("category", selected_category))


def has_all_zero_nutrients(product: dict[str, object]) -> bool:
    observed = [product.get(name) for name in NUTRIENTS]
    numeric = [float(value) for value in observed if value is not None]
    return bool(numeric) and all(value == 0.0 for value in numeric)


def nutrition_status(
    product: dict[str, object] | None,
    concept_key: str,
    selected_category: str,
    densities: dict[tuple[str, str], float],
) -> tuple[str, dict[str, object], float | None]:
    if product is None:
        return "product_nutrition_missing", {}, None
    serving_size = product.get("serving_size")
    unit = str(product.get("serving_size_unit") or "").strip().lower()
    try:
        serving = float(serving_size or 0)
    except (TypeError, ValueError):
        serving = 0.0
    if serving <= 0:
        return "serving_size_missing", product, None
    if has_all_zero_nutrients(product):
        return "product_nutrition_zero_or_rounded", product, None
    if unit in GRAM_UNITS:
        return "nutrition_ready_g", product, None
    if unit in ML_UNITS:
        density = density_for(concept_key, selected_category, densities)
        if density:
            return "nutrition_ready_ml_density", product, density
        return "serving_unit_not_grams", product, None
    return "serving_unit_not_supported", product, None


def choose_product(
    rows: list[dict[str, object]] | None,
    concept_key: str,
    selected_category: str,
    densities: dict[tuple[str, str], float],
) -> tuple[str, dict[str, object], float | None]:
    if not rows:
        return "product_nutrition_missing", {}, None
    for row in rows:
        status, product, density = nutrition_status(row, concept_key, selected_category, densities)
        if status in READY_NUTRITION_STATUSES:
            return status, product, density
    return nutrition_status(rows[0], concept_key, selected_category, densities)


def sr28_product_nutrition_row(
    concept_key: str,
    sr28_anchor: dict[str, str],
    sr28_nutrients: dict[str, dict[str, float]],
    *,
    policy: str = "",
    selected_description: str = "",
    selected_category: str = "",
) -> dict[str, object] | None:
    sr28_record = sr28_nutrients.get(sr28_anchor["fdc_id"])
    if not sr28_record:
        return None
    nutrition_status = sr28_anchor.get("nutrition_status") or "nutrition_ready_sr28_anchor"
    nutrient_divisor = 100.0
    per_gram = {}
    for nutrient in NUTRIENTS:
        value = sr28_record.get(nutrient)
        per_gram[f"{nutrient}_per_g"] = float(value) / nutrient_divisor if value is not None else None
    return {
        "concept_key": concept_key,
        "nutrition_status": nutrition_status,
        "policy": policy or "sr28_nutrition_only",
        "gtin_upc": "",
        "selected_description": selected_description or sr28_anchor["sr28_description"],
        "selected_category": selected_category or "SR28",
        "serving_size": None,
        "serving_size_unit": "",
        "density_g_per_ml": None,
        "nutrition_basis": sr28_anchor.get("nutrition_basis") or "sr28_anchor_per_100g",
        "sr28_fdc_id": sr28_anchor["fdc_id"],
        "sr28_description": sr28_anchor["sr28_description"],
        **per_gram,
    }


def load_product_nutrition(
    product_audit_csv: Path,
    products_db: Path,
    density_bridge_csv: Path,
    nutrition_anchor_csv: Path,
    sr28_fallback_csv: Path,
    sr28_nutrient_csv: Path,
) -> list[dict[str, object]]:
    products = load_product_rows(products_db)
    densities = load_density_bridge(density_bridge_csv)
    sr28_anchors = load_sr28_fallbacks(sr28_fallback_csv, DEFAULT_SR28_FOOD_CSV)
    sr28_anchors.update(load_reviewed_nutrition_anchors(nutrition_anchor_csv, DEFAULT_SR28_FOOD_CSV))
    sr28_nutrients = load_sr28_nutrients(sr28_nutrient_csv)
    fndds_rows = load_reviewed_fndds_nutrition_rows(nutrition_anchor_csv)
    branded_rows = load_reviewed_branded_nutrition_rows(nutrition_anchor_csv, products_db=products_db, densities=densities)
    rows: list[dict[str, object]] = []
    emitted_concepts: set[str] = set()
    with product_audit_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            concept_key = row["concept_key"]
            audit_status = row["audit_status"]
            policy = row["policy"]
            selected_description = row["selected_description"]
            selected_category = row["selected_category"]
            fndds_row = fndds_rows.get(concept_key)
            if fndds_row:
                rows.append(dict(fndds_row))
                emitted_concepts.add(concept_key)
                continue
            branded_row = branded_rows.get(concept_key)
            if branded_row:
                rows.append(dict(branded_row))
                emitted_concepts.add(concept_key)
                continue
            sr28_anchor = sr28_anchors.get(concept_key)
            sr28_record = sr28_nutrients.get(sr28_anchor["fdc_id"]) if sr28_anchor else None
            if audit_status != "contract_passed":
                if sr28_record:
                    sr28_row = sr28_product_nutrition_row(
                        concept_key,
                        sr28_anchor,
                        sr28_nutrients,
                    )
                    if sr28_row:
                        rows.append(sr28_row)
                        emitted_concepts.add(concept_key)
                    continue
                rows.append(
                    {
                        "concept_key": concept_key,
                        "nutrition_status": "contract_not_passed",
                        "policy": policy,
                        "gtin_upc": "",
                        "selected_description": selected_description,
                        "selected_category": selected_category,
                        "serving_size": None,
                        "serving_size_unit": "",
                        "density_g_per_ml": None,
                        "nutrition_basis": "",
                        "sr28_fdc_id": "",
                        "sr28_description": "",
                        **{f"{name}_per_g": None for name in NUTRIENTS},
                    }
                )
                emitted_concepts.add(concept_key)
                continue
            status, product, density = choose_product(
                products.get((selected_description, selected_category)),
                concept_key,
                selected_category,
                densities,
            )
            serving = float(product.get("serving_size") or 0) if product else 0.0
            nutrient_divisor = None
            nutrition_basis = ""
            sr28_fdc_id = ""
            sr28_description = ""
            if sr28_record:
                status = sr28_anchor.get("nutrition_status") or "nutrition_ready_sr28_anchor"
                nutrient_divisor = 100.0
                nutrition_basis = sr28_anchor.get("nutrition_basis") or "sr28_anchor_per_100g"
                sr28_fdc_id = sr28_anchor["fdc_id"]
                sr28_description = sr28_anchor["sr28_description"]
            elif status == "nutrition_ready_g":
                nutrient_divisor = 100.0
                nutrition_basis = "product_per_100g"
            elif status == "nutrition_ready_ml_density" and density:
                nutrient_divisor = 100.0 * density
                nutrition_basis = "product_per_100ml_density_bridge"
            elif status in SR28_FALLBACK_ELIGIBLE_STATUSES:
                fallback = sr28_anchors.get(concept_key)
                if fallback:
                    sr28_record = sr28_nutrients.get(fallback["fdc_id"])
                    if sr28_record:
                        status = "nutrition_ready_sr28_fallback"
                        nutrient_divisor = 100.0
                        nutrition_basis = "sr28_fallback_per_100g"
                        sr28_fdc_id = fallback["fdc_id"]
                        sr28_description = fallback["sr28_description"]
            per_gram = {}
            for nutrient in NUTRIENTS:
                if status in {"nutrition_ready_sr28_anchor", "nutrition_ready_sr28_fallback"}:
                    value = sr28_nutrients[sr28_fdc_id].get(nutrient)
                else:
                    value = product.get(nutrient) if product else None
                per_gram[f"{nutrient}_per_g"] = (
                    float(value) / nutrient_divisor
                    if nutrient_divisor and value is not None
                    else None
                )
            uses_sr28_nutrition = status in {"nutrition_ready_sr28_anchor", "nutrition_ready_sr28_fallback"}
            rows.append(
                {
                    "concept_key": concept_key,
                    "nutrition_status": status,
                    "policy": "sr28_nutrition_only" if uses_sr28_nutrition else policy,
                    "gtin_upc": "" if uses_sr28_nutrition else (product.get("gtin_upc", "") if product else ""),
                    "selected_description": sr28_description if uses_sr28_nutrition else selected_description,
                    "selected_category": "SR28" if uses_sr28_nutrition else selected_category,
                    "serving_size": None if uses_sr28_nutrition else (serving if product else None),
                    "serving_size_unit": "" if uses_sr28_nutrition else (product.get("serving_size_unit", "") if product else ""),
                    "density_g_per_ml": None if uses_sr28_nutrition else density,
                    "nutrition_basis": nutrition_basis,
                    "sr28_fdc_id": sr28_fdc_id,
                    "sr28_description": sr28_description,
                    **per_gram,
                }
            )
            emitted_concepts.add(concept_key)
    for concept_key, sr28_anchor in sorted(sr28_anchors.items()):
        if concept_key in emitted_concepts:
            continue
        sr28_row = sr28_product_nutrition_row(concept_key, sr28_anchor, sr28_nutrients)
        if sr28_row:
            rows.append(sr28_row)
    for concept_key, fndds_row in sorted(fndds_rows.items()):
        if concept_key in emitted_concepts:
            continue
        rows.append(dict(fndds_row))
    for concept_key, branded_row in sorted(branded_rows.items()):
        if concept_key in emitted_concepts:
            continue
        rows.append(dict(branded_row))
    return rows


def populate_product_nutrition(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    conn.execute("DROP TABLE IF EXISTS product_nutrition")
    conn.execute(
        """
        CREATE TABLE product_nutrition (
            concept_key TEXT PRIMARY KEY,
            nutrition_status TEXT NOT NULL,
            policy TEXT NOT NULL,
            gtin_upc TEXT NOT NULL,
            selected_description TEXT NOT NULL,
            selected_category TEXT NOT NULL,
            serving_size REAL,
            serving_size_unit TEXT,
            density_g_per_ml REAL,
            nutrition_basis TEXT,
            sr28_fdc_id TEXT,
            sr28_description TEXT,
            calories_per_g REAL,
            protein_g_per_g REAL,
            fat_g_per_g REAL,
            carbs_g_per_g REAL,
            fiber_g_per_g REAL,
            sugar_g_per_g REAL,
            sodium_mg_per_g REAL
        )
        """
    )
    fields = [
        "concept_key",
        "nutrition_status",
        "policy",
        "gtin_upc",
        "selected_description",
        "selected_category",
        "serving_size",
        "serving_size_unit",
        "density_g_per_ml",
        "nutrition_basis",
        "sr28_fdc_id",
        "sr28_description",
        "calories_per_g",
        "protein_g_per_g",
        "fat_g_per_g",
        "carbs_g_per_g",
        "fiber_g_per_g",
        "sugar_g_per_g",
        "sodium_mg_per_g",
    ]
    conn.executemany(
        f"INSERT INTO product_nutrition VALUES ({','.join('?' for _ in fields)})",
        [tuple(row.get(field) for field in fields) for row in rows],
    )
    conn.commit()


def populate_external_catalog_nutrition(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    conn.execute("DROP TABLE IF EXISTS external_catalog_nutrition")
    conn.execute(
        """
        CREATE TABLE external_catalog_nutrition (
            concept_key TEXT PRIMARY KEY,
            nutrition_status TEXT NOT NULL,
            shopping_label TEXT NOT NULL,
            shopping_category TEXT NOT NULL,
            sr28_fdc_id TEXT NOT NULL,
            sr28_description TEXT NOT NULL,
            calories_per_g REAL,
            protein_g_per_g REAL,
            fat_g_per_g REAL,
            carbs_g_per_g REAL,
            fiber_g_per_g REAL,
            sugar_g_per_g REAL,
            sodium_mg_per_g REAL
        )
        """
    )
    fields = [
        "concept_key",
        "nutrition_status",
        "shopping_label",
        "shopping_category",
        "sr28_fdc_id",
        "sr28_description",
        "calories_per_g",
        "protein_g_per_g",
        "fat_g_per_g",
        "carbs_g_per_g",
        "fiber_g_per_g",
        "sugar_g_per_g",
        "sodium_mg_per_g",
    ]
    conn.executemany(
        f"INSERT INTO external_catalog_nutrition VALUES ({','.join('?' for _ in fields)})",
        [tuple(row.get(field) for field in fields) for row in rows],
    )
    conn.commit()


def build_product_nutrition_state_cache(
    *,
    cache_db: Path,
    dependency_fingerprint: str,
    dependency_artifacts: list[dict[str, object]],
    product_audit_csv: Path,
    products_db: Path,
    density_bridge_csv: Path,
    nutrition_anchor_csv: Path,
    sr28_fallback_csv: Path,
    external_catalog_csv: Path,
    sr28_food_csv: Path,
    sr28_nutrient_csv: Path,
) -> dict[str, object]:
    cache_db.parent.mkdir(parents=True, exist_ok=True)
    if cache_db.exists():
        cache_db.unlink()
    cache_conn = connect(cache_db)
    product_rows = load_product_nutrition(
        product_audit_csv,
        products_db,
        density_bridge_csv,
        nutrition_anchor_csv,
        sr28_fallback_csv,
        sr28_nutrient_csv,
    )
    sr28_nutrients = load_sr28_nutrients(sr28_nutrient_csv)
    external_rows, external_stats = load_external_catalog_items_with_food_csv(
        external_catalog_csv,
        sr28_nutrients,
        sr28_food_csv,
    )
    populate_product_nutrition(cache_conn, product_rows)
    populate_external_catalog_nutrition(cache_conn, external_rows)
    cache_conn.execute(
        """
        CREATE TABLE product_nutrition_state_meta (
            dependency_fingerprint TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            product_rows INTEGER NOT NULL,
            external_rows INTEGER NOT NULL,
            external_stats_json TEXT NOT NULL,
            dependency_artifacts_json TEXT NOT NULL
        )
        """
    )
    metadata = {
        "dependency_fingerprint": dependency_fingerprint,
        "generated_at": now_utc(),
        "product_rows": len(product_rows),
        "external_rows": len(external_rows),
        "external_stats": external_stats,
        "dependency_artifacts": dependency_artifacts,
    }
    cache_conn.execute(
        """
        INSERT INTO product_nutrition_state_meta (
            dependency_fingerprint,
            generated_at,
            product_rows,
            external_rows,
            external_stats_json,
            dependency_artifacts_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            metadata["dependency_fingerprint"],
            metadata["generated_at"],
            metadata["product_rows"],
            metadata["external_rows"],
            json.dumps(metadata["external_stats"], sort_keys=True),
            json.dumps(metadata["dependency_artifacts"], sort_keys=True),
        ),
    )
    close_with_checkpoint(cache_conn)
    return metadata


def copy_cached_product_nutrition_state(
    audit_conn: sqlite3.Connection,
    cache_db: Path,
) -> None:
    cache_conn = sqlite3.connect(f"file:{cache_db.resolve()}?mode=ro", uri=True)
    try:
        for table in PRODUCT_NUTRITION_CACHE_TABLES:
            audit_conn.execute(f"DROP TABLE IF EXISTS {table}")
            ddl_row = cache_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if ddl_row and ddl_row[0]:
                audit_conn.execute(ddl_row[0])
            else:
                raise RuntimeError(f"Missing DDL for cache table {table}")
            cols = [desc[1] for desc in cache_conn.execute(f"PRAGMA table_info({table})")]
            placeholders = ",".join("?" for _ in cols)
            rows = cache_conn.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                audit_conn.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})", rows)
        audit_conn.execute("CREATE INDEX IF NOT EXISTS idx_product_nutrition_concept ON product_nutrition(concept_key)")
        audit_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_external_catalog_nutrition_concept ON external_catalog_nutrition(concept_key)"
        )
        audit_conn.commit()
    finally:
        cache_conn.close()


def install_product_nutrition_state(
    audit_conn: sqlite3.Connection,
    *,
    cache_db: Path,
    product_audit_csv: Path,
    products_db: Path,
    density_bridge_csv: Path,
    nutrition_anchor_csv: Path,
    sr28_fallback_csv: Path,
    external_catalog_csv: Path,
    sr28_food_csv: Path,
    sr28_nutrient_csv: Path,
    force_rebuild: bool,
) -> dict[str, object]:
    dependency_fingerprint, dependency_artifacts = product_nutrition_dependency_state(
        product_audit_csv=product_audit_csv,
        products_db=products_db,
        density_bridge_csv=density_bridge_csv,
        nutrition_anchor_csv=nutrition_anchor_csv,
        sr28_fallback_csv=sr28_fallback_csv,
        external_catalog_csv=external_catalog_csv,
        sr28_food_csv=sr28_food_csv,
        sr28_nutrient_csv=sr28_nutrient_csv,
    )
    cache_hit = (
        not force_rebuild
        and product_nutrition_cache_is_valid(cache_db, dependency_fingerprint)
    )
    if cache_hit:
        metadata = product_nutrition_cache_metadata(cache_db) or {}
        source = "cache_hit"
    else:
        metadata = build_product_nutrition_state_cache(
            cache_db=cache_db,
            dependency_fingerprint=dependency_fingerprint,
            dependency_artifacts=dependency_artifacts,
            product_audit_csv=product_audit_csv,
            products_db=products_db,
            density_bridge_csv=density_bridge_csv,
            nutrition_anchor_csv=nutrition_anchor_csv,
            sr28_fallback_csv=sr28_fallback_csv,
            external_catalog_csv=external_catalog_csv,
            sr28_food_csv=sr28_food_csv,
            sr28_nutrient_csv=sr28_nutrient_csv,
        )
        source = "cache_rebuilt"
    import time
    time.sleep(0.5)
    copy_cached_product_nutrition_state(audit_conn, cache_db)
    metadata = dict(metadata)
    metadata["source"] = source
    metadata["cache_db"] = str(cache_db)
    metadata["dependency_fingerprint"] = dependency_fingerprint
    return metadata


def load_recipe_id_filter(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Missing recipe ID filter CSV: {path}")
    recipe_ids: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "recipe_id" not in (reader.fieldnames or []):
            raise ValueError(f"Recipe ID filter CSV must have a recipe_id column: {path}")
        for row in reader:
            recipe_id = (row.get("recipe_id") or "").strip()
            if recipe_id:
                recipe_ids.add(recipe_id)
    return recipe_ids


def load_recipe_line_patches(path: Path | None) -> dict[tuple[str, str], dict[str, object]]:
    patches: dict[tuple[str, str], dict[str, object]] = {}
    if path is None or not path.exists():
        return patches
    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            if None in row:
                raise ValueError(f"Malformed recipe line patch row in {path}: extra columns on line {line_number}")
            if row.get("review_status") != "approved":
                continue
            recipe_id = (row.get("recipe_id") or "").strip()
            old_text = normalize_line(row.get("old_ingredient_text"))
            new_display = (row.get("new_display") or "").strip()
            new_item = (row.get("new_item") or "").strip()
            if not recipe_id or not old_text or not new_display or not new_item:
                raise ValueError(f"Approved recipe line patch {row.get('patch_id') or line_number} is missing required text fields")
            raw_grams = (row.get("new_grams") or "").strip()
            new_grams: float | None = None
            if raw_grams:
                try:
                    new_grams = float(raw_grams)
                except ValueError as exc:
                    raise ValueError(f"Approved recipe line patch {row.get('patch_id') or line_number} has invalid new_grams") from exc
                if new_grams <= 0:
                    new_grams = None
            patch = {
                "patch_id": (row.get("patch_id") or "").strip(),
                "new_display": new_display,
                "new_item": new_item,
                "new_grams": new_grams,
                "problem": (row.get("problem") or "").strip(),
            }
            key = (recipe_id, old_text)
            existing = patches.get(key)
            if existing is not None and existing != patch:
                raise ValueError(f"Conflicting recipe line patches for recipe_id={recipe_id} old_ingredient_text={old_text!r}")
            patches[key] = patch
    return patches


def populate_recipe_ingredients(
    conn: sqlite3.Connection,
    recipe_qa_db: Path,
    recipe_id_filter: set[str] | None = None,
    recipe_line_patches_csv: Path | None = DEFAULT_RECIPE_LINE_PATCHES_CSV,
) -> int:
    recipe_line_patches = load_recipe_line_patches(recipe_line_patches_csv)
    patches_applied = 0
    conn.execute("DROP TABLE IF EXISTS recipe_qa_ingredients")
    conn.execute(
        """
        CREATE TABLE recipe_qa_ingredients (
            recipe_id TEXT NOT NULL,
            title TEXT NOT NULL,
            ingredient_index INTEGER NOT NULL,
            display TEXT NOT NULL,
            item TEXT NOT NULL,
            normalized_line TEXT NOT NULL,
            grams REAL,
            patch_id TEXT,
            patch_problem TEXT,
            patched_old_display TEXT
        )
        """
    )
    source = sqlite3.connect(recipe_qa_db)
    batch = []
    for recipe_id, title, ingredients_json in source.execute(
        "SELECT recipe_id, title, ingredients_json FROM recipe_cleaned"
    ):
        recipe_id = str(recipe_id)
        if recipe_id_filter is not None and recipe_id not in recipe_id_filter:
            continue
        try:
            ingredients = json.loads(ingredients_json or "[]")
        except json.JSONDecodeError:
            ingredients = []
        for index, ingredient in enumerate(ingredients):
            if isinstance(ingredient, dict):
                display = str(ingredient.get("display") or ingredient.get("item") or "")
                item = str(ingredient.get("item") or "")
                grams = ingredient.get("grams")
            else:
                display = str(ingredient or "")
                item = display
                grams = None
            try:
                grams_value = float(grams) if grams is not None else None
            except (TypeError, ValueError):
                grams_value = None
            patch = recipe_line_patches.get((recipe_id, normalize_line(display)))
            patch_id = ""
            patch_problem = ""
            patched_old_display = ""
            if patch is not None:
                patch_id = str(patch.get("patch_id") or "")
                patch_problem = str(patch.get("problem") or "")
                patched_old_display = display
                display = str(patch["new_display"])
                item = str(patch["new_item"])
                patch_grams = patch.get("new_grams")
                if patch_grams is not None:
                    grams_value = float(patch_grams)
                patches_applied += 1
            batch.append(
                (
                    str(recipe_id),
                    str(title or ""),
                    index,
                    display,
                    item,
                    normalize_line(display),
                    grams_value,
                    patch_id,
                    patch_problem,
                    patched_old_display,
                )
            )
            if len(batch) >= 20_000:
                conn.executemany("INSERT INTO recipe_qa_ingredients VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                batch.clear()
    if batch:
        conn.executemany("INSERT INTO recipe_qa_ingredients VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
    source.close()
    conn.execute("CREATE INDEX idx_recipe_qa_ingredients_line ON recipe_qa_ingredients(normalized_line)")
    conn.execute("CREATE INDEX idx_recipe_qa_ingredients_recipe ON recipe_qa_ingredients(recipe_id)")
    conn.execute("CREATE INDEX idx_recipe_qa_ingredients_patch ON recipe_qa_ingredients(patch_id)")
    conn.commit()
    return patches_applied


def attach(conn: sqlite3.Connection, path: Path, alias: str) -> None:
    escaped = str(path).replace("'", "''")
    conn.execute(f"ATTACH DATABASE '{escaped}' AS {alias}")


def populate_to_taste_defaults(conn: sqlite3.Connection, csv_path: Path) -> int:
    conn.execute("DROP TABLE IF EXISTS to_taste_defaults")
    conn.execute(
        """
        CREATE TABLE to_taste_defaults (
            concept_key TEXT PRIMARY KEY,
            default_grams REAL NOT NULL,
            rationale TEXT,
            reviewer TEXT,
            evidence TEXT
        )
        """
    )
    rows = 0
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            batch = []
            for row in reader:
                key = (row.get("concept_key") or "").strip()
                if not key:
                    continue
                try:
                    grams = float(row.get("default_grams") or 0)
                except (TypeError, ValueError):
                    continue
                if grams <= 0:
                    continue
                batch.append(
                    (
                        key,
                        grams,
                        (row.get("rationale") or "").strip() or None,
                        (row.get("reviewer") or "").strip() or None,
                        (row.get("evidence") or "").strip() or None,
                    )
                )
            if batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO to_taste_defaults VALUES (?,?,?,?,?)",
                    batch,
                )
                rows = len(batch)
    conn.commit()
    return rows


def populate_quantity_policies(conn: sqlite3.Connection, csv_path: Path) -> list[dict[str, object]]:
    conn.execute("DROP TABLE IF EXISTS quantity_policies")
    conn.execute(
        """
        CREATE TABLE quantity_policies (
            policy_id TEXT PRIMARY KEY,
            concept_key TEXT NOT NULL,
            source_bucket TEXT NOT NULL,
            include_regex TEXT NOT NULL,
            exclude_regex TEXT,
            action TEXT NOT NULL,
            default_grams REAL,
            rationale TEXT
        )
        """
    )
    policies: list[dict[str, object]] = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("review_status") != "approved":
                    continue
                policy_id = (row.get("policy_id") or "").strip()
                concept_key = normalize_concept_key(row.get("concept_key"))
                source_bucket = (row.get("source_bucket") or "").strip()
                include_regex = (row.get("include_regex") or "").strip()
                action = (row.get("action") or "").strip()
                if action in {"garnish", "greasing", "dusting", "frying_absorbed"}:
                    action = "apply_default"
                if not policy_id or not source_bucket or action not in {"apply_default", "manual_prompt", "intentional_skip"}:
                    continue
                default_grams: float | None = None
                raw_grams = (row.get("default_grams") or "").strip()
                if raw_grams:
                    try:
                        default_grams = float(raw_grams)
                    except ValueError:
                        default_grams = None
                if action == "apply_default" and (default_grams is None or default_grams <= 0):
                    continue
                policy = {
                    "policy_id": policy_id,
                    "concept_key": concept_key,
                    "source_bucket": source_bucket,
                    "include_regex": include_regex,
                    "exclude_regex": (row.get("exclude_regex") or "").strip(),
                    "action": action,
                    "default_grams": default_grams,
                    "rationale": (row.get("rationale") or "").strip(),
                }
                policies.append(policy)
    if policies:
        conn.executemany(
            "INSERT OR REPLACE INTO quantity_policies VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    str(policy["policy_id"]),
                    str(policy["concept_key"]),
                    str(policy["source_bucket"]),
                    str(policy["include_regex"]),
                    str(policy["exclude_regex"]),
                    str(policy["action"]),
                    policy["default_grams"],
                    str(policy["rationale"]),
                )
                for policy in policies
            ],
        )
    conn.commit()
    return policies


def install_quantity_policy_functions(conn: sqlite3.Connection, policies: list[dict[str, object]]) -> None:
    compiled: list[dict[str, object]] = []
    for policy in policies:
        try:
            raw_include = str(policy["include_regex"]) if policy.get("include_regex") else ""
            include = re.compile(raw_include) if raw_include else None
            exclude = re.compile(str(policy["exclude_regex"])) if policy.get("exclude_regex") else None
        except re.error:
            continue
        compiled.append({**policy, "_include": include, "_exclude": exclude})

    def match_policy(concept_key: str | None, source_bucket: str | None, display: str | None, normalized_line: str | None) -> dict[str, object] | None:
        if not source_bucket:
            return None
        concept_key = normalize_concept_key(concept_key)
        text = f"{display or ''}\n{normalized_line or ''}"
        for policy in compiled:
            if policy["concept_key"] and policy["concept_key"] != concept_key:
                continue
            if policy["source_bucket"] != source_bucket:
                continue
            include = policy["_include"]
            exclude = policy["_exclude"]
            if (include is None or include.search(text)) and not (exclude and exclude.search(text)):
                return policy
        return None

    def quantity_policy_action(concept_key: str | None, source_bucket: str | None, display: str | None, normalized_line: str | None) -> str | None:
        policy = match_policy(concept_key, source_bucket, display, normalized_line)
        return str(policy["action"]) if policy else None

    def quantity_policy_default_grams(concept_key: str | None, source_bucket: str | None, display: str | None, normalized_line: str | None) -> float | None:
        policy = match_policy(concept_key, source_bucket, display, normalized_line)
        if not policy:
            return None
        grams = policy.get("default_grams")
        return float(grams) if grams is not None else None

    def quantity_policy_rationale(concept_key: str | None, source_bucket: str | None, display: str | None, normalized_line: str | None) -> str | None:
        policy = match_policy(concept_key, source_bucket, display, normalized_line)
        return str(policy["rationale"]) if policy else None

    conn.create_function("quantity_policy_action", 4, quantity_policy_action)
    conn.create_function("quantity_policy_default_grams", 4, quantity_policy_default_grams)
    conn.create_function("quantity_policy_rationale", 4, quantity_policy_rationale)


def install_split_default_nutrition_functions(conn: sqlite3.Connection) -> None:
    nutrition: dict[str, dict[str, float | str]] = {}
    for row in conn.execute(
        """
        SELECT
            concept_key,
            nutrition_status,
            calories_per_g,
            protein_g_per_g,
            fat_g_per_g,
            carbs_g_per_g,
            sodium_mg_per_g
        FROM product_nutrition
        """
    ):
        nutrition[str(row[0])] = {
            "nutrition_status": str(row[1] or ""),
            "calories": float(row[2] or 0),
            "protein": float(row[3] or 0),
            "fat": float(row[4] or 0),
            "carbs": float(row[5] or 0),
            "sodium": float(row[6] or 0),
        }
    defaults = {
        str(row[0]): float(row[1])
        for row in conn.execute("SELECT concept_key, default_grams FROM to_taste_defaults")
        if row[0] and row[1] is not None and float(row[1]) > 0
    }
    cache: dict[str, dict[str, float] | None] = {}

    def split_values(product_contract_key: str | None) -> dict[str, float] | None:
        key = str(product_contract_key or "").strip()
        if key in cache:
            return cache[key]
        parts = [part.strip() for part in key.split(";") if part.strip()]
        if len(parts) < 2:
            cache[key] = None
            return None
        totals = {"grams": 0.0, "calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "sodium": 0.0}
        for part in parts:
            grams = defaults.get(part)
            row = nutrition.get(part)
            if grams is None or row is None or row["nutrition_status"] not in READY_NUTRITION_STATUSES:
                cache[key] = None
                return None
            totals["grams"] += grams
            totals["calories"] += grams * float(row["calories"])
            totals["protein"] += grams * float(row["protein"])
            totals["fat"] += grams * float(row["fat"])
            totals["carbs"] += grams * float(row["carbs"])
            totals["sodium"] += grams * float(row["sodium"])
        cache[key] = totals
        return totals

    def split_default_ready(product_contract_key: str | None) -> int:
        return 1 if split_values(product_contract_key) is not None else 0

    def split_default_grams(product_contract_key: str | None) -> float | None:
        values = split_values(product_contract_key)
        return values["grams"] if values else None

    def split_default_nutrient(product_contract_key: str | None, nutrient: str | None) -> float | None:
        values = split_values(product_contract_key)
        name = str(nutrient or "")
        if not values or name not in values:
            return None
        return values[name]

    conn.create_function("split_default_ready", 1, split_default_ready)
    conn.create_function("split_default_grams", 1, split_default_grams)
    conn.create_function("split_default_nutrient", 2, split_default_nutrient)


def populate_household_unit_rules(conn: sqlite3.Connection, csv_path: Path) -> dict[tuple[str, str], dict[str, object]]:
    conn.execute("DROP TABLE IF EXISTS household_unit_rules")
    conn.execute(
        """
        CREATE TABLE household_unit_rules (
            rule_id TEXT PRIMARY KEY,
            concept_key TEXT NOT NULL,
            unit TEXT NOT NULL,
            grams_per_unit REAL NOT NULL,
            rationale TEXT
        )
        """
    )
    rules: dict[tuple[str, str], dict[str, object]] = {}
    rows: list[tuple[object, ...]] = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("review_status") != "approved":
                    continue
                rule_id = (row.get("rule_id") or "").strip()
                concept_key = normalize_concept_key(row.get("concept_key"))
                unit = normalize_household_unit(row.get("unit"))
                try:
                    grams_per_unit = float(row.get("grams_per_unit") or 0)
                except ValueError:
                    continue
                if not rule_id or not concept_key or not unit or grams_per_unit <= 0:
                    continue
                rationale = (row.get("rationale") or "").strip()
                rules[(concept_key, unit)] = {
                    "rule_id": rule_id,
                    "concept_key": concept_key,
                    "unit": unit,
                    "grams_per_unit": grams_per_unit,
                    "rationale": rationale,
                }
                rows.append((rule_id, concept_key, unit, grams_per_unit, rationale))
    if rows:
        conn.executemany("INSERT OR REPLACE INTO household_unit_rules VALUES (?,?,?,?,?)", rows)
    conn.commit()
    return rules


def clean_fdc_id(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.endswith(".0"):
        raw = raw[:-2]
    return raw if re.fullmatch(r"\d+", raw) else ""


def load_measure_units(csv_path: Path) -> dict[str, str]:
    units: dict[str, str] = {}
    if not csv_path.exists():
        return units
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            unit_id = (row.get("id") or "").strip()
            name = normalize_line(row.get("name"))
            if unit_id and name:
                units[unit_id] = name
    return units


def sr28_portion_unit(row: dict[str, str], measure_units: dict[str, str]) -> str:
    texts: list[str] = []
    measure_name = measure_units.get((row.get("measure_unit_id") or "").strip(), "")
    if measure_name and measure_name != "undetermined":
        texts.append(measure_name)
    texts.extend([row.get("modifier") or "", row.get("portion_description") or ""])
    unit_pattern = re.compile(
        r"\b("
        r"fluid\s+ounces?|fl\.?\s*oz\.?|"
        r"tablespoons?|tbsp\.?|tbs\.?|"
        r"teaspoons?|tsp\.?|"
        r"cups?|"
        r"ounces?|oz\.?|"
        r"pounds?|lbs?\.?|lb\.?|"
        r"cloves?|leaf|leaves|slices?|pieces?|sprigs?|stalks?|ribs?|rolls?|buns?|heads?|bunch(?:es)?|cans?|sticks?|pkgs?\.?|packages?|packets?|pods?|pitas?|rounds?|peppers?|potatoes?|"
        r"small|medium|large|rings?|strips?|pinches?|dashes?"
        r")\b"
    )
    for text in texts:
        normalized = normalize_line(text)
        match = unit_pattern.search(normalized)
        if match:
            return normalize_household_unit(match.group(1))
    return ""


def concept_fdc_ids_from_reviewed_sources(
    conn: sqlite3.Connection,
    *,
    sr28_fallback_csv: Path,
    external_catalog_csv: Path,
    nutrition_anchor_csv: Path,
) -> dict[str, str]:
    concept_to_fdc: dict[str, str] = {}
    try:
        for concept_key, fdc_id in conn.execute(
            """
            SELECT concept_key, sr28_fdc_id
            FROM product_nutrition
            WHERE sr28_fdc_id IS NOT NULL AND sr28_fdc_id != ''
            """
        ):
            cleaned = clean_fdc_id(fdc_id)
            if concept_key and cleaned:
                concept_to_fdc.setdefault(str(concept_key), cleaned)
    except sqlite3.OperationalError:
        pass

    reviewed_sources = [
        (sr28_fallback_csv, "fdc_id"),
        (external_catalog_csv, "fdc_id"),
        (nutrition_anchor_csv, "food_id"),
    ]
    for path, fdc_field in reviewed_sources:
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("review_status") != "approved":
                    continue
                concept_key = normalize_concept_key(row.get("concept_key"))
                fdc_id = clean_fdc_id(row.get(fdc_field))
                if concept_key and fdc_id:
                    concept_to_fdc.setdefault(concept_key, fdc_id)
    return concept_to_fdc


def add_sr28_portion_household_rules(
    conn: sqlite3.Connection,
    rules: dict[tuple[str, str], dict[str, object]],
    *,
    sr28_portion_csv: Path,
    sr28_measure_unit_csv: Path,
    sr28_fallback_csv: Path,
    external_catalog_csv: Path,
    nutrition_anchor_csv: Path,
) -> int:
    if not sr28_portion_csv.exists():
        return 0
    concept_to_fdc = concept_fdc_ids_from_reviewed_sources(
        conn,
        sr28_fallback_csv=sr28_fallback_csv,
        external_catalog_csv=external_catalog_csv,
        nutrition_anchor_csv=nutrition_anchor_csv,
    )
    if not concept_to_fdc:
        return 0
    concepts_by_fdc: dict[str, list[str]] = {}
    for concept_key, fdc_id in concept_to_fdc.items():
        concepts_by_fdc.setdefault(fdc_id, []).append(concept_key)
    measure_units = load_measure_units(sr28_measure_unit_csv)
    candidates: dict[tuple[str, str], list[float]] = {}
    form_candidates: dict[tuple[str, str, str], list[float]] = {}
    conn.execute("DROP TABLE IF EXISTS sr28_household_unit_form_rules")
    conn.execute(
        """
        CREATE TABLE sr28_household_unit_form_rules (
            rule_id TEXT PRIMARY KEY,
            concept_key TEXT NOT NULL,
            unit TEXT NOT NULL,
            form TEXT NOT NULL,
            grams_per_unit REAL NOT NULL,
            rationale TEXT
        )
        """
    )

    with sr28_portion_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            fdc_id = clean_fdc_id(row.get("fdc_id"))
            if fdc_id not in concepts_by_fdc:
                continue
            unit = sr28_portion_unit(row, measure_units)
            if not unit:
                continue
            try:
                amount = float(row.get("amount") or 0)
                gram_weight = float(row.get("gram_weight") or 0)
            except ValueError:
                continue
            if amount <= 0 or gram_weight <= 0:
                continue
            grams_per_unit = gram_weight / amount
            row_forms = portion_forms(" ".join([row.get("modifier") or "", row.get("portion_description") or ""]))
            for concept_key in concepts_by_fdc[fdc_id]:
                concept_forms = portion_forms(concept_key.replace("|", " "))
                if row_forms:
                    if concept_forms and not (row_forms & concept_forms):
                        continue
                    for form in row_forms:
                        form_candidates.setdefault((concept_key, unit, form), []).append(grams_per_unit)
                candidates.setdefault((concept_key, unit), []).append(grams_per_unit)

    for (concept_key, unit), grams_values in list(candidates.items()):
        rounded = {round(value, 3) for value in grams_values}
        if len(rounded) != 1:
            continue
        grams_per_unit = grams_values[0]
        if unit == "cup":
            candidates.setdefault((concept_key, "tbsp"), [grams_per_unit / 16.0])
            candidates.setdefault((concept_key, "tsp"), [grams_per_unit / 48.0])
            candidates.setdefault((concept_key, "fl oz"), [grams_per_unit / 8.0])
            candidates.setdefault((concept_key, "pint"), [grams_per_unit * 2.0])
            candidates.setdefault((concept_key, "quart"), [grams_per_unit * 4.0])
            candidates.setdefault((concept_key, "gallon"), [grams_per_unit * 16.0])
        elif unit == "tbsp":
            candidates.setdefault((concept_key, "tsp"), [grams_per_unit / 3.0])
            candidates.setdefault((concept_key, "cup"), [grams_per_unit * 16.0])
            candidates.setdefault((concept_key, "fl oz"), [grams_per_unit * 2.0])
        elif unit == "tsp":
            candidates.setdefault((concept_key, "tbsp"), [grams_per_unit * 3.0])
        elif unit == "fl oz":
            candidates.setdefault((concept_key, "tbsp"), [grams_per_unit / 2.0])
            candidates.setdefault((concept_key, "tsp"), [grams_per_unit / 6.0])
            candidates.setdefault((concept_key, "cup"), [grams_per_unit * 8.0])
            candidates.setdefault((concept_key, "pint"), [grams_per_unit * 16.0])
            candidates.setdefault((concept_key, "quart"), [grams_per_unit * 32.0])
            candidates.setdefault((concept_key, "gallon"), [grams_per_unit * 128.0])
        elif unit == "pint":
            candidates.setdefault((concept_key, "cup"), [grams_per_unit / 2.0])
            candidates.setdefault((concept_key, "fl oz"), [grams_per_unit / 16.0])
        elif unit == "quart":
            candidates.setdefault((concept_key, "cup"), [grams_per_unit / 4.0])
            candidates.setdefault((concept_key, "pint"), [grams_per_unit / 2.0])
            candidates.setdefault((concept_key, "fl oz"), [grams_per_unit / 32.0])
        elif unit == "gallon":
            candidates.setdefault((concept_key, "cup"), [grams_per_unit / 16.0])
            candidates.setdefault((concept_key, "quart"), [grams_per_unit / 4.0])
            candidates.setdefault((concept_key, "pint"), [grams_per_unit / 8.0])
            candidates.setdefault((concept_key, "fl oz"), [grams_per_unit / 128.0])

    rows: list[tuple[object, ...]] = []
    for (concept_key, unit), grams_values in sorted(candidates.items()):
        rounded = {round(value, 3) for value in grams_values}
        if len(rounded) != 1:
            continue
        if (concept_key, unit) in rules:
            continue
        grams_per_unit = grams_values[0]
        fdc_id = concept_to_fdc[concept_key]
        digest = hashlib.sha1(f"{concept_key}|{unit}|{fdc_id}".encode("utf-8")).hexdigest()[:10]
        rule_id = f"sr28_portion_{fdc_id}_{unit.replace(' ', '_')}_{digest}"
        rationale = f"SR28 food_portion conversion from FDC {fdc_id}."
        rule = {
            "rule_id": rule_id,
            "concept_key": concept_key,
            "unit": unit,
            "grams_per_unit": grams_per_unit,
            "rationale": rationale,
        }
        rules[(concept_key, unit)] = rule
        rows.append((rule_id, concept_key, unit, grams_per_unit, rationale))
    if rows:
        conn.executemany("INSERT OR REPLACE INTO household_unit_rules VALUES (?,?,?,?,?)", rows)
        conn.commit()
    form_rows: list[tuple[object, ...]] = []
    for (concept_key, unit, form), grams_values in sorted(form_candidates.items()):
        rounded = {round(value, 3) for value in grams_values}
        if len(rounded) != 1:
            continue
        if (concept_key, unit) in rules:
            continue
        grams_per_unit = grams_values[0]
        fdc_id = concept_to_fdc[concept_key]
        digest = hashlib.sha1(f"{concept_key}|{unit}|{form}|{fdc_id}".encode("utf-8")).hexdigest()[:10]
        rule_id = f"sr28_portion_form_{fdc_id}_{unit.replace(' ', '_')}_{form}_{digest}"
        rationale = f"SR28 food_portion {form} conversion from FDC {fdc_id}."
        form_rows.append((rule_id, concept_key, unit, form, grams_per_unit, rationale))
    if form_rows:
        conn.executemany("INSERT OR REPLACE INTO sr28_household_unit_form_rules VALUES (?,?,?,?,?,?)", form_rows)
        conn.commit()
    return len(rows) + len(form_rows)


def install_household_unit_functions(conn: sqlite3.Connection, rules: dict[tuple[str, str], dict[str, object]]) -> None:
    form_rules: dict[tuple[str, str, str], dict[str, object]] = {}
    try:
        for row in conn.execute(
            """
            SELECT rule_id, concept_key, unit, form, grams_per_unit, rationale
            FROM sr28_household_unit_form_rules
            """
        ):
            form_rules[(str(row[1]), str(row[2]), str(row[3]))] = {
                "rule_id": row[0],
                "concept_key": row[1],
                "unit": row[2],
                "form": row[3],
                "grams_per_unit": row[4],
                "rationale": row[5],
            }
    except sqlite3.OperationalError:
        form_rules = {}

    def match_rule(concept_key: str | None, parsed_unit: str | None) -> dict[str, object] | None:
        unit = normalize_household_unit(parsed_unit)
        if not unit:
            return None
        concept_key = normalize_concept_key(concept_key)
        if concept_key:
            rule = rules.get((concept_key, unit))
            if rule:
                return rule
        return rules.get(("*", unit))

    def match_form_rule(concept_key: str | None, parsed_unit: str | None, display: str | None) -> dict[str, object] | None:
        concept_key = normalize_concept_key(concept_key)
        if not concept_key:
            return None
        unit = normalize_household_unit(parsed_unit)
        if not unit:
            return None
        for form in portion_forms(display or ""):
            rule = form_rules.get((concept_key, unit, form))
            if rule:
                return rule
        return None

    def household_unit_grams(concept_key: str | None, parsed_quantity: str | None, parsed_unit: str | None) -> float | None:
        quantity = parse_quantity_value(parsed_quantity)
        if quantity is None or quantity <= 0:
            return None
        rule = match_rule(concept_key, parsed_unit)
        if not rule:
            return None
        grams = float(rule["grams_per_unit"]) * quantity
        return grams if grams > 0 else None

    def household_unit_rationale(concept_key: str | None, parsed_unit: str | None) -> str | None:
        rule = match_rule(concept_key, parsed_unit)
        return str(rule["rationale"]) if rule else None

    def sr28_display_household_grams(
        concept_key: str | None,
        parsed_quantity: str | None,
        parsed_unit: str | None,
        display: str | None,
    ) -> float | None:
        quantity = parse_quantity_value(parsed_quantity)
        if quantity is None or quantity <= 0:
            return None
        rule = match_form_rule(concept_key, parsed_unit, display)
        if not rule:
            return None
        return quantity * float(rule["grams_per_unit"])

    def sr28_display_household_rationale(
        concept_key: str | None,
        parsed_unit: str | None,
        display: str | None,
    ) -> str | None:
        rule = match_form_rule(concept_key, parsed_unit, display)
        return str(rule["rationale"]) if rule else None

    def mass_unit_grams(parsed_quantity: str | None, parsed_unit: str | None) -> float | None:
        quantity = parse_quantity_value(parsed_quantity)
        if quantity is None or quantity <= 0:
            return None
        factor = MASS_UNIT_GRAMS.get(normalize_household_unit(parsed_unit))
        if factor is None:
            return None
        return quantity * factor

    def density_volume_unit_grams(
        parsed_quantity: str | None,
        parsed_unit: str | None,
        density_g_per_ml: float | None,
    ) -> float | None:
        quantity = parse_quantity_value(parsed_quantity)
        if quantity is None or quantity <= 0:
            return None
        try:
            density = float(density_g_per_ml or 0)
        except (TypeError, ValueError):
            return None
        if density <= 0:
            return None
        ml = VOLUME_UNIT_ML.get(normalize_household_unit(parsed_unit))
        if ml is None:
            return None
        return quantity * ml * density

    conn.create_function("household_unit_grams", 3, household_unit_grams)
    conn.create_function("household_unit_rationale", 2, household_unit_rationale)
    conn.create_function("sr28_display_household_grams", 4, sr28_display_household_grams)
    conn.create_function("sr28_display_household_rationale", 3, sr28_display_household_rationale)
    conn.create_function("mass_unit_grams", 2, mass_unit_grams)
    conn.create_function("density_volume_unit_grams", 3, density_volume_unit_grams)


def install_display_parse_functions(conn: sqlite3.Connection) -> None:
    cache: dict[str, dict[str, str]] = {}
    removable_prefixes = {
        "very",
        "thin",
        "thinly",
        "loosely",
        "petite",
        "yellow-flesh",
        "finely",
        "coarsely",
        "cut",
        "minced",
        "snipped",
        "chopped",
        "diced",
        "slices",
        "sliced",
        "shredded",
        "grated",
        "julienne",
        "julienned",
        "packed",
        "pureed",
        "crisp",
        "fresh",
        "drained",
        "chilled",
        "seedless",
        "pared",
        "strips",
        "strip",
        "up",
    }
    fresh_state_preserve_heads = {
        "basil",
        "cilantro",
        "coriander",
        "dill",
        "ginger",
        "mint",
        "oregano",
        "parsley",
        "rosemary",
        "sage",
        "tarragon",
        "thyme",
    }

    def parsed(display: str | None) -> dict[str, str]:
        text = display or ""
        cached = cache.get(text)
        if cached is not None:
            return cached
        try:
            result = parse_recipe_line(text)
        except Exception:
            result = {}
        parsed_unit = str(result.get("parsed_unit") or "")
        parsed_quantity = str(result.get("parsed_quantity") or "")
        surface = normalize_line(result.get("cleaned_surface") or "")
        food_phrase = normalize_line(result.get("parsed_food_phrase") or surface)
        normalized_display = normalize_line(text)
        labeled_quantity_match = re.match(
            r"^(?:[a-z][a-z\s'-]{0,60}\s+)?(?:dressing|croutons|salad|starter|custard|filling|sauce):\s*"
            r"(?P<body>.+)$",
            normalized_display,
        )
        if labeled_quantity_match and re.match(r"^\d", labeled_quantity_match.group("body")):
            normalized_display = labeled_quantity_match.group("body")
        labeled_dash_quantity_match = re.match(
            r"^(?:[a-z][a-z\s'-]{0,60}\s+)?(?:dressing|croutons|salad|starter|custard|filling|sauce)\s+-\s*(?P<body>\d.+)$",
            normalized_display,
        )
        if labeled_dash_quantity_match:
            normalized_display = labeled_dash_quantity_match.group("body")
        display_unit_pattern = (
            r"cups?|tbsp\.?|tablespoons?|tbs\.?|tsp\.?|teaspoons?|in\.?|inch(?:es)?|"
            r"slices?|pieces?|fillets?|packets?|punnets?|pods?|ears?|blossoms?|"
            r"dashes?|pinches?|small|medium|large|loaves?|bottles?|cans?|heads?|"
            r"bunch(?:es)?|sprigs?|stalks?|ribs?|rings?"
        )
        display_quantity_pattern = (
            r"(?:\d+(?:\s+\d+\s*[/⁄]\s*\d+|\s*[/⁄]\s*\d+|\.\d+)?|"
            r"\d+\s*(?:-|to)\s*\d+)"
        )
        leading_quantity_match = re.match(
            rf"^(?:[-–—]\s*)?(?P<quantity>{display_quantity_pattern})\s+"
            rf"(?P<unit>{display_unit_pattern})\s+(?P<surface>.+)$",
            normalized_display,
        )
        if leading_quantity_match:
            parsed_quantity = leading_quantity_match.group("quantity")
            parsed_unit = leading_quantity_match.group("unit")
            surface = leading_quantity_match.group("surface")
            food_phrase = surface
            odd_bulgur_match = re.match(
                r"lb\s+2\s+medium\s+or\s+#\s*3\s+coarse\s+(?P<surface>bulgur\s+wheat)(?:\s+or\b.*)?$",
                surface,
            )
            if odd_bulgur_match:
                surface = odd_bulgur_match.group("surface")
                food_phrase = surface
        elif not parsed_unit:
            trailing_quantity_match = re.match(
                rf"^(?P<surface>[a-z][a-z\s'-]+?),\s*"
                rf"(?P<quantity>{display_quantity_pattern})\s+"
                rf"(?P<unit>{display_unit_pattern})(?:\b.*)?$",
                normalized_display,
            )
            if trailing_quantity_match:
                parsed_quantity = trailing_quantity_match.group("quantity")
                parsed_unit = trailing_quantity_match.group("unit")
                surface = trailing_quantity_match.group("surface")
                food_phrase = surface
        if not parsed_unit:
            parenthetical_mass_match = re.search(
                r"\(\s*(?:about\s+|approx(?:imately)?\.?\s+)?"
                r"(?P<quantity>\d+(?:-\d+[/⁄]\d+|\s+\d+\s*[/⁄]\s*\d+|\s*[/⁄]\s*\d+|\.\d+)?)\s+"
                r"(?P<unit>pounds?|lbs?\.?|ounces?|oz\.?)\b",
                normalized_display,
            )
            if parenthetical_mass_match:
                parsed_quantity = parenthetical_mass_match.group("quantity")
                parsed_unit = parenthetical_mass_match.group("unit")
        if not parsed_unit:
            quantity_variants = [
                parsed_quantity.strip(),
                normalize_line(parsed_quantity),
            ]
            for quantity_value in dict.fromkeys(value for value in quantity_variants if value):
                unit_match = re.match(
                    rf"^{re.escape(quantity_value)}\s+"
                    r"(slices?|pieces?|fillets?|packets?|punnets?|pods?|ears?|blossoms?|dashes?|pinches?)\s+(.+)$",
                    normalized_display,
                )
                if unit_match:
                    parsed_unit = unit_match.group(1)
                    surface = unit_match.group(2)
                    food_phrase = surface
                    break
        if not parsed_unit:
            first_word = food_phrase.split(" ", 1)[0] if food_phrase else ""
            if first_word in {"small", "medium", "large"}:
                parsed_unit = first_word
                surface = food_phrase.split(" ", 1)[1] if " " in food_phrase else surface
        if parsed_unit in {"small", "medium", "large"} and food_phrase:
            clove_match = re.search(r"\s+cloves?(?:,.*)?$", food_phrase)
            if clove_match:
                parsed_unit = "clove"
                surface = food_phrase[: clove_match.start()]
        if not parsed_unit and food_phrase:
            for suffix_pattern, unit in (
                (r"\s+slices?(?:,.*)?$", "slice"),
                (r"\s+pieces?(?:,.*)?$", "piece"),
                (r"\s+rounds?(?:,.*)?$", "round"),
                (r"\s+ribs?(?:,.*)?$", "rib"),
            ):
                suffix_match = re.search(suffix_pattern, food_phrase)
                if suffix_match:
                    parsed_unit = unit
                    surface = food_phrase[: suffix_match.start()]
                    break
        surface = re.sub(r"\s*\([^)]*\)", " ", surface)
        surface = surface.split(" or ", 1)[0]
        surface = surface.split(",", 1)[0]
        surface = normalize_line(surface)
        while True:
            parts = surface.split(" ", 1)
            if parts and parts[0] in removable_prefixes and len(parts) > 1:
                if parts[0] == "fresh":
                    head = parts[1].split(" ", 1)[0]
                    if head in fresh_state_preserve_heads:
                        break
                surface = parts[1]
                continue
            break
        if not parsed_unit and surface.endswith(" leaves"):
            parsed_unit = "count"
        if not parsed_unit and surface.endswith(" blossoms"):
            parsed_unit = "blossom"
        parsed_result = {
            "parsed_quantity": parsed_quantity,
            "parsed_unit": parsed_unit,
            "cleaned_surface": surface,
        }
        cache[text] = parsed_result
        return parsed_result

    def parsed_display_quantity(display: str | None) -> str | None:
        return parsed(display).get("parsed_quantity") or None

    def parsed_display_unit(display: str | None) -> str | None:
        return parsed(display).get("parsed_unit") or None

    def parsed_display_surface(display: str | None) -> str | None:
        return parsed(display).get("cleaned_surface") or None

    conn.create_function("parsed_display_quantity", 1, parsed_display_quantity)
    conn.create_function("parsed_display_unit", 1, parsed_display_unit)
    conn.create_function("parsed_display_surface", 1, parsed_display_surface)


ITEM_FALLBACK_BLOCKED_ACTIONS = frozenset({
    "true_alternative_review",
    "component_split_review",
    "approved_alternative_options",
    "approved_split",
})

ITEM_FALLBACK_ALWAYS_TRUSTED_SOURCES = frozenset({
    "approved_normalization_exact",
    "approved_normalization_regex",
    "approved_normalization_reject",
    "normalized_item_bridge",
    "recipe_line_patch_item",
    "approved_normalization_split",
    "reviewed_sr28_surface",
})


def bridge_failure_bucket(product_contract_status: str) -> str:
    if product_contract_status == "contract_passed":
        return "calculation_candidate"
    if product_contract_status == "contract_failed":
        return "product_contract_failed"
    if product_contract_status == "contract_missing":
        return "product_contract_missing"
    if product_contract_status == "not_candidate_covered":
        return "product_not_candidate_covered"
    if product_contract_status == "not_in_audit_scope":
        return "product_not_in_audit_scope"
    return "product_unknown"


def build_item_fallback_lookup(
    conn: sqlite3.Connection,
    normalized_item_bridge_csv: Path | None = None,
    recipe_line_patches_csv: Path | None = DEFAULT_RECIPE_LINE_PATCHES_CSV,
    sr28_fallback_csv: Path | None = DEFAULT_SR28_FALLBACK_CSV,
    approved_rules_csv: Path | None = DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
) -> int:
    """Build item -> concept lookup, preferring the normalized-item bridge.

    The bridge is deliberately first. If ``r.item`` is a reviewed normalized item
    like ``unsalted butter``, it should not wait for line parsing to fail before
    resolving. The old line_eval fallback remains as second priority for items
    not yet present in the bridge.
    """
    conn.execute("DROP TABLE IF EXISTS normalized_item_bridge_source")
    conn.execute(
        """
        CREATE TABLE normalized_item_bridge_source (
            cleaned_surface TEXT PRIMARY KEY,
            concept_key TEXT NOT NULL,
            product_contract_key TEXT NOT NULL,
            product_audit_status TEXT NOT NULL,
            product_policy TEXT NOT NULL,
            dictionary_match_status TEXT NOT NULL,
            resolution_action TEXT NOT NULL,
            failure_bucket TEXT NOT NULL,
            is_concept_mapped INTEGER NOT NULL,
            parsed_quantity TEXT,
            parsed_unit TEXT,
            quantity_bucket TEXT NOT NULL,
            recipe_count INTEGER NOT NULL,
            lookup_source TEXT NOT NULL,
            priority INTEGER NOT NULL
        )
        """
    )
    bridge_rows: list[tuple[object, ...]] = []
    if normalized_item_bridge_csv is not None and normalized_item_bridge_csv.exists():
        with normalized_item_bridge_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("bridge_status") != "concept_ready":
                    continue
                concept_key = normalize_concept_key(row.get("canonical_concept_key"))
                if not concept_key or concept_key == "|||" or ";" in concept_key:
                    continue
                product_contract_key = normalize_concept_key_list(row.get("product_contract_key")) or concept_key
                product_status = (row.get("product_contract_status") or "").strip()
                bridge_rows.append(
                    (
                        normalize_line(row.get("normalized_item")),
                        concept_key,
                        product_contract_key,
                        product_status,
                        "",
                        "normalized_item_bridge_match",
                        "item_bridge_match",
                        bridge_failure_bucket(product_status),
                        1,
                        None,
                        None,
                        "",
                        int(row.get("occurrence_count") or 0),
                        "normalized_item_bridge",
                        2,
                    )
                )
    if bridge_rows:
        conn.executemany("INSERT OR REPLACE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", bridge_rows)

    patch_item_rows: list[tuple[object, ...]] = []
    patch_items = Counter()
    for patch in load_recipe_line_patches(recipe_line_patches_csv).values():
        new_item = normalize_line(str(patch.get("new_item") or ""))
        if new_item:
            patch_items[new_item] += 1
    if patch_items:
        resolver = NormalizedItemBridgeResolver(
            DEFAULT_ARTIFACTS.dictionary_csv,
            DEFAULT_ARTIFACTS.supplemental_concepts_csv,
            DEFAULT_ARTIFACTS.approved_normalization_rules_csv,
            DEFAULT_ARTIFACTS.product_contract_audit_csv,
        )
        for item, occurrence_count in patch_items.items():
            row = resolver.resolve(item, occurrence_count)
            if row.get("bridge_status") != "concept_ready":
                continue
            concept_key = normalize_concept_key(row.get("canonical_concept_key"))
            if not concept_key or concept_key == "|||" or ";" in concept_key:
                continue
            product_contract_key = normalize_concept_key_list(row.get("product_contract_key")) or concept_key
            product_status = (row.get("product_contract_status") or "").strip()
            patch_item_rows.append(
                (
                    item,
                    concept_key,
                    product_contract_key,
                    product_status,
                    "",
                    "recipe_line_patch_item_bridge_match",
                    "recipe_line_patch_item_bridge_match",
                    bridge_failure_bucket(product_status),
                    1,
                    None,
                    None,
                    "",
                    occurrence_count,
                    "recipe_line_patch_item",
                    3,
                )
            )
    if patch_item_rows:
        conn.executemany("INSERT OR REPLACE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", patch_item_rows)

    sr28_surface_rows: list[tuple[object, ...]] = []
    if sr28_fallback_csv is not None and sr28_fallback_csv.exists():
        with sr28_fallback_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("review_status") != "approved":
                    continue
                concept_key = normalize_concept_key(row.get("concept_key"))
                parts = (concept_key.split("|") + ["", "", "", ""])[:4]
                if not concept_key or not parts[0] or any(parts[1:]):
                    continue
                sr28_surface_rows.append(
                    (
                        normalize_line(parts[0]),
                        concept_key,
                        concept_key,
                        "not_candidate_covered",
                        "sr28_nutrition_only",
                        "reviewed_sr28_surface_match",
                        "reviewed_sr28_surface_match",
                        "product_not_candidate_covered",
                        1,
                        None,
                        None,
                        "",
                        0,
                        "reviewed_sr28_surface",
                        4,
                    )
                )
    if sr28_surface_rows:
        conn.executemany("INSERT OR REPLACE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sr28_surface_rows)

    has_recipe_qa_ingredients = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='recipe_qa_ingredients'"
    ).fetchone()[0]
    current_item_surfaces = Counter()
    current_item_parsed_surfaces: dict[str, str] = {}
    if has_recipe_qa_ingredients:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(recipe_qa_ingredients)").fetchall()
        }
        if "display" in columns:
            for item, display, count in conn.execute(
                "SELECT item, display, COUNT(*) FROM recipe_qa_ingredients GROUP BY item, display"
            ):
                surface = normalize_line(item)
                if surface:
                    current_item_surfaces[surface] += count
                if surface and surface == normalize_line(display):
                    try:
                        parsed_surface = conn.execute(
                            "SELECT parsed_display_surface(?)",
                            (display,),
                        ).fetchone()[0]
                    except sqlite3.OperationalError:
                        parsed_surface = None
                    parsed_surface = normalize_line(parsed_surface)
                    if parsed_surface and parsed_surface != surface:
                        current_item_surfaces[parsed_surface] += count
                        current_item_parsed_surfaces[surface] = parsed_surface
        else:
            item_rows = conn.execute("SELECT item, COUNT(*) FROM recipe_qa_ingredients GROUP BY item")
            for item, count in item_rows:
                surface = normalize_line(item)
                if surface:
                    current_item_surfaces[surface] += count
    approved_alias_rows: list[tuple[object, ...]] = []
    approved_reject_rows: list[tuple[object, ...]] = []
    approved_dirty_alias_rows: list[tuple[object, ...]] = []
    approved_dirty_reject_rows: list[tuple[object, ...]] = []
    if current_item_surfaces and approved_rules_csv is not None and approved_rules_csv.exists():
        approved_rules = load_approved_normalization_rules(approved_rules_csv)
        for surface, recipe_count in current_item_surfaces.items():
            row = approved_rule_for_surface(surface, approved_rules)
            if not row:
                continue
            rule_type = row.get("rule_type")
            if rule_type not in {"alias", "manual_quantity", "reject"}:
                continue
            match_type = row.get("match_type") or "exact"
            if rule_type == "reject":
                concept_key = ""
                source = "approved_normalization_reject"
                action = "approved_normalization_reject_match"
                product_status = "contract_passed"
                product_policy = "no_buy"
                failure_bucket = "intentional_skip"
            else:
                concept_key = normalize_concept_key(row.get("canonical_concept_key"))
                if not concept_key or concept_key == "|||" or ";" in concept_key:
                    continue
                source = "approved_normalization_regex" if match_type == "regex" else "approved_normalization_exact"
                action = f"{source}_match"
                product_status = "not_candidate_covered"
                product_policy = "sr28_nutrition_only"
                failure_bucket = "product_not_candidate_covered"
            rule_row = (
                surface,
                concept_key,
                concept_key,
                product_status,
                product_policy,
                action,
                action,
                failure_bucket,
                1,
                None,
                None,
                "",
                recipe_count,
                source,
                6,
            )
            if rule_type == "reject":
                approved_reject_rows.append(rule_row)
            else:
                approved_alias_rows.append(rule_row)
        for dirty_surface, parsed_surface in current_item_parsed_surfaces.items():
            row = approved_rule_for_surface(parsed_surface, approved_rules)
            if not row:
                continue
            rule_type = row.get("rule_type")
            if rule_type not in {"alias", "manual_quantity", "reject"}:
                continue
            match_type = row.get("match_type") or "exact"
            if rule_type == "reject":
                concept_key = ""
                source = "approved_normalization_reject"
                action = "approved_normalization_reject_match"
                product_status = "contract_passed"
                product_policy = "no_buy"
                failure_bucket = "intentional_skip"
            else:
                concept_key = normalize_concept_key(row.get("canonical_concept_key"))
                if not concept_key or concept_key == "|||" or ";" in concept_key:
                    continue
                source = "approved_normalization_regex" if match_type == "regex" else "approved_normalization_exact"
                action = f"{source}_match"
                product_status = "not_candidate_covered"
                product_policy = "sr28_nutrition_only"
                failure_bucket = "product_not_candidate_covered"
            rule_row = (
                dirty_surface,
                concept_key,
                concept_key,
                product_status,
                product_policy,
                action,
                action,
                failure_bucket,
                1,
                None,
                None,
                "",
                current_item_surfaces.get(dirty_surface, 0),
                source,
                6,
            )
            if rule_type == "reject":
                approved_dirty_reject_rows.append(rule_row)
            else:
                approved_dirty_alias_rows.append(rule_row)
    if approved_alias_rows:
        conn.executemany("INSERT OR IGNORE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", approved_alias_rows)
    if approved_reject_rows:
        conn.executemany("INSERT OR REPLACE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", approved_reject_rows)
    if approved_dirty_alias_rows:
        conn.executemany("INSERT OR REPLACE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", approved_dirty_alias_rows)
    if approved_dirty_reject_rows:
        conn.executemany("INSERT OR REPLACE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", approved_dirty_reject_rows)

    split_rule_rows: list[tuple[object, ...]] = []
    if approved_rules_csv is not None and approved_rules_csv.exists():
        with approved_rules_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") != "approved":
                    continue
                if row.get("rule_type") != "split" or row.get("match_type") != "exact":
                    continue
                surface = normalize_line(row.get("input_surface"))
                components = (row.get("components") or "").strip()
                if not surface or not components or ";" not in components:
                    continue
                split_rule_rows.append(
                    (
                        surface,
                        "",
                        components,
                        "contract_passed",
                        "",
                        "approved_normalization_split_match",
                        "approved_split",
                        "calculation_candidate",
                        1,
                        None,
                        None,
                        "",
                        0,
                        "approved_normalization_split",
                        5,
                    )
                )
    if split_rule_rows:
        conn.executemany("INSERT OR IGNORE INTO normalized_item_bridge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", split_rule_rows)

    conn.execute("DROP TABLE IF EXISTS item_fallback_lookup")
    conn.execute(
        """
        CREATE TABLE item_fallback_lookup AS
        SELECT
            cleaned_surface,
            concept_key,
            product_contract_key,
            product_audit_status,
            product_policy,
            dictionary_match_status,
            resolution_action,
            failure_bucket,
            is_concept_mapped,
            parsed_quantity,
            parsed_unit,
            quantity_bucket,
            lookup_source
        FROM (
            SELECT
                source.cleaned_surface,
                source.concept_key,
                source.product_contract_key,
                source.product_audit_status,
                source.product_policy,
                source.dictionary_match_status,
                source.resolution_action,
                source.failure_bucket,
                source.is_concept_mapped,
                source.parsed_quantity,
                source.parsed_unit,
                source.quantity_bucket,
                source.lookup_source,
                ROW_NUMBER() OVER (
                    PARTITION BY source.cleaned_surface
                    ORDER BY source.priority DESC, source.is_concept_mapped DESC, source.recipe_count DESC
                ) AS rn
            FROM (
                SELECT * FROM normalized_item_bridge_source
                UNION ALL
                SELECT
                    le.cleaned_surface,
                    le.concept_key,
                    le.product_contract_key,
                    le.product_audit_status,
                    le.product_policy,
                    le.dictionary_match_status,
                    le.resolution_action,
                    le.failure_bucket,
                    le.is_concept_mapped,
                    le.parsed_quantity,
                    le.parsed_unit,
                    le.quantity_bucket,
                    le.recipe_count,
                    'line_eval_cleaned_surface',
                    1
                FROM line_audit.line_eval le
                WHERE le.is_concept_mapped = 1
                  AND le.concept_key IS NOT NULL
                  AND le.concept_key != ''
                  AND le.concept_key != '|||'
                  AND le.resolution_action NOT IN ('true_alternative_review', 'component_split_review',
                                                    'approved_alternative_options', 'approved_split')
            ) source
        )
        WHERE rn = 1
        """
    )
    conn.execute("CREATE UNIQUE INDEX idx_item_fallback_surface ON item_fallback_lookup(cleaned_surface)")
    count = conn.execute("SELECT COUNT(*) FROM item_fallback_lookup").fetchone()[0]
    conn.commit()
    return count


def build_ingredient_eval(conn: sqlite3.Connection) -> None:
    conn.create_function("canonical_concept_key", 1, normalize_concept_key)
    conn.create_function("canonical_concept_key_list", 1, normalize_concept_key_list)
    ready_status_sql = "'nutrition_ready_g', 'nutrition_ready_ml_density', 'nutrition_ready_sr28_anchor', 'nutrition_ready_sr28_fallback', 'nutrition_ready_fndds_anchor', 'nutrition_ready_branded_fdc_proxy', 'nutrition_ready_external_catalog', 'nutrition_ready_split_to_taste_defaults'"
    external_catalog_bucket_sql = ", ".join(f"'{bucket}'" for bucket in EXTERNAL_CATALOG_FALLBACK_BUCKETS)
    trusted_item_source_sql = ", ".join(f"'{source}'" for source in sorted(ITEM_FALLBACK_ALWAYS_TRUSTED_SOURCES))
    # DRY: the item-field fallback condition used in multiple CASE expressions
    ifl_cond = f"""ifl.is_concept_mapped = 1
                         AND (
                             ifl.lookup_source IN ({trusted_item_source_sql})
                             OR
                             LOWER(TRIM(r.item)) = LOWER(TRIM(r.display))
                             OR (
                                 r.item NOT LIKE '%% or %%'
                                 AND r.item NOT LIKE '%% and %%'
                             )
                         )
                         AND (
                             ifl.lookup_source IN ({trusted_item_source_sql})
                             OR (
                                 (
                                     le.concept_key IS NULL
                                     OR le.concept_key = ''
                                     OR le.concept_key = '|||'
                                     OR COALESCE(le.failure_bucket, '') = 'concept_unresolved'
                                 )
                                 AND (
                                     COALESCE(le.resolution_action, '') IN ('', 'promotion_review_needed', 'parser_fragment_review', 'parser_review_needed', 'true_alternative_review')
                                     OR (
                                         COALESCE(le.resolution_action, '') = 'component_split_review'
                                         AND (
                                             (
                                                 LOWER(TRIM(r.item)) != LOWER(TRIM(r.display))
                                                 AND r.item NOT LIKE '%% or %%'
                                                 AND r.item NOT LIKE '%% and %%'
                                             )
                                             OR (
                                                 parsed_display_surface(r.display) NOT LIKE '%% and %%'
                                                 AND parsed_display_surface(r.display) NOT LIKE '%% or %%'
                                                 AND LOWER(TRIM(r.display)) NOT LIKE '%% or %%'
                                             )
                                         )
                                     )
                                 )
                             )
                         )"""
    # Effective concept_key: fallback to ifl when condition met
    eff_ck = f"canonical_concept_key(CASE WHEN {ifl_cond} THEN ifl.concept_key ELSE le.concept_key END)"
    # Effective product_contract_key: split rules carry component keys here while concept_key stays empty.
    eff_pck = f"""canonical_concept_key_list(CASE
                    WHEN {ifl_cond}
                    THEN COALESCE(NULLIF(ifl.product_contract_key, ''), ifl.concept_key, '')
                    ELSE COALESCE(NULLIF(le.product_contract_key, ''), le.concept_key, '')
                END)"""
    quantity_key = f"""CASE
                    WHEN (({eff_ck}) IS NULL OR ({eff_ck}) = '' OR ({eff_ck}) = '|||')
                         AND instr(({eff_pck}), ';') > 0
                    THEN ({eff_pck})
                    ELSE ({eff_ck})
                END"""
    # Effective failure_bucket: fallback to ifl when condition met
    eff_fb = f"CASE WHEN {ifl_cond} THEN ifl.failure_bucket ELSE le.failure_bucket END"
    parsed_qty = f"""CASE
                    WHEN {ifl_cond}
                    THEN COALESCE(parsed_display_quantity(r.display), NULLIF(ifl.parsed_quantity, ''), NULLIF(le.parsed_quantity, ''))
                    ELSE COALESCE(NULLIF(le.parsed_quantity, ''), NULLIF(ifl.parsed_quantity, ''), parsed_display_quantity(r.display))
                END"""
    parsed_unit = f"""CASE
                    WHEN {ifl_cond}
                    THEN COALESCE(parsed_display_unit(r.display), NULLIF(ifl.parsed_unit, ''), NULLIF(le.parsed_unit, ''))
                    ELSE COALESCE(NULLIF(le.parsed_unit, ''), NULLIF(ifl.parsed_unit, ''), parsed_display_unit(r.display))
                END"""
    qty_bucket = f"CASE WHEN {parsed_qty} IS NULL THEN 'grams_missing_or_zero' ELSE COALESCE(NULLIF({eff_fb}, ''), 'grams_missing_or_zero') END"
    nutrition_density_expr = f"""CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN NULL
                    ELSE pn.density_g_per_ml
                END"""
    household_grams_expr = (
        f"COALESCE(household_unit_grams({eff_ck}, {parsed_qty}, {parsed_unit}), "
        f"sr28_display_household_grams({eff_ck}, {parsed_qty}, {parsed_unit}, r.display), "
        f"mass_unit_grams({parsed_qty}, {parsed_unit}), "
        f"density_volume_unit_grams({parsed_qty}, {parsed_unit}, {nutrition_density_expr}))"
    )
    household_rationale_expr = (
        f"COALESCE(household_unit_rationale({eff_ck}, {parsed_unit}), "
        f"sr28_display_household_rationale({eff_ck}, {parsed_unit}, r.display))"
    )
    conn.execute("DROP TABLE IF EXISTS ingredient_eval")
    conn.execute(
        f"""
        CREATE TABLE ingredient_eval AS
        WITH resolved AS (
            SELECT
                r.recipe_id,
                r.title,
                r.ingredient_index,
                r.display,
                r.item,
                r.normalized_line,
                r.patch_id,
                r.patch_problem,
                r.patched_old_display,
                r.grams AS raw_grams,
                CASE
                    WHEN {ifl_cond}
                    THEN 1 ELSE 0
                END AS _item_fallback_used,
                CASE
                    WHEN {ifl_cond}
                    THEN ifl.failure_bucket
                    ELSE le.failure_bucket
                END AS raw_failure_bucket,
                {parsed_qty} AS parsed_quantity,
                {parsed_unit} AS parsed_unit,
                {eff_ck} AS concept_key,
                {eff_pck} AS product_contract_key,
                CASE
                    WHEN {ifl_cond}
                    THEN COALESCE(ifl.product_policy, pn.policy, '')
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                         AND COALESCE(le.product_policy, '') = ''
                    THEN 'external_catalog_buy'
                    WHEN COALESCE(le.product_policy, '') = ''
                         AND pn.policy IS NOT NULL
                    THEN pn.policy
                    ELSE le.product_policy
                END AS product_policy,
                CASE
                    WHEN {ifl_cond}
                    THEN ifl.product_audit_status
                    ELSE le.product_audit_status
                END AS product_audit_status,
                CASE
                    WHEN {ifl_cond}
                    THEN ifl.quantity_bucket
                    ELSE le.quantity_bucket
                END AS quantity_bucket,
                CASE
                    WHEN {ifl_cond}
                    THEN ifl.dictionary_match_status
                    ELSE le.dictionary_match_status
                END AS dictionary_match_status,
                CASE
                    WHEN {ifl_cond}
                    THEN ifl.resolution_action
                    ELSE le.resolution_action
                END AS resolution_action,
                CASE
                    WHEN {parsed_qty} IS NULL
                         AND split_default_ready({eff_pck}) = 1
                    THEN 'nutrition_ready_split_to_taste_defaults'
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.nutrition_status
                    ELSE pn.nutrition_status
                END AS nutrition_status,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ''
                    ELSE pn.gtin_upc
                END AS gtin_upc,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.shopping_label
                    ELSE pn.selected_description
                END AS selected_description,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.shopping_category
                    ELSE pn.selected_category
                END AS selected_category,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.calories_per_g
                    ELSE pn.calories_per_g
                END AS calories_per_g,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.protein_g_per_g
                    ELSE pn.protein_g_per_g
                END AS protein_g_per_g,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.fat_g_per_g
                    ELSE pn.fat_g_per_g
                END AS fat_g_per_g,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.carbs_g_per_g
                    ELSE pn.carbs_g_per_g
                END AS carbs_g_per_g,
                CASE
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN ecn.sodium_mg_per_g
                    ELSE pn.sodium_mg_per_g
                END AS sodium_mg_per_g,
                ttd.default_grams AS to_taste_default_grams,
                ttd.rationale AS to_taste_rationale,
                CASE
                    WHEN r.grams IS NULL OR r.grams <= 0
                    THEN {household_grams_expr}
                    ELSE NULL
                END AS household_unit_grams,
                CASE
                    WHEN r.grams IS NULL OR r.grams <= 0
                    THEN {household_rationale_expr}
                    ELSE NULL
                END AS household_unit_rationale,
                CASE
                    WHEN {qty_bucket} IN ('quantity_missing', 'manual_quantity_required', 'quantity_to_taste', 'quantity_as_needed', 'grams_missing_or_zero')
                    THEN quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line)
                    ELSE NULL
                END AS quantity_policy_action,
                CASE
                    WHEN {qty_bucket} IN ('quantity_missing', 'manual_quantity_required', 'quantity_to_taste', 'quantity_as_needed', 'grams_missing_or_zero')
                    THEN quantity_policy_default_grams({quantity_key}, {qty_bucket}, r.display, r.normalized_line)
                    ELSE NULL
                END AS quantity_policy_default_grams,
                CASE
                    WHEN {qty_bucket} IN ('quantity_missing', 'manual_quantity_required', 'quantity_to_taste', 'quantity_as_needed', 'grams_missing_or_zero')
                    THEN quantity_policy_rationale({quantity_key}, {qty_bucket}, r.display, r.normalized_line)
                    ELSE NULL
                END AS quantity_policy_rationale,
                CASE
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {household_grams_expr} IS NOT NULL
                    THEN {household_grams_expr}
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {parsed_qty} IS NULL
                         AND split_default_ready({eff_pck}) = 1
                    THEN split_default_grams({eff_pck})
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line) = 'apply_default'
                         AND quantity_policy_default_grams({quantity_key}, {qty_bucket}, r.display, r.normalized_line) IS NOT NULL
                    THEN quantity_policy_default_grams({quantity_key}, {qty_bucket}, r.display, r.normalized_line)
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {eff_fb} IN ('quantity_to_taste', 'quantity_as_needed')
                         AND ttd.default_grams IS NOT NULL
                    THEN ttd.default_grams
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {parsed_qty} IS NULL
                         AND ttd.default_grams IS NOT NULL
                    THEN ttd.default_grams
                    ELSE r.grams
                END AS effective_grams,
                CASE
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {household_grams_expr} IS NOT NULL
                    THEN 'calculation_candidate'
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {parsed_qty} IS NULL
                         AND split_default_ready({eff_pck}) = 1
                    THEN 'calculation_candidate'
                    WHEN quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line) = 'intentional_skip'
                    THEN 'intentional_skip'
                    WHEN quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line) = 'apply_default'
                         AND quantity_policy_default_grams({quantity_key}, {qty_bucket}, r.display, r.normalized_line) IS NOT NULL
                    THEN 'calculation_candidate'
                    WHEN quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line) = 'manual_prompt'
                    THEN 'manual_quantity_required'
                    WHEN {eff_fb} IN ('quantity_to_taste', 'quantity_as_needed')
                         AND ttd.default_grams IS NOT NULL
                    THEN 'calculation_candidate'
                    WHEN {parsed_qty} IS NULL
                         AND ttd.default_grams IS NOT NULL
                    THEN 'calculation_candidate'
                    WHEN {eff_fb} IN ({external_catalog_bucket_sql})
                         AND ecn.concept_key IS NOT NULL
                    THEN 'calculation_candidate'
                    WHEN {eff_fb} IN (
                            'product_not_candidate_covered',
                            'product_contract_missing',
                            'product_not_in_audit_scope',
                            'product_contract_failed',
                            'product_unknown',
                            'product_product_contract_unknown',
                            'contract_not_passed'
                         )
                         AND pn.nutrition_status IN ({ready_status_sql})
                    THEN 'calculation_candidate'
                    ELSE {eff_fb}
                END AS effective_failure_bucket,
                CASE
                    WHEN {parsed_qty} IS NULL
                         AND split_default_ready({eff_pck}) = 1
                    THEN 1
                    WHEN {eff_fb} IN ('quantity_to_taste', 'quantity_as_needed')
                         AND ttd.default_grams IS NOT NULL
                    THEN 1
                    WHEN {parsed_qty} IS NULL
                         AND ttd.default_grams IS NOT NULL
                    THEN 1
                    ELSE 0
                END AS to_taste_default_applied,
                CASE
                    WHEN quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line) IN ('apply_default', 'intentional_skip')
                         AND (
                            quantity_policy_action({quantity_key}, {qty_bucket}, r.display, r.normalized_line) = 'intentional_skip'
                            OR quantity_policy_default_grams({quantity_key}, {qty_bucket}, r.display, r.normalized_line) IS NOT NULL
                         )
                    THEN 1
                    ELSE 0
                END AS quantity_policy_applied,
                CASE
                    WHEN (r.grams IS NULL OR r.grams <= 0)
                         AND {household_grams_expr} IS NOT NULL
                    THEN 1
                    ELSE 0
                END AS household_unit_applied
            FROM recipe_qa_ingredients r
            LEFT JOIN line_audit.line_eval le ON le.normalized_line = r.normalized_line
            LEFT JOIN item_fallback_lookup ifl ON ifl.cleaned_surface = CASE
                WHEN LOWER(TRIM(r.item)) = LOWER(TRIM(r.display))
                THEN parsed_display_surface(r.display)
                ELSE LOWER(TRIM(r.item))
            END
            LEFT JOIN product_nutrition pn ON pn.concept_key = canonical_concept_key_list(COALESCE(
                NULLIF(
                    CASE
                        WHEN {ifl_cond}
                        THEN COALESCE(NULLIF(ifl.product_contract_key, ''), ifl.concept_key)
                        ELSE COALESCE(NULLIF(le.product_contract_key, ''), le.concept_key)
                    END,
                    ''
                ),
                le.concept_key
            ))
            LEFT JOIN external_catalog_nutrition ecn ON ecn.concept_key = canonical_concept_key(CASE
                WHEN {ifl_cond}
                THEN ifl.concept_key
                ELSE le.concept_key
            END)
            LEFT JOIN to_taste_defaults ttd ON ttd.concept_key = canonical_concept_key(CASE
                WHEN {ifl_cond}
                THEN ifl.concept_key
                ELSE le.concept_key
            END)
        )
        SELECT
            recipe_id,
            title,
            ingredient_index,
            display,
            item,
            normalized_line,
            patch_id,
            patch_problem,
            patched_old_display,
            raw_grams AS grams,
            effective_grams,
            raw_failure_bucket AS line_failure_bucket,
            effective_failure_bucket,
            parsed_quantity,
            parsed_unit,
            household_unit_grams,
            household_unit_rationale,
            household_unit_applied,
            to_taste_default_grams,
            to_taste_rationale,
            to_taste_default_applied,
            quantity_policy_action,
            quantity_policy_default_grams,
            quantity_policy_rationale,
            quantity_policy_applied,
            concept_key,
            product_contract_key,
            product_policy,
            product_audit_status,
            quantity_bucket,
            dictionary_match_status,
            resolution_action,
            nutrition_status,
            gtin_upc,
            selected_description,
            selected_category,
            CASE
                WHEN normalized_line IS NULL THEN 'line_not_in_audit'
                WHEN effective_failure_bucket = 'intentional_skip' THEN 'intentional_skip'
                WHEN effective_grams IS NULL OR effective_grams <= 0 THEN 'grams_missing_or_zero'
                WHEN instr(product_contract_key, ';') > 0
                     AND nutrition_status = 'nutrition_ready_split_to_taste_defaults'
                THEN 'nutrition_calculable'
                WHEN instr(product_contract_key, ';') > 0 THEN 'split_component_needs_allocation'
                WHEN product_policy = 'no_buy' THEN 'nutrition_ready_no_buy'
                WHEN nutrition_status IN ({ready_status_sql}) THEN 'nutrition_calculable'
                WHEN effective_failure_bucket != 'calculation_candidate' THEN effective_failure_bucket
                ELSE COALESCE(nutrition_status, 'product_nutrition_missing')
            END AS strict_bucket,
            CASE
                WHEN effective_failure_bucket = 'calculation_candidate' AND nutrition_status = 'nutrition_ready_split_to_taste_defaults'
                THEN split_default_nutrient(product_contract_key, 'calories')
                WHEN effective_grams > 0 AND nutrition_status IN ({ready_status_sql}) AND instr(product_contract_key, ';') = 0
                THEN effective_grams * calories_per_g
                ELSE NULL
            END AS calories_calc,
            CASE
                WHEN effective_failure_bucket = 'calculation_candidate' AND nutrition_status = 'nutrition_ready_split_to_taste_defaults'
                THEN split_default_nutrient(product_contract_key, 'protein')
                WHEN effective_grams > 0 AND nutrition_status IN ({ready_status_sql}) AND instr(product_contract_key, ';') = 0
                THEN effective_grams * protein_g_per_g
                ELSE NULL
            END AS protein_g_calc,
            CASE
                WHEN effective_failure_bucket = 'calculation_candidate' AND nutrition_status = 'nutrition_ready_split_to_taste_defaults'
                THEN split_default_nutrient(product_contract_key, 'fat')
                WHEN effective_grams > 0 AND nutrition_status IN ({ready_status_sql}) AND instr(product_contract_key, ';') = 0
                THEN effective_grams * fat_g_per_g
                ELSE NULL
            END AS fat_g_calc,
            CASE
                WHEN effective_failure_bucket = 'calculation_candidate' AND nutrition_status = 'nutrition_ready_split_to_taste_defaults'
                THEN split_default_nutrient(product_contract_key, 'carbs')
                WHEN effective_grams > 0 AND nutrition_status IN ({ready_status_sql}) AND instr(product_contract_key, ';') = 0
                THEN effective_grams * carbs_g_per_g
                ELSE NULL
            END AS carbs_g_calc,
            CASE
                WHEN effective_failure_bucket = 'calculation_candidate' AND nutrition_status = 'nutrition_ready_split_to_taste_defaults'
                THEN split_default_nutrient(product_contract_key, 'sodium')
                WHEN effective_grams > 0 AND nutrition_status IN ({ready_status_sql}) AND instr(product_contract_key, ';') = 0
                THEN effective_grams * sodium_mg_per_g
                ELSE NULL
            END AS sodium_mg_calc
        FROM resolved
        """
    )
    conn.execute("CREATE INDEX idx_ingredient_eval_bucket ON ingredient_eval(strict_bucket)")
    conn.execute("CREATE INDEX idx_ingredient_eval_recipe ON ingredient_eval(recipe_id)")
    conn.commit()


def build_recipe_scores(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS recipe_scores")
    conn.execute(
        """
        CREATE TABLE recipe_scores AS
        SELECT
            recipe_id,
            MAX(title) AS title,
            COUNT(*) AS ingredient_lines,
            SUM(CASE WHEN strict_bucket IN ('nutrition_calculable', 'nutrition_ready_no_buy', 'intentional_skip') THEN 1 ELSE 0 END) AS nutrition_ready_lines,
            SUM(CASE WHEN strict_bucket = 'nutrition_calculable' THEN 1 ELSE 0 END) AS product_nutrition_calculable_lines,
            SUM(CASE WHEN strict_bucket = 'nutrition_ready_no_buy' THEN 1 ELSE 0 END) AS no_buy_ready_lines,
            SUM(CASE WHEN strict_bucket = 'grams_missing_or_zero' THEN 1 ELSE 0 END) AS grams_missing_or_zero_lines,
            SUM(CASE WHEN strict_bucket = 'concept_unresolved' THEN 1 ELSE 0 END) AS concept_unresolved_lines,
            SUM(CASE WHEN strict_bucket = 'product_contract_missing' THEN 1 ELSE 0 END) AS product_contract_missing_lines,
            SUM(CASE WHEN strict_bucket = 'product_not_candidate_covered' THEN 1 ELSE 0 END) AS product_not_candidate_covered_lines,
            SUM(CASE WHEN strict_bucket = 'product_not_in_audit_scope' THEN 1 ELSE 0 END) AS product_not_in_audit_scope_lines,
            SUM(CASE WHEN strict_bucket = 'product_nutrition_missing' THEN 1 ELSE 0 END) AS product_nutrition_missing_lines,
            SUM(CASE WHEN strict_bucket = 'serving_unit_not_grams' THEN 1 ELSE 0 END) AS serving_unit_not_grams_lines,
            SUM(CASE WHEN strict_bucket = 'split_component_needs_allocation' THEN 1 ELSE 0 END) AS split_component_needs_allocation_lines,
            SUM(COALESCE(calories_calc, 0)) AS partial_calories,
            SUM(COALESCE(protein_g_calc, 0)) AS partial_protein_g,
            SUM(COALESCE(fat_g_calc, 0)) AS partial_fat_g,
            SUM(COALESCE(carbs_g_calc, 0)) AS partial_carbs_g,
            SUM(COALESCE(sodium_mg_calc, 0)) AS partial_sodium_mg
        FROM ingredient_eval
        GROUP BY recipe_id
        """
    )
    conn.execute("CREATE INDEX idx_recipe_scores_ready ON recipe_scores(nutrition_ready_lines)")
    conn.commit()


def pct(numerator: int | float | None, denominator: int | float | None) -> float:
    if not denominator:
        return 0.0
    return round((numerator or 0) / denominator * 100, 2)


def summarize(conn: sqlite3.Connection) -> dict[str, object]:
    totals = conn.execute(
        """
        SELECT
            COUNT(*),
            SUM(ingredient_lines),
            SUM(nutrition_ready_lines),
            SUM(product_nutrition_calculable_lines),
            SUM(no_buy_ready_lines),
            SUM(grams_missing_or_zero_lines),
            SUM(concept_unresolved_lines),
            SUM(product_contract_missing_lines),
            SUM(product_not_candidate_covered_lines),
            SUM(product_not_in_audit_scope_lines),
            SUM(product_nutrition_missing_lines),
            SUM(serving_unit_not_grams_lines),
            SUM(split_component_needs_allocation_lines)
        FROM recipe_scores
        """
    ).fetchone()
    fields = [
        "recipes",
        "ingredient_lines",
        "nutrition_ready_lines",
        "product_nutrition_calculable_lines",
        "no_buy_ready_lines",
        "grams_missing_or_zero_lines",
        "concept_unresolved_lines",
        "product_contract_missing_lines",
        "product_not_candidate_covered_lines",
        "product_not_in_audit_scope_lines",
        "product_nutrition_missing_lines",
        "serving_unit_not_grams_lines",
        "split_component_needs_allocation_lines",
    ]
    summary = dict(zip(fields, totals))
    ingredient_lines = summary["ingredient_lines"]
    summary["nutrition_ready_line_percent"] = pct(summary["nutrition_ready_lines"], ingredient_lines)
    summary["product_nutrition_calculable_line_percent"] = pct(
        summary["product_nutrition_calculable_lines"],
        ingredient_lines,
    )

    bucket_counts: Counter[str] = Counter()
    for total, ready in conn.execute("SELECT ingredient_lines, nutrition_ready_lines FROM recipe_scores"):
        ratio = (ready or 0) / total if total else 0
        if ratio >= 0.999999:
            bucket = "100"
        elif ratio >= 0.90:
            bucket = "90-99"
        elif ratio >= 0.80:
            bucket = "80-89"
        elif ratio >= 0.70:
            bucket = "70-79"
        elif ratio >= 0.60:
            bucket = "60-69"
        elif ratio >= 0.50:
            bucket = "50-59"
        else:
            bucket = "under_50"
        bucket_counts[bucket] += 1
    summary["recipe_nutrition_buckets"] = dict(bucket_counts)
    summary["recipe_nutrition_bucket_percent"] = {
        bucket: pct(count, summary["recipes"])
        for bucket, count in sorted(bucket_counts.items())
    }
    summary["strict_bucket_counts"] = dict(
        conn.execute(
            "SELECT strict_bucket, COUNT(*) FROM ingredient_eval GROUP BY strict_bucket ORDER BY COUNT(*) DESC"
        ).fetchall()
    )
    summary["resolution_action_counts"] = dict(
        conn.execute(
            "SELECT COALESCE(resolution_action, ''), COUNT(*) FROM ingredient_eval GROUP BY resolution_action ORDER BY COUNT(*) DESC"
        ).fetchall()
    )
    summary["product_nutrition_status_counts"] = dict(
        conn.execute(
            "SELECT nutrition_status, COUNT(*) FROM product_nutrition GROUP BY nutrition_status ORDER BY COUNT(*) DESC"
        ).fetchall()
    )
    return summary


def write_top_failures(conn: sqlite3.Connection, path: Path, limit: int = 500) -> list[dict[str, object]]:
    fields = [
        "strict_bucket",
        "mentions",
        "display",
        "normalized_line",
        "concept_key",
        "product_contract_key",
        "line_failure_bucket",
        "nutrition_status",
    ]
    rows = []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for values in conn.execute(
            """
            SELECT
                strict_bucket,
                COUNT(*) AS mentions,
                MAX(display) AS display,
                normalized_line,
                COALESCE(concept_key, '') AS concept_key,
                COALESCE(product_contract_key, '') AS product_contract_key,
                COALESCE(line_failure_bucket, '') AS line_failure_bucket,
                COALESCE(nutrition_status, '') AS nutrition_status
            FROM ingredient_eval
            WHERE strict_bucket NOT IN ('nutrition_calculable', 'nutrition_ready_no_buy')
            GROUP BY strict_bucket, normalized_line
            ORDER BY mentions DESC, normalized_line
            LIMIT ?
            """,
            (limit,),
        ):
            row = dict(zip(fields, values))
            writer.writerow(row)
            rows.append(row)
    return rows


def write_low_recipes(conn: sqlite3.Connection, path: Path, limit: int = 250) -> list[dict[str, object]]:
    fields = [
        "recipe_id",
        "title",
        "ingredient_lines",
        "nutrition_ready_lines",
        "nutrition_ready_percent",
        "partial_calories",
        "failure_examples",
    ]
    rows = []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for recipe in conn.execute(
            """
            SELECT
                recipe_id,
                title,
                ingredient_lines,
                nutrition_ready_lines,
                partial_calories
            FROM recipe_scores
            WHERE ingredient_lines >= 5
              AND CAST(nutrition_ready_lines AS REAL) / ingredient_lines < 0.80
            ORDER BY
                (ingredient_lines - nutrition_ready_lines) DESC,
                ingredient_lines DESC
            LIMIT ?
            """,
            (limit,),
        ):
            recipe_id, title, ingredient_lines, ready, partial_calories = recipe
            examples = [
                f"{bucket}:{display}"
                for bucket, display in conn.execute(
                    """
                    SELECT strict_bucket, display
                    FROM ingredient_eval
                    WHERE recipe_id = ?
                      AND strict_bucket NOT IN ('nutrition_calculable', 'nutrition_ready_no_buy')
                    ORDER BY strict_bucket, ingredient_index
                    LIMIT 16
                    """,
                    (recipe_id,),
                )
            ]
            row = {
                "recipe_id": recipe_id,
                "title": title,
                "ingredient_lines": ingredient_lines,
                "nutrition_ready_lines": ready,
                "nutrition_ready_percent": pct(ready, ingredient_lines),
                "partial_calories": round(partial_calories or 0, 2),
                "failure_examples": " | ".join(examples),
            }
            writer.writerow(row)
            rows.append(row)
    return rows


def write_report(
    path: Path,
    summary: dict[str, object],
    top_failures: list[dict[str, object]],
    low_recipes: list[dict[str, object]],
) -> None:
    lines = [
        "# Recipe QA Gram-Backed Nutrition Calculation Audit",
        "",
        "This is stricter than the full 2.7M funnel audit. It uses `recipe_qa.db` because that source stores ingredient grams.",
        "",
        "A line is `nutrition_calculable` only when grams are present and the normalized line has per-gram nutrition from an approved SR28/FNDDS anchor, trusted product nutrients, an approved density bridge, or an approved external-catalog shopping item. Product/card failures still remain visible in shopping fields; they do not block nutrition when an SR28/FNDDS anchor is approved.",
        "",
        "## Summary",
        "",
        f"- Recipes scored: `{summary['recipes']:,}`",
        f"- Ingredient lines: `{summary['ingredient_lines']:,}`",
        f"- Nutrition-ready lines, counting no-buy lines: `{summary['nutrition_ready_lines']:,}` (`{summary['nutrition_ready_line_percent']}%`)",
        f"- Calculation-ready lines excluding no-buy lines: `{summary['product_nutrition_calculable_lines']:,}` (`{summary['product_nutrition_calculable_line_percent']}%`)",
        "",
        "## Strict Failure Buckets",
        "",
        "| Bucket | Ingredient lines |",
        "|---|---:|",
    ]
    for bucket, count in sorted(summary["strict_bucket_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{bucket}` | `{count:,}` |")
    lines.extend(
        [
            "",
            "## Recipe Nutrition Buckets",
            "",
            "| Bucket | Recipes | Percent |",
            "|---|---:|---:|",
        ]
    )
    order = ["100", "90-99", "80-89", "70-79", "60-69", "50-59", "under_50"]
    for bucket in order:
        count = summary["recipe_nutrition_buckets"].get(bucket, 0)
        percent = summary["recipe_nutrition_bucket_percent"].get(bucket, 0)
        lines.append(f"| `{bucket}` | `{count:,}` | `{percent}%` |")
    lines.extend(
        [
            "",
            "## Product Nutrition Status",
            "",
            "| Status | Contracts |",
            "|---|---:|",
        ]
    )
    for status, count in sorted(summary["product_nutrition_status_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{status}` | `{count:,}` |")
    lines.extend(
        [
            "",
            "## Top Failures",
            "",
            "| Mentions | Bucket | Display | Concept | Product key | Line failure | Nutrition status |",
            "|---:|---|---|---|---|---|---|",
        ]
    )
    for row in top_failures[:60]:
        lines.append(
            f"| `{int(row['mentions']):,}` | `{row['strict_bucket']}` | `{row['display']}` | `{row['concept_key']}` | `{row['product_contract_key']}` | `{row['line_failure_bucket']}` | `{row['nutrition_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Low-Readiness Recipe Examples",
            "",
            "| Ready % | Lines | Ready lines | Title | Failure examples |",
            "|---:|---:|---:|---|---|",
        ]
    )
    for row in low_recipes[:30]:
        lines.append(
            f"| `{row['nutrition_ready_percent']}%` | `{row['ingredient_lines']}` | `{row['nutrition_ready_lines']}` | `{row['title']}` | `{row['failure_examples']}` |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit gram-backed nutrition calculation readiness for recipe_qa.")
    parser.add_argument("--recipe-qa-db", type=Path, default=DEFAULT_RECIPE_QA_DB)
    parser.add_argument("--products-db", type=Path, default=DEFAULT_PRODUCTS_DB)
    parser.add_argument("--line-audit-db", type=Path, default=DEFAULT_LINE_AUDIT_DB)
    parser.add_argument("--product-audit-csv", type=Path, default=DEFAULT_PRODUCT_AUDIT_CSV)
    parser.add_argument("--product-nutrition-state-db", type=Path, default=DEFAULT_PRODUCT_NUTRITION_STATE_DB)
    parser.add_argument(
        "--rebuild-product-nutrition-state",
        action="store_true",
        help="Force rebuild of the shared product/external nutrition cache before auditing recipes.",
    )
    parser.add_argument("--density-bridge-csv", type=Path, default=DEFAULT_DENSITY_BRIDGE_CSV)
    parser.add_argument("--nutrition-anchor-csv", type=Path, default=DEFAULT_NUTRITION_ANCHORS_CSV)
    parser.add_argument("--sr28-fallback-csv", type=Path, default=DEFAULT_SR28_FALLBACK_CSV)
    parser.add_argument("--external-catalog-csv", type=Path, default=DEFAULT_EXTERNAL_CATALOG_CSV)
    parser.add_argument("--sr28-food-csv", type=Path, default=DEFAULT_SR28_FOOD_CSV)
    parser.add_argument("--sr28-nutrient-csv", type=Path, default=DEFAULT_SR28_NUTRIENT_CSV)
    parser.add_argument("--sr28-food-portion-csv", type=Path, default=DEFAULT_SR28_FOOD_PORTION_CSV)
    parser.add_argument("--sr28-measure-unit-csv", type=Path, default=DEFAULT_SR28_MEASURE_UNIT_CSV)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--top-failures-csv", type=Path, default=DEFAULT_TOP_FAILURES_CSV)
    parser.add_argument("--low-recipes-csv", type=Path, default=DEFAULT_LOW_RECIPES_CSV)
    parser.add_argument("--normalized-item-bridge-csv", type=Path, default=DEFAULT_NORMALIZED_ITEM_BRIDGE_CSV)
    parser.add_argument("--to-taste-defaults-csv", type=Path, default=DEFAULT_TO_TASTE_DEFAULTS_CSV)
    parser.add_argument("--quantity-policies-csv", type=Path, default=DEFAULT_QUANTITY_POLICIES_CSV)
    parser.add_argument("--household-unit-grams-csv", type=Path, default=DEFAULT_HOUSEHOLD_UNIT_GRAMS_CSV)
    parser.add_argument("--recipe-line-patches-csv", type=Path, default=DEFAULT_RECIPE_LINE_PATCHES_CSV)
    parser.add_argument(
        "--recipe-id-filter-csv",
        type=Path,
        default=None,
        help="Optional CSV with recipe_id column. Use for attack-surface scratch audits, not canonical full output.",
    )
    args = parser.parse_args()

    recipe_id_filter = load_recipe_id_filter(args.recipe_id_filter_csv)
    if recipe_id_filter is not None and args.output_db.resolve() == DEFAULT_OUTPUT_DB.resolve():
        raise ValueError(
            "Filtered recipe QA audits must write to a non-canonical scratch --output-db; "
            "otherwise the full canonical audit would be overwritten with a subset."
        )

    if args.output_db.exists():
        args.output_db.unlink()
    conn = connect(args.output_db)
    product_state = install_product_nutrition_state(
        conn,
        cache_db=args.product_nutrition_state_db,
        product_audit_csv=args.product_audit_csv,
        products_db=args.products_db,
        density_bridge_csv=args.density_bridge_csv,
        nutrition_anchor_csv=args.nutrition_anchor_csv,
        sr28_fallback_csv=args.sr28_fallback_csv,
        external_catalog_csv=args.external_catalog_csv,
        sr28_food_csv=args.sr28_food_csv,
        sr28_nutrient_csv=args.sr28_nutrient_csv,
        force_rebuild=args.rebuild_product_nutrition_state,
    )
    print(
        "Product nutrition state "
        f"{product_state['source']} from {product_state['cache_db']} "
        f"({int(product_state.get('product_rows') or 0):,} product rows, "
        f"{int(product_state.get('external_rows') or 0):,} external rows)"
    )
    external_stats = product_state.get("external_stats") or {}
    if external_stats:
        print(f"External catalog loader stats: {json.dumps(external_stats, sort_keys=True)}")
    patches_applied = populate_recipe_ingredients(conn, args.recipe_qa_db, recipe_id_filter, args.recipe_line_patches_csv)
    print(f"Applied {patches_applied:,} reviewed recipe-line patches from {args.recipe_line_patches_csv}")
    if recipe_id_filter is not None:
        print(f"Loaded recipe ID filter with {len(recipe_id_filter):,} requested recipes from {args.recipe_id_filter_csv}")
    defaults_loaded = populate_to_taste_defaults(conn, args.to_taste_defaults_csv)
    print(f"Loaded {defaults_loaded} reviewed to-taste defaults from {args.to_taste_defaults_csv}")
    install_split_default_nutrition_functions(conn)
    quantity_policies = populate_quantity_policies(conn, args.quantity_policies_csv)
    install_quantity_policy_functions(conn, quantity_policies)
    print(f"Loaded {len(quantity_policies)} reviewed quantity policies from {args.quantity_policies_csv}")
    household_unit_rules = populate_household_unit_rules(conn, args.household_unit_grams_csv)
    sr28_portion_rule_count = add_sr28_portion_household_rules(
        conn,
        household_unit_rules,
        sr28_portion_csv=args.sr28_food_portion_csv,
        sr28_measure_unit_csv=args.sr28_measure_unit_csv,
        sr28_fallback_csv=args.sr28_fallback_csv,
        external_catalog_csv=args.external_catalog_csv,
        nutrition_anchor_csv=args.nutrition_anchor_csv,
    )
    install_household_unit_functions(conn, household_unit_rules)
    install_display_parse_functions(conn)
    print(
        f"Loaded {len(household_unit_rules)} household unit gram rules "
        f"({sr28_portion_rule_count} from SR28 food_portion) from {args.household_unit_grams_csv}"
    )
    attach(conn, args.line_audit_db, "line_audit")
    fallback_count = build_item_fallback_lookup(
        conn,
        args.normalized_item_bridge_csv,
        args.recipe_line_patches_csv,
        args.sr28_fallback_csv,
    )
    bridge_count = conn.execute(
        "SELECT COUNT(*) FROM item_fallback_lookup WHERE lookup_source = 'normalized_item_bridge'"
    ).fetchone()[0]
    print(
        f"Built item bridge/fallback lookup: {fallback_count:,} distinct items "
        f"({bridge_count:,} from normalized-item bridge)"
    )
    build_ingredient_eval(conn)
    build_recipe_scores(conn)
    summary = summarize(conn)
    summary["product_nutrition_state"] = {
        "source": product_state.get("source"),
        "cache_db": product_state.get("cache_db"),
        "dependency_fingerprint": product_state.get("dependency_fingerprint"),
        "product_rows": product_state.get("product_rows"),
        "external_rows": product_state.get("external_rows"),
        "external_stats": product_state.get("external_stats", {}),
    }
    top_failures = write_top_failures(conn, args.top_failures_csv)
    low_recipes = write_low_recipes(conn, args.low_recipes_csv)
    close_with_checkpoint(conn)

    args.report_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_report(args.report_md, summary, top_failures, low_recipes)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
