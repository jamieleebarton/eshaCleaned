"""Shopping resolver — Hestia-style.

Takes a resolved canonical's sr28_fdc_id (or fndds_code) and returns the
priced products tagged with that code. No string matching at runtime; the
tags live in priced_products_tagged.db (built once by
recipe_pricing/scripts/build_priced_products_tagged.py).

Public API:
  cpg_for_codes(sr28_fdc_id, fndds_code) -> dict[vendor, dict]
      vendor is 'walmart' | 'kroger'. Each vendor dict has
      {cpg, example, n_candidates, min_cpg, max_cpg, median_grams}.

  products_for_codes(sr28_fdc_id, fndds_code, vendor=None, limit=20)
      Returns raw product rows (source, name, grams, cents, cpg).
"""
from __future__ import annotations
import sqlite3
import statistics
from pathlib import Path

from price_product_filters import is_retail_price_reject, passes_retail_identity
from card_verdict_layer import is_rejected as _card_rejected
from non_food_product_filter import is_non_food, is_search_term_fallback

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "recipe_pricing" / "data" / "priced_products_tagged.db"
MP_PATH = ROOT / "data" / "master_products.db"

_CONN: sqlite3.Connection | None = None
_MP_CONN: sqlite3.Connection | None = None


def _mp_conn() -> sqlite3.Connection:
    global _MP_CONN
    if _MP_CONN is None:
        _MP_CONN = sqlite3.connect(f"file:{MP_PATH}?mode=ro", uri=True, check_same_thread=False)
    return _MP_CONN


def _categories_for_upcs(upcs: list[str]) -> dict[str, str]:
    """Fetch branded_food_category from master_products.db for a batch of UPCs.
    Returns {normalized_upc: category}. UPCs are normalized by stripping leading zeros.
    Master_products UPCs can be stored zero-padded; we match with LIKE on suffix."""
    if not upcs: return {}
    out: dict[str, str] = {}
    conn = _mp_conn()
    # Build OR clause matching suffix equality (handles zero-pad mismatch)
    placeholders = ",".join("?" * len(upcs))
    norm_upcs = [u.lstrip("0") for u in upcs]
    # Try exact match first
    for upc in norm_upcs:
        row = conn.execute(
            "SELECT gtin_upc, branded_food_category FROM products WHERE gtin_upc = ? OR gtin_upc = ? LIMIT 1",
            (upc, upc.zfill(14))
        ).fetchone()
        if row:
            out[upc] = (row[1] or "").lower()
    return out


def _stem(tok: str) -> str:
    """Crude plural fold so 'onion' matches 'onions', 'berry' matches 'berries'."""
    if len(tok) < 4:
        return tok
    if tok.endswith('ies'):
        return tok[:-3] + 'y'
    if tok.endswith('es') and len(tok) > 4:
        return tok[:-2]
    if tok.endswith('s'):
        return tok[:-1]
    return tok


def _stem_all(text: str) -> str:
    import re as _re
    return ' '.join(_stem(t) for t in _re.split(r'\s+', text.strip()))


def _head_noun(canonical: str) -> str:
    """Return the stemmed last word — the head noun — of a canonical phrase.
    Used to match varieties to their parent ('red onion' head = 'onion';
    'heavy whipping cream' head = 'cream') while rejecting derivatives
    ('pecan flour' head = 'flour' ≠ 'pecan')."""
    import re as _re
    toks = [t for t in _re.split(r'\s+', (canonical or '').strip().lower()) if t]
    if not toks:
        return ''
    return _stem(toks[-1])


def _conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    return _CONN


def products_for_codes(sr28_fdc_id: str = "", fndds_code: str = "",
                        canonical: str = "",
                        vendor: str | None = None, limit: int = 100,
                        max_quality: int = 1) -> list[dict]:
    """Return tagged product rows for a code. sr28 is primary; fndds is fallback
    when sr28 misses.

    canonical filter: when provided, only return products tagged to this
    canonical name. This prevents a query for `black pepper` from pulling in
    `pepper sauce`-tagged rows even when both share the same SR28 code — the
    tagger wrote each row's own canonical into the `canonical` column.

    max_quality gates how permissive we are about match quality:
      1 = only products whose name contains the full canonical phrase
      2 = also allow products with at least one canonical content-token overlap
      3 = allow anything tagged with this code
    Callers start at q=1 and widen only when q=1 is empty (see cpg_for_codes).

    An empty result is honest — do not silently widen.
    """
    where: list[str] = []
    params: list = []
    if sr28_fdc_id:
        where.append("sr28_fdc_id = ?")
        params.append(sr28_fdc_id)
    elif fndds_code:
        where.append("fndds_code = ?")
        params.append(fndds_code)
    else:
        return []
    if canonical:
        where.append("canonical = ?")
        params.append(canonical.strip().lower())
    where.append("quality <= ?")
    params.append(max_quality)
    where.append("non_food_drop = 0")
    if vendor:
        where.append("source = ?")
        params.append(vendor)
    q = f"""SELECT source, upc, name, grams, cents, cpg, canonical, quality, tag_trust
            FROM priced_products_tagged
            WHERE {' AND '.join(where)}
            ORDER BY quality ASC, cpg ASC
            LIMIT ?"""
    # Over-fetch generously so noise/identity filters have enough candidates
    # to find surviving rows even when the cpg-cheapest UPCs all get rejected.
    params.append(max(limit * 20, 500))
    rows = _conn().execute(q, params).fetchall()
    cols = ["source", "upc", "name", "grams", "cents", "cpg", "canonical", "quality", "tag_trust"]
    # Batch-fetch categories from master_products for the retail-identity gate
    upcs = [r[1] for r in rows if r[1]]
    cats = _categories_for_upcs(upcs)
    filtered = [
        dict(zip(cols, r))
        for r in rows
        if not is_retail_price_reject(r[2] or "", canonical or r[6] or "")
        and passes_retail_identity(r[2] or "", canonical or r[6] or "", cats.get((r[1] or "").lstrip("0"), ""))
        and not _card_rejected(r[1] or "", canonical or r[6] or "")
        and not is_non_food(r[2] or "")
        and not (r[7] == 1 and is_search_term_fallback(r[8] or ""))
    ]
    return filtered[:limit]


def _tier4_canonical_only(canonical: str, limit: int = 500) -> list[dict]:
    """Fetch priced rows by canonical alone (sr28/fndds may be null)."""
    q = """SELECT source, upc, name, grams, cents, cpg, canonical, quality, tag_trust
           FROM priced_products_tagged
           WHERE canonical = ? AND quality = 1 AND non_food_drop = 0
           ORDER BY cpg ASC LIMIT ?"""
    rows = _conn().execute(q, (canonical.strip().lower(), limit)).fetchall()
    cols = ["source", "upc", "name", "grams", "cents", "cpg", "canonical", "quality", "tag_trust"]
    upcs = [r[1] for r in rows if r[1]]
    cats = _categories_for_upcs(upcs)
    from price_product_filters import is_retail_price_reject, passes_retail_identity
    out = []
    for r in rows:
        if is_retail_price_reject(r[2] or "", canonical): continue
        if not passes_retail_identity(r[2] or "", canonical, cats.get((r[1] or "").lstrip("0"), "")): continue
        if _card_rejected(r[1] or "", canonical): continue
        if is_non_food(r[2] or ""): continue
        # Tier 4 intentionally accepts search_term_fallback rows. Canonical-exact
        # plus identity + non_food + card-verdict filtering is enough signal
        # without the stf guard — dropping it here would needlessly empty out
        # canonicals that only have priced rows under that trust label.
        out.append(dict(zip(cols, r)))
    return out


def _filter_for_query_canonical(rows: list[dict], canonical: str) -> list[dict]:
    if not canonical:
        return rows
    out: list[dict] = []
    for r in rows:
        name = r.get("name") or ""
        if is_retail_price_reject(name, canonical):
            continue
        if not passes_retail_identity(name, canonical, ""):
            continue
        out.append(r)
    return out


def cpg_for_codes(sr28_fdc_id: str = "", fndds_code: str = "",
                   canonical: str = "") -> dict[str, dict]:
    """Median cpg per vendor for products tagged with this code.

    canonical (optional): when provided, filter to products tagged to this
    exact canonical. Prevents a query for 'black pepper' from picking up
    'pepper sauce'-tagged products even when both share an SR28 code.

    Fallback: if canonical filter yields no rows, retry without it so codes
    that don't have a canonical-exact row still return something honest.

    Example shape:
      {
        'walmart': {'cpg': 0.011, 'example': 'Hormel Cure 81', 'n_candidates': 14,
                    'min_cpg': 0.002, 'max_cpg': 0.028, 'median_grams': 680.0},
        'kroger':  {...}
      }
    A vendor is absent from the dict if no products tagged (honest gap).
    """
    if not (sr28_fdc_id or fndds_code):
        return {}
    # Shopping-only substitution: ingredients a home cook can't buy standalone
    # resolve to the whole-food retail equivalent for the shopping answer.
    # Nutrition keeps its own precise SR28 elsewhere — this only affects which
    # product we tell the user to put in their cart.
    SHOPPING_SUBSTITUTES = {
        "egg yolk":  ("172154", "egg"),  # whole egg SR28 + canonical
        "egg yolks": ("172154", "egg"),
        "egg white": ("172154", "egg"),
        "egg whites": ("172154", "egg"),
    }
    sub = SHOPPING_SUBSTITUTES.get((canonical or "").strip().lower())
    if sub:
        sr28_fdc_id, canonical = sub
    # Tier 1: canonical exact. Ideal but often empty because tagger picks the
    # MOST specific canonical for each product (Red Onion → 'red onion' not
    # 'onion'). A query for canonical='onion' would miss those variants.
    rows = products_for_codes(sr28_fdc_id=sr28_fdc_id, fndds_code=fndds_code,
                               canonical=canonical, limit=500, max_quality=1)
    # Tier 2: head-noun variant match. When tier 1 misses, accept products
    # whose tagged canonical shares a HEAD NOUN (last word, stemmed) with the
    # query canonical. This matches varieties ('red onion' → 'onion'; 'heavy
    # whipping cream' → 'heavy cream') but rejects derivatives ('pecan flour'
    # head is 'flour' not 'pecan').
    if not rows and canonical:
        q_head = _head_noun(canonical)
        code_rows = products_for_codes(sr28_fdc_id=sr28_fdc_id, fndds_code=fndds_code,
                                        canonical="", limit=500, max_quality=1)
        rows = [r for r in code_rows
                if r.get('canonical') and _head_noun(r['canonical']) == q_head]
        rows = _filter_for_query_canonical(rows, canonical)
        # Tier 3: same-SR28 fallback. When head-noun also misses, accept any
        # quality-1 product that shares this SR28 code (regardless of its
        # tagged canonical name). This covers synonym pairs that the tagger
        # labeled differently: 'scallion' query + 'green onions' tagged, or
        # 'garlic clove' query + 'garlic' tagged. Quality=1 ensures the
        # product name actually matched a canonical phrase (no search-term
        # fallback noise) so we're still shopping real-food products.
        if not rows:
            rows = _filter_for_query_canonical(code_rows, canonical)
    if not rows and not canonical:
        rows = products_for_codes(sr28_fdc_id=sr28_fdc_id, fndds_code=fndds_code,
                                   canonical="", limit=500, max_quality=2)
    # Tier 4: canonical-only fallback. Some real products exist in the priced
    # cache tagged to this canonical but with sr28/fndds unset (the tagger
    # didn't derive a code at build time). Honor them when the previous tiers
    # returned nothing — the canonical match still means the product name
    # contains the canonical phrase, so this is safe.
    if not rows and canonical:
        canon_rows = _tier4_canonical_only(canonical)
        rows = _filter_for_query_canonical(canon_rows, canonical)
    by_vendor: dict[str, list[dict]] = {}
    for r in rows:
        by_vendor.setdefault(r["source"], []).append(r)
    out: dict[str, dict] = {}
    for vendor, vrows in by_vendor.items():
        cpgs = [r["cpg"] for r in vrows if r["cpg"] is not None]
        if not cpgs:
            continue
        med = statistics.median(cpgs)
        # Example picker: prefer the shortest product-name that sits near the
        # median cpg. Short names tend to be the most generic and least
        # adjective-stuffed ("Morton Iodized Salt, 26 oz" beats "Wellsley
        # Farms Honey Roasted Peanuts with Sea Salt"). Within ±25% of median
        # cpg, pick the row with the shortest name.
        near_med = [r for r in vrows if med * 0.75 <= r["cpg"] <= med * 1.25]
        pool = near_med or vrows
        example = min(pool, key=lambda r: len(r["name"] or ""))
        out[vendor] = {
            "cpg": med,
            "example": example["name"],
            "example_upc": example["upc"],
            "n_candidates": len(vrows),
            "min_cpg": min(cpgs),
            "max_cpg": max(cpgs),
            "median_grams": statistics.median(r["grams"] for r in vrows),
        }
    return out
