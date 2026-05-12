"""Read-side loader for esha_nutrition.csv.

Public API:
    nutrition_for_esha(esha_code: str) -> dict | None
        Returns {kcal, protein, fat, carbs, tier, n, sr28_proxy, fndds_proxy,
                 review_status} per-100g for the given EshaCode.
        Returns None when the EshaCode isn't in the table.

Built by implementation/build_esha_nutrition.py. Three tiers inside:
  tier='A_label_median'     -> numbers derived from Walmart/Kroger product
                               labels via token-overlap tagging
  tier='B_sr28_fndds_proxy' -> auto-batched proxy to SR28/FNDDS description.
                               Nutrition must be looked up from SR28 per-100g
                               at runtime (this loader does that).
  tier='C_unknown'          -> no nutrition source.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TABLE = ROOT / 'esha_nutrition.csv'

_CACHE: dict[str, dict] | None = None


def _load() -> dict[str, dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out: dict[str, dict] = {}
    if not TABLE.exists():
        _CACHE = out
        return out
    with TABLE.open(newline='') as f:
        for r in csv.DictReader(f):
            code = r['EshaCode'].strip()
            if not code:
                continue

            def _flt(k):
                v = (r.get(k) or '').strip()
                try: return float(v) if v else None
                except ValueError: return None

            out[code] = {
                'tier': r.get('tier', '').strip(),
                'kcal': _flt('kcal_per_100g'),
                'protein': _flt('protein_per_100g'),
                'fat': _flt('fat_per_100g'),
                'carbs': _flt('carbs_per_100g'),
                'n': int(r.get('n_products_contributing') or 0 or 0),
                'sr28_proxy': (r.get('sr28_proxy_fdc_id') or '').strip(),
                'fndds_proxy': (r.get('fndds_proxy_code') or '').strip(),
                'review_status': r.get('review_status', '').strip(),
                'description': r.get('esha_description', '').strip(),
            }
    _CACHE = out
    return out


def nutrition_for_esha(esha_code: str) -> dict | None:
    """Per-100g nutrition for an EshaCode. Includes tier for caller to map
    to the right NutritionState (A→EXACT-like, B→REVIEWED_PROXY, C→UNKNOWN).

    When tier is B (proxy), kcal/protein/fat/carbs may be empty because
    this loader doesn't cross-reference SR28 per-100g inline — the caller
    should use sr28_proxy to look up SR28 nutrition directly. The calculator
    module already knows how to do that.
    """
    if not esha_code:
        return None
    return _load().get(esha_code.strip())
