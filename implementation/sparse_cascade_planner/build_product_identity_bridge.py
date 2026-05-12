#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "implementation" / "output" / "sparse_cascade_planner"
DEFAULT_API_CACHE_CSV = ROOT / "recipe_pricing" / "data" / "api_cache_products.csv"
DEFAULT_OUT_CSV = OUT_DIR / "product_identity_bridge.csv"
DEFAULT_OUT_SUMMARY = OUT_DIR / "product_identity_bridge.summary.json"
MAX_PRODUCT_IDENTITY_CENTS_PER_GRAM = 10.0


@dataclass(frozen=True)
class ProductIdentity:
    product_identity: str
    ingredient_key: str
    food_description: str
    classification_reason: str


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str) -> set[str]:
    tokens: set[str] = set()
    for token in normalize_text(title).split():
        tokens.add(token)
        if len(token) > 3 and token.endswith("s"):
            tokens.add(token[:-1])
        if token == "walnuts":
            tokens.add("walnut")
        if token == "muffins":
            tokens.add("muffin")
    return tokens


def classify_product_identity(title: str) -> ProductIdentity | None:
    key = normalize_text(title)
    tokens = title_tokens(title)
    if not key:
        return None

    if not {"banana", "muffin"} <= tokens:
        return None

    is_mix = "mix" in tokens
    is_baked = not is_mix and not (tokens & {"batter", "bread"})
    has_nut = bool(tokens & {"nut", "walnut"})
    other_flavor = tokens & {"blueberry", "chocolate", "chip", "chunk", "cinnamon"}
    variety_or_case = tokens & {"assortment", "case", "variety"}

    if is_mix:
        if "batter" in tokens or "case" in tokens:
            return None
        if has_nut and not other_flavor:
            return ProductIdentity(
                product_identity="banana nut muffin mix",
                ingredient_key="FNDDS:58610005",
                food_description="banana nut muffin mix",
                classification_reason="title_gate:banana_nut_muffin_mix",
            )
        if not has_nut and not other_flavor:
            return ProductIdentity(
                product_identity="banana muffin mix",
                ingredient_key="FNDDS:58610004",
                food_description="banana muffin mix",
                classification_reason="title_gate:banana_muffin_mix",
            )
        return None

    if is_baked:
        if variety_or_case or other_flavor:
            return None
        if has_nut:
            return ProductIdentity(
                product_identity="banana nut muffin",
                ingredient_key="ESHA:18966",
                food_description="Muffin, banana nut",
                classification_reason="title_gate:banana_nut_muffin_baked",
            )
        return ProductIdentity(
            product_identity="banana muffin",
            ingredient_key="ESHA:25738",
            food_description="Muffin, banana",
            classification_reason="title_gate:banana_muffin_baked",
        )

    return None


def _row_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        (row.get("source") or "").strip(),
        (row.get("upc") or "").strip(),
        (row.get("name") or "").strip(),
        (row.get("grams") or "").strip(),
        (row.get("cents") or "").strip(),
    )


def build_product_identity_bridge(
    *,
    api_cache_csv: Path,
    out_csv: Path,
    out_summary: Path,
) -> dict[str, Any]:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    stats: Counter[str] = Counter()

    with api_cache_csv.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader((line.replace("\x00", "") for line in handle))
        for row in reader:
            stats["api_cache_rows"] += 1
            identity = classify_product_identity(row.get("name") or "")
            if identity is None:
                stats["skip_no_product_identity"] += 1
                continue
            source = (row.get("source") or "").strip()
            if source not in {"kroger", "walmart"}:
                stats["skip_bad_retail_source"] += 1
                continue
            upc = (row.get("upc") or "").strip()
            if not upc:
                stats["skip_missing_upc"] += 1
                continue
            try:
                grams = round(float(row.get("grams") or 0), 3)
                cents = int(round(float(row.get("cents") or 0)))
            except ValueError:
                stats["skip_bad_numeric"] += 1
                continue
            if grams <= 0 or cents <= 0:
                stats["skip_bad_package"] += 1
                continue
            if cents / grams > MAX_PRODUCT_IDENTITY_CENTS_PER_GRAM:
                stats["skip_implausible_unit_price"] += 1
                continue

            key = _row_key(row)
            item = grouped.setdefault(
                key,
                {
                    "retail_source": source,
                    "upc": upc,
                    "name": (row.get("name") or "").strip(),
                    "grams": f"{grams:g}",
                    "cents": str(cents),
                    "product_identity": identity.product_identity,
                    "ingredient_key": identity.ingredient_key,
                    "food_description": identity.food_description,
                    "classification_reason": identity.classification_reason,
                    "search_terms": set(),
                },
            )
            search_term = (row.get("search_term") or "").strip()
            if search_term:
                item["search_terms"].add(search_term)
            stats[f"classified:{identity.ingredient_key}"] += 1

    rows = sorted(
        grouped.values(),
        key=lambda item: (
            item["ingredient_key"],
            item["retail_source"],
            float(item["cents"]) / max(float(item["grams"]), 0.001),
            item["name"],
        ),
    )

    fieldnames = [
        "retail_source",
        "upc",
        "name",
        "grams",
        "cents",
        "product_identity",
        "ingredient_key",
        "food_description",
        "classification_reason",
        "search_terms",
    ]
    tmp = out_csv.with_suffix(out_csv.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out_row = dict(row)
            out_row["search_terms"] = "|".join(sorted(out_row["search_terms"]))
            writer.writerow(out_row)
    tmp.replace(out_csv)

    by_key = Counter(row["ingredient_key"] for row in rows)
    summary = {
        "api_cache_csv": str(api_cache_csv),
        "out_csv": str(out_csv),
        "row_count": len(rows),
        "ingredient_keys": dict(sorted(by_key.items())),
        "max_product_identity_cents_per_gram": MAX_PRODUCT_IDENTITY_CENTS_PER_GRAM,
        "stats": dict(stats),
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build UPC/title-level product identities for sparse cascade pricing.")
    parser.add_argument("--api-cache-csv", type=Path, default=DEFAULT_API_CACHE_CSV)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_product_identity_bridge(
        api_cache_csv=args.api_cache_csv.expanduser(),
        out_csv=args.out_csv.expanduser(),
        out_summary=args.out_summary.expanduser(),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
