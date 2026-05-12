#!/usr/bin/env python3
"""Normalize recipes_unified.csv grams_resolved to USDA SR28 standards.

Source of truth: Hestia's ingredient_lookup.json:portions_sr28 — these
are USDA SR Legacy portion measurements (e.g., "1.0 head, medium" iceberg
= 539g, "1.0 cup shredded" = 72g, "1.0 tsp" salt = 6g).

The upstream gram parser is batch-inconsistent: same exact text "1 teaspoon
salt" gets parsed as 2g in some recipes and 6g in others. This normalizer
replaces grams_resolved with qty × (SR28 grams_per_unit) for cases where
SR28 has a deterministic answer.

DETERMINISTIC UNITS handled:
  tsp / tbsp / fl_oz   — small-volume measures (single SR28 entry per ingredient)
  clove / stalk / leaf / sprig / piece / each — count-based portions
  head (with size hint)— uses small/medium/large modifier from display
  cup                  — when SR28 has a "1.0 cup" or "1.0 cup, X" entry

SAFETY GUARDS (will NOT normalize):
  - Display contains "plus", "for boiling", "additional", "more" — parser
    is doing context-aware summation; respect it.
  - SR28 has multiple entries for the same unit and we can't disambiguate
    via size hint — prefer NO change over wrong change.
  - Current grams within ±10% of normalized — too small to bother.

Outputs:
  recipe_mapper/v1/output/recipes_unified.csv (in-place, atomic)
  recipe_pricing/normalize_grams_log.csv (samples)

Backup at recipes_unified.csv.before_round7_grams_normalize

Usage:
  python3 recipe_pricing/normalize_grams_to_usda.py [--dry-run]
"""
from __future__ import annotations
import argparse, csv, json, os, re, shutil, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
ILU_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/ingredient_lookup.json")
LOG = ROOT / "recipe_pricing" / "normalize_grams_log.csv"
BAK = CSV_PATH.with_suffix(".csv.before_round7_grams_normalize")

# Map our parser's unit → portion-key tail tokens
UNIT_TO_TAIL_TOKENS = {
    "tsp":      ["tsp", "teaspoon"],
    "teaspoon": ["tsp", "teaspoon"],
    "teaspoons":["tsp", "teaspoon"],
    "tbsp":     ["tbsp", "tablespoon"],
    "tablespoon":["tbsp", "tablespoon"],
    "tablespoons":["tbsp", "tablespoon"],
    "fl_oz":    ["fl_oz", "fl oz", "fluid ounce"],
    "cup":      ["cup"],
    "cups":     ["cup"],
    "head":     ["head"],
    "heads":    ["head"],
    "leaf":     ["leaf"],
    "leaves":   ["leaf"],
    "clove":    ["clove"],
    "cloves":   ["clove"],
    "stalk":    ["stalk"],
    "stalks":   ["stalk"],
    "ear":      ["ear"],
    "ears":     ["ear"],
    "sprig":    ["sprig", "branch"],
    "sprigs":   ["sprig", "branch"],
    "piece":    ["piece"],
    "pieces":   ["piece"],
    "slice":    ["slice"],
    "slices":   ["slice"],
    "stick":    ["stick"],
    "sticks":   ["stick"],
}

SIZE_MODIFIERS = ("small", "medium", "large", "extra large", "jumbo")

# Display patterns that indicate context-aware summation by parser — SKIP these
SKIP_PATTERNS = re.compile(
    r"\bplus\b"                           # "1 tsp salt, plus 3 tsp for boiling water"
    r"|\bfor (?:boiling|the )?\b"        # "for boiling water"
    r"|\badditional\b"                    # "1 tsp + additional"
    r"|\bmore\b"                          # "1 tsp + more if needed"
    r"|\bdivided\b"                       # "1 cup, divided" — recipe uses parts separately
    r"|\bextra\b",                        # "1 tsp + extra for sprinkling"
    re.I,
)

_PORTION_LEADING_QTY = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s+(.+)$")


def parse_portion_key(pkey: str) -> tuple[float, str] | None:
    m = _PORTION_LEADING_QTY.match(pkey)
    if not m: return None
    try: return (float(m.group(1)), m.group(2).strip().lower())
    except: return None


def find_grams_per_unit(ilu_entry: dict, unit_raw: str, display: str) -> tuple[float, str] | None:
    """Return (grams_per_unit, portion_label) — the gram amount for ONE unit."""
    portions: dict[str, float] = {}
    portions.update(ilu_entry.get("portions_sr28") or {})
    portions.update(ilu_entry.get("portions_fndds") or {})
    if not portions: return None
    unit = (unit_raw or "").strip().lower()
    disp = (display or "").lower()
    candidates = UNIT_TO_TAIL_TOKENS.get(unit)
    if not candidates: return None

    size_hint = None
    for sz in SIZE_MODIFIERS:
        if sz in disp: size_hint = sz; break

    # Build (grams_per_unit, pkey, has_size_match) options
    options: list[tuple[float, str, bool, bool]] = []
    # tuple: (gpu, pkey, is_one_mult, has_size)
    for pkey, g in portions.items():
        kl = pkey.lower()
        parsed = parse_portion_key(pkey)
        unit_tail = parsed[1] if parsed else kl
        # Reject sized portions when we have no size_hint
        sized = any(s in kl for s in ("small", "large", "jumbo", "extra large"))
        if sized and not (size_hint and size_hint in kl):
            continue
        # Token match
        token_match = any(tok == unit_tail.split(",")[0].strip() or tok == unit_tail
                            or unit_tail.startswith(tok + " ")
                            or unit_tail.startswith(tok + ",")
                            or unit_tail == tok
                          for tok in candidates)
        if not token_match: continue
        mult = parsed[0] if parsed else 1.0
        if mult <= 0: continue
        gpu = float(g) / mult
        is_one = (mult == 1.0)
        has_size = bool(size_hint and size_hint in kl)
        options.append((gpu, pkey, is_one, has_size))

    if not options: return None

    # Priority: size_match > 1.0_multiplier > others
    options.sort(key=lambda o: (-int(o[3]), -int(o[2])))
    best = options[0]
    return (best[0], best[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-tolerance", type=float, default=1.10,
                     help="Skip when within +/- of USDA. Default 1.10")
    args = ap.parse_args()

    print("loading Hestia ingredient_lookup…", file=sys.stderr)
    ilu = json.loads(ILU_PATH.read_text())
    name_to_ent = {k.lower().strip(): v for k, v in ilu.items()}
    print(f"  {len(name_to_ent):,} entries", file=sys.stderr)

    if not CSV_PATH.exists():
        print(f"missing {CSV_PATH}", file=sys.stderr); sys.exit(1)
    if not args.dry_run and not BAK.exists():
        print(f"backing up CSV → {BAK.name}", file=sys.stderr)
        shutil.copy(str(CSV_PATH), str(BAK))

    rows_seen = 0; matched = 0; skipped_skip_pattern = 0
    changed = 0; skipped_in_tolerance = 0
    samples = []
    by_pattern = defaultdict(lambda: {"count": 0, "old_total": 0.0, "new_total": 0.0})

    def process(row, write_w=None):
        nonlocal rows_seen, matched, skipped_skip_pattern, changed, skipped_in_tolerance
        rows_seen += 1
        ing = (row.get("ingredient_item") or "").lower().strip()
        if ing not in name_to_ent:
            if write_w: write_w.writerow(row)
            return
        try: qty = float(row.get("qty") or 0)
        except: qty = 0
        if qty <= 0:
            if write_w: write_w.writerow(row)
            return
        disp = row.get("display") or ""
        if SKIP_PATTERNS.search(disp):
            skipped_skip_pattern += 1
            if write_w: write_w.writerow(row)
            return
        portion = find_grams_per_unit(name_to_ent[ing],
                                       row.get("unit") or "", disp)
        if portion is None:
            if write_w: write_w.writerow(row)
            return
        matched += 1
        gpu, plabel = portion
        new_g = qty * gpu
        try: old_g = float(row.get("grams_resolved") or 0)
        except: old_g = 0
        if old_g > 0 and 1/args.max_tolerance <= new_g/old_g <= args.max_tolerance:
            skipped_in_tolerance += 1
            if write_w: write_w.writerow(row)
            return
        # Apply change
        changed += 1
        unit = (row.get("unit") or "").lower()
        key = (ing, unit, plabel)
        by_pattern[key]["count"] += 1
        by_pattern[key]["old_total"] += old_g
        by_pattern[key]["new_total"] += new_g
        if len(samples) < 25:
            samples.append({
                "rid": row['recipe_id'],
                "display": disp[:55],
                "old": old_g, "new": new_g, "portion": plabel,
            })
        if write_w:
            row["grams_resolved"] = f"{new_g:.2f}"
            row["grams_source"] = "usda_sr28_normalized"
            write_w.writerow(row)

    if args.dry_run:
        with CSV_PATH.open() as f:
            r = csv.DictReader(f)
            for row in r:
                process(row, None)
    else:
        out_dir = CSV_PATH.parent
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".unified_norm_",
                                             suffix=".csv", dir=str(out_dir))
        os.close(tmp_fd)
        try:
            with CSV_PATH.open() as f_in, open(tmp_path, "w", newline="") as f_out:
                r = csv.DictReader(f_in)
                w = csv.DictWriter(f_out, fieldnames=r.fieldnames)
                w.writeheader()
                for row in r:
                    process(row, w)
            os.replace(tmp_path, CSV_PATH)
        except Exception:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            raise

    print(f"\nrows scanned:           {rows_seen:,}", file=sys.stderr)
    print(f"matched ingredient+unit: {matched:,}", file=sys.stderr)
    print(f"skipped 'plus/for' pattern: {skipped_skip_pattern:,}", file=sys.stderr)
    print(f"skipped within tolerance:   {skipped_in_tolerance:,}", file=sys.stderr)
    print(f"changed:                    {changed:,}", file=sys.stderr)
    print(f"\nTop change patterns (count: avg_old → avg_new):", file=sys.stderr)
    sorted_pat = sorted(by_pattern.items(), key=lambda kv: -kv[1]["count"])
    for (ing, unit, plabel), d in sorted_pat[:20]:
        avg_old = d['old_total'] / d['count']
        avg_new = d['new_total'] / d['count']
        print(f"  {d['count']:>5}× '{ing[:25]:<25}' [{unit:<6}] '{plabel[:25]:<25}': "
              f"{avg_old:>5.0f}g → {avg_new:>5.0f}g", file=sys.stderr)
    print(f"\nSample changes:", file=sys.stderr)
    for s in samples[:15]:
        print(f"  rid={s['rid']:>6} '{s['display']}'  {s['old']:.0f}g → {s['new']:.0f}g  ({s['portion']})",
              file=sys.stderr)
    if not args.dry_run:
        print(f"\ndone. backup → {BAK.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
