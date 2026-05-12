"""SR28 nutrition lookup service.

Reads data/sr28_csv/food_nutrient.csv once, caches per-fdc_id macro values.
Call sr28_per_100g(fdc_id) to get {'kcal','protein','fat','carbs'} per 100g
as recorded in SR28.

Nutrient IDs used:
  1008 Energy (kcal)        — primary kcal source
  2047 Energy Atwater       — fallback
  1003 Protein (g)
  1004 Total lipid / fat (g)
  1005 Carbohydrate (g)

Per-100g basis: SR28 food_nutrient.amount is per 100 g.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOOD_NUTRIENT = ROOT / 'data' / 'sr28_csv' / 'food_nutrient.csv'

NUT_KCAL = {'1008', '2047'}
NUT_PROTEIN = {'1003'}
NUT_FAT = {'1004'}
NUT_CARBS = {'1005'}
ALL_IDS = NUT_KCAL | NUT_PROTEIN | NUT_FAT | NUT_CARBS

_CACHE: dict[str, dict[str, float]] | None = None


def _load() -> dict[str, dict[str, float]]:
    global _CACHE
    if _CACHE is not None: return _CACHE
    out: dict[str, dict[str, float]] = {}
    with FOOD_NUTRIENT.open() as f:
        for row in csv.DictReader(f):
            nid = row['nutrient_id'].strip()
            if nid not in ALL_IDS: continue
            fid = row['fdc_id'].strip()
            try: amt = float(row['amount'])
            except Exception: continue
            d = out.setdefault(fid, {})
            if nid in NUT_KCAL:
                # Prefer 1008; keep first non-zero
                if 'kcal' not in d or (d['kcal'] == 0 and amt > 0):
                    d['kcal'] = amt
            elif nid in NUT_PROTEIN: d['protein'] = amt
            elif nid in NUT_FAT:     d['fat'] = amt
            elif nid in NUT_CARBS:   d['carbs'] = amt
    _CACHE = out
    return _CACHE


def sr28_per_100g(fdc_id: str) -> dict[str, float] | None:
    """Return {'kcal','protein','fat','carbs'} per 100g, or None if unknown."""
    if not fdc_id: return None
    d = _load().get(str(fdc_id).strip())
    if not d: return None
    return {
        'kcal':    d.get('kcal', 0.0),
        'protein': d.get('protein', 0.0),
        'fat':     d.get('fat', 0.0),
        'carbs':   d.get('carbs', 0.0),
    }


def nutrition_for_grams(fdc_id: str, grams: float) -> dict[str, float] | None:
    p = sr28_per_100g(fdc_id)
    if p is None or grams is None or grams <= 0: return None
    scale = grams / 100.0
    return {k: v * scale for k, v in p.items()}
