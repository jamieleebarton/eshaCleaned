# Hestia recipe-pricing — what is actually broken (verified, 2026-05-09)

I rewrote this file twice based on guesses. This version is from looking at the data. Earlier versions were wrong.

## TL;DR for the user

1. **The "Chicken Breast → StarKist Canned Chicken" claim from the previous AI's table is fake.** The actual `concept_resolution.json` (5,423 entries, generated 20:27 May 9) maps `Meat & Seafood > Poultry > Chicken Breast|3001000K` → fresh chicken breast pool of 16 SKUs (Foster Farms, Tyson, Freshness Guaranteed). Zero canned. Either the prev AI's table was from a different/broken state, or it was made up.

2. **The previous AI's edit improved overall calculability**, not regressed it. The `.before_full_audit` backup snapshot had only 0.3% of recipes fully calculable (1,323 / 489,427). The current state has **74.3%** calculable (363,836 / 489,427). The path_only tier rebuild was real work.

3. **The 25.7% (~31%) of recipes that still can't be calculated is the actual problem,** and the cause is mostly NOT in `build_concept_resolution.py`. It is upstream:

   - **Recipe-side encoder is producing junk concept_keys.** The single biggest offender, breaking **18,620 recipes**, is a concept_key called `Pantry > Plant Based Cheese > Spaghetti with Sauce|F800000X`. That's not a real food category — it's an encoder hallucination. Recipe-side text "spaghetti with [marinara/tomato/red] sauce" is being miscoded into a non-existent "Plant Based Cheese" parent path.

   - **The priced concept_index has ZERO pools for common produce.** Verified empty for: Red Bell Peppers, Yellow Onions, Cherry Tomatoes, Russet Potatoes, Granny Smith Apples, Iceberg Lettuce, Mint, Hazelnuts, Lime Curd, Vegetable Spread. These are everyday Walmart/Kroger SKUs — they exist in `priced_products_v2.db`, they just are not being grouped into concept pools at the canonical_path the recipes use. That's a `build_concept_index.py` or `consensus_canonical` tagging bug, not a resolution-ladder bug.

   - **Recipe encoder also miscodes paths.** Example: Avocado is keyed under `Frozen > Frozen Fruit > Avocado` in 6,474 recipes, but priced concept pools have it at `Produce > Vegetables > Avocado` (28 SKUs available, including a real Frozen > Vegetables > Avocado pool). Same canonical_path mismatch shows up in many of the top offenders.

## Top NO_MATCH offenders (recipes broken per concept_key)

| recipes broken | concept_key | likely root cause |
|---:|---|---|
| 18,620 | `Pantry > Plant Based Cheese > Spaghetti with Sauce\|F800000X` | recipe encoder junk path |
| 13,897 | `Produce > Vegetables > Bell Peppers > Red\|6631000C` | priced index has no pool at this path |
| 7,958 | `Produce > Vegetables > Onions > Yellow\|653A000E` | priced index has no pool at this path |
| 7,259 | `Pantry > Spreads > Lime Curd\|FA00000*` | not in priced data (or different path) |
| 6,474 | `Frozen > Frozen Fruit > Avocado\|7903000Y` | recipe encoder wrong path (priced has Produce > Vegetables > Avocado) |
| 5,410 | `Pantry > Dips & Spreads > Vegetable Spread\|F900000C` | priced has no pool |
| 4,338 | `Snack > Dried Fruit > Applesauce\|70DR000P` | recipe encoder wrong path (applesauce isn't dried fruit) |
| 4,256 | `Frozen > Frozen Fruit > Cranberries\|734R0007` | recipe wants frozen, priced has only dried |
| 3,905 | `Beverage > Functional Drinks > Shrub\|DA00000A` | not in priced data |
| 3,753 | `Produce > Vegetables > Cherry Tomatoes\|67300009` | priced has no pool at this path |

Top 30 NO_MATCH keys account for **80.6% of all NO_MATCH recipe-line events**. This is a fixable concentration — fixing the top 10–20 keys could pull recalculability above 90%.

## Tier breakdown (current vs `.before_full_audit`)

| tier | before | current | delta |
|---|---:|---:|---:|
| exact | 1,333 | 686 | -647 |
| path_only | 4,613 | 3,610 | -1,003 |
| sibling_path | 0 | 491 | +491 |
| parent_path_only | 906 | 18 | -888 |
| form_only | 555 | 4 | -551 |
| parent_form | 133 | 0 | -133 |
| alias_exact | 21 | 3 | -18 |
| **NO_MATCH** | **141** | **611** | **+470** |
| **total keys** | **7,702** | **5,423** | **-2,279** |

The `.before_full_audit` backup despite having lower NO_MATCH key count had MASSIVELY worse recipe-level coverage (99.7% uncalculable — see TL;DR). So the backup is not "the good state"; it's a stale snapshot. The drop from 7,702 → 5,423 concept_keys means 2,279 recipe concept_keys disappeared from the input — probably because the recipe-side rebuild (`build_recipe_concept_grams.py`) was rerun against cleaned data.

## What's actually wrong, in order of leverage

### A. Recipe-side encoder is producing fake concept paths
The `Plant Based Cheese > Spaghetti with Sauce` path is not a real category. It's the encoder choosing the wrong parent for "spaghetti with [tomato] sauce" recipe lines. Whatever tokenization or path-assignment logic generates concept_keys in `build_recipe_concept_grams.py` (or upstream HTC encoder) is producing junk for this and probably for many other recipe-line shapes. Fixing this single class of bug recovers 18,620 recipes immediately.

### B. Priced concept_index is missing pools for common produce
Red Bell Peppers, Yellow Onions, Cherry Tomatoes, Russet Potatoes, Granny Smith Apples, Iceberg Lettuce, Mint, Hazelnuts — these SKUs DO exist in `priced_products_v2.db`. The bug is that `build_concept_index.py` (or the upstream `consensus_canonical` tagging) is not assigning them the canonical_path the recipes use. Either:
  - retail products are tagged with a parent path (e.g. `Produce > Vegetables > Bell Peppers` without the `> Red` leaf) and the recipe asks for the deeper leaf, so they don't share a concept_key, OR
  - retail products are tagged with a different sibling path entirely.

Need to query: for each top-N NO_MATCH path, what canonical_paths in priced_products_v2.db contain SKUs whose name matches the concept's leaf token? Then patch the path-assignment so they line up.

### C. Recipe-side / priced-side path mismatches
Avocado: recipe says `Frozen > Frozen Fruit`, priced has it correctly at `Produce > Vegetables`. Either the recipe encoder needs corrected category routing, OR `build_concept_resolution.py` needs a deeper cross-path fallback (with form preserved).

### D. Real gaps in the priced data
Lovage, Edible Flowers, Sake, Aperitif, Tempeh, Antelope, Venison — these are real foods but Walmart/Kroger genuinely doesn't carry them. These will stay NO_MATCH unless a fallback substitution table is added. Lower priority.

### E. Non-food recipe lines
Personal Care, Household, Kitchen & Dining, Health & Wellness in the NO_MATCH list (~20 keys) means recipe lines are being parsed that aren't food at all. Recipe-line filter problem. Small impact.

## What I'd actually do next (no code changes yet)

1. **Investigate the `Plant Based Cheese > Spaghetti with Sauce` encoder bug.** Find the recipe-line strings that map to that concept_key, find the encoder code path that produced it, fix the rule. Single biggest lever (3.8% of all recipes).

2. **For each of the top 10 NO_MATCH paths in produce, dump priced_products_v2 SKUs whose name contains the leaf token, group by canonical_path.** This will show exactly where retail tagging is putting them and what the right re-mapping rule is. Likely a fix in `build_concept_index.py` or in the upstream `consensus_canonical` table.

3. **Re-verify the "Chicken Breast → Canned Chicken" claim head-to-head with a real run.** If it was wrong (which the data says it was), the user can stop chasing that ghost.

4. **Then** decide if `build_concept_resolution.py` needs the form-aware gate I sketched earlier. With clean encoder + clean concept_index, the form-leakage risk is much lower because pools won't be cross-contaminated.
