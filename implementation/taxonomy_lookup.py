from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DB = Path("/Users/jamiebarton/Desktop/Hestia/api/data/hestia_taxonomy_lookup.db")
TAXONOMY_DB = Path(os.environ.get("HESTIA_TAXONOMY_LOOKUP_DB") or DEFAULT_DB)


@dataclass(frozen=True)
class TaxonomyMetadata:
    canonical_path: str = ""
    retail_leaf_path: str = ""
    canonical_label: str = ""
    product_identity_fixed: str = ""
    htc_code: str = ""
    htc_sku_code: str = ""
    htc_group: str = ""
    htc_family: str = ""
    htc_food: str = ""
    htc_form: str = ""
    htc_processing: str = ""
    htc_ptype: str = ""
    htc_check: str = ""
    htc_confidence: float | None = None
    htc_source: str = ""
    taxonomy_source: str = ""


def normalize_key(value: str) -> str:
    text = (value or "").lower().replace("&", " and ").replace("|", " ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


_EMPTY = TaxonomyMetadata()
_CACHE: dict[tuple, TaxonomyMetadata] = {}


def _connect() -> sqlite3.Connection | None:
    if not TAXONOMY_DB.exists():
        return None
    conn = sqlite3.connect(TAXONOMY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _metadata_from_row(row: sqlite3.Row | None) -> TaxonomyMetadata:
    if row is None:
        return _EMPTY
    keys = set(row.keys())

    def s(name: str) -> str:
        if name not in keys:
            return ""
        value = row[name]
        return "" if value is None else str(value)

    conf = None
    if "htc_confidence" in keys and row["htc_confidence"] is not None:
        try:
            conf = float(row["htc_confidence"])
        except (TypeError, ValueError):
            conf = None
    return TaxonomyMetadata(
        canonical_path=s("canonical_path"),
        retail_leaf_path=s("retail_leaf_path"),
        canonical_label=s("canonical_label"),
        product_identity_fixed=s("product_identity_fixed"),
        htc_code=s("htc_code"),
        htc_sku_code=s("htc_sku_code") or s("htc_code"),
        htc_group=s("htc_group"),
        htc_family=s("htc_family"),
        htc_food=s("htc_food"),
        htc_form=s("htc_form"),
        htc_processing=s("htc_processing"),
        htc_ptype=s("htc_ptype"),
        htc_check=s("htc_check"),
        htc_confidence=conf,
        htc_source=s("htc_source"),
        taxonomy_source=s("source_table"),
    )


def _lookup_ingredient(conn: sqlite3.Connection, key: str) -> TaxonomyMetadata:
    row = conn.execute(
        """
        SELECT i.*
        FROM ingredient_alias a
        JOIN ingredient_taxonomy i ON i.id = a.ingredient_id
        WHERE a.alias_key = ?
          AND i.htc_code IS NOT NULL
          AND i.htc_code != ''
        ORDER BY a.source_priority DESC,
                 CASE a.alias_field
                    WHEN 'title' THEN 4
                    WHEN 'canonical_label' THEN 3
                    WHEN 'product_identity_fixed' THEN 2
                    ELSE 1
                 END DESC,
                 COALESCE(i.recipe_count, 0) DESC,
                 i.id
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    return _metadata_from_row(row)


def _lookup_code(conn: sqlite3.Connection, code_type: str, code: str) -> TaxonomyMetadata:
    row = conn.execute(
        """
        SELECT *
        FROM code_taxonomy
        WHERE code_type = ?
          AND code = ?
          AND htc_code IS NOT NULL
          AND htc_code != ''
        ORDER BY source_priority DESC, row_count DESC
        LIMIT 1
        """,
        (code_type, code),
    ).fetchone()
    return _metadata_from_row(row)


def _lookup_product(conn: sqlite3.Connection, key_type: str, key: str) -> TaxonomyMetadata:
    row = conn.execute(
        """
        SELECT *
        FROM product_taxonomy
        WHERE key_type = ?
          AND product_key = ?
          AND htc_code IS NOT NULL
          AND htc_code != ''
        ORDER BY source_priority DESC
        LIMIT 1
        """,
        (key_type, key),
    ).fetchone()
    return _metadata_from_row(row)


def lookup_taxonomy(
    *,
    item: str = "",
    display: str = "",
    canonical_name: str = "",
    shopping_canonical: str = "",
    fndds_code: str = "",
    sr28_fdc_id: str = "",
    esha_code: str = "",
    upc: str = "",
) -> TaxonomyMetadata:
    cache_key = (
        normalize_key(item),
        normalize_key(display),
        normalize_key(canonical_name),
        normalize_key(shopping_canonical),
        fndds_code,
        sr28_fdc_id,
        esha_code,
        upc,
    )
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    conn = _connect()
    if conn is None:
        _CACHE[cache_key] = _EMPTY
        return _EMPTY
    try:
        if upc:
            meta = _lookup_product(conn, "upc", upc) or _EMPTY
            if not meta.htc_code and upc.lstrip("0") != upc:
                meta = _lookup_product(conn, "upc", upc.lstrip("0"))
            if meta.htc_code:
                _CACHE[cache_key] = meta
                return meta

        for raw in (shopping_canonical, canonical_name, item, display):
            key = normalize_key(raw)
            if not key:
                continue
            meta = _lookup_ingredient(conn, key)
            if meta.htc_code:
                _CACHE[cache_key] = meta
                return meta

        if sr28_fdc_id:
            for code in (sr28_fdc_id, f"SR28-{sr28_fdc_id}"):
                meta = _lookup_code(conn, "sr28_fdc_id" if not code.startswith("SR28-") else "fdc_id", code)
                if meta.htc_code:
                    _CACHE[cache_key] = meta
                    return meta
        if fndds_code:
            meta = _lookup_code(conn, "fndds_code", fndds_code)
            if meta.htc_code:
                _CACHE[cache_key] = meta
                return meta
        if esha_code:
            meta = _lookup_code(conn, "esha_code", esha_code)
            if meta.htc_code:
                _CACHE[cache_key] = meta
                return meta
    finally:
        conn.close()

    _CACHE[cache_key] = _EMPTY
    return _EMPTY


def metadata_kwargs(meta: TaxonomyMetadata) -> dict[str, object]:
    return {
        "canonical_path": meta.canonical_path,
        "retail_leaf_path": meta.retail_leaf_path,
        "canonical_label": meta.canonical_label,
        "product_identity_fixed": meta.product_identity_fixed,
        "htc_code": meta.htc_code,
        "htc_sku_code": meta.htc_sku_code,
        "htc_group": meta.htc_group,
        "htc_family": meta.htc_family,
        "htc_food": meta.htc_food,
        "htc_form": meta.htc_form,
        "htc_processing": meta.htc_processing,
        "htc_ptype": meta.htc_ptype,
        "htc_check": meta.htc_check,
        "htc_confidence": meta.htc_confidence,
        "htc_source": meta.htc_source,
        "taxonomy_source": meta.taxonomy_source,
    }
