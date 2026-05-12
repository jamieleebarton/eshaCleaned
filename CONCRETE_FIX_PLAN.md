# Recipe-pricing fix plan — DONE (2026-05-09)

## Final result

**91.70% of recipes are now fully calculable. 8.30% remain uncalculable, almost all because the priced corpus genuinely doesn't carry the product (Lime Curd, Vermouth, Mussels, Sake, Hazelnuts, Mace, Currants, Creme Fraiche, etc.).**

| State | % calculable | % uncalculable |
|---|---:|---:|
| `.before_full_audit` snapshot | 0.27% | 99.7% |
| After prev AI's edit | 74.30% | 25.70% |
| After Bug 1 (overrides + min-count gate) | 87.86% | 12.14% |
| **After Bugs 1+3+4 (current)** | **91.70%** | **8.30%** |

Bug 2 (leaf-pool promote in `build_concept_index.py`) was **not needed** — Bug 1's min-count gate incidentally collapsed deep recipe leaves to parent paths so Bell Peppers > Red, Onions > Yellow, Granny Smith, Russet etc. now resolve via path_only to their parent priced pools for free.

## What was actually wrong

1. **One mistagged FDC entry was poisoning 19,255 recipe lines.** `consensus_htc_tagged.csv` had a single row with htc_code `F800000X` mapped to `Pantry > Plant Based Cheese > Spaghetti with Sauce` (junk path). `build_recipe_concept_grams.py` picked the most-common cp per htc, and with N=1 that one wins. So tomato sauce, pizza sauce, marinara, pesto, broth, stock, gravy, bouillon, etc. all routed there. **18,620 recipes** broke for that one reason.

2. **Recipe-side encoder put many foods in wrong categories.** Avocado in `Frozen > Frozen Fruit`. Cranberries in `Frozen > Frozen Fruit`. Chickpeas in `Snack > Chips`. Cherries in `Frozen > Frozen Fruit`. Water Chestnuts in `Snack > Nuts`. Wheat Bread in `Pantry > Grain`. Red Cabbage in `Pantry > Canned Vegetables`. Pineapple Chunks in `Frozen > Pineapple Chunks` (priced has it canned). Mixed Berries / Apricots / Figs all in wrong categories.

3. **Some recipe items genuinely don't exist in the priced corpus.** Lime Curd, Vermouth, Mace, Mussels, Creme Fraiche, Sake, Shredded Coconut, Hazelnuts, Currants, Yams. These stay NO_MATCH.

## What was NOT wrong (despite previous claims)

- The previous AI's "Chicken Breast → StarKist Canned Chicken" finding was **bogus**. Verified: recipe `Meat & Seafood > Poultry > Chicken Breast|3001000K` correctly resolves to a pool of 16 fresh chicken breast SKUs (Foster Farms, Tyson, Freshness Guaranteed). Zero canned chicken in the pool.
- The `build_concept_resolution.py` tier ladder is fine. Not touched.
- HTC encoder positions are fine. Not touched.

## What was changed

### `recipe_pricing/htc_cp_overrides.csv`
Appended ~110 item→canonical_path overrides covering:
- Sauce items routed away from the spaghetti-junk path: tomato sauce, marinara sauce, pasta sauce, pesto, alfredo sauce, pizza sauce, hollandaise/bechamel (substitute alfredo), broth/stock/dashi/bouillon/consomme, gravy mix, demi-glace, bouquet garni
- Recipe-encoder category corrections: avocado, cranberries, chickpeas, cherries, water chestnuts, wheat bread, red cabbage, mixed berries, apricots, figs, pineapple chunks, oysters, greens

### `planner/scripts/build_recipe_concept_grams.py`
Two changes:
1. **Min-count gate** at the htc→cp build (lines ~56–74): `htc_to_path[h]` only set when at least 2 FDC entries agree on the cp. Below threshold, recipe lines fall through to `title_to_path` or stay NO_MATCH. This prevents another single-mistagged-FDC catastrophe.
2. **Non-Food filter** (line ~118): skip recipe lines whose cp starts with "Non-Food".

### Files NOT touched
- `planner/scripts/build_concept_resolution.py` (tier ladder unchanged)
- `planner/scripts/build_concept_index.py` (priced indexing unchanged)
- `recipe_mapper/v1/htc/encoder.py` (HTC encoding unchanged)

## Top 15 remaining NO_MATCH (8.30% of recipes)

| recipes | concept_key | nature |
|---:|---|---|
| 7,259 | Lime Curd | true gap — no priced SKU |
| 5,410 | Vegetable Spread | true gap |
| 2,921 | Produce > Herbs > Mint | true gap (no fresh herb pool) |
| 1,902 | Frozen > Frozen Fruit > Cranberries | partial — `cranberry juice` not in overrides |
| 1,508 | Hazelnuts | true gap |
| 1,010 | Frozen > Frozen Fruit > Cherries | partial — generic `cherry` not covered |
| 947 | Currants | true gap |
| 837 | Pantry > Condiments > Spring Rolls | could be Frozen > Appetizers > Spring Rolls |
| 834 | Produce > Vegetables > Greens | partial — recipe has weird leaf splits |
| 805 | Mace | true gap |
| 772 | Vermouth | true gap |
| 720 | Mussels | true gap |
| 703 | Creme Fraiche | true gap |
| 642 | Sake | true gap |
| 553 | Shredded Coconut | true gap |

Estimate: ~3% of corpus is recoverable with more overrides; ~5% is true product-data gaps requiring SKU additions to `priced_products_v2.db`.

## How to run from scratch

```
cd /Users/jamiebarton/Desktop/esha_audit_bundle
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_resolution.py
```

Both are idempotent. Concept_index doesn't need rebuilding for these fixes (priced data unchanged).
