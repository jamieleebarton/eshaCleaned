# 12-week plan audit V3 — after encoder fix (2026-05-09)

**Plan file:** `audit_results/multi_week_ours_12w_v3.json`
**Mode:** thrifty, 4 people, 2000 cal/day, 12 weeks
**Total cost:** $1,011.80 ($84.32/wk, $3.01/person/day)
**Recipes:** 252 unique, 41 repeats
**Recipe-level calculability: 92.35%** (V2: 91.70%, V1: 74.30%, V0: 0.27%)

## V1 → V2 → V3

| Metric | V1 (after first round) | V2 (Bugs 1–6) | **V3 (encoder fix)** |
|---|---|---|---|
| Calculability | 74.30% | 91.70% | **92.35%** |
| Total cost / 12 wk | $1,035.38 | $1,048.25 | **$1,011.80** |
| **exact tier %** | **58.0%** | **57.5%** | **91.4%** |
| path_only tier % | 39.5% | 39.9% | 6.4% |
| RESOLVED_LOSSY flags | 795 | 756 | **121** |
| NO_RESOLUTION lines | 27 | 0 | 0 |
| IMPOSTER_TOKEN flags | 18 | 1 | 10 (most are false positives — bouillon = broth) |
| Mott's Strawberry Applesauce wrong | 5 | 0 | 0 |
| Kraft Mozzarella Blend wrong | 11 | 0 | 0 |
| Smart Balance "oil" wrong | 6 | 0 | 0 |

**The big win:** exact-tier resolution went from 58% → **91.4%**. That means the encoder is now producing htc_codes that match the priced data directly without needing path_only fallback. Architectural fix landed.

## Verified target picks (all the Phase 0 REAL_BUGs)

| Recipe item / cluster | Before | After (V3 picks via exact tier) |
|---|---|---|
| Broth/Stock (44k recipe lines) | Routed to Poultry/Beef/Vegetables/Fish (wrong) | **Great Value Chicken Broth 14.5oz**, **Reduced Sodium Chicken Broth 32oz**, etc. — 45 broth picks across the 12-wk plan, all real broth SKUs |
| Baking soda (32k lines) | Routed to Beverage > Carbonated > Soda | **Great Value Baking Soda 1lb** ✓ |
| Almond/vanilla/yeast extracts | Routed to Nuts/Beverage/Spices wrong | **Great Value Pure Vanilla Extract 1fl oz**, **Great Value Active Dry Yeast** ✓ |
| Sauerkraut (1.3k) | Routed to Vegetable Spread | **Great Value Sauerkraut 14.5oz** ✓ |
| Vanilla bean | Routed to Pantry > Beans (legumes!) | **Pantry > Spices & Seasonings > Vanilla Bean** ✓ |
| Chocolate chips | Routed to Dairy via "milk" | **Pantry > Chocolate Chips** ✓ |
| Coconut flakes | Routed to Snack > Candy > Candied Fruit | **Pantry > Flakes > Coconut Flakes** ✓ |
| Cayenne / ground red pepper | Routed to Vegetables | **Pantry > Spices & Seasonings > Cayenne Pepper** ✓ |

## What the encoder fix actually did (Phase 3 mechanics)

Inserted **8 new precedence-guard rules** at the top of `GROUP_RULES` in `recipe_mapper/v1/htc/encoder.py`. Each catches a specific item-pattern that was being misrouted by a downstream broad-noun rule:

1. broth/stock/bouillon → group J (was 2/3/4/6)
2. baking soda/powder/bicarbonate/yeast → group J (was D)
3. extracts/essences/flavorings (16 flavor variants) → group E (was A/D/E-generic)
4. chocolate chips (milk/white/dark/semisweet/butterscotch/cinnamon/peanut-butter) → group J (was 1)
5. coconut flakes/shreds/desiccated → group J (was 1)
6. cayenne / ground red pepper / crushed red pepper → group E (was 6)
7. dried/dehydrated onion flakes → group E (was 6)
8. sauerkraut → group J (was F via fallback)

Re-ran `tag_ingredients_with_htc.py` → **23,857 unique items changed group** (32% of the 74,624-item recipe-ingredient corpus). Re-ran `restamp_recipes_unified_htc.py` → **2,319,244 recipe lines (49% of 4.7M) got their htc_code rewritten**.

Re-ran the rest of the pipeline. Tensor cache exclusions: 37,436 recipes with partial-unresolved (was 36,027) — slight uptick because the new finer-grained codes surface more genuine product-data gaps.

## What's left (the real gaps, not encoder bugs)

Top 15 remaining NO_MATCH concept_keys (recipe lines affected):

| recipes | concept_key | type |
|---:|---|---|
| 7,772 | Frozen > Vegetables > Ginger | recipe wants frozen, no priced |
| 5,907 | Pantry > Baking Decorations > Candied Fruit | true gap |
| 1,903 | Frozen > Vegetables > Squash | likely fresh only at retail |
| 1,732 | Frozen > Frozen Fruit > Cherries | frozen pool weak |
| 1,718 | Produce > Herbs > Mint | true gap (no fresh herbs in priced) |
| 1,405 | Pantry > Spreads > Lime Curd | true gap |
| 1,217 | Produce > Herbs > Mint (different htc) | same as above |
| 1,054 | Dairy > Cream > Creme Fraiche | true gap |
| 796 | Pantry > Grain > Wheat > Wheat Bread | priced has only 1 SKU |
| 772 | Frozen > Appetizers > Hot Dog | recipe wants frozen, priced has fresh |
| 642 | Beverage > Alcoholic Beverages > Sake | true gap |
| 560 | Produce > Herbs > Lovage | true gap |
| 493 | Pantry > Spices & Seasonings > Mint | partial — fresh-mint variant |
| 437 | Pantry > Sauces & Salsas > Miso | true gap (rare in priced) |
| 398 | Meal > Rice & Grains > Brown Rice | the recipe is a prepared meal, not raw rice |

These need either: more SKUs in `priced_products_v2.db`, more substitute overrides, or accepting NO_MATCH as honest.

## Notes on the audit's "false positive" flags

- **IMPOSTER_TOKEN went up from 1 to 10**. Most are actually correct picks: "Knorr Chicken Cube Bouillon" for chicken-broth recipes (bouillon = broth — substitute is fine), "Maggi Beef Bouillon Cubes" for bouillon-cube recipes (correct). The `picked_recipe_audit.py` IMPOSTER list flags "bouillon" as imposter, which is wrong. One genuine concern: "Great Value Shredded Caroline Reaper Blend Cheese" picked for a generic "Cheese" pool — the variant-prune from Bug 5 should have dropped this; the pool may have all-flavored SKUs (no plain to anchor against), so the prune didn't fire. Minor, can patch.
- **TINY_POOL went up to 122** because exact-tier matches now succeed against smaller, more specific pools (which is the right behavior; previously path_only flattened many recipes onto a few large pools).

## What this round delivered

- Exact-tier resolution: 11.4% → **29.4%** (concept-key level)
- Exact-tier resolution: 58% → **91.4%** (in picked recipes)
- Recipe coverage: 91.7% → **92.35%**
- Cost: $1,048 → **$1,012** (more accurate matches → cheaper)
- All Phase 0 REAL_BUGs (broth, baking soda, extracts, chocolate chips, coconut flakes, cayenne, sauerkraut) resolved at the encoder level — no per-item overrides needed for those classes anymore.

## Next: Phase 5 — delete redundant overrides

`htc_cp_overrides.csv` currently has ~280 rows. Many were for items the encoder now handles natively. Going to walk the override list, encode each item, and delete rows where the encoder produces the right cp without help. Expected: ~280 → <50.

Then Phase 6 — ground-truth tests so this never regresses.
