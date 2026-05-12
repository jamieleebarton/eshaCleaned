#!/usr/bin/env python3
from __future__ import annotations

import csv
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED_CSV = ROOT / "data" / "manual_master_products.csv"
MASTER_DB = ROOT / "data" / "master_products.db"


PRODUCT_COLUMNS = [
    "gtin_upc",
    "fdc_id",
    "description",
    "brand_owner",
    "brand_name",
    "branded_food_category",
    "package_weight",
    "serving_size",
    "serving_size_unit",
    "household_serving",
    "store_id",
    "source",
    "submitted_by",
    "submitted_at",
    "submission_confidence",
]


def _float_or_none(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    return float(value)


def _int_or_none(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    return int(value)


def _row_values(row: dict[str, str], submitted_at: int) -> dict[str, object]:
    return {
        "gtin_upc": row["gtin_upc"].strip(),
        "fdc_id": _int_or_none(row.get("fdc_id", "")),
        "description": row["description"].strip(),
        "brand_owner": row.get("brand_owner", "").strip(),
        "brand_name": row.get("brand_name", "").strip(),
        "branded_food_category": row.get("branded_food_category", "").strip(),
        "package_weight": row.get("package_weight", "").strip(),
        "serving_size": _float_or_none(row.get("serving_size", "")),
        "serving_size_unit": row.get("serving_size_unit", "").strip(),
        "household_serving": row.get("household_serving", "").strip(),
        "store_id": row.get("store_id", "").strip(),
        "source": row.get("source", "manual_master_products").strip() or "manual_master_products",
        "submitted_by": row.get("submitted_by", "codex").strip() or "codex",
        "submitted_at": submitted_at,
        "submission_confidence": _float_or_none(row.get("submission_confidence", "")),
    }


def _upsert_product(conn: sqlite3.Connection, values: dict[str, object]) -> None:
    placeholders = ", ".join("?" for _ in PRODUCT_COLUMNS)
    columns = ", ".join(PRODUCT_COLUMNS)
    updates = ", ".join(
        [
            "fdc_id = COALESCE(products.fdc_id, excluded.fdc_id)",
            "description = excluded.description",
            "brand_owner = excluded.brand_owner",
            "brand_name = excluded.brand_name",
            "branded_food_category = excluded.branded_food_category",
            "package_weight = excluded.package_weight",
            "serving_size = excluded.serving_size",
            "serving_size_unit = excluded.serving_size_unit",
            "household_serving = excluded.household_serving",
            "store_id = excluded.store_id",
            "source = excluded.source",
            "submitted_by = excluded.submitted_by",
            "submitted_at = excluded.submitted_at",
            "submission_confidence = excluded.submission_confidence",
        ]
    )
    conn.execute(
        f"""
        INSERT INTO products ({columns})
        VALUES ({placeholders})
        ON CONFLICT(gtin_upc) DO UPDATE SET {updates}
        """,
        [values[column] for column in PRODUCT_COLUMNS],
    )


def _insert_tags(conn: sqlite3.Connection, row: dict[str, str]) -> int:
    gtin = row["gtin_upc"].strip()
    default_source = row.get("source", "manual_master_products").strip() or "manual_master_products"
    tag_sources = [
        source.strip()
        for source in (row.get("tag_sources") or default_source).replace(";", "|").split("|")
        if source.strip()
    ]
    if default_source not in tag_sources:
        tag_sources.append(default_source)
    inserted = 0
    for tag_type, field in (("sr28", "sr28_code"), ("fndds", "fndds_code")):
        for code in (row.get(field) or "").replace(";", "|").split("|"):
            code = code.strip()
            if not code:
                continue
            for source in tag_sources:
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO product_code_tags (gtin_upc, tag_type, code, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (gtin, tag_type, code, source),
                )
                if conn.total_changes > before:
                    inserted += 1
    return inserted


def apply_seed(seed_csv: Path = SEED_CSV, master_db: Path = MASTER_DB) -> dict[str, int]:
    if not seed_csv.exists():
        raise SystemExit(f"missing seed CSV: {seed_csv}")
    if not master_db.exists():
        raise SystemExit(f"missing master DB: {master_db}")

    submitted_at = int(time.time())
    products = 0
    tags = 0
    with seed_csv.open(newline="", encoding="utf-8-sig") as handle, sqlite3.connect(master_db) as conn:
        for row in csv.DictReader(handle):
            if not (row.get("gtin_upc") or "").strip() or not (row.get("description") or "").strip():
                continue
            _upsert_product(conn, _row_values(row, submitted_at))
            products += 1
            tags += _insert_tags(conn, row)
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
    return {"products_upserted": products, "tags_inserted": tags}


def main() -> None:
    stats = apply_seed()
    print(stats)


if __name__ == "__main__":
    main()
