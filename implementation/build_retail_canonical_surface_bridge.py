#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION = ROOT / "implementation"
OUT_DIR = IMPLEMENTATION / "output"
LOCAL_CLEAN_ROOT = ROOT.parent / "clean"

REPO_SURFACE_CSV = OUT_DIR / "canonical_surface_normalized_with_product_proxies_CLEANED.csv"
LOCAL_RFT_SURFACE_CSV = LOCAL_CLEAN_ROOT / "canonical_surface_normalized_with_product_proxies_rft_cleaned.csv"
DEFAULT_SURFACE_CSV = REPO_SURFACE_CSV

REPO_API_CACHE_CSV = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
LOCAL_API_CACHE_CSV = LOCAL_CLEAN_ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
DEFAULT_API_CACHE_CSV = REPO_API_CACHE_CSV if REPO_API_CACHE_CSV.exists() else LOCAL_API_CACHE_CSV

OUT_CSV = OUT_DIR / "retail_canonical_surface_bridge.csv"
OUT_SUMMARY = OUT_DIR / "retail_canonical_surface_bridge_summary.json"

FIELDNAMES = [
    "retail_source",
    "upc",
    "name",
    "grams",
    "cents",
    "cpg",
    "search_term",
    "canonical_match_status",
    "match_key",
    "match_field",
    "canonical_surface",
    "canonical_normalized",
    "canonical_shopping_item",
    "product_query",
    "record_type",
    "sr28_code",
    "sr28_description",
    "fndds_code",
    "fndds_description",
    "esha_code",
    "esha_description",
    "hestia_product_proxy_code",
    "product_proxy_review_status",
    "product_proxy_matched_product_count",
    "product_proxy_basis",
    "product_proxy_sr28_anchor_code",
    "product_proxy_sr28_anchor_description",
    "rft_verdict",
    "rft_leaf_id",
    "rft_leaf_canonical",
    "rft_esha_code",
    "rft_esha_desc",
]


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ").replace("|", " ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


def reviewed_nutrition_score(row: dict[str, str]) -> int:
    state = (row.get("nutrition_match_state") or "").strip()
    code_type = (row.get("nutrition_code_type") or "").strip()
    if state in {"sr28_match", "fndds_match"}:
        return 1
    if code_type in {"sr28_reference_match", "fndds_reference_match"}:
        return 1
    return 0


def row_score(row: dict[str, str], key: str, field: str) -> tuple[int, int, int, int, int]:
    return (
        1 if (row.get("record_type") or "") == "ingredient" else 0,
        1 if field == "canonical_surface" and normalize_key(row.get(field, "")) == key else 0,
        1 if field == "product_query" and normalize_key(row.get(field, "")) == key else 0,
        reviewed_nutrition_score(row),
        1 if (row.get("esha_code") or "").strip() else 0,
    )


def build_surface_index(surface_csv: Path) -> dict[str, tuple[dict[str, str], str]]:
    index: dict[str, tuple[dict[str, str], str]] = {}
    with surface_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            for field in ("canonical_surface", "canonical_normalized", "canonical_shopping_item", "product_query"):
                key = normalize_key(row.get(field, ""))
                if not key:
                    continue
                current = index.get(key)
                if current is None or row_score(row, key, field) > row_score(current[0], key, current[1]):
                    index[key] = (row, field)
    return index


def cpg_for(row: dict[str, str]) -> str:
    try:
        grams = float(row.get("grams") or 0)
        cents = float(row.get("cents") or 0)
    except ValueError:
        return ""
    if grams <= 0 or cents <= 0:
        return ""
    return f"{cents / 100.0 / grams:.8f}"


def bridge_row(retail_row: dict[str, str], surface_match: tuple[dict[str, str], str] | None, match_key: str) -> dict[str, str]:
    out = {
        "retail_source": (retail_row.get("source") or "").strip(),
        "upc": (retail_row.get("upc") or "").strip(),
        "name": (retail_row.get("name") or "").strip(),
        "grams": (retail_row.get("grams") or "").strip(),
        "cents": (retail_row.get("cents") or "").strip(),
        "cpg": cpg_for(retail_row),
        "search_term": (retail_row.get("search_term") or "").strip(),
        "canonical_match_status": "unmatched",
        "match_key": match_key,
        "match_field": "",
    }
    if surface_match is None:
        return {field: out.get(field, "") for field in FIELDNAMES}

    surface_row, match_field = surface_match
    out.update(
        {
            "canonical_match_status": "assigned",
            "match_field": match_field,
            "canonical_surface": surface_row.get("canonical_surface", ""),
            "canonical_normalized": surface_row.get("canonical_normalized", ""),
            "canonical_shopping_item": surface_row.get("canonical_shopping_item", ""),
            "product_query": surface_row.get("product_query", ""),
            "record_type": surface_row.get("record_type", ""),
            "sr28_code": surface_row.get("sr28_code", ""),
            "sr28_description": surface_row.get("sr28_description", ""),
            "fndds_code": surface_row.get("fndds_code", ""),
            "fndds_description": surface_row.get("fndds_description", ""),
            "esha_code": surface_row.get("esha_code", ""),
            "esha_description": surface_row.get("esha_description", ""),
            "hestia_product_proxy_code": surface_row.get("hestia_product_proxy_code", ""),
            "product_proxy_review_status": surface_row.get("product_proxy_review_status", ""),
            "product_proxy_matched_product_count": surface_row.get("product_proxy_matched_product_count", ""),
            "product_proxy_basis": surface_row.get("product_proxy_basis", ""),
            "product_proxy_sr28_anchor_code": surface_row.get("product_proxy_sr28_anchor_code", ""),
            "product_proxy_sr28_anchor_description": surface_row.get("product_proxy_sr28_anchor_description", ""),
            "rft_verdict": surface_row.get("rft_verdict", ""),
            "rft_leaf_id": surface_row.get("rft_leaf_id", ""),
            "rft_leaf_canonical": surface_row.get("rft_leaf_canonical", ""),
            "rft_esha_code": surface_row.get("rft_esha_code", ""),
            "rft_esha_desc": surface_row.get("rft_esha_desc", ""),
        }
    )
    return {field: out.get(field, "") for field in FIELDNAMES}


def build_bridge(
    *,
    surface_csv: Path = DEFAULT_SURFACE_CSV,
    api_cache_csv: Path = DEFAULT_API_CACHE_CSV,
    out_csv: Path = OUT_CSV,
    out_summary: Path = OUT_SUMMARY,
) -> dict[str, object]:
    surface_index = build_surface_index(surface_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    assigned = 0
    source_counts: Counter[str] = Counter()
    match_field_counts: Counter[str] = Counter()
    unmatched_terms: Counter[str] = Counter()

    tmp = out_csv.with_suffix(out_csv.suffix + ".tmp")
    with api_cache_csv.open(newline="", encoding="utf-8-sig", errors="replace") as in_handle, tmp.open(
        "w", newline="", encoding="utf-8"
    ) as out_handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in in_handle))
        writer = csv.DictWriter(out_handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for retail_row in reader:
            rows += 1
            source = (retail_row.get("source") or "").strip()
            source_counts[source] += 1
            match_key = normalize_key(retail_row.get("search_term", ""))
            surface_match = surface_index.get(match_key)
            if surface_match:
                assigned += 1
                match_field_counts[surface_match[1]] += 1
            else:
                unmatched_terms[retail_row.get("search_term", "")] += 1
            writer.writerow(bridge_row(retail_row, surface_match, match_key))

    tmp.replace(out_csv)
    summary: dict[str, object] = {
        "api_cache_csv": str(api_cache_csv),
        "surface_csv": str(surface_csv),
        "output_csv": str(out_csv),
        "rows": rows,
        "assigned": assigned,
        "unmatched": rows - assigned,
        "assigned_rate": assigned / rows if rows else 0.0,
        "source_counts": dict(source_counts),
        "match_field_counts": dict(match_field_counts),
        "top_unmatched_terms": unmatched_terms.most_common(25),
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Map retail cache rows to canonical surface rows.")
    parser.add_argument("--surface-csv", type=Path, default=DEFAULT_SURFACE_CSV)
    parser.add_argument("--api-cache-csv", type=Path, default=DEFAULT_API_CACHE_CSV)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()

    print(json.dumps(build_bridge(**vars(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
