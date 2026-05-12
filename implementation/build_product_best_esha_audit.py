from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
import sqlite3
import argparse


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "implementation" / "output"
ROLLUP_CSV = OUT_DIR / "product_esha_code_rollup.csv"
LEGACY_BEST_MAP_CSV = OUT_DIR / "product_to_best_esha_map.csv"
PRODUCTS_DB = ROOT / "data" / "master_products.db"
OUT_CSV = OUT_DIR / "product_to_best_esha_audit.csv"
OUT_SUMMARY = OUT_DIR / "product_to_best_esha_audit_summary.json"

FIELDNAMES = [
    "gtin_upc",
    "fdc_id",
    "product_description",
    "branded_food_category",
    "brand_owner",
    "brand_name",
    "best_esha_code",
    "best_esha_description",
    "best_esha_canonical_title",
    "collision_status",
    "esha_code_count",
    "all_esha_codes",
]


def normalize_gtin(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def build_best_esha_audit_from_rollup() -> dict[str, int | str]:
    if not ROLLUP_CSV.exists():
        raise FileNotFoundError(f"missing rollup csv: {ROLLUP_CSV}")

    status_counts: Counter[str] = Counter()
    rows_written = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_suffix(".csv.tmp")

    with ROLLUP_CSV.open(newline="", encoding="utf-8", errors="replace") as src, tmp.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader((line.replace("\x00", "") for line in src))
        writer = csv.DictWriter(dst, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in reader:
            status = (row.get("collision_status") or "").strip() or "unassigned"
            status_counts[status] += 1
            rows_written += 1
            writer.writerow(
                {
                    "gtin_upc": row.get("gtin_upc", ""),
                    "fdc_id": row.get("fdc_id", ""),
                    "product_description": row.get("product_description", ""),
                    "branded_food_category": row.get("branded_food_category", ""),
                    "brand_owner": row.get("brand_owner", ""),
                    "brand_name": row.get("brand_name", ""),
                    "best_esha_code": row.get("primary_esha_code", ""),
                    "best_esha_description": row.get("primary_esha_description", ""),
                    "best_esha_canonical_title": row.get("primary_esha_canonical_title", ""),
                    "collision_status": status,
                    "esha_code_count": row.get("esha_code_count", ""),
                    "all_esha_codes": row.get("esha_codes", ""),
                }
            )

    tmp.replace(OUT_CSV)
    summary = {
        "products": rows_written,
        "assigned_single": status_counts.get("single", 0),
        "assigned_collision": status_counts.get("collision", 0),
        "unassigned": status_counts.get("unassigned", 0),
        "audit_csv": str(OUT_CSV),
        "source_rollup_csv": str(ROLLUP_CSV),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def iter_products() -> list[tuple[str, str, str, str, str, str]]:
    sql = """
        SELECT gtin_upc, fdc_id, description, brand_owner, brand_name, branded_food_category
        FROM products
        ORDER BY gtin_upc
    """
    con = sqlite3.connect(PRODUCTS_DB)
    try:
        return list(con.execute(sql))
    finally:
        con.close()


def load_legacy_best_map() -> dict[str, dict[str, str]]:
    if not LEGACY_BEST_MAP_CSV.exists():
        raise FileNotFoundError(f"missing legacy best map csv: {LEGACY_BEST_MAP_CSV}")
    by_gtin: dict[str, dict[str, str]] = {}
    with LEGACY_BEST_MAP_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            gtin = normalize_gtin(row.get("gtin_upc", ""))
            if gtin and gtin not in by_gtin:
                by_gtin[gtin] = row
    return by_gtin


def build_best_esha_audit_from_legacy_best_map() -> dict[str, int | str]:
    best_map = load_legacy_best_map()
    status_counts: Counter[str] = Counter()
    rows_written = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_suffix(".csv.tmp")

    with tmp.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=FIELDNAMES)
        writer.writeheader()
        for gtin, fdc_id, description, brand_owner, brand_name, category in iter_products():
            product = best_map.get(normalize_gtin(gtin), {})
            has_best = bool(product.get("best_esha_code", ""))
            status = "single" if has_best else "unassigned"
            status_counts[status] += 1
            rows_written += 1
            writer.writerow(
                {
                    "gtin_upc": gtin,
                    "fdc_id": fdc_id,
                    "product_description": description,
                    "branded_food_category": category,
                    "brand_owner": brand_owner,
                    "brand_name": brand_name,
                    "best_esha_code": product.get("best_esha_code", ""),
                    "best_esha_description": product.get("best_esha_description", ""),
                    "best_esha_canonical_title": product.get("best_esha_description", ""),
                    "collision_status": status,
                    "esha_code_count": "1" if has_best else "0",
                    "all_esha_codes": product.get("best_esha_code", ""),
                }
            )

    tmp.replace(OUT_CSV)
    summary = {
        "products": rows_written,
        "assigned_single": status_counts.get("single", 0),
        "assigned_collision": 0,
        "unassigned": status_counts.get("unassigned", 0),
        "audit_csv": str(OUT_CSV),
        "source_best_map_csv": str(LEGACY_BEST_MAP_CSV),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def build_best_esha_audit(source: str = "rollup") -> dict[str, int | str]:
    if source == "legacy-best-map":
        return build_best_esha_audit_from_legacy_best_map()
    return build_best_esha_audit_from_rollup()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("rollup", "legacy-best-map"), default="rollup")
    args = parser.parse_args()
    print(json.dumps(build_best_esha_audit(source=args.source), indent=2))


if __name__ == "__main__":
    main()
