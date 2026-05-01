#!/usr/bin/env python3
"""Snap DeepSeek path corrections to the closest existing canonical_path
in the original tree. Reverts inventions; preserves close matches.

Reads:
  - retail_mapper/v2/path_describe_corrections.csv (DeepSeek proposals)
  - retail_mapper/v2/full_corpus_audit.csv (current state)

For each correction:
  1. If new_path exists in the pre-correction tree → keep
  2. If a fuzzy match (Jaccard ≥ 0.7) finds a close existing path → snap
  3. Otherwise → revert (drop the correction)

Writes:
  - retail_mapper/v2/path_describe_corrections.csv (overwritten with snapped/filtered)
  - retail_mapper/v2/path_corrections_snap_log.csv (audit trail per-row)
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CORR = V2 / "path_describe_corrections.csv"
AUDIT = V2 / "full_corpus_audit.csv"
LOG_OUT = V2 / "path_corrections_snap_log.csv"

csv.field_size_limit(sys.maxsize)

WORD_RX = re.compile(r"[A-Za-z0-9]+")

# Aliases: when DeepSeek picked a parent path that means the same as one we
# already have, rewrite the prefix. Order: longest-first to avoid partial-overlap.
ALIASES: dict[str, str] = {
    "Pantry > Tortillas > Flour Tortillas":     "Bakery > Tortillas > Flour",
    "Pantry > Tortillas > Corn Tortillas":      "Bakery > Tortillas > Corn",
    "Pantry > Tortillas":                        "Bakery > Tortillas",
    "Snack > Energy & Granola Bars":            "Snack > Bars > Granola Bars",
    "Snack > Granola Bars":                      "Snack > Bars > Granola Bars",
    "Snack > Energy Bars":                       "Snack > Bars > Energy Bars",
    "Snack > Protein Bars":                      "Snack > Bars > Protein Bars",
    "Snack > Cereal Bars":                       "Snack > Bars > Cereal Bars",
    "Pantry > Baking & Cooking Mixes":           "Pantry > Baking Mixes",
    "Pantry > Baking Mixes & Ingredients":       "Pantry > Baking Mixes",
    "Pantry > Soups & Broths":                   "Pantry > Bouillon & Broth",
    "Pantry > Soups":                            "Pantry > Soup",
    "Pantry > Stew":                             "Pantry > Soup",
    "Beverage > Drink Mixes":                    "Beverage > Drink Mix",
    "Beverage > Soda":                           "Beverage > Carbonated",
    "Beverage > Water > Sparkling Water":        "Beverage > Sparkling Water",
    "Beverage > Water > Flavored Water":         "Beverage > Sparkling Water",
    "Beverage > Coffee > Cold Brew":             "Beverage > Coffee > Cold Brew Coffee",
    "Snack > Nuts & Seeds":                      "Snack > Nuts",
    "Snack > Chocolate":                         "Snack > Candy > Chocolate Candy",
    "Snack > Candy > Chocolate":                 "Snack > Candy > Chocolate Candy",
    "Snack > Cookies > Sandwich Cookies":        "Snack > Cookies",
    "Snack > Cookies > Sugar Cookies":           "Snack > Cookies",
    "Snack > Cookies > Shortbread":              "Snack > Cookies",
    "Snack > Cookies > Wafers":                  "Snack > Cookies",
    "Snack > Cookies > Chocolate":               "Snack > Cookies",
    "Snack > Cookies > Graham Crackers":         "Snack > Crackers",
    "Frozen > Ice Cream & Frozen Yogurt":        "Frozen > Ice Cream",
    "Frozen > Entrees":                           "Frozen > Single Entrees",
    "Frozen > Vegetables":                        "Produce > Vegetables",
    "Frozen > Fruit":                             "Produce > Fruit",
    "Frozen > Pizza":                             "Meal > Pizza",
    "Frozen > Breakfast > Sandwiches":           "Frozen > Breakfast Sandwiches",
    "Meat & Seafood > Cold Cuts > Ham":          "Meat & Seafood > Ham",
    "Meat & Seafood > Cold Cuts":                "Meat & Seafood > Deli",
    "Pantry > Rice":                              "Pantry > Grain > Rice",
    "Pantry > Condiments > Mustard":             "Pantry > Sauces & Salsas > Mustard",
    "Pantry > Condiments > Ketchup":             "Pantry > Sauces & Salsas > Ketchup",
    "Pantry > Condiments > Mayonnaise":          "Pantry > Sauces & Salsas > Mayonnaise",
    "Pantry > Condiments":                        "Pantry > Sauces & Salsas",
    "Pantry > Sauces & Salsas > Cooking Sauce":  "Pantry > Sauces & Salsas > Sauce",
    "Pantry > Sauces & Salsas > Salad Dressing": "Pantry > Salad Dressings",
    "Meal > Stew":                                "Meal > Soups",
}


def apply_aliases(path: str) -> str:
    """Replace any matching alias prefix with its target, longest first."""
    for src in sorted(ALIASES, key=len, reverse=True):
        if path == src:
            return ALIASES[src]
        if path.startswith(src + " > "):
            return ALIASES[src] + path[len(src):]
    return path


def tokens(s: str) -> set[str]:
    return {t.lower() for t in WORD_RX.findall(s) if len(t) > 1}


def main() -> None:
    if not CORR.exists():
        raise SystemExit(f"missing {CORR}")
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")

    # Build set of paths that exist in the audit, EXCLUDING rows whose path
    # was set by path-describe corrections (we want the pre-correction tree).
    pd_corrected_fdcs: set[str] = set()
    with CORR.open() as fh:
        for r in csv.DictReader(fh):
            pd_corrected_fdcs.add(r["fdc_id"])

    print(f"  reading audit to build pre-correction tree...")
    known_paths: set[str] = set()
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("fdc_id") in pd_corrected_fdcs:
                # Use OLD path from corrections file, not the (overridden) audit value
                continue
            cp = (r.get("canonical_path") or "").strip()
            if cp:
                known_paths.add(cp)
    # Also add ALL old_paths from the corrections file (those existed before override)
    with CORR.open() as fh:
        for r in csv.DictReader(fh):
            cp = r.get("old_path", "").strip()
            if cp:
                known_paths.add(cp)
    print(f"  known canonical paths: {len(known_paths):,}")

    # Index by top-level family for faster fuzzy match
    paths_by_family: dict[str, list[tuple[str, set[str]]]] = {}
    for p in known_paths:
        family = p.split(" > ", 1)[0]
        paths_by_family.setdefault(family, []).append((p, tokens(p)))
    print(f"  indexed by {len(paths_by_family):,} top-level families")

    # Build prefix index — every parent prefix that exists in our tree.
    # Used for the "leaf-extends-existing-parent" rule.
    known_prefixes: set[str] = set()
    for p in known_paths:
        parts = p.split(" > ")
        for i in range(2, len(parts) + 1):
            known_prefixes.add(" > ".join(parts[:i]))
    print(f"  known prefixes (incl. ancestors): {len(known_prefixes):,}")

    # Process each correction
    n_total = 0
    n_kept_exact = 0
    n_alias = 0
    n_extend = 0
    n_snapped = 0
    n_reverted = 0
    out_rows: list[dict] = []
    log_rows: list[dict] = []
    with CORR.open() as fh:
        cols = next(csv.reader(fh))  # save header
    with CORR.open() as fh:
        for r in csv.DictReader(fh):
            n_total += 1
            new = r["new_path"].strip()
            old = r["old_path"].strip()

            # Step 1: Apply aliases (rewrite known parent renames)
            aliased = apply_aliases(new)
            if aliased != new:
                new = aliased
                r["new_path"] = new

            # Step 2: Exact existing path
            if new in known_paths:
                n_kept_exact += 1 if aliased == r["new_path"] else 0
                if aliased != r["new_path"]:
                    n_alias += 1
                out_rows.append(r)
                log_rows.append({**{k: r[k] for k in r}, "snap_action": "exact",
                                  "snap_target": new, "snap_score": "1.00"})
                continue

            # Step 3: Parent (path minus leaf) exists → extend the tree
            parts = new.split(" > ")
            parent = " > ".join(parts[:-1]) if len(parts) > 1 else ""
            if parent and parent in known_prefixes:
                n_extend += 1
                out_rows.append(r)
                log_rows.append({**{k: r[k] for k in r}, "snap_action": "extend",
                                  "snap_target": new, "snap_score": "1.00"})
                continue

            # Step 4: Fuzzy match within new_path's family
            new_family = new.split(" > ", 1)[0]
            new_tokens = tokens(new)
            candidates = paths_by_family.get(new_family, [])
            best_score = 0.0
            best_path = ""
            for cand_path, cand_tokens in candidates:
                if not cand_tokens or not new_tokens:
                    continue
                score = len(new_tokens & cand_tokens) / len(new_tokens | cand_tokens)
                if score > best_score:
                    best_score = score
                    best_path = cand_path
            if best_score >= 0.65:  # slightly lower than before
                r["new_path"] = best_path
                n_snapped += 1
                out_rows.append(r)
                log_rows.append({**{k: r[k] for k in r}, "snap_action": "snap",
                                  "snap_target": best_path, "snap_score": f"{best_score:.2f}"})
            else:
                # revert
                n_reverted += 1
                log_rows.append({**{k: r[k] for k in r}, "snap_action": "revert",
                                  "snap_target": old, "snap_score": f"{best_score:.2f}"})

    # Overwrite the corrections file with the snapped/kept set
    with CORR.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    # Write audit log
    log_cols = cols + ["snap_action", "snap_target", "snap_score"]
    with LOG_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=log_cols)
        w.writeheader()
        w.writerows(log_rows)

    print()
    print(f"=== Snap-to-tree results ===")
    print(f"  total corrections evaluated: {n_total:,}")
    print(f"    exact existing match:    {n_kept_exact:,} ({100*n_kept_exact/n_total:.0f}%)")
    print(f"    alias-redirected:        {n_alias:,} ({100*n_alias/n_total:.0f}%)")
    print(f"    extends existing parent: {n_extend:,} ({100*n_extend/n_total:.0f}%)")
    print(f"    snapped to closest:      {n_snapped:,} ({100*n_snapped/n_total:.0f}%)")
    print(f"    reverted (no good match): {n_reverted:,} ({100*n_reverted/n_total:.0f}%)")
    print()
    print(f"  corrections file: {len(out_rows):,} kept (will be applied)")
    print(f"  audit log:        {LOG_OUT.name}")


if __name__ == "__main__":
    main()
