from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DB = ROOT / "data" / "master_products.db"
OUT_DIR = ROOT / "implementation" / "output"
OUT_ASSIGNMENTS = OUT_DIR / "product_esha_assignments.csv"
OUT_ROLLUP = OUT_DIR / "product_esha_code_rollup.csv"
OUT_DB = OUT_DIR / "product_esha_lookup.db"

ROLLUP_FIELDS = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "brand_owner",
    "brand_name",
    "branded_food_category",
    "esha_code_count",
    "esha_codes",
    "esha_descriptions",
    "primary_esha_code",
    "primary_esha_description",
    "primary_esha_canonical_title",
    "collision_status",
    "match_reasons",
]


def clean_cell(value: object) -> str:
    return str(value or "").replace("\x00", "")


def csv_rows(path: Path) -> csv.DictReader:
    handle = path.open(newline="", encoding="utf-8", errors="replace")
    return csv.DictReader((line.replace("\x00", "") for line in handle))


def assignment_sort_key(row: dict[str, str]) -> tuple[int, int, int]:
    rank = int(row.get("assignment_rank") or "999999")
    score = int(float(row.get("match_score") or "0"))
    code = int(row.get("esha_code") or "999999") if (row.get("esha_code") or "").isdigit() else 10**9
    return rank, -score, code


def load_assignments() -> dict[str, list[dict[str, str]]]:
    by_gtin: dict[str, list[dict[str, str]]] = defaultdict(list)
    if not OUT_ASSIGNMENTS.exists():
        return by_gtin
    for row in csv_rows(OUT_ASSIGNMENTS):
        gtin = row.get("gtin_upc", "")
        if gtin:
            by_gtin[gtin].append(row)
    for rows in by_gtin.values():
        rows.sort(key=assignment_sort_key)
    return by_gtin


def iter_products():
    sql = """
        SELECT gtin_upc, fdc_id, description, brand_owner, brand_name, branded_food_category
        FROM products
        ORDER BY gtin_upc
    """
    con = sqlite3.connect(PRODUCTS_DB)
    try:
        for row in con.execute(sql):
            yield tuple(clean_cell(value) for value in row)
    finally:
        con.close()


def rollup_row(product: tuple[str, str, str, str, str, str], assignments: list[dict[str, str]]) -> dict[str, str]:
    gtin, fdc_id, description, brand_owner, brand_name, category = product
    primary = assignments[0] if assignments else {}
    codes = [row.get("esha_code", "") for row in assignments if row.get("esha_code")]
    descriptions = [row.get("esha_description", "") for row in assignments if row.get("esha_description")]
    reasons = [f"{row.get('esha_code', '')}:{row.get('match_reason', '')}" for row in assignments if row.get("esha_code")]
    if len(codes) > 1:
        collision_status = "collision"
    elif len(codes) == 1:
        collision_status = "single"
    else:
        collision_status = "unassigned"
    return {
        "gtin_upc": gtin,
        "fdc_id": fdc_id,
        "product_description": description,
        "brand_owner": brand_owner,
        "brand_name": brand_name,
        "branded_food_category": category,
        "esha_code_count": str(len(codes)),
        "esha_codes": "|".join(codes),
        "esha_descriptions": "|".join(descriptions),
        "primary_esha_code": primary.get("esha_code", ""),
        "primary_esha_description": primary.get("esha_description", ""),
        "primary_esha_canonical_title": primary.get("esha_canonical_title", ""),
        "collision_status": collision_status,
        "match_reasons": "|".join(reasons),
    }


def write_rollup_csv() -> dict[str, int]:
    assignments = load_assignments()
    counts = {"products": 0, "assigned": 0, "collisions": 0}
    tmp = OUT_ROLLUP.with_suffix(".csv.tmp")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROLLUP_FIELDS)
        writer.writeheader()
        for product in iter_products():
            gtin = product[0]
            row_assignments = assignments.get(gtin, [])
            writer.writerow(rollup_row(product, row_assignments))
            counts["products"] += 1
            if row_assignments:
                counts["assigned"] += 1
            if len(row_assignments) > 1:
                counts["collisions"] += 1
    tmp.replace(OUT_ROLLUP)
    return counts


def write_rollup_db() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(OUT_DB)
    try:
        con.execute("DROP TABLE IF EXISTS product_esha_code_rollup")
        con.execute(
            """
            CREATE TABLE product_esha_code_rollup (
                gtin_upc TEXT PRIMARY KEY,
                fdc_id TEXT,
                product_description TEXT,
                brand_owner TEXT,
                brand_name TEXT,
                branded_food_category TEXT,
                esha_code_count INTEGER,
                esha_codes TEXT,
                esha_descriptions TEXT,
                primary_esha_code TEXT,
                primary_esha_description TEXT,
                primary_esha_canonical_title TEXT,
                collision_status TEXT,
                match_reasons TEXT
            )
            """
        )
        with OUT_ROLLUP.open(newline="", encoding="utf-8", errors="replace") as handle:
            con.executemany(
                """
                INSERT INTO product_esha_code_rollup VALUES (
                    :gtin_upc, :fdc_id, :product_description, :brand_owner, :brand_name,
                    :branded_food_category, :esha_code_count, :esha_codes, :esha_descriptions,
                    :primary_esha_code, :primary_esha_description, :primary_esha_canonical_title,
                    :collision_status, :match_reasons
                )
                """,
                csv.DictReader((line.replace("\x00", "") for line in handle)),
            )
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_esha_code_rollup_primary ON product_esha_code_rollup(primary_esha_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_esha_code_rollup_status ON product_esha_code_rollup(collision_status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_esha_code_rollup_category ON product_esha_code_rollup(branded_food_category)")
        con.commit()
    finally:
        con.close()


def build_rollup(write_db: bool = True) -> dict[str, int | str]:
    counts = write_rollup_csv()
    if write_db:
        write_rollup_db()
    return {
        **counts,
        "rollup_csv": str(OUT_ROLLUP),
        "lookup_db": str(OUT_DB),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_rollup(write_db=not args.no_db), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
