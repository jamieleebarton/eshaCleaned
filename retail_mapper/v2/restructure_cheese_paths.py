#!/usr/bin/env python3
"""Restructure compound cheese paths into proper top-down hierarchy.

Problem: paths like `Dairy > Cheese > Low Moisture Part Skim Mozzarella` smush
the cheese name and its modifiers into a single segment. Proper structure:
  Dairy > Cheese > {Cheese Name} > {Modifier1} > {Modifier2} > ...

Algorithm: for each path under `Dairy > Cheese` with a 3rd segment containing
a known CHEESE_NAMES word, split that segment and any subsequent ones:
  - Move the cheese name to be the 3rd segment
  - Order modifiers: structural (Whole Milk, Low Moisture, Part Skim) → quality
    (Fresh, Smoked, Sharp, Mild, Aged) → form (Shredded, Sliced, Cubed, Sticks)
    → claims (Reduced Fat, Organic, etc.)
  - Drop unknown words

Operates on both canonical_path and retail_leaf_path.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
LOG = V2 / "restructure_cheese_log.csv"

csv.field_size_limit(sys.maxsize)

# Multi-word cheese names need to match before single-word ones
CHEESE_NAMES_MULTI = [
    "Cottage Cheese", "Cream Cheese", "Goat Cheese", "Monterey Jack",
    "Pepper Jack", "Blue Cheese", "Swiss Cheese", "String Cheese",
    "Cheddar Jack", "Colby Jack", "Mexican Blend", "Italian Blend",
    "Mozzarella Provolone", "Sheep Milk", "Sheeps Milk",
]
CHEESE_NAMES_SINGLE = [
    "Mozzarella", "Cheddar", "Parmesan", "Provolone", "Feta", "Ricotta",
    "Brie", "Camembert", "Swiss", "Gouda", "Asiago", "Burrata", "Manchego",
    "Romano", "Havarti", "Gruyere", "Muenster", "Mascarpone", "Halloumi",
    "Limburger", "Pecorino", "Stilton", "Cotija", "Queso", "Paneer",
    "Brick", "Edam", "Bocconcini", "Reggiano", "Cambozola", "Boursin",
    "Fontina", "Halloumi", "Roquefort", "Gorgonzola", "Jarlsberg",
    "Boursault", "Emmental", "Gruyère", "Raclette", "Taleggio",
    "Wensleydale", "Caciocavallo", "Gloucester", "Stracchino",
    "Robiola", "Quark", "Tomme",
]

# Modifier categories (ordered: structural → quality → form → claims)
STRUCTURAL = ["Whole Milk", "Low Moisture", "Part Skim", "Skim Milk", "Lowfat", "Reduced Fat", "Fat Free", "Nonfat", "Full Fat", "Light", "2%", "1%"]
QUALITY = ["Fresh", "Smoked", "Aged", "Sharp", "Extra Sharp", "Mild", "Medium", "Mellow", "Cured", "Raw"]
FORM = ["Shredded", "Sliced", "Cubed", "Cubes", "Block", "Sticks", "Stick", "String", "Crumbled", "Grated", "Spread", "Wedge", "Pearls", "Ciliegine", "Bocconcini", "Whipped", "Curds", "Snack Pack", "Snack Packs", "Loaf"]
CLAIMS = ["Organic", "Natural", "Plant Based", "Vegan", "Lactose Free", "Gluten Free", "Probiotic", "Grass Fed", "Fortified", "Imported", "Domestic"]

ALL_CHEESES = CHEESE_NAMES_MULTI + CHEESE_NAMES_SINGLE
ALL_MODIFIERS = STRUCTURAL + QUALITY + FORM + CLAIMS
MODIFIER_RANK: dict[str, int] = {}
for i, m in enumerate(STRUCTURAL): MODIFIER_RANK[m.lower()] = (1, i)
for i, m in enumerate(QUALITY):    MODIFIER_RANK[m.lower()] = (2, i)
for i, m in enumerate(FORM):       MODIFIER_RANK[m.lower()] = (3, i)
for i, m in enumerate(CLAIMS):     MODIFIER_RANK[m.lower()] = (4, i)


def find_cheese(text: str) -> str | None:
    """Find the longest-matching cheese name in text, prefer multi-word."""
    text_lower = " " + text.lower() + " "
    for name in CHEESE_NAMES_MULTI:
        if " " + name.lower() + " " in text_lower:
            return name
    for name in CHEESE_NAMES_SINGLE:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            return name
    return None


def extract_modifiers(text: str) -> list[str]:
    """Extract modifier tokens from text, return in canonical order."""
    found_set: set[str] = set()
    text_lower = text.lower()
    # Multi-word modifiers first to avoid splitting them
    for m in sorted(ALL_MODIFIERS, key=lambda x: -len(x)):
        if m.lower() in text_lower:
            found_set.add(m)
            text_lower = text_lower.replace(m.lower(), " ")
    # Sort by category rank
    return sorted(found_set, key=lambda m: MODIFIER_RANK.get(m.lower(), (99, 0)))


def restructure_path(path: str) -> str | None:
    """Return restructured path, or None if no change is warranted."""
    if not path.startswith("Dairy > Cheese"):
        return None
    segs = path.split(" > ")
    if len(segs) < 3:
        return None

    # Try to find a cheese name in segments 3+
    cheese: str | None = None
    cheese_seg_idx: int = -1
    for i, s in enumerate(segs[2:], start=2):
        c = find_cheese(s)
        if c:
            cheese = c
            cheese_seg_idx = i
            break
    if cheese is None:
        return None

    # If 3rd seg is exactly the cheese name and structure already looks fine, leave it
    if (segs[2].lower() == cheese.lower() and
        all(len(s.split()) <= 2 for s in segs[3:])):
        return None

    # Collect all modifiers across all segments (excluding generic 'Cheese' word)
    blob = " ".join(segs[2:])
    modifiers = extract_modifiers(blob.replace(cheese, ""))

    # Build new path: Dairy > Cheese > {cheese} > {mods in canonical order}
    new_segs = ["Dairy", "Cheese", cheese] + modifiers
    new_path = " > ".join(new_segs)
    return new_path if new_path != path else None


def main() -> None:
    tmp = AUDIT.with_suffix(".restruct.csv")
    log_rows: list[dict] = []
    n_total = 0
    n_changed_cp = 0
    n_changed_rlp = 0
    cheese_counts: dict[str, int] = defaultdict(int)

    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for r in rdr:
            n_total += 1
            old_cp = r.get("canonical_path", "") or ""
            old_rlp = r.get("retail_leaf_path", "") or ""
            new_cp = restructure_path(old_cp) or old_cp
            new_rlp = restructure_path(old_rlp) or old_rlp
            cp_changed = new_cp != old_cp
            rlp_changed = new_rlp != old_rlp
            if cp_changed or rlp_changed:
                if cp_changed:
                    n_changed_cp += 1
                    cheese = find_cheese(new_cp)
                    if cheese: cheese_counts[cheese] += 1
                if rlp_changed: n_changed_rlp += 1
                r["canonical_path"] = new_cp
                r["retail_leaf_path"] = new_rlp
                log_rows.append({
                    "fdc_id": r.get("fdc_id", ""),
                    "title": (r.get("title", "") or "")[:60],
                    "old_canonical": old_cp,
                    "new_canonical": new_cp,
                    "old_retail_leaf": old_rlp,
                    "new_retail_leaf": new_rlp,
                })
            wtr.writerow(r)

    shutil.move(str(tmp), str(AUDIT))
    print(f"  total rows                : {n_total:,}")
    print(f"  canonical_path rewrites   : {n_changed_cp:,}")
    print(f"  retail_leaf_path rewrites : {n_changed_rlp:,}")
    print(f"  total rows touched        : {len(log_rows):,}")
    if cheese_counts:
        print(f"  per-cheese:")
        for c in sorted(cheese_counts, key=lambda k: -cheese_counts[k])[:25]:
            print(f"    {c:<20} {cheese_counts[c]:>5}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
