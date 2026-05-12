#!/usr/bin/env python3
"""Explain gram drift by replaying the SR28 household-portion bridge.

The determinism audit says that the same (ingredient, qty, unit) tuple still
has multiple gram values. This script answers the next question: why?

For each top drift bucket it checks:
  - whether the ingredient has an ingredient->SR28 or htc->SR28 bridge;
  - whether the bridge points at the same food family;
  - whether SR28 food_portion has a usable modifier for the parsed unit;
  - whether a pipeline guard intentionally preserved or skipped the row;
  - whether the row is still blob/parser-origin even though SR28 could fix it.

Outputs:
  recipe_pricing/audit_gram_drift_causes.csv
  recipe_pricing/audit_gram_drift_cause_examples.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import normalize_grams_to_sr28 as sr28  # noqa: E402

RECIPES = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
DRIFT_TOP = ROOT / "recipe_pricing" / "audit_gram_determinism_top.csv"
ING_TO_SR28 = ROOT / "recipe_mapper" / "v1" / "output" / "ingredient_to_sr28.csv"
OVERRIDES = ROOT / "recipe_pricing" / "ingredient_fdc_overrides.csv"
HTC_TO_FDC = ROOT / "recipe_pricing" / "htc_to_fdc.csv"
FOOD_PORTION = ROOT / "data" / "sr28_csv" / "food_portion.csv"
OUT_BUCKETS = ROOT / "recipe_pricing" / "audit_gram_drift_causes.csv"
OUT_EXAMPLES = ROOT / "recipe_pricing" / "audit_gram_drift_cause_examples.csv"

STOPWORDS_ING = {
    "the", "a", "an", "of", "and", "or", "with", "fresh", "whole", "raw",
    "organic", "plain", "ground", "dried", "cooked", "mix",
}
STOPWORDS_SR = {
    "raw", "cooked", "with", "without", "added", "prepared", "equal",
    "volume", "water", "canned", "frozen", "ready", "serve", "unit",
}

WRONG_FAMILY_HINTS = {
    "canned entree",
    "banana, raw",
    "meatless",
    "beverage",
    "drink",
    "sherbet",
    "marmalade",
}


def as_float(value: str | None) -> float | None:
    try:
        return float(value or "")
    except (TypeError, ValueError):
        return None


def norm_key(row: dict[str, str]) -> tuple[str, str, str]:
    item = (row.get("item") or row.get("ingredient_item") or "").strip().lower()
    qty = as_float(row.get("qty"))
    unit = (row.get("unit") or "").strip().lower()
    return (item, f"{qty:g}" if qty is not None else "", unit)


def display_has_explicit_weight(display: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:g|grams?|kg|oz|ounces?|lb|lbs|pounds?)\b", display, re.I))


def load_item_to_fdc() -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    with ING_TO_SR28.open() as f:
        for row in csv.DictReader(f):
            item = (row.get("item") or "").strip().lower()
            fdc = (row.get("fdc_id") or "").strip()
            desc = (row.get("sr_description") or "").strip()
            if item and fdc:
                out[item] = (fdc, desc, "ingredient_to_sr28")
    if OVERRIDES.exists():
        with OVERRIDES.open() as f:
            for row in csv.DictReader(f):
                item = (row.get("item") or "").strip().lower()
                fdc = (row.get("fdc_id") or "").strip()
                desc = (row.get("sr_description") or "").strip()
                if item and fdc:
                    out[item] = (fdc, desc, "ingredient_fdc_overrides")
    return out


def load_htc_to_fdc() -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    with HTC_TO_FDC.open() as f:
        for row in csv.DictReader(f):
            htc = (row.get("htc_code") or "").strip()
            fdc = (row.get("fdc_id") or "").strip()
            desc = (row.get("sr_description") or "").strip()
            if htc and fdc:
                out[htc] = (fdc, desc, "htc_to_fdc")
    return out


def load_portions() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    with FOOD_PORTION.open() as f:
        for row in csv.DictReader(f):
            fdc = (row.get("fdc_id") or "").strip()
            if fdc:
                out[fdc].append(row)
    return out


def token_overlap_ok(item: str, sr_desc: str) -> bool:
    if "water" in (item or "").lower() and "water" in (sr_desc or "").lower():
        return True
    ing_toks = set(re.findall(r"[a-z]+", item.lower())) - STOPWORDS_ING
    sr_toks = set(re.findall(r"[a-z]+", sr_desc.lower())) - STOPWORDS_SR
    if ("powder" in ing_toks or "dry" in ing_toks) and not (
        sr_toks & {"powder", "dry", "spice", "spices", "seed", "seeds"}
    ):
        return False
    return not (ing_toks and sr_toks and not (ing_toks & sr_toks))


def normalized_tokens(text: str, stopwords: set[str]) -> set[str]:
    out = set()
    for token in set(re.findall(r"[a-z]+", text.lower())) - stopwords:
        out.add(token)
        if token.endswith("ies") and len(token) > 4:
            out.add(token[:-3] + "y")
        if token.endswith("es") and len(token) > 3:
            out.add(token[:-2])
        if token.endswith("s") and len(token) > 3:
            out.add(token[:-1])
        if token == "breadcrumbs":
            out.update({"bread", "crumb", "crumbs"})
        if token in {"catsup", "ketchup"}:
            out.update({"catsup", "ketchup"})
        if token in {"macaroni", "noodle", "noodles", "pasta"}:
            out.update({"macaroni", "noodle", "noodles", "pasta"})
    return out


def normalized_token_overlap_ok(item: str, sr_desc: str) -> bool:
    ing_toks = normalized_tokens(item, STOPWORDS_ING)
    sr_toks = normalized_tokens(sr_desc, STOPWORDS_SR)
    return not (ing_toks and sr_toks and not (ing_toks & sr_toks))


def likely_wrong_family(item: str, sr_desc: str) -> bool:
    desc = sr_desc.lower()
    if "water" in (item or "").lower() and "water" in desc:
        return False
    if any(hint in desc for hint in WRONG_FAMILY_HINTS):
        return True
    item_toks = set(re.findall(r"[a-z]+", item.lower())) - STOPWORDS_ING
    sr_toks = set(re.findall(r"[a-z]+", desc)) - STOPWORDS_SR
    if item_toks and sr_toks and not normalized_token_overlap_ok(item, sr_desc):
        return True
    if "powder" in item_toks and "powder" not in sr_toks and "spice" not in sr_toks and "spices" not in sr_toks:
        return True
    if "stick" in item_toks and "ground" in sr_toks:
        return True
    fruit_words = {"orange", "apple", "grape", "pineapple", "lemon", "lime", "cranberry"}
    item_fruits = item_toks & fruit_words
    sr_fruits = sr_toks & fruit_words
    if item_fruits and sr_fruits and not (item_fruits & sr_fruits):
        return True
    return False


def all_portion_labels(portions: list[dict[str, str]]) -> str:
    labels = []
    for p in portions:
        mod = (p.get("modifier") or "").strip().lower()
        if not mod:
            continue
        labels.append(f"{mod}:{p.get('gram_weight', '')}g/{p.get('amount', '')}")
    return "|".join(labels[:12])


def sr28_portion_labels(portions: list[dict[str, str]], unit: str) -> str:
    candidates = sr28.UNIT_MAP.get(unit, [])
    labels = []
    for p in portions:
        mod = (p.get("modifier") or "").strip().lower()
        if not mod:
            continue
        if any(mod == tok or mod.startswith(tok + " ") or mod.startswith(tok + ",") for tok in candidates):
            labels.append(f"{mod}:{p.get('gram_weight', '')}g/{p.get('amount', '')}")
    return "|".join(labels[:8])


def explain_row(
    row: dict[str, str],
    item_to_fdc: dict[str, tuple[str, str, str]],
    htc_to_fdc: dict[str, tuple[str, str, str]],
    fdc_portions: dict[str, list[dict[str, str]]],
    reviewed_portions: dict[tuple[str, str], list[dict]],
) -> dict[str, str]:
    item = (row.get("ingredient_item") or "").strip().lower()
    unit = (row.get("unit") or "").strip().lower()
    display = row.get("display") or ""
    source = (row.get("grams_source") or "").strip()
    qty = as_float(row.get("qty"))
    old_g = as_float(row.get("grams_resolved"))
    blob_g = as_float(row.get("grams_blob"))

    out = {
        "recipe_id": row.get("recipe_id", ""),
        "recipe_title": row.get("recipe_title", ""),
        "item": item,
        "qty": f"{qty:g}" if qty is not None else "",
        "unit": unit,
        "display": display[:160],
        "grams_resolved": f"{old_g:g}" if old_g is not None else "",
        "grams_blob": f"{blob_g:g}" if blob_g is not None else "",
        "grams_source": source,
        "htc_code": row.get("htc_code", ""),
        "bridge_source": "",
        "fdc_id": "",
        "sr_description": "",
        "sr28_portion": "",
        "sr28_expected_g": "",
        "available_sr28_portions": "",
        "portion_options_for_unit": "",
        "row_reason": "",
    }

    if qty is None or qty <= 0:
        out["row_reason"] = "invalid_or_missing_qty"
        return out
    if not unit:
        out["row_reason"] = "missing_unit"
        return out

    reviewed_portion = sr28.pick_reviewed_portion(reviewed_portions, item, unit, display)

    def explain_reviewed_portion() -> dict[str, str]:
        assert reviewed_portion is not None
        gpu, label = reviewed_portion
        expected = qty * gpu
        out["sr28_portion"] = label
        out["sr28_expected_g"] = f"{expected:.2f}"
        if expected > 5000 and (old_g is None or old_g <= 0 or old_g < expected / 3):
            out["row_reason"] = "absurd_jump_guard"
        elif source == sr28.REVIEWED_SOURCE:
            out["row_reason"] = "reviewed_household_portion_already_applied"
        elif old_g is not None and abs(expected - old_g) < 0.01:
            out["row_reason"] = "already_equal_to_reviewed_expected"
        elif display_has_explicit_weight(display):
            out["row_reason"] = "explicit_weight_text_disagrees_with_reviewed_portion"
        else:
            out["row_reason"] = "reviewed_household_portion_available_but_not_applied"
        return out

    if unit not in sr28.UNIT_MAP and reviewed_portion is None:
        out["row_reason"] = "unit_not_supported_by_sr28_normalizer"
        return out

    bridge = item_to_fdc.get(item)
    if bridge is None:
        bridge = htc_to_fdc.get((row.get("htc_code") or "").strip())
    if bridge is None:
        if reviewed_portion is not None:
            return explain_reviewed_portion()
        out["row_reason"] = "no_sr28_bridge"
        return out

    fdc, desc, bridge_source = bridge
    out["bridge_source"] = bridge_source
    out["fdc_id"] = fdc
    out["sr_description"] = desc

    portions = fdc_portions.get(fdc, [])
    out["available_sr28_portions"] = all_portion_labels(portions)
    out["portion_options_for_unit"] = sr28_portion_labels(portions, unit)

    wrong_family = likely_wrong_family(item, desc)
    if wrong_family:
        if reviewed_portion is not None:
            return explain_reviewed_portion()
        out["row_reason"] = "sr28_bridge_probably_wrong_food"
        return out
    if not sr28.token_overlap_ok(item, desc):
        if reviewed_portion is not None:
            return explain_reviewed_portion()
        out["row_reason"] = "bridge_name_safety_skip"
        return out

    if not portions:
        if reviewed_portion is not None:
            return explain_reviewed_portion()
        out["row_reason"] = "sr28_food_has_no_portions"
        return out

    if sr28.SKIP_PATTERNS.search(display):
        out["row_reason"] = "display_skip_pattern"
        return out

    if source in sr28.PRESERVE_GRAMS_SOURCES:
        if source == "usda_sr28_normalized":
            out["row_reason"] = "sr28_already_applied_but_bucket_still_mixed"
        elif source == "deterministic_modal_normalized":
            out["row_reason"] = "modal_normalizer_applied_after_sr28_gap"
        else:
            out["row_reason"] = "preserved_prior_gram_repair_source"
        return out

    portion = sr28.pick_portion(portions, unit, display)
    source_label = "sr28"
    if portion is None:
        portion = reviewed_portion
        source_label = "reviewed"
    if portion is None:
        out["row_reason"] = "no_matching_sr28_or_reviewed_portion"
        return out

    gpu, label = portion
    expected = qty * gpu
    out["sr28_portion"] = label
    out["sr28_expected_g"] = f"{expected:.2f}"

    if expected > 5000 and (old_g is None or old_g <= 0 or old_g < expected / 3):
        out["row_reason"] = "absurd_jump_guard"
        return out
    if source == "temperature_quantity_restored":
        out["row_reason"] = "parser_temperature_as_quantity_repaired"
        return out
    if source == sr28.REVIEWED_SOURCE:
        out["row_reason"] = "reviewed_household_portion_already_applied"
        return out
    if wrong_family:
        out["row_reason"] = "sr28_bridge_probably_wrong_food"
        return out
    if old_g is not None and abs(expected - old_g) < 0.01:
        out["row_reason"] = "already_equal_to_sr28_expected"
        return out
    if display_has_explicit_weight(display):
        out["row_reason"] = "explicit_weight_text_disagrees_with_sr28_portion"
        return out
    if source_label == "reviewed":
        out["row_reason"] = "reviewed_household_portion_available_but_not_applied"
    else:
        out["row_reason"] = "sr28_available_but_current_grams_not_normalized"
    return out


def bucket_primary_reason(reason_counts: Counter[str], example_rows: list[dict[str, str]]) -> str:
    if not reason_counts:
        return "no_rows_found_for_drift_bucket"
    if len(reason_counts) == 1:
        return next(iter(reason_counts))
    if reason_counts.get("sr28_bridge_probably_wrong_food", 0) >= max(1, sum(reason_counts.values()) // 3):
        return "sr28_bridge_probably_wrong_food"
    if reason_counts.get("reviewed_household_portion_available_but_not_applied", 0) >= max(1, sum(reason_counts.values()) // 3):
        return "reviewed_household_portion_available_but_not_applied"
    if reason_counts.get("no_matching_sr28_portion_modifier", 0) >= max(2, sum(reason_counts.values()) // 3):
        return "sr28_bridge_present_but_unit_portion_missing"
    if reason_counts.get("sr28_available_but_current_grams_not_normalized", 0) >= max(2, sum(reason_counts.values()) // 3):
        return "sr28_available_but_not_applied_consistently"
    if reason_counts.get("modal_normalizer_applied_after_sr28_gap", 0) and reason_counts.get("sr28_already_applied_but_bucket_still_mixed", 0):
        return "mixed_sr28_and_modal_repairs"
    if reason_counts.get("explicit_weight_text_disagrees_with_sr28_portion", 0):
        return "explicit_weight_text_mixed_with_household_portion"
    if reason_counts.get("display_skip_pattern", 0) >= max(2, sum(reason_counts.values()) // 3):
        return "display_skip_pattern_mixed_bucket"
    return reason_counts.most_common(1)[0][0]


def load_target_keys(limit: int) -> dict[tuple[str, str, str], dict[str, str]]:
    targets: dict[tuple[str, str, str], dict[str, str]] = {}
    if not DRIFT_TOP.exists():
        return targets
    with DRIFT_TOP.open() as f:
        for i, row in enumerate(csv.DictReader(f)):
            if limit and i >= limit:
                break
            targets[norm_key(row)] = row
    return targets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300,
                        help="number of top drift buckets to explain")
    parser.add_argument("--max-examples-per-bucket", type=int, default=12)
    args = parser.parse_args()

    targets = load_target_keys(args.limit)
    if not targets:
        print(f"no target drift rows in {DRIFT_TOP}", file=sys.stderr)
        sys.exit(0)

    print("loading SR28 bridges and portions", file=sys.stderr)
    item_to_fdc = load_item_to_fdc()
    htc_to_fdc = load_htc_to_fdc()
    fdc_portions = load_portions()
    reviewed_portions = sr28.load_reviewed_household_portions()

    buckets = {
        key: {
            "target": row,
            "n_seen": 0,
            "reason_counts": Counter(),
            "source_counts": Counter(),
            "fdc_counts": Counter(),
            "sr_desc_counts": Counter(),
            "portion_counts": Counter(),
            "examples": [],
        }
        for key, row in targets.items()
    }

    print(f"scanning recipes for {len(targets):,} drift buckets", file=sys.stderr)
    with RECIPES.open() as f:
        for n, row in enumerate(csv.DictReader(f), start=1):
            item = (row.get("ingredient_item") or "").strip().lower()
            qty = as_float(row.get("qty"))
            unit = (row.get("unit") or "").strip().lower()
            if qty is None:
                continue
            key = (item, f"{qty:g}", unit)
            bucket = buckets.get(key)
            if bucket is None:
                continue
            explanation = explain_row(row, item_to_fdc, htc_to_fdc, fdc_portions, reviewed_portions)
            bucket["n_seen"] += 1
            bucket["reason_counts"][explanation["row_reason"]] += 1
            bucket["source_counts"][explanation["grams_source"]] += 1
            if explanation["fdc_id"]:
                bucket["fdc_counts"][explanation["fdc_id"]] += 1
            if explanation["sr_description"]:
                bucket["sr_desc_counts"][explanation["sr_description"]] += 1
            if explanation["sr28_portion"]:
                bucket["portion_counts"][explanation["sr28_portion"]] += 1
            if len(bucket["examples"]) < args.max_examples_per_bucket:
                bucket["examples"].append(explanation)
            if n % 500_000 == 0:
                print(f"  {n:,} rows scanned", file=sys.stderr)

    bucket_rows: list[dict[str, str]] = []
    example_rows: list[dict[str, str]] = []
    cause_totals = Counter()
    for key, bucket in buckets.items():
        target = bucket["target"]
        reason_counts = bucket["reason_counts"]
        primary = bucket_primary_reason(reason_counts, bucket["examples"])
        cause_totals[primary] += int(target.get("n_lines") or 0)
        top_fdc = bucket["fdc_counts"].most_common(1)
        top_desc = bucket["sr_desc_counts"].most_common(1)
        top_portion = bucket["portion_counts"].most_common(1)
        row = {
            "item": key[0],
            "qty": key[1],
            "unit": key[2],
            "n_lines_from_drift_audit": target.get("n_lines", ""),
            "n_rows_replayed": str(bucket["n_seen"]),
            "primary_reason": primary,
            "reason_counts": "|".join(f"{k}={v}" for k, v in reason_counts.most_common()),
            "source_counts": "|".join(f"{k}={v}" for k, v in bucket["source_counts"].most_common()),
            "fdc_id": top_fdc[0][0] if top_fdc else "",
            "sr_description": top_desc[0][0] if top_desc else "",
            "sr28_portion": top_portion[0][0] if top_portion else "",
            "all_grams": target.get("all_grams", ""),
            "sample_from_drift_audit": target.get("sample", ""),
        }
        bucket_rows.append(row)
        for ex in bucket["examples"]:
            ex2 = {"bucket_primary_reason": primary}
            ex2.update(ex)
            example_rows.append(ex2)

    bucket_rows.sort(key=lambda r: -int(r["n_lines_from_drift_audit"] or 0))
    with OUT_BUCKETS.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bucket_rows[0].keys()))
        writer.writeheader()
        writer.writerows(bucket_rows)

    if example_rows:
        with OUT_EXAMPLES.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(example_rows[0].keys()))
            writer.writeheader()
            writer.writerows(example_rows)

    print("\nCause totals weighted by drift-audit n_lines:", file=sys.stderr)
    for reason, n_lines in cause_totals.most_common(20):
        print(f"  {reason:<52} {n_lines:>8,}", file=sys.stderr)

    print("\nTop explained buckets:", file=sys.stderr)
    for row in bucket_rows[:20]:
        print(
            f"  {row['n_lines_from_drift_audit']:>5}x {row['item'][:24]:<24} "
            f"{row['qty']} {row['unit']:<8} {row['primary_reason']}",
            file=sys.stderr,
        )
    print(f"\n-> {OUT_BUCKETS}\n-> {OUT_EXAMPLES}", file=sys.stderr)


if __name__ == "__main__":
    main()
