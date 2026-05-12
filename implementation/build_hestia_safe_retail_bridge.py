#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from build_retail_canonical_surface_bridge import OUT_CSV as DEFAULT_IN_CSV
from surface_lab_calculator import LabProduct, _review_products, normalize_key


OUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_OUT_CSV = OUT_DIR / "retail_canonical_surface_bridge.hestia_safe.csv"
DEFAULT_OUT_SUMMARY = OUT_DIR / "retail_canonical_surface_bridge.hestia_safe.summary.json"


def _canonical_for(row: dict[str, str]) -> str:
    return (
        row.get("canonical_shopping_item")
        or row.get("canonical_surface")
        or row.get("canonical_normalized")
        or row.get("search_term")
        or ""
    ).strip()


def _product_for(row: dict[str, str]) -> LabProduct:
    retail_source = (row.get("retail_source") or row.get("source") or "").strip()
    return LabProduct(
        gtin_upc=(row.get("upc") or row.get("gtin_upc") or "").strip(),
        description=(row.get("name") or "").strip(),
        brand_name=retail_source,
        category="",
        source=f"retail_surface_bridge:{retail_source}" if retail_source else "retail_surface_bridge",
    )


def _valid_package(row: dict[str, str]) -> bool:
    try:
        grams = float(row.get("grams") or 0)
        cents = float(row.get("cents") or 0)
    except ValueError:
        return False
    return 0 < grams <= 50_000 and 0 < cents <= 100_000


def build_safe_bridge(
    *,
    in_csv: Path = DEFAULT_IN_CSV,
    out_csv: Path = DEFAULT_OUT_CSV,
    out_summary: Path = DEFAULT_OUT_SUMMARY,
) -> dict[str, object]:
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    kept = 0
    skipped: Counter[str] = Counter()
    reject_reasons: Counter[str] = Counter()
    kept_by_surface: Counter[str] = Counter()

    tmp = out_csv.with_suffix(out_csv.suffix + ".tmp")
    with in_csv.open(newline="", encoding="utf-8-sig", errors="replace") as in_handle, tmp.open(
        "w", newline="", encoding="utf-8"
    ) as out_handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in in_handle))
        base_fields = list(reader.fieldnames or [])
        extra_fields = ["hestia_bridge_decision", "hestia_bridge_reason"]
        writer = csv.DictWriter(out_handle, fieldnames=base_fields + [f for f in extra_fields if f not in base_fields])
        writer.writeheader()

        for row in reader:
            rows += 1
            if (row.get("canonical_match_status") or "").strip() != "assigned":
                skipped["not_assigned"] += 1
                continue
            if not row.get("fndds_code"):
                skipped["missing_fndds"] += 1
                continue
            if not _valid_package(row):
                skipped["bad_package_numeric"] += 1
                continue
            canonical = _canonical_for(row)
            if not canonical:
                skipped["missing_canonical"] += 1
                continue
            product = _product_for(row)
            accepted, rejected = _review_products([product], canonical, limit=1)
            if not accepted:
                reason = rejected[0].reason if rejected else "rejected_by_product_validator"
                skipped["validator_reject"] += 1
                reject_reasons[reason] += 1
                continue

            row["hestia_bridge_decision"] = "accept"
            row["hestia_bridge_reason"] = accepted[0].reason
            writer.writerow(row)
            kept += 1
            kept_by_surface[normalize_key(canonical)] += 1

    tmp.replace(out_csv)
    summary: dict[str, object] = {
        "input_csv": str(in_csv),
        "output_csv": str(out_csv),
        "rows": rows,
        "kept": kept,
        "kept_rate": kept / rows if rows else 0.0,
        "skipped": dict(skipped),
        "top_reject_reasons": reject_reasons.most_common(40),
        "top_kept_surfaces": kept_by_surface.most_common(40),
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter the retail bridge to rows safe enough for Hestia package pricing.")
    parser.add_argument("--in-csv", type=Path, default=DEFAULT_IN_CSV)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    args = parser.parse_args()

    print(json.dumps(build_safe_bridge(**vars(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
