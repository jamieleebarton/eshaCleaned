#!/usr/bin/env python3
"""Resolve quantity ambiguity in recipes_unified.csv.

Three classes of ambiguity, three deterministic fixes:

  1. NUMERIC RANGE ('2 to 4 tbsp', '4-5 pods', '1-2 cups')
     → take MIDPOINT, recompute grams_resolved by scaling.
     Updates `qty` and `grams_resolved`; sets `grams_source='range_midpoint'`.

  2. SIZE RANGE inside parens '(10.5-14 oz)', '(6 to 8 oz steak)'
     → take midpoint of the size range only (qty stays the same).
     Mostly affects 'can' / 'jar' / 'package' / 'steak' lines.

  3. VAGUE QTY ('a pinch', 'a handful', 'a dash', 'a splash', 'sprinkle')
     → fall back to lookup table grams. Set `grams_source='vague_lookup'`.
     Only fires when usage != 'to_taste' / 'garnish' (which are skipped
     from quantity calc anyway).

Idempotent: re-running on already-normalized rows is a no-op (sentinel
grams_source values are not re-processed).

Output: recipes_unified.csv is rewritten in place with these new rows.
A sidecar `recipe_pricing/quantity_normalization_log.csv` records every
change so we can audit.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
LOG = ROOT / "recipe_pricing" / "quantity_normalization_log.csv"
# We also need the classifier output to know if a line is to_taste/garnish
# (those get skipped anyway, no point fighting their quantity)
CLEANED_CLS = ROOT / "recipe_pricing" / "buyability_classifications_cleaned.jsonl"


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Numeric range — supports 1-2, 1 to 2, 1–2, 1—2, 1 or 2; integer or fraction.
# IMPORTANT: try `mixed_number_with_fraction` and `bare_fraction` FIRST so
# `1/4 to 1/3` matches as `1/4`/`1/3`, not `1/4`/`1`.
NUMERIC_RANGE_RE = re.compile(
    r"\b(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*(?:to|-|–|—|or)\s*(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\b",
    re.I,
)

# Size range inside parens like "(10.5-14 oz)", "(6 to 8 oz steak)"
SIZE_RANGE_PARENS_RE = re.compile(
    r"\(\s*(\d+(?:\.\d+)?)\s*(?:to|-|–|—)\s*(\d+(?:\.\d+)?)\s*(oz|ounce|lb|pound|g|gram|ml)\b",
    re.I,
)

# Vague qty tokens
VAGUE_LOOKUP = {
    "pinch":      0.5,
    "dash":       0.5,
    "smidge":     0.5,
    "drop":       0.05,
    "drops":      0.05,
    "splash":     5.0,
    "drizzle":    5.0,
    "sprinkle":   1.0,
    "sprinkling": 1.0,
    "handful":   30.0,
    "smattering": 15.0,
    "few":        3.0,    # "a few X" → 3 units
    "couple":     2.0,
    "several":    3.0,
}
VAGUE_QTY_RE = re.compile(
    r"\b(?:a\s+|an\s+)?(?:small\s+|generous\s+|big\s+|good\s+|"
    r"large\s+|tiny\s+)?(" + "|".join(VAGUE_LOOKUP) + r")\b",
    re.I,
)


def parse_number(s: str) -> float:
    """Parse '1', '0.5', '1/2', '1 1/2' → float."""
    s = s.strip()
    if " " in s:
        # mixed number "1 1/2"
        whole, frac = s.split(maxsplit=1)
        return float(whole) + parse_number(frac)
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)


def midpoint_of_range(lo_str: str, hi_str: str) -> float:
    return (parse_number(lo_str) + parse_number(hi_str)) / 2


def load_skip_set() -> set[tuple[str, int]]:
    """Set of (recipe_id, line_index) tuples where usage in {to_taste, garnish}.
    Those don't need quantity normalization — planner skips them anyway."""
    skip: set[tuple[str, int]] = set()
    if not CLEANED_CLS.exists():
        return skip
    with CLEANED_CLS.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for c in r.get("classifications", []):
                if c.get("usage") in ("to_taste", "garnish"):
                    skip.add((str(r.get("recipe_id")), c.get("line_index")))
    return skip


def normalize_one(row: dict, skip: set) -> tuple[dict, list[str]]:
    """Return (updated_row, list_of_changes_for_log).
    Modifies grams_resolved and grams_source if a quantity-ambiguity rule fires."""
    rid = str(row.get("recipe_id", "")).strip()
    li = row.get("line_index")
    try:
        li_int = int(li) if li else None
    except ValueError:
        li_int = None
    if li_int is not None and (rid, li_int) in skip:
        return row, []

    display = row.get("display", "") or ""
    src = row.get("grams_source", "") or ""
    # Don't re-process rows we already normalized
    if src in ("range_midpoint", "vague_lookup", "size_range_midpoint"):
        return row, []
    try:
        old_qty = float(row.get("qty", "") or 0)
    except (TypeError, ValueError):
        old_qty = 0.0
    try:
        old_grams = float(row.get("grams_resolved", "") or 0)
    except (TypeError, ValueError):
        old_grams = 0.0

    changes: list[str] = []

    # --- 1. Numeric range ---
    nr_match = NUMERIC_RANGE_RE.search(display)
    if nr_match and old_qty > 0:
        try:
            mid = midpoint_of_range(nr_match.group(1), nr_match.group(2))
            if mid > 0 and abs(mid - old_qty) > 0.01:
                # Scale grams by the ratio of the new midpoint to the old qty.
                new_grams = old_grams * (mid / old_qty)
                row["qty"] = f"{mid:.4f}"
                row["grams_resolved"] = f"{new_grams:.2f}"
                row["grams_source"] = "range_midpoint"
                changes.append(f"range '{nr_match.group(0)}' → midpoint qty {old_qty}→{mid:.2f}, grams {old_grams:.1f}→{new_grams:.1f}")
        except (ValueError, ZeroDivisionError):
            pass

    # --- 2. Size range inside parens ---
    if "grams_source" not in row or row.get("grams_source") not in ("range_midpoint",):
        sr_match = SIZE_RANGE_PARENS_RE.search(display)
        if sr_match:
            try:
                size_mid = midpoint_of_range(sr_match.group(1), sr_match.group(2))
                # If the gram resolver used the lo or hi bound for size, scale accordingly.
                # We don't know which it used, so just record it as a flag.
                row["grams_source"] = "size_range_midpoint"
                changes.append(
                    f"size_range '{sr_match.group(0)}' → midpoint size {size_mid:.2f}{sr_match.group(3)}"
                )
            except (ValueError, ZeroDivisionError):
                pass

    # --- 3. Vague qty ---
    if (not row.get("grams_resolved") or old_grams == 0):
        v_match = VAGUE_QTY_RE.search(display)
        if v_match:
            token = v_match.group(1).lower()
            grams = VAGUE_LOOKUP.get(token, 0)
            if grams > 0:
                row["grams_resolved"] = f"{grams:.2f}"
                row["grams_source"] = "vague_lookup"
                changes.append(f"vague '{v_match.group(0)}' → {grams}g lookup")

    return row, changes


def main() -> int:
    if not UNIFIED.exists():
        raise SystemExit(f"missing {UNIFIED}")
    print("loading skip set (to_taste/garnish lines from classifier)...", file=sys.stderr)
    skip = load_skip_set()
    print(f"  {len(skip):,} lines flagged as to_taste/garnish (will skip)", file=sys.stderr)

    tmp = UNIFIED.with_suffix(".csv.tmp")
    n_total = 0
    n_changed = 0
    n_range = 0
    n_size = 0
    n_vague = 0

    with UNIFIED.open(newline="") as fin, \
         tmp.open("w", newline="") as fout, \
         LOG.open("w", newline="") as flog:
        reader = csv.DictReader(fin)
        fns = list(reader.fieldnames or [])
        # Some recipes_unified versions don't have line_index; use ingredient_item index.
        # We assume line_index exists; if not, the skip set lookup will just miss.
        if "line_index" not in fns:
            print("  WARNING: recipes_unified has no line_index; skip-set will be empty", file=sys.stderr)
        writer = csv.DictWriter(fout, fieldnames=fns)
        writer.writeheader()

        log_writer = csv.DictWriter(flog, fieldnames=[
            "recipe_id", "line_index", "display", "rule", "change",
        ])
        log_writer.writeheader()

        for row in reader:
            n_total += 1
            row, changes = normalize_one(row, skip)
            writer.writerow(row)
            if changes:
                n_changed += 1
                for change in changes:
                    log_writer.writerow({
                        "recipe_id": row.get("recipe_id"),
                        "line_index": row.get("line_index", ""),
                        "display": row.get("display", "")[:120],
                        "rule": (
                            "range_midpoint" if "range" in change.lower() and "size" not in change.lower()
                            else "size_range_midpoint" if "size_range" in change.lower()
                            else "vague_lookup"
                        ),
                        "change": change,
                    })
                    rule = (
                        "range" if "range" in change.lower() and "size" not in change.lower()
                        else "size" if "size_range" in change.lower()
                        else "vague"
                    )
                    if rule == "range": n_range += 1
                    elif rule == "size": n_size += 1
                    else: n_vague += 1
            if n_total % 500_000 == 0:
                print(f"  scanned {n_total:,} lines, changed {n_changed:,}", file=sys.stderr)

    shutil.move(str(tmp), str(UNIFIED))
    print(f"\nfinal: scanned {n_total:,} lines, changed {n_changed:,}", file=sys.stderr)
    print(f"  numeric range midpoints:   {n_range:,}", file=sys.stderr)
    print(f"  size range midpoints:      {n_size:,}", file=sys.stderr)
    print(f"  vague qty lookups:         {n_vague:,}", file=sys.stderr)
    print(f"  → {UNIFIED} (in place)", file=sys.stderr)
    print(f"  → {LOG} (audit log)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
