"""Load packet substrate from local sources (no live retailer calls).

For each fndds_code we surface:
- audit candidates from full_corpus_enriched.csv (canonical/variant/flavor/form/processing/portions)
- packages the planner picks from (food_packages_final.db.packages with product_meta parsed)
"""
from __future__ import annotations
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from ruvs.schemas import ProductCandidate

DEFAULT_AUDIT_CSV = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2/full_corpus_enriched.csv")
DEFAULT_PACKAGES_DB = Path("/Users/jamiebarton/Desktop/Hestia/api/data/food_packages_final.db")


def load_audit_by_fndds(csv_path: Path = DEFAULT_AUDIT_CSV, top_per_code: int = 5) -> dict[str, list[dict]]:
    """{fndds_code: [audit_row_dict, ...]} sorted by match_score desc, top_per_code each."""
    by_code: dict[str, list[dict]] = defaultdict(list)
    with csv_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("fndds_code") or "").strip()
            if not code:
                continue
            try:
                score = float(row.get("match_score") or 0.0)
            except ValueError:
                score = 0.0
            by_code[code].append({
                "fdc_id": row.get("fdc_id") or "",
                "title": row.get("title") or "",
                "canonical_path": row.get("canonical_path") or "",
                "canonical_label": row.get("product_identity_fixed") or row.get("title") or "",
                "variant": row.get("variant") or "",
                "flavor": row.get("flavor") or "",
                "modifier": row.get("modifier") or "",
                "fndds_code": code,
                "sr28_code": row.get("sr28_code") or "",
                "esha_code": row.get("esha_code") or "",
                "match_score": score,
                "portions_json": row.get("portions_json") or "",
            })
    # sort + truncate
    for code, rows in by_code.items():
        rows.sort(key=lambda r: r["match_score"], reverse=True)
        by_code[code] = rows[:top_per_code]
    return dict(by_code)


def load_packages_by_fndds(
    db_path: Path = DEFAULT_PACKAGES_DB, top_per_code: int = 6,
) -> dict[str, dict[str, list[ProductCandidate]]]:
    """{fndds_code: {'walmart': [ProductCandidate,...], 'kroger': [ProductCandidate,...]}}.

    Reads food_packages_final.db, parses product_meta JSON, splits by retailer.
    These ARE the candidates the planner picks from at runtime.
    """
    out: dict[str, dict[str, list[ProductCandidate]]] = defaultdict(lambda: {"walmart": [], "kroger": []})
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT fndds_code, food_description, package_weight_grams, "
            "walmart_price_cents, kroger_price_cents, source, product_meta, confidence_tier "
            "FROM packages "
            "ORDER BY fndds_code, confidence_tier DESC, package_weight_grams"
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        fcode = str(r[0])
        food_desc = r[1] or ""
        weight = float(r[2] or 0.0)
        wp_cents = r[3]
        kp_cents = r[4]
        source = (r[5] or "").lower()
        try:
            meta = json.loads(r[6]) if r[6] else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        # Walmart variant
        wm_name = meta.get("walmart_name") or ""
        if wm_name or "walmart" in source or wp_cents:
            pc = ProductCandidate(
                upc=str(meta.get("upc") or ""),
                title=wm_name or food_desc,
                grams=weight,
                price_cents=int(wp_cents or 0),
                retail="walmart",
                raw={
                    "food_description": food_desc,
                    "brand": meta.get("walmart_brand") or meta.get("brand") or "",
                    "walmart_item_id": meta.get("walmart_item_id"),
                    "categories": meta.get("categories") or [],
                    "ingredient_statement": meta.get("ingredient_statement") or "",
                    "confidence_tier": r[7],
                    "source": source,
                },
            )
            out[fcode]["walmart"].append(pc)
        # Kroger variant
        kr_name = meta.get("name") or ""
        if (kr_name and not wm_name) or "kroger" in source or kp_cents:
            pc = ProductCandidate(
                upc=str(meta.get("upc") or ""),
                title=kr_name or food_desc,
                grams=weight,
                price_cents=int(kp_cents or 0),
                retail="kroger",
                raw={
                    "food_description": food_desc,
                    "brand": meta.get("brand") or "",
                    "categories": meta.get("categories") or [],
                    "ingredient_statement": meta.get("ingredient_statement") or "",
                    "confidence_tier": r[7],
                    "source": source,
                },
            )
            out[fcode]["kroger"].append(pc)
    # cap each retailer per fndds at top_per_code
    for fcode in out:
        out[fcode]["walmart"] = out[fcode]["walmart"][:top_per_code]
        out[fcode]["kroger"] = out[fcode]["kroger"][:top_per_code]
    return dict(out)


def fndds_food_description(db_path: Path = DEFAULT_PACKAGES_DB) -> dict[str, str]:
    """{fndds_code: food_description} - the canonical name per ingredient."""
    out: dict[str, str] = {}
    conn = sqlite3.connect(db_path)
    try:
        for fcode, desc in conn.execute("SELECT DISTINCT fndds_code, food_description FROM packages WHERE food_description IS NOT NULL"):
            out[str(fcode)] = desc
    finally:
        conn.close()
    return out
