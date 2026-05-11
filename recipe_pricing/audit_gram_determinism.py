#!/usr/bin/env python3
"""Gram determinism audit for recipes_unified.csv.

The main gate audits deterministic units only: if the same
(ingredient_item.lower(), qty, unit) tuple appears with multiple gram values,
after excluding package units and explicit form/size states, the calculator is
still drifting.

Two classes are audited separately instead of failing the main gate:
  - variable package units such as can/jar/bag/package, because "1 can" is not
    deterministic without package-size evidence;
  - explicit form/state exceptions, where display text says whipped, packed,
    sliced, small, whole peppercorn, etc. and ingredient_item does not.

Outputs:
  audit_gram_determinism_drift.csv
  audit_gram_determinism_top.csv
  audit_gram_determinism_package_units.csv
  audit_gram_determinism_state_exceptions.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**30)

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT_DRIFT = ROOT / "recipe_pricing" / "audit_gram_determinism_drift.csv"
OUT_TOP = ROOT / "recipe_pricing" / "audit_gram_determinism_top.csv"
OUT_PACKAGE = ROOT / "recipe_pricing" / "audit_gram_determinism_package_units.csv"
OUT_STATE = ROOT / "recipe_pricing" / "audit_gram_determinism_state_exceptions.csv"
OUT_COMPOUND = ROOT / "recipe_pricing" / "audit_gram_determinism_compound_quantities.csv"
OUT_REPAIRED = ROOT / "recipe_pricing" / "audit_gram_determinism_quantity_repairs.csv"

ANCHOR_GRAMS_SOURCES = {
    "usda_sr28_normalized",
    "reviewed_household_portion_normalized",
}
ACTIONABLE_RATIO = 1.5

COMPOUND_QUANTITY_PATTERNS = re.compile(
    r"\bplus\s+(?:\d|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"|\bfor boiling\b",
    re.I,
)

VARIABLE_PACKAGE_UNITS = {
    "bag", "bags",
    "bottle", "bottles",
    "box", "boxes",
    "can", "cans",
    "carton", "cartons",
    "container", "containers",
    "envelope", "envelopes",
    "jar", "jars",
    "package", "packages",
    "packet", "packets",
    "pkg", "pkgs",
    "pouch", "pouches",
    "sprig", "sprigs",
    "bunch", "bunches",
}

REPAIRED_QUANTITY_SOURCES = {
    "range_lower_bound",
    "range_clamped_to_blob",
    "text_range_clamped_to_blob",
    "per_pound_parenthetical_fixed",
    "temperature_quantity_restored",
}

DENSITY_STATE_TOKENS = {
    "whipped",
    "powdered",
    "condensed",
    "concentrated",
    "dehydrated",
    "freeze-dried",
}

FORM_STATE_TOKENS = {
    "packed",
    "unpacked",
    "brownulated",
    "fresh",
    "dried",
    "ground",
    "whole",
    "peppercorn",
    "peppercorns",
    "cracked",
    "crumbled",
    "crushed",
    "chopped",
    "diced",
    "minced",
    "sliced",
    "grated",
    "shredded",
    "julienned",
    "strips",
    "rings",
    "quartered",
    "halved",
    "hulled",
    "mashed",
    "pureed",
    "puree",
    "cubed",
    "cubes",
    "cut",
    "wedges",
    "chunks",
    "drained",
    "sifted",
    "toasted",
    "halves",
    "pieces",
    "small",
    "medium",
    "large",
    "jumbo",
}


def num(x: str | None) -> float | None:
    try:
        return float(x or "")
    except (TypeError, ValueError):
        return None


def has_density_state_exception(item: str, display: str) -> bool:
    for token in DENSITY_STATE_TOKENS | FORM_STATE_TOKENS:
        if token in display and token not in item:
            return True
    return False


def new_bucket() -> dict:
    return {"grams": defaultdict(int), "sources": defaultdict(int),
            "htcs": defaultdict(int), "samples": []}


def add_bucket(bucket: dict, key: tuple, row: dict, grams: float) -> None:
    entry = bucket[key]
    entry["grams"][round(grams, 1)] += 1
    entry["sources"][row.get("grams_source", "")] += 1
    entry["htcs"][row.get("htc_code", "")] += 1
    if len(entry["samples"]) < 3:
        entry["samples"].append((row.get("display", "") or "")[:60])


def build_drift_rows(bucket: dict) -> tuple[list[dict], int, int, int]:
    drift_rows: list[dict] = []
    n_drifted = 0
    n_drift_with_sr28 = 0
    n_lines_drifted = 0

    for (item, q, u), entry in bucket.items():
        grams_dict = entry["grams"]
        if len(grams_dict) <= 1:
            continue
        n_drifted += 1
        n_lines = sum(grams_dict.values())
        n_lines_drifted += n_lines
        ordered = sorted(grams_dict.items(), key=lambda kv: (-kv[1], kv[0]))
        sr28_present = bool(ANCHOR_GRAMS_SOURCES & set(entry["sources"]))
        if sr28_present:
            n_drift_with_sr28 += 1
        max_g, min_g = max(grams_dict.keys()), min(grams_dict.keys())
        ratio = (max_g / min_g) if min_g > 0 else 0
        drift_rows.append({
            "item": item,
            "qty": q,
            "unit": u,
            "n_distinct_grams": len(grams_dict),
            "n_lines": n_lines,
            "min_g": min_g,
            "max_g": max_g,
            "ratio": round(ratio, 2),
            "modal_g": ordered[0][0],
            "modal_count": ordered[0][1],
            "all_grams": "|".join(f"{g}g={n}" for g, n in ordered[:6]),
            "sources": "|".join(f"{s}={n}" for s, n in entry["sources"].items()),
            "n_htcs": len(entry["htcs"]),
            "sample": " ; ".join(entry["samples"]),
        })

    drift_rows.sort(key=lambda row: -row["n_lines"])
    return drift_rows, n_drifted, n_drift_with_sr28, n_lines_drifted


def write_rows(path: Path, rows: list[dict], limit: int | None = None) -> None:
    if not rows:
        if path.exists():
            path.unlink()
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows[:limit] if limit else rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-drift", action="store_true",
                        help="exit nonzero if deterministic gram drift remains")
    parser.add_argument("--max-drift-tuples", type=int, default=0,
                        help="allowed drift tuple count when --fail-on-drift is set")
    parser.add_argument("--max-high-ratio-tuples", type=int, default=0,
                        help="allowed ratio>=ACTIONABLE_RATIO tuple count when --fail-on-drift is set")
    args = parser.parse_args()

    if not IN.exists():
        print(f"missing {IN}", file=sys.stderr)
        sys.exit(1)

    bucket: dict = defaultdict(new_bucket)
    package_bucket: dict = defaultdict(new_bucket)
    state_bucket: dict = defaultdict(new_bucket)
    compound_bucket: dict = defaultdict(new_bucket)
    repaired_bucket: dict = defaultdict(new_bucket)
    n_rows = 0
    skipped_package_rows = 0
    skipped_state_rows = 0
    skipped_compound_rows = 0
    skipped_repaired_rows = 0

    with IN.open() as f:
        for row in csv.DictReader(f):
            n_rows += 1
            item = (row.get("ingredient_item", "") or "").lower().strip()
            q = num(row.get("qty"))
            u = (row.get("unit", "") or "").lower().strip()
            g = num(row.get("grams_resolved"))
            if not item or q is None or q <= 0 or not u or g is None or g <= 0:
                continue
            key = (item, q, u)
            display = (row.get("display", "") or "").lower()
            if (row.get("grams_source", "") or "") in REPAIRED_QUANTITY_SOURCES:
                skipped_repaired_rows += 1
                add_bucket(repaired_bucket, key, row, g)
                continue
            if COMPOUND_QUANTITY_PATTERNS.search(display):
                skipped_compound_rows += 1
                add_bucket(compound_bucket, key, row, g)
                continue
            if u in VARIABLE_PACKAGE_UNITS:
                skipped_package_rows += 1
                add_bucket(package_bucket, key, row, g)
                continue
            if has_density_state_exception(item, display):
                skipped_state_rows += 1
                add_bucket(state_bucket, key, row, g)
                continue
            add_bucket(bucket, key, row, g)
            if n_rows % 500_000 == 0:
                print(f"  {n_rows:,} rows...", file=sys.stderr)

    print(f"\nscanned {n_rows:,} lines, {len(bucket):,} main distinct keys",
          file=sys.stderr)

    drift_rows, n_drifted, n_drift_with_sr28, n_lines_drifted = build_drift_rows(bucket)
    package_rows, _, _, _ = build_drift_rows(package_bucket)
    state_rows, _, _, _ = build_drift_rows(state_bucket)
    compound_rows, _, _, _ = build_drift_rows(compound_bucket)
    repaired_rows, _, _, _ = build_drift_rows(repaired_bucket)

    write_rows(OUT_DRIFT, drift_rows)
    write_rows(OUT_PACKAGE, package_rows, limit=300)
    write_rows(OUT_STATE, state_rows, limit=300)
    write_rows(OUT_COMPOUND, compound_rows, limit=300)
    write_rows(OUT_REPAIRED, repaired_rows, limit=300)

    top = [row for row in drift_rows if row["ratio"] >= ACTIONABLE_RATIO]
    write_rows(OUT_TOP, top, limit=300)

    print(f"\ndrifted (item,qty,unit) tuples:       {n_drifted:,}", file=sys.stderr)
    print(f"  of those, with sr28 source present:  {n_drift_with_sr28:,}", file=sys.stderr)
    print(f"total lines affected by drift:        {n_lines_drifted:,}", file=sys.stderr)
    print(f"package-unit rows audited separately: {skipped_package_rows:,}", file=sys.stderr)
    print(f"density-state rows audited separately:{skipped_state_rows:,}", file=sys.stderr)
    print(f"compound-quantity rows separately:    {skipped_compound_rows:,}", file=sys.stderr)
    print(f"quantity-repair rows separately:      {skipped_repaired_rows:,}", file=sys.stderr)

    print("\nTop 25 drifted tuples by line-count:", file=sys.stderr)
    for row in drift_rows[:25]:
        print(
            f"  {row['n_lines']:>5}x '{row['item'][:24]:<24}' "
            f"{row['qty']} {row['unit']:<10} {row['n_distinct_grams']}distinct "
            f"{row['min_g']}-{row['max_g']}g ({row['ratio']}x) "
            f"modal={row['modal_g']}g",
            file=sys.stderr,
        )
    print(f"\n-> {OUT_DRIFT}\n-> {OUT_TOP}\n-> {OUT_PACKAGE}\n-> {OUT_STATE}\n-> {OUT_COMPOUND}\n-> {OUT_REPAIRED}",
          file=sys.stderr)
    if args.fail_on_drift and (
        n_drifted > args.max_drift_tuples or len(top) > args.max_high_ratio_tuples
    ):
        print(
            "\nFAIL: deterministic gram drift exceeds configured limits "
            f"(tuples={n_drifted:,}, high_ratio={len(top):,})",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
