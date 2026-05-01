#!/usr/bin/env python3
"""Generate path_rewrite_map.py from path_quality_clusters.csv.

For each word-order swap cluster: every variant != suggested_canonical gets
a rewrite entry mapping its full canonical_path → the canonical's full path.

For comma-leaves and deep-paths: rewrite from MANUAL_PATH_REWRITES below.

Output: retail_mapper/v2/path_rewrite_map.py with PATH_REWRITE: dict[str, str].
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
SRC = V2 / "path_quality_clusters.csv"
OUT = V2 / "path_rewrite_map.py"

csv.field_size_limit(sys.maxsize)

# Hand-written rewrites for comma-leaves, deep-paths, and any other
# non-cluster path-quality issues. These get merged with the cluster-derived
# rewrites. Keys are FULL canonical_path strings.
# Parent-segment rewrites — applied as prefix substitutions across every
# descendant path. Use for awkward intermediate segments that affect a whole
# subtree (avoiding having to enumerate every leaf manually).
PREFIX_REWRITES: dict[str, str] = {
    "Frozen > Fruit & Fruit Juice Concentrates":  "Frozen > Fruit",
    "Snack > Rice Cakes & Corn Cakes":             "Snack > Rice Cakes",
}

MANUAL_PATH_REWRITES: dict[str, str] = {
    # ---- Comma-leaf flattenings ----
    # Frozen breakfast group — drop the comma-blob middle segment.
    "Frozen > Pancakes, Waffles, French Toast & Crepes > Pancakes":
        "Frozen > Pancakes",
    "Frozen > Pancakes, Waffles, French Toast & Crepes > Waffles":
        "Frozen > Waffles",
    "Frozen > Pancakes, Waffles, French Toast & Crepes > French Toast":
        "Frozen > French Toast",
    "Frozen > Pancakes, Waffles, French Toast & Crepes > French Toast Sticks":
        "Frozen > French Toast > French Toast Sticks",
    "Frozen > Pancakes, Waffles, French Toast & Crepes > Pancake Bites":
        "Frozen > Pancakes > Pancake Bites",
    "Frozen > Pancakes, Waffles, French Toast & Crepes > Potato Pancakes":
        "Frozen > Pancakes > Potato Pancakes",
    "Frozen > Breakfast Sandwiches, Biscuits & Meals > Biscuits":
        "Frozen > Breakfast > Biscuits",
    "Frozen > Breakfast Sandwiches, Biscuits & Meals > Breakfast Bake":
        "Frozen > Breakfast > Breakfast Bake",
    "Frozen > Breakfast Sandwiches, Biscuits & Meals > Hash Browns":
        "Frozen > Hash Browns",
    "Frozen > Breakfast Sandwiches, Biscuits & Meals > Oatmeal Bowl":
        "Frozen > Breakfast > Oatmeal Bowl",
    "Frozen > Breakfast Sandwiches, Biscuits & Meals > Hot Cereal":
        "Frozen > Breakfast > Hot Cereal",
    "Frozen > Breakfast Sandwiches, Biscuits & Meals > Omelet Bites":
        "Frozen > Breakfast > Omelet Bites",
    "Pantry > Gelatin, Gels, Pectins & Desserts > Pectin":
        "Pantry > Pectin",
    "Pantry > Gelatin, Gels, Pectins & Desserts > Fruit Pectin":
        "Pantry > Pectin > Fruit Pectin",
    "Produce > Vegetables > Kale, Spinach & Chard":
        "Produce > Vegetables > Leafy Greens",
    "Snack > Popcorn, Peanuts, Seeds & Related Snacks > Toasted Corn Kernels":
        "Snack > Toasted Corn Kernels",
    "Snack > Popcorn, Peanuts, Seeds & Related Snacks > Puffed Sorghum":
        "Snack > Puffed Sorghum",

    # ---- Deep-path flattenings (≥5 segments) ----
    # Leaf duplicates the parent — drop the leaf.
    "Pantry > Pasta > Macaroni > Shells > Macaroni":
        "Pantry > Pasta > Shells",
    "Beverage > Tea > Chai > Concentrate > Chai Concentrate":
        "Beverage > Tea > Chai > Concentrate",
    "Pantry > Pasta > Couscous > Mixes > Couscous Mix":
        "Pantry > Pasta > Couscous Mix",
    "Beverage > Tea > Matcha > Powdered > Matcha Powder":
        "Beverage > Tea > Matcha > Powder",
    "Beverage > Tea > Chai > Mixes > Chai Mix":
        "Beverage > Tea > Chai Mix",
    "Pantry > Grain > Quinoa > Flour > Quinoa Flour":
        "Pantry > Flour > Quinoa Flour",
    "Pantry > Grain > Wheat > Flour > Wheat Bran":
        "Pantry > Grain > Wheat Bran",
    "Pantry > Frosting/Topping > Icing > Cake > Cake Icing":
        "Pantry > Frosting/Topping > Cake Icing",
    # Wrong family or redundant intermediate.
    "Pantry > Sweeteners > Sugar > Cream > Coconut Cream":
        "Pantry > Coconut > Coconut Cream",
    "Pantry > Grain > Wheat > Cereal > Bulgur Wheat":
        "Pantry > Grain > Bulgur",
    "Produce > Vegetables > Potatoes > French Fries > Fries":
        "Produce > Vegetables > Potatoes > French Fries",
    "Produce > Vegetables > Potatoes > French Fries > Waffle Fries":
        "Produce > Vegetables > Potatoes > Waffle Fries",
    "Produce > Vegetables > Potatoes > French Fries > Yuca Fries":
        "Produce > Vegetables > Potatoes > Yuca Fries",
    "Pantry > Grain > Oat Meal > Ground > Flaxseed Meal":
        "Pantry > Seeds > Flaxseed Meal",
    "Pantry > Grain > Rye > Flakes > Rye Bread":
        "Bakery > Bread > Rye Bread",
    "Pantry > Pasta > Macaroni > Meat Sauce > Macaroni and Beef":
        "Pantry > Pasta > Macaroni and Beef",
    "Pantry > Oil > Olives > Garlic > Roasted Garlic":
        "Pantry > Olives > Roasted Garlic",
    "Produce > Vegetables > Potatoes > French Fries > Plantain Fries":
        "Produce > Vegetables > Plantain Fries",
    "Produce > Vegetables > Potatoes > French Fries > Frozen French Fries":
        "Produce > Vegetables > Potatoes > French Fries",
    "Pantry > Sweeteners > Sugar > Chips > White Baking Chips":
        "Pantry > Baking > White Baking Chips",
    "Pantry > Protein > Whey > Concentrate > Whey Protein Concentrate":
        "Pantry > Protein > Whey Protein Concentrate",
    "Pantry > Grain > Wheat > Biscuits > Breakfast Biscuits":
        "Bakery > Biscuits > Breakfast Biscuits",
    "Pantry > Grain > Blend > Oats > Oat Blend":
        "Pantry > Grain > Oat Blend",
    "Pantry > Grain > Wheat > Cereal > Crispbread":
        "Bakery > Crispbread",
    "Pantry > Grain > Wheat > Cereal > Upma":
        "Pantry > Grain > Upma",
    "Pantry > Grain > Wheat > Chips > Farro Chips":
        "Snack > Chips > Farro Chips",
    "Pantry > Grain > Wheat > Flour > Wheat Germ":
        "Pantry > Grain > Wheat Germ",
    "Beverage > Juice > Smoothies > Protein Powders > Protein Smoothie Mix":
        "Beverage > Smoothies > Protein Smoothie Mix",
    "Pantry > Grain > Oat Meal > Ground > Flax Meal":
        "Pantry > Seeds > Flax Meal",
    "Meat & Seafood > Meat > Smoked > Cured > Cured Smoked Meat":
        "Meat & Seafood > Cured Meat > Smoked",
    "Pantry > Pasta > Noodles > Stir Fry > Stir Fry Noodles":
        "Pantry > Pasta > Stir Fry Noodles",
    "Meat & Seafood > Charcuterie > Salame > Trio > Salame Trio":
        "Meat & Seafood > Charcuterie > Salame Trio",
    "Pantry > Butter > Margarine > Sticks > Margarine Sticks":
        "Pantry > Butter > Margarine Sticks",
    "Pantry > Gelatin > Gel > Desserts > Tofu Dessert":
        "Dairy > Tofu > Tofu Dessert",
    "Pantry > Sweeteners > Sugar > Cake Mate > Cake Topper":
        "Bakery > Cake > Cake Topper",
    "Beverage > Carbonated > Soda > Mixes > Soda Water":
        "Beverage > Carbonated > Soda Water",
    "Beverage > Carbonated > Soda > Mixes > Soda Mix":
        "Beverage > Carbonated > Soda Mix",
    "Pantry > Sweeteners > Sugar > Chips > Chocolate Chips":
        "Pantry > Baking > Chocolate Chips",
    "Pantry > Sweeteners > Sugar > Chips > Decorating Chips":
        "Pantry > Baking > Decorating Chips",
    "Beverage > Tea > Matcha > Greens Drink Mix > Matcha Drink Mix":
        "Beverage > Tea > Matcha Drink Mix",
    "Pantry > Soup > Chicken and Wild Rice Soup":
        "Pantry > Soup > Chicken Wild Rice Soup",
}


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run audit_path_quality.py first")

    rewrite: dict[str, str] = {}

    # 0. Preserve any existing rewrites from the prior generation. Once a
    #    cluster has been resolved and the audit CSV rewritten, the cluster
    #    no longer appears in path_quality_clusters.csv — but we still need
    #    to keep the rewrite alive so re-running the pipeline doesn't lose it.
    n_existing = 0
    if OUT.exists():
        prior_ns: dict = {}
        try:
            exec(OUT.read_text(), prior_ns)
            for k, v in (prior_ns.get("PATH_REWRITE") or {}).items():
                rewrite[k] = v
                n_existing += 1
        except Exception as e:
            print(f"  WARN: could not load prior {OUT.name}: {e}")

    # 1. Cluster-derived rewrites (word-order swaps)
    n_cluster = 0
    with SRC.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["issue_type"] != "word_order_swap":
                continue
            parent = row["parent_path"]
            suggested = row["suggested_canonical"].strip()
            if not suggested:
                continue
            canonical_full = f"{parent} > {suggested}" if parent else suggested
            # Each variant != suggested gets a rewrite to canonical_full.
            for chunk in row["variants_with_counts"].split(" | "):
                # chunk = "Variant Name (count)"
                form = chunk.rsplit(" (", 1)[0]
                if form != suggested:
                    old = f"{parent} > {form}" if parent else form
                    rewrite[old] = canonical_full
                    n_cluster += 1

    # 2. Manual rewrites
    n_manual = 0
    for old, new in MANUAL_PATH_REWRITES.items():
        if old in rewrite and rewrite[old] != new:
            print(f"  WARN: manual override conflicts with cluster rule for {old!r}")
        rewrite[old] = new
        n_manual += 1

    # 3. Prefix rewrites — when a parent segment is awkward, rewrite every
    #    descendant path that starts with the bad prefix to the cleaner one.
    n_prefix = 0
    for bad_prefix, good_prefix in PREFIX_REWRITES.items():
        # Walk all distinct paths that start with bad_prefix (we don't have
        # them here, so we read full audit). Easier: just emit prefix rules
        # by reading the audit CSV's parent_path column.
        pass
    # Read full corpus audit briefly to collect all paths starting with a
    # bad prefix and emit per-path rewrites.
    audit_csv = V2 / "full_corpus_audit.csv"
    if audit_csv.exists() and PREFIX_REWRITES:
        seen_paths: set[str] = set()
        with audit_csv.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cp = (r.get("canonical_path") or "").strip()
                if cp and cp not in seen_paths:
                    seen_paths.add(cp)
        for cp in seen_paths:
            for bad, good in PREFIX_REWRITES.items():
                if cp.startswith(bad):
                    new_cp = good + cp[len(bad):]
                    if new_cp != cp and cp not in rewrite:
                        rewrite[cp] = new_cp
                        n_prefix += 1
                    break

    # 3. Resolve transitive chains: if rewrite[A] = B and rewrite[B] = C,
    #    flatten so rewrite[A] = C.
    for k in list(rewrite):
        seen = set()
        cur = rewrite[k]
        while cur in rewrite and cur not in seen:
            seen.add(cur)
            cur = rewrite[cur]
        rewrite[k] = cur

    # Emit Python file
    lines = [
        '"""Path rewrites — applied last in build_audit_csv.py.',
        "",
        "Auto-generated by build_path_rewrite_map.py from",
        "path_quality_clusters.csv + MANUAL_PATH_REWRITES in that script.",
        "",
        "Maps any non-canonical canonical_path string → the canonical form.",
        '"""',
        "",
        "PATH_REWRITE: dict[str, str] = {",
    ]
    for old in sorted(rewrite):
        new = rewrite[old]
        old_q = old.replace('"', '\\"')
        new_q = new.replace('"', '\\"')
        lines.append(f'    "{old_q}": "{new_q}",')
    lines.append("}")
    lines.append("")
    OUT.write_text("\n".join(lines))
    print(f"  wrote {OUT.name} ({len(rewrite)} entries)")
    print(f"    preserved from prior: {n_existing}")
    print(f"    new cluster-derived:  {n_cluster}")
    print(f"    manual:               {n_manual}")
    print(f"    prefix-derived:       {n_prefix}")


if __name__ == "__main__":
    main()
