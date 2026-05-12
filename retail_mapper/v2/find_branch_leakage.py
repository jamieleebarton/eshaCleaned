#!/usr/bin/env python3
"""Detect branch leakage across the entire taxonomy.

Branch leakage = a type-name (e.g., 'Greek', 'Fresh', 'Sharp', 'Whole Milk') exists
as a real parent segment in some paths AND is glued into a compound segment in others.

Detection: for each parent (top-2 segments like 'Dairy > Yogurt'), collect every
3rd-segment value used. For each compound 3rd segment 'X Y Z', check if its
first word `X` (or first two words 'X Y' for known multi-word types) exists as
a STANDALONE 3rd segment in the same parent. If yes → leakage.

Output: retail_mapper/v2/branch_leakage_report.csv
  Per parent + leaked-prefix:
    parent | leaked_prefix | n_proper_skus | n_leaked_skus | n_leaked_paths | sample_proper_path | sample_leaked_paths

Console: top offenders by leaked-SKU count.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "branch_leakage_report.csv"

csv.field_size_limit(sys.maxsize)

# Multi-word type-prefixes worth keeping as a single phrase
KNOWN_MULTI_PREFIXES = {
    "Whole Milk", "Low Moisture", "Part Skim", "Fat Free", "Low Fat",
    "Reduced Fat", "Extra Sharp", "Mild Cheddar", "Sharp Cheddar",
    "Cream Cheese", "Cottage Cheese", "Goat Cheese", "Blue Cheese",
    "Mexican Blend", "Italian Blend", "Cheddar Jack", "Pepper Jack",
    "Monterey Jack", "Coffee Creamer", "Sour Cream", "Heavy Cream",
    "Whipping Cream", "Half and Half", "Frozen Yogurt", "Greek Style",
    "Plant Based", "Dairy Free", "Lactose Free", "Gluten Free", "Sugar Free",
    "Long Grain", "Short Grain", "Brown Rice", "White Rice", "Jasmine Rice",
    "Whole Grain", "Multi Grain", "Iced Tea", "Green Tea", "Black Tea",
    "White Tea", "Herbal Tea", "Oolong Tea", "Hot Sauce", "Pasta Sauce",
    "Tomato Sauce", "Soy Sauce", "Salad Dressing", "Olive Oil", "Coconut Oil",
    "Avocado Oil", "Sesame Oil", "Vegetable Oil", "Canola Oil", "Peanut Oil",
    "Sunflower Oil", "Almond Butter", "Peanut Butter", "Cashew Butter",
    "Sunflower Seed Butter", "Hazelnut Butter", "Cocoa Butter", "Cookie Butter",
    "Ice Cream", "Frozen Custard", "Sweet Potato", "Bell Pepper", "Black Bean",
    "Pinto Bean", "Kidney Bean", "Lima Bean", "Garbanzo Bean", "String Cheese",
    "Mozzarella Provolone", "Almond Milk", "Oat Milk", "Soy Milk", "Coconut Milk",
    "Cashew Milk", "Rice Milk", "Hazelnut Milk", "Macadamia Milk",
    "Grass Fed", "Free Range", "Cage Free", "Wild Caught",
    "Maple Syrup", "Honey Mustard", "Apple Cider", "Sparkling Water", "Spring Water",
    "Mineral Water", "Tonic Water", "Energy Drink", "Sports Drink", "Protein Drink",
    "Drink Mix", "Powdered Drink", "Frozen Pizza", "Hand Tossed", "Thin Crust",
    "Stuffed Crust", "Fried Chicken", "Grilled Chicken", "Roasted Chicken",
    "Smoked Salmon", "Atlantic Salmon", "Pacific Salmon",
}

WORD_RX = re.compile(r"[A-Za-z0-9%]+")


def first_one_or_two_words(seg: str) -> tuple[str, str | None]:
    """Return (one_word_prefix, two_word_prefix_if_any). For 'Greek Vanilla' →
    ('Greek', None). For 'Whole Milk Vanilla' → ('Whole', 'Whole Milk')."""
    words = seg.split()
    if not words: return seg, None
    one = words[0]
    two = None
    if len(words) >= 2:
        candidate = " ".join(words[:2])
        if candidate in KNOWN_MULTI_PREFIXES:
            two = candidate
    return one, two


def main() -> None:
    # parent -> Counter(third_segment) over both columns
    parent_to_thirds: dict[tuple[str, str], Counter] = defaultdict(Counter)
    # parent -> third_segment -> set(full_paths_using_it)
    parent_third_to_paths: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    n_total = 0
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n_total += 1
            for col in ("canonical_path", "retail_leaf_path"):
                v = (r.get(col) or "").strip()
                if not v: continue
                segs = v.split(" > ")
                if len(segs) < 3: continue
                parent = (segs[0], segs[1])
                third = segs[2]
                parent_to_thirds[parent][third] += 1
                parent_third_to_paths[parent][third].add(v)

    # For each parent, find compound 3rd-segments whose prefix exists as a standalone 3rd segment
    leakage_rows: list[dict] = []
    for parent, third_counter in parent_to_thirds.items():
        thirds_set = set(third_counter.keys())
        # For each compound, check if its prefix is a standalone
        # Group by 'leaked_prefix'
        leak_per_prefix: dict[str, list[str]] = defaultdict(list)
        for third in thirds_set:
            if " " not in third: continue  # not compound
            one, two = first_one_or_two_words(third)
            # Try two-word prefix first
            if two and two in thirds_set and two != third:
                leak_per_prefix[two].append(third)
            elif one in thirds_set and one != third:
                leak_per_prefix[one].append(third)
        for prefix, leaked_thirds in leak_per_prefix.items():
            n_proper = third_counter[prefix]
            n_leaked = sum(third_counter[t] for t in leaked_thirds)
            n_leaked_paths = sum(len(parent_third_to_paths[parent][t]) for t in leaked_thirds)
            sample_proper = next(iter(parent_third_to_paths[parent][prefix]))
            sample_leaked = sorted(
                {p for t in leaked_thirds for p in parent_third_to_paths[parent][t]},
                key=lambda x: -third_counter[x.split(" > ")[2]]
            )[:5]
            leakage_rows.append({
                "parent": " > ".join(parent),
                "leaked_prefix": prefix,
                "n_proper_skus": n_proper,
                "n_leaked_skus": n_leaked,
                "n_leaked_paths": len(leaked_thirds),
                "sample_proper_path": sample_proper,
                "sample_leaked_paths": " | ".join(sample_leaked),
            })

    leakage_rows.sort(key=lambda r: -r["n_leaked_skus"])
    cols = ["parent", "leaked_prefix", "n_proper_skus", "n_leaked_skus",
            "n_leaked_paths", "sample_proper_path", "sample_leaked_paths"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(leakage_rows)
    print(f"  scanned {n_total:,} rows × 2 columns")
    print(f"  parents with content     : {len(parent_to_thirds):,}")
    print(f"  branch-leakage findings  : {len(leakage_rows):,}")
    print(f"  total LEAKED SKUs        : {sum(r['n_leaked_skus'] for r in leakage_rows):,}")
    print(f"  wrote {OUT.name}")
    print()
    print("=" * 90)
    print("TOP 30 BRANCH-LEAKAGE OFFENDERS BY LEAKED-SKU COUNT")
    print("=" * 90)
    for r in leakage_rows[:30]:
        print(f"\n  parent='{r['parent']}'  leaked_prefix='{r['leaked_prefix']}'")
        print(f"    proper branch ({r['n_proper_skus']} SKUs): {r['sample_proper_path']}")
        print(f"    leaked off branch ({r['n_leaked_skus']} SKUs across {r['n_leaked_paths']} paths):")
        for s in r['sample_leaked_paths'].split(" | ")[:5]:
            print(f"      - {s}")


if __name__ == "__main__":
    main()
