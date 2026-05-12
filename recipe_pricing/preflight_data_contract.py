#!/usr/bin/env python3
"""Preflight checks for the pricing/planner data contract.

This is intentionally strict about stale HTC columns:
  - recipe htc_code must agree with htc_full_code's bucket;
  - recipe htc_code must match the current encoder when checked;
  - product htc_code must agree with product htc_full_code's bucket;
  - product htc_code/htc_form_code must match the current encoder for coded
    food rows when checked;
  - the legacy household portion file must be fully represented in the active
    reviewed portion authority.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "recipe_pricing" / "data_authority_manifest.csv"
RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
PRICED_DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
ACTIVE_PORTIONS = ROOT / "recipe_pricing" / "reviewed_household_portions.csv"
LEGACY_PORTIONS = ROOT / "implementation" / "reviewed_household_unit_gram_rules.csv"

VALID_ROLES = {"SOURCE", "REVIEWED_OVERRIDE", "GENERATED"}
BAD_HTC_GROUPS = {"0", "N"}

sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
from htc.encoder import encode  # noqa: E402


def clean_code(value: str | None) -> str:
    return (value or "").strip().lstrip("~")


def valid_htc(code: str | None) -> bool:
    code = clean_code(code)
    return bool(code) and code != "00000000" and code[:1] not in BAD_HTC_GROUPS


def fail(message: str) -> None:
    raise AssertionError(message)


def check_manifest() -> list[str]:
    if not MANIFEST.exists():
        fail(f"missing data authority manifest: {MANIFEST}")
    warnings: list[str] = []
    with MANIFEST.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"path", "role", "active"}
        missing_cols = required - set(reader.fieldnames or [])
        if missing_cols:
            fail(f"manifest missing columns: {sorted(missing_cols)}")
        for row in reader:
            path = ROOT / (row.get("path") or "")
            role = row.get("role") or ""
            active = (row.get("active") or "").strip().lower() in {"1", "yes", "true"}
            if role not in VALID_ROLES:
                fail(f"bad manifest role for {path}: {role}")
            if active and not path.exists():
                fail(f"active manifest path is missing: {path}")
            if not active and not path.exists():
                warnings.append(f"inactive manifest path is missing: {path}")
    return warnings


def check_recipe_full_prefix(sample_limit: int = 8) -> dict[str, object]:
    rows = 0
    mismatches = 0
    samples: list[tuple[str, str, str, str]] = []
    with RECIPES.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            htc = clean_code(row.get("htc_code"))
            full = clean_code(row.get("htc_full_code"))
            if htc and full and not full.startswith(htc):
                mismatches += 1
                if len(samples) < sample_limit:
                    samples.append((
                        row.get("ingredient_item", ""),
                        htc,
                        full[:24],
                        row.get("display", "")[:80],
                    ))
    if mismatches:
        fail(f"recipes_unified htc_code disagrees with htc_full_code on {mismatches:,} rows; samples={samples}")
    return {"rows": rows, "mismatches": mismatches}


def check_recipe_encoder(sample: int, sample_limit: int = 8) -> dict[str, object]:
    rows = 0
    checked = 0
    mismatches = 0
    samples: list[tuple[str, str, str, str]] = []
    cache: dict[tuple[str, str], str] = {}
    with RECIPES.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            if sample and checked >= sample:
                break
            item = (row.get("ingredient_item") or "").strip()
            cp = (row.get("normalized_canonical_text") or "").strip()
            if not item:
                continue
            key = (item.lower(), cp)
            if key not in cache:
                try:
                    cache[key] = encode(
                        "",
                        description=item,
                        food_name=item,
                        canonical_path=cp,
                        identity_mode=True,
                    ).code
                except Exception:
                    cache[key] = ""
            expected = cache[key]
            if not valid_htc(expected):
                continue
            checked += 1
            actual = clean_code(row.get("htc_code"))
            if actual != expected:
                mismatches += 1
                if len(samples) < sample_limit:
                    samples.append((item, actual, expected, row.get("display", "")[:80]))
    if mismatches:
        scope = f"first {sample:,} checked rows" if sample else "full file"
        fail(f"recipes_unified htc_code disagrees with current encoder in {scope}: {mismatches:,}; samples={samples}")
    return {"rows_seen": rows, "checked": checked, "mismatches": mismatches, "cache": len(cache)}


def check_product_prefix() -> dict[str, object]:
    con = sqlite3.connect(str(PRICED_DB))
    cur = con.cursor()
    total = cur.execute("SELECT COUNT(*) FROM priced_products").fetchone()[0]
    mismatches = cur.execute(
        """
        SELECT COUNT(*) FROM priced_products
        WHERE htc_full_code IS NOT NULL
          AND htc_full_code != ''
          AND htc_code IS NOT NULL
          AND htc_code != ''
          AND REPLACE(htc_full_code, '~', '') NOT LIKE REPLACE(htc_code, '~', '') || '%'
        """
    ).fetchone()[0]
    if mismatches:
        fail(f"priced_products htc_code disagrees with htc_full_code on {mismatches:,} rows")
    return {"rows": total, "mismatches": mismatches}


def check_product_encoder(sample: int, sample_limit: int = 8) -> dict[str, object]:
    con = sqlite3.connect(str(PRICED_DB))
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT rowid, name, consensus_canonical, htc_code, htc_form_code
        FROM priced_products
        WHERE name IS NOT NULL
          AND consensus_canonical IS NOT NULL
          AND consensus_canonical != ''
        """
    ).fetchall()
    checked = 0
    mismatches = 0
    samples: list[tuple[int, str, str, str, str, str]] = []
    cache: dict[tuple[str, str], tuple[str, str]] = {}
    for rowid, name, cp, old_id, old_form in rows:
        if sample and checked >= sample:
            break
        old_id_clean = clean_code(old_id)
        old_form_clean = clean_code(old_form)
        if not valid_htc(old_id_clean):
            continue
        key = (name or "", cp or "")
        if key not in cache:
            leaf = (cp or "").split(" > ")[-1]
            try:
                h_id = encode("", description=name or "", food_name=leaf, canonical_path=cp or "", identity_mode=True).code
                h_form = encode("", description=name or "", food_name=leaf, canonical_path=cp or "", identity_mode=False).code
            except Exception:
                h_id = ""
                h_form = ""
            cache[key] = (h_id, h_form)
        expected_id, expected_form = cache[key]
        if not valid_htc(expected_id):
            continue
        checked += 1
        bad = old_id_clean != expected_id
        if valid_htc(expected_form):
            bad = bad or old_form_clean != expected_form
        if bad:
            mismatches += 1
            if len(samples) < sample_limit:
                samples.append((
                    rowid,
                    (name or "")[:60],
                    old_id_clean,
                    expected_id,
                    old_form_clean,
                    expected_form,
                ))
    if mismatches:
        scope = f"first {sample:,} checked coded food rows" if sample else "coded food rows"
        fail(f"priced_products disagrees with current encoder in {scope}: {mismatches:,}; samples={samples}")
    return {"rows_seen": len(rows), "checked": checked, "mismatches": mismatches, "cache": len(cache)}


def legacy_item(concept_key: str) -> str:
    ck = (concept_key or "").strip().lower()
    if ck == "*":
        return "*"
    if ck.endswith("|||") and "|" not in ck[:-3]:
        return ck[:-3]
    return ck


def norm_grams(value: str | float) -> str:
    grams = float(value)
    return f"{grams:.4f}".rstrip("0").rstrip(".")


def check_portion_authority(sample_limit: int = 8) -> dict[str, object]:
    active_keys: set[tuple[str, str, str]] = set()
    with ACTIVE_PORTIONS.open(newline="") as handle:
        for row in csv.DictReader(handle):
            item = (row.get("item") or "").strip().lower()
            unit = (row.get("unit") or "").strip().lower()
            grams_raw = (row.get("grams_per_unit") or "").strip()
            if not item or not unit or not grams_raw:
                continue
            try:
                active_keys.add((item, unit, norm_grams(grams_raw)))
            except ValueError:
                continue

    checked = 0
    missing = 0
    samples: list[tuple[str, str, str, str]] = []
    with LEGACY_PORTIONS.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("review_status") or "").strip() != "approved":
                continue
            item = legacy_item(row.get("concept_key") or "")
            unit = (row.get("unit") or "").strip().lower()
            grams_raw = (row.get("grams_per_unit") or "").strip()
            if not item or not unit or not grams_raw:
                continue
            checked += 1
            try:
                key = (item, unit, norm_grams(grams_raw))
            except ValueError:
                continue
            if key not in active_keys:
                missing += 1
                if len(samples) < sample_limit:
                    samples.append((row.get("rule_id", ""), item, unit, key[2]))
    if missing:
        fail(f"legacy household portion rules missing from active authority: {missing:,}; samples={samples}")
    return {"legacy_checked": checked, "missing_from_active": missing, "active_keys": len(active_keys)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-recipe-encoder", action="store_true")
    parser.add_argument("--skip-product-encoder", action="store_true")
    parser.add_argument("--sample-recipe-encoder", type=int, default=0,
                        help="0 means full recipe encoder check")
    parser.add_argument("--sample-product-encoder", type=int, default=0,
                        help="0 means full product encoder check")
    args = parser.parse_args()

    try:
        warnings = check_manifest()
        recipe_prefix = check_recipe_full_prefix()
        recipe_encoder = None if args.skip_recipe_encoder else check_recipe_encoder(args.sample_recipe_encoder)
        product_prefix = check_product_prefix()
        product_encoder = None if args.skip_product_encoder else check_product_encoder(args.sample_product_encoder)
        portion_authority = check_portion_authority()
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(2)

    print("PASS: data authority preflight")
    print(f"  manifest warnings: {len(warnings)}")
    print(f"  recipe htc/full prefix: {recipe_prefix}")
    if recipe_encoder is not None:
        print(f"  recipe encoder: {recipe_encoder}")
    print(f"  product htc/full prefix: {product_prefix}")
    if product_encoder is not None:
        print(f"  product encoder: {product_encoder}")
    print(f"  portion authority: {portion_authority}")


if __name__ == "__main__":
    main()
