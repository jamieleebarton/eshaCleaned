"""Match a canonical's codes to products via the product_code_tags sidecar.

Order of preference: cleaned overlay (D) > FNDDS crosswalk (A) > category (B)
> normalizer (C). When the cleaned overlay is present for a given code, ONLY
cleaned products are returned for that code's tag_type (overrides A/B/C for that code).
"""
from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from schema import ProductCandidate
from price_product_filters import is_retail_price_reject, passes_retail_identity

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "master_products.db"


def _fts_query(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def match_products(
    sr28_fdc_id: str,
    fndds_code: str,
    pseudo_code: str,
    canonical: str = "",
) -> list[ProductCandidate]:
    if not any([sr28_fdc_id, fndds_code, pseudo_code]):
        return []
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        out: list[ProductCandidate] = []
        seen_gtins: set[str] = set()
        for tag_type, code in (("pseudo", pseudo_code), ("fndds", fndds_code), ("sr28", sr28_fdc_id)):
            if not code:
                continue
            # Check if there's a D_cleaned_overlay for this (tag_type, code). If yes, ONLY use D.
            overlay_hit = con.execute(
                "SELECT 1 FROM product_code_tags WHERE tag_type=? AND code=? AND source='D_cleaned_overlay' LIMIT 1",
                (tag_type, code),
            ).fetchone()
            if overlay_hit:
                rows = con.execute(
                    """SELECT p.gtin_upc, p.description, p.brand_name, p.branded_food_category, t.source
                    FROM products p JOIN product_code_tags t USING(gtin_upc)
                    WHERE t.tag_type=? AND t.code=? AND t.source='D_cleaned_overlay'""",
                    (tag_type, code),
                ).fetchall()
            else:
                rows = con.execute(
                    """SELECT p.gtin_upc, p.description, p.brand_name, p.branded_food_category, t.source
                    FROM products p JOIN product_code_tags t USING(gtin_upc)
                    WHERE t.tag_type=? AND t.code=?""",
                    (tag_type, code),
                ).fetchall()
            for r in rows:
                if r["gtin_upc"] in seen_gtins:
                    continue
                name = r["description"] or ""
                category = r["branded_food_category"] or ""
                if canonical and is_retail_price_reject(name, canonical):
                    continue
                if canonical and not passes_retail_identity(name, canonical, category):
                    continue
                seen_gtins.add(r["gtin_upc"])
                out.append(ProductCandidate(
                    gtin_upc=r["gtin_upc"],
                    description=name,
                    brand_name=r["brand_name"] or "",
                    branded_food_category=category,
                    source=r["source"],
                ))
        return out
    finally:
        con.close()


def search_products(query: str, limit: int = 25, canonical: str = "") -> list[ProductCandidate]:
    fts = _fts_query(query)
    if not fts:
        return []
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT p.gtin_upc, p.description, p.brand_name, p.branded_food_category, 'fts_search' AS source
            FROM products_fts f
            JOIN products p ON p.rowid = f.rowid
            WHERE products_fts MATCH ?
            ORDER BY bm25(products_fts)
            LIMIT ?""",
            (fts, limit),
        ).fetchall()
        out: list[ProductCandidate] = []
        for row in rows:
            name = row["description"] or ""
            category = row["branded_food_category"] or ""
            if canonical and is_retail_price_reject(name, canonical):
                continue
            if canonical and not passes_retail_identity(name, canonical, category):
                continue
            out.append(
                ProductCandidate(
                    gtin_upc=row["gtin_upc"],
                    description=name,
                    brand_name=row["brand_name"] or "",
                    branded_food_category=category,
                    source=row["source"],
                )
            )
        return out
    finally:
        con.close()
