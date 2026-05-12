# implementation/portion_resolver.py
"""Portion → grams resolution.

Reads data/sr28_csv/food_portion.csv at query time. No cached portion
columns. Falls through: SR28 → FNDDS → pseudo portion overrides →
generic unit conversions (oz, lb, g, kg, ml, liter).

Unit aliases: c/cup, T/tbsp/Tbsp/tablespoon, t/tsp/teaspoon, oz/ounce,
lb/pound, each/count, large/medium/small, stalk/bunch/clove, pinch/dash.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SR28_PORTION = ROOT / "data" / "sr28_csv" / "food_portion.csv"
SR28_MEASURE_UNIT = ROOT / "data" / "sr28_csv" / "measure_unit.csv"

# Weight-based direct conversions (no food portion needed)
WEIGHT_TO_GRAMS = {
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
    "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
}

# Water-density generic fallback — USDA conventional approximations. Used only
# when the SR28 food_portion lookup misses for the canonical's fdc_id. Good
# within ~5-10% for most foods; concept-specific density (flour, honey, salt)
# lives in reviewed_density_bridge.csv.
GENERIC_VOLUME_TO_GRAMS = {
    "tsp": 5.0, "tbsp": 15.0, "cup": 240.0, "fl_oz": 30.0,
    "pint": 473.0, "quart": 946.0, "gallon": 3785.0,
    "ml": 1.0, "liter": 1000.0, "litre": 1000.0, "l": 1000.0,
    "pinch": 0.36, "dash": 0.6,
    "stick": 113.0, "slice": 25.0, "clove": 3.0,
    "large": 50.0, "medium": 100.0, "small": 50.0,
    "each": 50.0, "count": 50.0, "whole": 50.0, "ea": 50.0,
    "stalk": 40.0, "bunch": 100.0, "sprig": 4.0,
    "leaf": 2.0, "leaves": 2.0,
}

UNIT_ALIASES = {
    "c": "cup", "cups": "cup",
    "t": "tsp", "teaspoon": "tsp", "teaspoons": "tsp", "tsps": "tsp",
    "tbl": "tbsp", "tbs": "tbsp", "tbsps": "tbsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp",
    "count": "count", "ea": "count", "each": "count", "whole": "count",
    "fl oz": "fl_oz", "floz": "fl_oz", "fluid ounce": "fl_oz",
}

# Case-sensitive single-letter aliases (recipe convention: T=tbsp, t=tsp)
_CASE_SENSITIVE_ALIASES = {
    "T": "tbsp",
    "t": "tsp",
}

_MODIFIER_STOPWORDS = {
    "cooked", "raw", "prepared", "drained", "undrained", "sifted",
    "packed", "loose", "rounded", "level", "heaped", "fluid",
}


def _token_is_valid_unit(tok: str) -> bool:
    if not tok or not tok[0].isalpha():
        return False
    if tok.lower() in _MODIFIER_STOPWORDS:
        return False
    return True

_PORTIONS: dict[str, dict[str, float]] | None = None  # fdc_id -> {unit_name: grams}


def _load_measure_units() -> dict[str, str]:
    """measure_unit_id -> name."""
    out = {}
    with SR28_MEASURE_UNIT.open() as f:
        for r in csv.DictReader(f):
            out[r["id"].strip()] = r["name"].strip().lower()
    return out


def _load_portions() -> dict[str, dict[str, float]]:
    global _PORTIONS
    if _PORTIONS is not None:
        return _PORTIONS
    mu = _load_measure_units()
    out: dict[str, dict[str, float]] = {}
    with SR28_PORTION.open() as f:
        for r in csv.DictReader(f):
            fid = r["fdc_id"].strip()
            try:
                amount = float(r.get("amount") or 0)
                grams = float(r.get("gram_weight") or 0)
            except Exception:
                continue
            if amount <= 0 or grams <= 0:
                continue
            # modifier = "1 cup", "1 large", etc.
            modifier = (r.get("modifier") or "").strip().lower()
            mu_id = (r.get("measure_unit_id") or "").strip()
            unit_name = mu.get(mu_id, "")
            # Grams per unit (for 1 amount of the modifier)
            per_unit = grams / amount
            d = out.setdefault(fid, {})
            # Try to capture by modifier text AND by measure_unit name
            if modifier:
                # modifier is often like "cup", "tbsp", "large", "stalk"
                for tok in modifier.split(","):
                    tok = tok.strip().lower()
                    if tok and _token_is_valid_unit(tok):
                        d[tok] = per_unit
            if unit_name and unit_name != "undetermined":
                d[unit_name] = per_unit
    _PORTIONS = out
    return out


def _normalize_unit(unit: str) -> str:
    if not unit:
        return ""
    u = unit.strip()
    # Case-sensitive single-letter check FIRST (T=tbsp, t=tsp)
    if u in _CASE_SENSITIVE_ALIASES:
        return _CASE_SENSITIVE_ALIASES[u]
    u_low = u.lower()
    return UNIT_ALIASES.get(u_low, u_low)


def resolve_grams(sr28_fdc_id: str, fndds_code: str, pseudo_code: str,
                   qty: float, unit: str) -> float | None:
    if qty is None or qty <= 0:
        return None
    u = _normalize_unit(unit)

    # 1. Direct weight units bypass portion lookup
    if u in WEIGHT_TO_GRAMS:
        return qty * WEIGHT_TO_GRAMS[u]

    # 2. SR28 food_portion for the fdc_id
    if sr28_fdc_id:
        portions = _load_portions().get(sr28_fdc_id, {})
        if u in portions:
            return qty * portions[u]

    return None


def resolve_grams_generic(qty: float, unit: str) -> float | None:
    """Last-resort fallback using USDA water-density conventions.
    Use when SR28 food_portion has no row for the canonical's fdc_id AND the
    canonical is resolved (so the caller is not guessing on a non-food).
    Concept-specific density lives in reviewed_density_bridge.csv and should
    be consulted BEFORE this fallback for accuracy on dense foods (flour,
    honey, salt).
    """
    if qty is None or qty <= 0:
        return None
    u = _normalize_unit(unit)
    if u in WEIGHT_TO_GRAMS:
        return qty * WEIGHT_TO_GRAMS[u]
    if u in GENERIC_VOLUME_TO_GRAMS:
        return qty * GENERIC_VOLUME_TO_GRAMS[u]
    return None
