#!/usr/bin/env python3
"""Rebuild OUR priced products db from the raw walmart/kroger cache.

Fixes:
  1. Drop Walmart marketplace items (third-party sellers like the $962 50-lb
     mace bag from Sapna Foods). Only keep marketplace=False AND
     fulfilledByWalmart=True AND stock=Available.
  2. Preserve seller_info, brand, marketplace flag — never lose this metadata
     again.
  3. Tag every product with our HTC encoder over the product name (using BFC
     data when available from cache).
  4. Match each product to its SR-28 fdc using the same logic as
     build_ingredient_sr28_map.py.

Source: Hestia's api_cache.db (12,189 kroger_search + 7,387 walmart_search
        — these are the actual fetched results we paid for)
Output: recipe_pricing/data/priced_products_v2.db
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htc.encoder import encode  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HESTIA_CACHE = Path("/Users/jamiebarton/Desktop/Hestia/api/data/api_cache.db")
OUT_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"


# ── Walmart size → grams parser ─────────────────────────────────────────
SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(?:x\s*(\d+(?:\.\d+)?)\s*)?"           # multipack: "12 x 8 fl oz"
    r"(oz|fl\.?\s*oz|lb|lbs|pound|g|gm|gram|kg|ml|liter|litre|l)\b",
    re.I,
)
COUNT_RE = re.compile(r"(\d+)\s*(?:ct|count|pack|pk)\b", re.I)
EGG_COUNT_RE = re.compile(r"(\d+)\s*(?:large|medium|small|jumbo|extra\s+large|ct|count)?\b", re.I)
UNIT_TO_G = {
    "oz": 28.3495, "fl oz": 29.5735, "fl. oz": 29.5735, "fl.oz": 29.5735,
    "fl  oz": 29.5735,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592,
    "g": 1.0, "gm": 1.0, "gram": 1.0, "kg": 1000.0,
    "ml": 1.0, "liter": 1000.0, "litre": 1000.0, "l": 1000.0,
}

EGG_SIZE_GRAMS = {
    "jumbo": 70.0,
    "extra large": 56.0,
    "large": 50.0,
    "medium": 44.0,
    "small": 38.0,
}


def parse_grams(size: str, name: str = "") -> float | None:
    """Parse a Walmart `size` field like '24 oz', '12 x 8 fl oz', '50 lb. Case'.
    Falls back to scanning the name. Returns grams or None."""
    text = (size or "") + " " + (name or "")
    m = SIZE_RE.search(text)
    if m:
        per = float(m.group(1))
        mult = float(m.group(2)) if m.group(2) else 1.0
        unit = m.group(3).lower().replace(".", "").replace("  ", " ").strip()
        # normalize "fl oz" variants
        if "fl" in unit and "oz" in unit:
            unit = "fl oz"
        # "50 lb. Case" → 50 lb
        if unit in UNIT_TO_G:
            grams = per * mult * UNIT_TO_G[unit]
            # Sanity-cap: a single grocery package is rarely > 25kg.
            # If we get something huge, it's almost certainly a count parsed
            # as kg or a wholesale case we don't want anyway.
            if grams > 25_000:
                return None
            if grams < 1:
                return None
            return grams
    if re.search(r"\beggs?\b", name or "", re.I):
        count_match = COUNT_RE.search(text) or EGG_COUNT_RE.search(size or "")
        if count_match:
            count = int(count_match.group(1))
            size_lc = f"{size or ''} {name or ''}".lower()
            grams_per_egg = 50.0
            for label, weight in EGG_SIZE_GRAMS.items():
                if label in size_lc:
                    grams_per_egg = weight
                    break
            grams = count * grams_per_egg
            if 100 <= grams <= 6000:
                return grams
    return None


# ── BFC mapping for HTC encoding ───────────────────────────────────────
def category_path_to_bfc(path: str) -> str:
    """Walmart's categoryPath like 'Home Page/Food/Beverages/Juices/Apple Juice'
    → a BFC-shaped string the HTC encoder can use."""
    if not path:
        return ""
    parts = [p.strip() for p in path.split("/") if p.strip()]
    # drop the leading 'Home Page' / 'Food' levels
    parts = [p for p in parts if p.lower() not in ("home page", "food")]
    return " ".join(parts[:3])


# ── Build ────────────────────────────────────────────────────────────────
def main() -> int:
    OUT_DB.parent.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        OUT_DB.unlink()
    out = sqlite3.connect(str(OUT_DB))
    out.execute("""
        CREATE TABLE priced_products (
            source           TEXT NOT NULL,        -- walmart | kroger
            upc              TEXT,
            name             TEXT NOT NULL,
            brand            TEXT,
            grams            REAL,
            cents            INTEGER NOT NULL,
            cpg              REAL,
            size_display     TEXT,
            category_path    TEXT,
            seller           TEXT,                 -- Walmart.com | Kroger | third-party name
            marketplace      INTEGER DEFAULT 0,    -- 1 = third-party seller (we filter these out)
            fulfilled_walmart INTEGER DEFAULT 0,
            available        INTEGER DEFAULT 1,
            stock            TEXT,
            search_term      TEXT,
            htc_code         TEXT,
            htc_group        TEXT,
            htc_confidence   REAL
        )
    """)
    out.execute("CREATE INDEX idx_pp_upc ON priced_products(upc)")
    out.execute("CREATE INDEX idx_pp_htc_group ON priced_products(htc_group)")
    out.execute("CREATE INDEX idx_pp_source ON priced_products(source)")
    out.commit()

    hc = sqlite3.connect(str(HESTIA_CACHE))

    # ── Walmart pass ────────────────────────────────────────────────────
    n_walmart_total = 0
    n_walmart_kept = 0
    n_walmart_dropped_mp = 0
    n_walmart_dropped_unavail = 0
    n_walmart_dropped_size = 0
    walmart_rows = []
    for cache_key, raw in hc.execute(
        "SELECT cache_key, raw_json FROM api_cache WHERE source='walmart_search'"
    ):
        try:
            items = json.loads(raw)
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        search_term = cache_key.rsplit(":", 1)[0]
        for it in items:
            n_walmart_total += 1
            mp = bool(it.get("marketplace"))
            fbw = bool(it.get("fulfilledByWalmart"))
            avail = it.get("stock") == "Available" and it.get("availableOnline")
            if mp or not fbw:
                n_walmart_dropped_mp += 1
                continue
            if not avail:
                n_walmart_dropped_unavail += 1
                continue
            size = it.get("size") or ""
            name = it.get("name") or ""
            grams = parse_grams(size, name)
            if grams is None:
                n_walmart_dropped_size += 1
                continue
            sale = it.get("salePrice") or it.get("msrp")
            if not sale or float(sale) <= 0:
                continue
            cents = int(round(float(sale) * 100))
            seller = it.get("sellerInfo") or "Walmart.com"
            cat_path = it.get("categoryPath") or ""
            bfc = category_path_to_bfc(cat_path)
            h = encode(category=bfc, description=name)
            walmart_rows.append((
                "walmart",
                str(it.get("upc") or it.get("itemId") or "").strip(),
                name, it.get("brandName") or "",
                grams, cents, cents / grams if grams else 0,
                size, cat_path, seller,
                int(mp), int(fbw), 1, "Available",
                search_term,
                h.code, h.group, h.confidence,
            ))
            n_walmart_kept += 1
    out.executemany(
        "INSERT INTO priced_products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        walmart_rows,
    )
    out.commit()

    # ── Kroger pass ─────────────────────────────────────────────────────
    n_kroger_total = 0
    n_kroger_kept = 0
    n_kroger_dropped = 0
    kroger_rows = []
    for cache_key, raw in hc.execute(
        "SELECT cache_key, raw_json FROM api_cache WHERE source='kroger_search'"
    ):
        try:
            items = json.loads(raw)
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        search_term = cache_key.rsplit(":", 1)[0]
        for it in items:
            n_kroger_total += 1
            grams = it.get("grams")
            cents = it.get("price_cents")
            name = it.get("name") or ""
            if not grams or not cents or grams <= 0 or cents <= 0:
                n_kroger_dropped += 1
                continue
            try:
                grams = float(grams)
                cents = int(cents)
            except (TypeError, ValueError):
                n_kroger_dropped += 1
                continue
            if grams > 25_000:        # same sanity cap
                n_kroger_dropped += 1
                continue
            meta = it.get("product_meta") or {}
            if isinstance(meta, str):
                try: meta = json.loads(meta)
                except: meta = {}
            brand = meta.get("brand") or ""
            cats = meta.get("categories") or []
            bfc = " ".join(cats[:3]) if cats else ""
            h = encode(category=bfc, description=name)
            kroger_rows.append((
                "kroger",
                str(it.get("upc") or "").strip(),
                name, brand,
                grams, cents, cents / grams,
                it.get("display") or "",
                bfc,
                "Kroger",
                0, 1, 1, "Available",
                search_term,
                h.code, h.group, h.confidence,
            ))
            n_kroger_kept += 1
    out.executemany(
        "INSERT INTO priced_products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        kroger_rows,
    )
    out.commit()

    # ── Stats ──────────────────────────────────────────────────────────
    print("=" * 75)
    print("OUR REBUILT priced_products_v2.db")
    print("=" * 75)
    print()
    print("WALMART pass:")
    print(f"  raw items in cache:                   {n_walmart_total:,}")
    print(f"  dropped (marketplace 3rd-party):      {n_walmart_dropped_mp:,}  ({n_walmart_dropped_mp/n_walmart_total:.1%})")
    print(f"  dropped (out-of-stock/unavailable):   {n_walmart_dropped_unavail:,}")
    print(f"  dropped (couldn't parse size):        {n_walmart_dropped_size:,}")
    print(f"  KEPT (Walmart-direct, available):     {n_walmart_kept:,}  ({n_walmart_kept/n_walmart_total:.1%})")
    print()
    print("KROGER pass:")
    print(f"  raw items in cache:                   {n_kroger_total:,}")
    print(f"  dropped (no grams/price/oversize):    {n_kroger_dropped:,}")
    print(f"  KEPT:                                 {n_kroger_kept:,}")
    print()
    total = n_walmart_kept + n_kroger_kept
    print(f"TOTAL clean priced products:            {total:,}")
    # HTC group distribution
    print()
    print("HTC group distribution (real food only):")
    for r in out.execute("""
        SELECT htc_group, COUNT(*) FROM priced_products
        WHERE htc_group NOT IN ('0','N')
        GROUP BY htc_group ORDER BY 2 DESC
    """):
        print(f"  {r[0]}: {r[1]:,}")
    print(f"\n→ {OUT_DB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
