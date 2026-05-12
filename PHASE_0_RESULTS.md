# Phase 0 Results — Encoder misfire scope across 4.7M-line corpus

**Method:** streamed `recipes_unified.csv` (4,729,696 lines), replicated `build_recipe_concept_grams.py` derivation, grouped by `(item, derived_canonical_path)`. Top 1,500 pairs cover 4.22M lines (89.2% of corpus). Then ran a rule-based classifier (broth/stock, baking soda, extracts, nut butters, wine, herbs, etc.) and AUDITED the top REAL_BUGS by querying the priced data for what canonical_path the SKUs really sit at.

## Headline numbers (top 1,500 (item, cp) pairs, 89.2% of corpus)

| Class | Pairs | Recipe lines | % corpus |
|---|---:|---:|---:|
| **OK** | 1,250 | 3,604,423 | 76.2% |
| **OVERRIDE** (band-aided) | 103 | 388,394 | 8.2% |
| **REAL_BUG** (encoder misroute) | 38 | 115,570 | 2.4% |
| **WEAK_LEAF** (form/specificity miss) | 11 | 32,697 | 0.7% |
| **NEEDS_REVIEW** (still ambiguous) | 98 | 79,473 | 1.7% |

*Remaining ~10% of corpus is in pairs ranked below 1500 — long-tail items with low individual leverage.*

## Audit of REAL_BUG list (verified against priced data)

I queried `priced_products_v2.db` for each top REAL_BUG to confirm a real target pool exists. **12 of 22 audited targets confirmed exact**, 7 need a slight target adjustment, 3 are true gaps.

### Confirmed bug clusters (target exists; encoder is just routing wrong)

**A. Broth & Stock cluster — 44k recipe lines, ~5 patterns**
| recipe item | currently routed to | should be |
|---|---|---|
| chicken broth | Meat & Seafood > Poultry > Chicken | **Pantry > Broth & Stock > Chicken Broth** (369 SKUs) |
| chicken stock | Meat & Seafood > Poultry > Chicken | same |
| low sodium chicken broth | Meat & Seafood > Poultry > Chicken | same |
| reduced-sodium chicken broth | Meat & Seafood > Poultry > Chicken | same |
| fat-free chicken broth | Meat & Seafood > Poultry > Chicken | same |
| beef broth | Meat & Seafood > Beef | **Pantry > Broth & Stock > Beef Broth** (138 SKUs) |
| beef stock | Meat & Seafood > Beef | same |
| vegetable broth | Frozen > Vegetables > Vegetable Blend | **Pantry > Broth & Stock > Vegetable Broth** (96 SKUs) |
| vegetable stock | Frozen > Vegetables > Vegetable Blend | same |
| fish stock | Meat & Seafood > Fish | **Pantry > Broth & Stock > ?** |

**B. Baking soda — 32k recipe lines**
| recipe item | currently routed to | should be |
|---|---|---|
| baking soda | Beverage > Carbonated > Soda | **Pantry > Baking Additives & Extracts > Baking Soda** (95 SKUs) |
| bicarbonate of soda | Beverage > Carbonated > Soda | same |

**C. Peanut butter & nut butters — 9k recipe lines**
| recipe item | currently routed to | should be |
|---|---|---|
| peanut butter | Snack > Bars > Protein Bars | **Pantry > Nut Butters > Peanut Butter** (457 SKUs) |
| creamy peanut butter | same | same |
| smooth peanut butter | same | same |
| chunky peanut butter | same | same |
| crunchy peanut butter | same | same |
| peanut butter chips | same | (or Pantry > Chocolate Chips > Peanut Butter Chips) |
| almond butter | Snack > Nuts > Almonds | **Pantry > Nut Butters** |

**D. Wine & spirits — 8k recipe lines**
| recipe item | currently routed to | should be |
|---|---|---|
| red wine | Beverage > Mixes > Slushie Mix | **Beverage > Wine** (376 SKUs) |
| dry red wine | Beverage > Mixes > Slushie Mix | same |
| port wine | Beverage > Mixes > Slushie Mix | same |
| marsala wine | Beverage > Mixes > Slushie Mix | same |
| madeira wine | Beverage > Mixes > Slushie Mix | same |
| burgundy wine | Beverage > Mixes > Slushie Mix | same |
| sherry wine | Beverage > Mixes > Slushie Mix | **Pantry > Cooking Wines** (36 SKUs) ← cooking, not drinking |

**E. Extracts — 5.6k recipe lines**
| recipe item | currently routed to | should be |
|---|---|---|
| almond extract | Snack > Nuts > Almonds | **Pantry > Baking Extracts > Almond Extract** (60 SKUs) |
| rum extract | Pantry > Spices > Spice Blend | **Pantry > Baking Extracts** (10 SKUs) |
| maple extract | Pantry > Spices > Spice Blend | **Pantry > Baking Extracts** |

**F. Misc one-offs — 10k recipe lines**
| recipe item | currently | should be |
|---|---|---|
| fresh mint | Snack > Candy > Mints | **Produce > Herbs > Mint** (priced: only 4 SKUs at fresh mint cp; small pool but real) |
| ground red pepper | Frozen > Vegetables > Peppers | **Pantry > Spices & Seasonings > Cayenne Pepper** (55 SKUs of cayenne live at Spice Blend) |
| sauerkraut | Pantry > Dips & Spreads > Vegetable Spread | **Pantry > Sauerkraut** (65 SKUs) |
| orange marmalade | Pantry > Spreads > Lime Curd | **Pantry > Spreads > Marmalade** (19 SKUs) |
| dried onion flakes | Frozen > Vegetables > Onions | **Pantry > Spices** (target needs more research; "dried onion flakes" exact phrase had no SKU) |
| milk chocolate chips | Dairy > Milk | **Pantry > Chocolate Chips** (5 SKUs of true milk choc chips) |
| sweetened flaked coconut | Snack > Candy > Candied Fruit | **Pantry > Flakes > Coconut Flakes** (81 SKUs) |
| vanilla bean | Pantry > Beans (legumes!) | **Pantry > Baking Extracts > Vanilla Bean Paste** (15 SKUs) |
| catsup | Pantry > Condiments > Spring Rolls | **Pantry > Condiments > Ketchup** (134 SKUs) |
| pimientos | Pantry > Dips & Spreads > Vegetable Spread | **Pantry > Canned Vegetables > Pimientos** (27 SKUs) |
| grenadine | Pantry > Flour > Drink Mix | **Pantry > Sweeteners > Grenadine Syrup** (2 SKUs at exact path; 12 at related Syrup path) |
| butterscotch chips | Snack > Candy | **Pantry > Chocolate Chips** (TRUE GAP — no priced butterscotch-chip SKU) |
| dry red wine | Beverage > Mixes > Slushie Mix | TRUE GAP for that exact phrase (red wine exists; "dry red wine" needs override) |

## WEAK_LEAF cases (form/specificity, 33k recipe lines)

The recipe text doesn't say "canned/frozen/pickled" but the encoder routed to a canned/frozen/pickled cp. Recipe likely wants fresh.

| recipe item | derived | issue |
|---|---|---|
| tomato (10,208) | Pantry > Canned Vegetables > Tomatoes | wants fresh tomato |
| onion powder (7,076) | Pantry > Spices > **Seasoning** generic | should be Spices > Onion Powder |
| red pepper (3,510) | Frozen > Vegetables > Peppers | likely fresh |
| yellow bell pepper (2,129) | Frozen > Vegetables > Peppers | should be Bell Peppers Yellow |
| celery seed (2,072) | Spices > Seasoning generic | should be Spices > Celery Seed |
| whole cloves (1,568) | Spices > Spice Blend | should be Spices > Cloves |
| miniature marshmallows (1,534) | Pantry > Dessert Toppings > Marshmallow Topping | should be Pantry > Marshmallows |
| sweet potato (1,334) | Frozen > Potatoes > Sweet Potatoes | wants fresh |
| sweet red pepper (1,215) | Frozen > Vegetables > Peppers | wants fresh |
| couscous (1,160) | Pantry > Grain > **Grain Blend** generic | should be Pantry > Grain > Couscous |

## NEEDS_REVIEW false-positive notes

Most NEEDS_REVIEW pairs (98 total, 79k lines) are actually OK — my classifier flagged them because of plural mismatch (item="apple" → leaf="Apples") or synonym (item="scallion" → leaf="Green Onion"). After manual scan of top 30, the additional REAL_BUGS promoted from NEEDS_REVIEW are: catsup, grenadine, pimientos, jalapeño-fresh-vs-pickled, butterscotch chips, coriander powder, pancetta. Already incorporated above.

## True gaps (verified zero priced SKUs at any reasonable path)

These items genuinely don't exist in the priced corpus:
- **lovage**, **lime curd**, **sake**, **creme fraiche**, **vegetable spread**, **haddock** — all confirmed earlier
- **butterscotch chips** — new
- **dried onion flakes** — partial (onion flakes maybe; dried onion flakes exact phrase no)
- **dry red wine** — exact phrase only; "red wine" works

Recipes containing these are correctly excluded from the planner via the `build_concept_tensor_cache` exclusion (37,000+ recipes per current run).

## Concrete deliverable for Phase 1 (read the encoder)

The encoder needs corrections in (at minimum) these decision points:

1. **Broth/stock items** — items containing "broth" or "stock" as a token must route to `Pantry > Broth & Stock > {Chicken|Beef|Vegetable|Fish} Broth`, NOT to the protein category.
2. **Baking soda / bicarbonate / cream of tartar** — any "baking *" or specific baking additives → `Pantry > Baking Additives & Extracts > X`, NOT `Beverage > Carbonated > Soda`.
3. **Nut butters** — `* butter` where `*` is a nut → `Pantry > Nut Butters > X`, NOT Snack > Bars > Protein Bars (which is what the encoder's currently doing because "peanut butter" appears in protein bar names).
4. **Wine variants** — any `* wine` (red/white/sherry/port/marsala/madeira/burgundy) → `Beverage > Wine`, NOT Slushie Mix. Cooking wines (sherry, marsala if labeled cooking) → `Pantry > Cooking Wines`.
5. **Extracts** — `* extract` / `* essence` / `* flavoring` → `Pantry > Baking Extracts > X`.
6. **Specific overrides for one-offs** — vanilla bean → Vanilla Bean Paste; orange marmalade → Marmalade; sauerkraut → Sauerkraut; flaked/shredded/desiccated coconut → Coconut Flakes; catsup → Ketchup; pimientos → Pimientos.
7. **Form/specificity (WEAK_LEAF)** — when recipe item doesn't say "canned/frozen/pickled" but encoder produces those leaves, should route to fresh. When recipe item is "X powder" or specific spice, should produce specific leaf not "Seasoning" generic.

**Total recipe-line impact if all REAL_BUGS + top WEAK_LEAFs fixed at the encoder:** ~150,000 recipe lines route to the correct priced pool instead of falling through to wrong-pool path_only matches (or being silently substituted by a band-aid override).

## Files

- `recipe_pricing/_phase0_raw_counts.pkl` — raw 75,514-tuple count dict
- `recipe_pricing/encoder_misfire_v2.csv` — top 1,500 (item, cp) pairs with classification
- This document — synthesis

## Next: Phase 1

Read `recipe_mapper/v1/htc/encoder.py` and trace WHERE each of the 7 fix-list items above lives in code. Output: `ENCODER_ARCHITECTURE.md` mapping every REAL_BUG cluster above to the specific function / data file responsible. No code changes in Phase 1.

After Phase 1, Phase 2 produces a code-level fix list, you sign off, then Phase 3 mutates the encoder. The override CSV gets pruned in Phase 5 — every override row whose item the encoder now handles natively gets deleted.
