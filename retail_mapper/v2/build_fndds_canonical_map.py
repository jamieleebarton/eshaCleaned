#!/usr/bin/env python3
"""Generate FNDDS_CANONICAL_PATH_MAP and FNDDS_CANONICAL_IDENTITY_MAP from the
audit CSV, picking dominant path/identity per FNDDS code.

Rule: for any FNDDS code with at least N=3 SKUs and a dominant path that covers
≥60% of those SKUs, force all SKUs with that FNDDS to the dominant path and
identity.

Out-of-scope: FNDDS codes whose paths span multiple top-levels (Frozen, Pantry,
Produce). Those are legitimate form-differences (Corn at Frozen Vegetables vs
Pantry Canned Vegetables vs Produce Vegetables). Excluded by checking
top-level diversity ≥2.

Outputs:
  - retail_mapper/v2/fndds_canonical_map.py  (Python dict, ready to import)
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "full_corpus_audit.csv"
OUT = V2 / "fndds_canonical_map.py"

DOMINANCE_THRESHOLD = 0.6
MIN_SKUS = 3

# Description-keyword rules. When an FNDDS description matches one of these
# patterns, force its canonical_path AND identity regardless of LLM-dominance.
# The FNDDS description is more reliable than the LLM-assigned dominant path
# for category-shaped queries (cake mix products always go to Baking Mixes,
# regardless of how the LLM tagged them).
# Order: most-specific first.
DESC_RULES: list[tuple[str, str, str]] = [
    # pattern in FNDDS desc, canonical path, canonical identity
    ("english muffin",      "Bakery > English Muffins",            "English Muffins"),
    ("pancake mix",         "Pantry > Baking Mixes > Pancake Mix",   "Pancake Mix"),
    ("waffle mix",          "Pantry > Baking Mixes > Waffle Mix",    "Waffle Mix"),
    ("cake mix",            "Pantry > Baking Mixes > Cake Mix",      "Cake Mix"),
    ("brownie mix",         "Pantry > Baking Mixes > Brownie Mix",   "Brownie Mix"),
    ("cookie mix",          "Pantry > Baking Mixes > Cookie Mix",    "Cookie Mix"),
    ("biscuit mix",         "Pantry > Baking Mixes > Biscuit Mix",   "Biscuit Mix"),
    ("muffin mix",          "Pantry > Baking Mixes > Muffin Mix",    "Muffin Mix"),
    ("bread mix",           "Pantry > Baking Mixes > Bread Mix",     "Bread Mix"),
    ("baking mix",          "Pantry > Baking Mixes",                  "Baking Mix"),
    ("dough mix",           "Pantry > Baking Mixes > Dough Mix",      "Dough Mix"),
    ("crouton",             "Bakery > Croutons",                      "Croutons"),
    ("breadstick",          "Bakery > Breadsticks",                   "Breadsticks"),
    ("doughnut",            "Bakery > Doughnuts",                     "Doughnuts"),
    ("donut",               "Bakery > Doughnuts",                     "Doughnuts"),
    ("churros",             "Bakery > Pastry > Churros",              "Churros"),
    ("danish",              "Bakery > Pastry > Danishes",             "Danishes"),
    ("croissant",           "Bakery > Pastry > Croissants",           "Croissants"),
    ("eclair",              "Bakery > Pastry > Eclairs",              "Eclairs"),
    ("scone",               "Bakery > Scones",                        "Scones"),
    ("biscotti",            "Bakery > Biscotti",                      "Biscotti"),
    ("cornbread",           "Bakery > Cornbread",                     "Cornbread"),
    ("corn bread",          "Bakery > Cornbread",                     "Cornbread"),
    ("rye bread",           "Bakery > Bread > Rye Bread",             "Rye Bread"),
    ("pumpernickel",        "Bakery > Bread > Pumpernickel Bread",    "Pumpernickel Bread"),
    ("sourdough bread",     "Bakery > Bread > Sourdough Bread",       "Sourdough Bread"),
    ("bagel",               "Bakery > Bagels",                        "Bagels"),
    ("naan",                "Bakery > Naan",                          "Naan"),
    ("pita",                "Bakery > Pita Bread",                    "Pita Bread"),
    ("tortilla",            "Bakery > Tortillas",                     "Tortillas"),
    ("flatbread",           "Bakery > Flatbread",                     "Flatbread"),
    ("flat bread",          "Bakery > Flatbread",                     "Flatbread"),
    ("crab cake",           "Meat & Seafood > Crab > Crab Cakes",     "Crab Cakes"),
    ("fish cake",           "Meat & Seafood > Seafood > Fish Cakes",  "Fish Cakes"),
    ("salmon cake",         "Meat & Seafood > Salmon > Salmon Cakes", "Salmon Cakes"),
    ("hard candy",          "Snack > Candy > Hard Candy",             "Hard Candy"),
    ("gummy",               "Snack > Candy > Gummy Candy",            "Gummy Candy"),
    ("chocolate candy",     "Snack > Candy > Chocolate Candy",        "Chocolate Candy"),
    ("chocolate bar",       "Snack > Chocolate Candy > Chocolate Bars","Chocolate Bars"),
    ("rice cake",           "Snack > Rice Cakes",                     "Rice Cakes"),
    ("popcorn",             "Snack > Popcorn",                        "Popcorn"),
    ("pretzel",             "Snack > Pretzels",                       "Pretzels"),
    ("trail mix",           "Snack > Trail Mix",                      "Trail Mix"),
    ("granola",             "Snack > Granola",                        "Granola"),
    ("granola bar",         "Snack > Bars > Granola Bars",            "Granola Bars"),
    ("protein bar",         "Snack > Bars > Protein Bars",            "Protein Bars"),
    ("energy bar",          "Snack > Bars > Energy Bars",             "Energy Bars"),
    ("cereal bar",          "Snack > Bars > Cereal Bars",             "Cereal Bars"),
    ("snack cake",          "Bakery > Snack Cakes",                   "Snack Cakes"),
    ("honey bun",           "Bakery > Snack Cakes > Honey Buns",      "Honey Buns"),
    ("twinkie",             "Bakery > Snack Cakes > Twinkies",        "Twinkies"),
    ("ho ho",               "Bakery > Snack Cakes > Ho Hos",          "Ho Hos"),
    ("ding dong",           "Bakery > Snack Cakes > Ding Dongs",      "Ding Dongs"),
    ("zinger",              "Bakery > Snack Cakes > Zingers",         "Zingers"),
    ("ice cream",           "Frozen > Ice Cream",                     "Ice Cream"),
    ("frozen yogurt",       "Frozen > Frozen Yogurt",                 "Frozen Yogurt"),
    ("almond milk",         "Beverage > Plant Milk > Almond Milk",    "Almond Milk"),
    ("oat milk",            "Beverage > Plant Milk > Oat Milk",       "Oat Milk"),
    ("soy milk",            "Beverage > Plant Milk > Soy Milk",       "Soy Milk"),
    ("coconut milk",        "Beverage > Plant Milk > Coconut Milk",   "Coconut Milk"),
    ("rice milk",           "Beverage > Plant Milk > Rice Milk",      "Rice Milk"),
    ("greek yogurt",        "Dairy > Yogurt > Greek Yogurt",          "Greek Yogurt"),
    ("whole milk",          "Dairy > Milk > Whole Milk",              "Whole Milk"),
    ("hummus",              "Pantry > Dips & Spreads > Hummus",       "Hummus"),
    ("mac and cheese",      "Meal > Pasta Dishes > Mac and Cheese",   "Mac and Cheese"),
    ("lasagna",             "Meal > Pasta Dishes > Lasagna",          "Lasagna"),
    ("spaghetti",           "Pantry > Pasta > Spaghetti",             "Spaghetti"),
    ("baby food",           "Baby & Toddler > Baby Food",             "Baby Food"),
    ("infant formula",      "Baby & Toddler > Infant Formula",        "Infant Formula"),
]


def apply_desc_rule(desc: str) -> tuple[str, str] | None:
    """If desc matches a known pattern, return (canonical_path, canonical_identity).
    Returns None if no rule matches. Most-specific patterns first."""
    desc_l = desc.lower()
    for pat, path, ident in DESC_RULES:
        if pat in desc_l:
            return path, ident
    return None

csv.field_size_limit(sys.maxsize)


def main() -> None:
    print(f"  reading {SRC.name}")
    fndds_paths: dict[str, Counter] = defaultdict(Counter)
    fndds_identities: dict[str, Counter] = defaultdict(Counter)
    fndds_descs: dict[str, str] = {}

    with SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cp = (row.get("canonical_path") or "").strip()
            pid = (row.get("product_identity_fixed") or "").strip()
            f = (row.get("fndds_code") or "").strip()
            fdesc = (row.get("fndds_desc") or "").strip()
            if not (cp and pid and f):
                continue
            fndds_paths[f][cp] += 1
            fndds_identities[f][pid] += 1
            if f not in fndds_descs and fdesc:
                fndds_descs[f] = fdesc

    print(f"  scanned {sum(sum(c.values()) for c in fndds_paths.values()):,} fdc rows")
    print(f"  fndds codes: {len(fndds_paths):,}")

    path_map: dict[str, str] = {}
    id_map: dict[str, str] = {}
    skipped_form_diff = 0
    skipped_low_dominance = 0
    skipped_too_few = 0
    accepted_by_desc = 0
    accepted = 0

    for fcode, paths in fndds_paths.items():
        n_skus = sum(paths.values())
        if n_skus < MIN_SKUS:
            skipped_too_few += 1
            continue

        # Description-rule override: FNDDS desc beats LLM dominance.
        desc_rule = apply_desc_rule(fndds_descs.get(fcode, ""))
        if desc_rule is not None:
            path_map[fcode], id_map[fcode] = desc_rule
            accepted_by_desc += 1
            continue

        # Check top-level diversity. If paths span multiple top-levels, it's
        # likely a legitimate form-diff (Corn at Frozen / Pantry / Produce).
        tops = {p.split(">", 1)[0].strip() for p in paths}
        if len(tops) > 1:
            # Form diff — check if dominant path STILL covers >85% (then it's
            # a strong canonical)
            dominant_path, n_dom = paths.most_common(1)[0]
            if n_dom / n_skus < 0.85:
                skipped_form_diff += 1
                continue

        dominant_path, n_dom = paths.most_common(1)[0]
        if n_dom / n_skus < DOMINANCE_THRESHOLD:
            skipped_low_dominance += 1
            continue

        # Pick canonical identity from the dominant cluster
        ids = fndds_identities[fcode]
        dominant_id, _ = ids.most_common(1)[0]

        path_map[fcode] = dominant_path
        id_map[fcode] = dominant_id
        accepted += 1

    print(f"  accepted (desc-rule):               {accepted_by_desc:,}")
    print(f"  accepted (dominance):               {accepted:,}")
    print(f"  skipped (form-diff cross-toplevel): {skipped_form_diff:,}")
    print(f"  skipped (low-dominance same-top):   {skipped_low_dominance:,}")
    print(f"  skipped (too few SKUs):             {skipped_too_few:,}")
    accepted = accepted + accepted_by_desc

    # Emit the Python file
    lines = [
        '"""FNDDS canonical-path/identity overrides.',
        "",
        f"Auto-generated by audit_fndds_path_clusters.py / build_fndds_canonical_map.py.",
        f"Trust threshold: dominant path covers ≥{int(DOMINANCE_THRESHOLD*100)}% of SKUs",
        f"(or ≥85% if paths span multiple top-levels).",
        "",
        "When a SKU has fndds_code in this map, force its canonical_path/identity",
        "to the values below — overrides anything the LLM or path-vote produced.",
        '"""',
        "",
        "FNDDS_CANONICAL_PATH_MAP: dict[str, str] = {",
    ]
    for fcode in sorted(path_map):
        d = fndds_descs.get(fcode, "").replace('"', "'")
        path = path_map[fcode].replace('"', "'")
        lines.append(f'    "{fcode}": "{path}",  # {d}')
    lines.append("}")
    lines.append("")
    lines.append("FNDDS_CANONICAL_IDENTITY_MAP: dict[str, str] = {")
    for fcode in sorted(id_map):
        d = fndds_descs.get(fcode, "").replace('"', "'")
        ident = id_map[fcode].replace('"', "'")
        lines.append(f'    "{fcode}": "{ident}",  # {d}')
    lines.append("}")
    lines.append("")
    OUT.write_text("\n".join(lines))
    print(f"  wrote {OUT.name} ({accepted} entries)")


if __name__ == "__main__":
    main()
