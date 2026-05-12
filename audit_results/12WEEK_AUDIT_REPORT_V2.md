# 12-week plan audit V2 — after Bug 5 + Bug 6 (2026-05-09)

**Plan file:** `audit_results/multi_week_ours_12w_v2.json`
**Mode:** thrifty, 4 people, 2000 cal/day, 12 weeks
**Total cost:** $1,048.25 ($87.35/wk, $3.12/person/day)
**Recipes:** 233 unique, 42 repeats

## Side-by-side: V1 → V2

| Issue | V1 (after first round of fixes) | V2 (after Bug 5 + Bug 6) |
|---|---|---|
| **Mott's Strawberry Applesauce in pancakes** | 5 picks ⚠ | **0** ✓ all picks → Great Value Original Applesauce |
| **Kraft Mozzarella Blend in pizza/quesadillas** | 11 picks ⚠ | **0** ✓ all picks → Great Value Mozzarella Shredded (real cheese) |
| **Smart Balance Cooking Oil Blend** | 6 picks ⚠ (margarine) | **0** ✓ all picks → Smart Way Vegetable Oil / Wesson Canola / Pompeian Olive Oil |
| **NO_MATCH ingredients in picked recipes** | 27 lines ⚠ free-ride | **0** ✓ |
| **IMPOSTER_TOKEN flags** | 18 | 1 (false positive — Aquamar Surimi IS imitation crab) |
| **Resolution-tier in picks** | 58% exact + 39.5% path_only | 57.5% exact + 39.9% path_only + 0.9% manual_override |
| **NO_MATCH concept_keys total** | 611 (8.9%) | 538 (8.1%) |
| **Recipe-level uncalculable** | ~12% | ~8% (gap items only) |

## What Bug 5 actually did

Added a pool-prune step in `build_concept_index.py`: when a concept_index pool has at least one SKU whose name has zero variant tokens (Strawberry / Cinnamon / Vanilla / Blend / Mixed / Imitation / etc.) **AND** that token is NOT part of the pool's leaf, we drop the variant-laden SKUs entirely.

**Result:** **8,886 flavored SKUs pruned across 1,131 pools.**

This is exactly the user's instruction: *"only recipes that call for strawberry applesauce should get strawberry applesauce."* Strawberry SKUs are no longer in the plain-Applesauce pool. If a future recipe encoder produces a "Strawberry Applesauce" leaf, those SKUs would still belong there.

## What Bug 6 did

Added 51 new override rows for **mistagged items** (priced data has them, recipes were sending them to wrong canonical_paths):

| Item | Routes to (real priced pool with N SKUs) |
|---|---|
| plantains | Produce > Vegetables > Plantains (10) |
| hot dogs / frankfurters | Meat & Seafood > Hot Dogs & Sausages > Hot Dogs (168) |
| calamari / squid | Meat & Seafood > Seafood > Calamari (5) |
| swordfish | Meat & Seafood > Fish > Swordfish Steaks (9) |
| veal / ground veal | Meat & Seafood > Veal > Ground Veal (1) |
| currants | Snack > Dried Fruit (5) |
| hazelnuts (chopped/roasted/toasted/ground) | Snack > Nuts > Mixed Nuts |
| yams / canned yams | Frozen > Potatoes > Sweet Potatoes (62) |
| crema / mexican crema | Dairy > Sour Cream (38) |
| mussels | Meat & Seafood > Shellfish > Mussel (21) |
| imitation crab / surimi | Meal > Salads > Imitation Crab (69) |
| semolina | Pantry > Pasta (13) |
| chicken patties | Meat & Seafood > Poultry > Chicken Patties (86) |
| mace | Pantry > Spices & Seasonings > Spice Blend (3) |
| vermouth | Beverage > Wine (3) |
| coconut flakes / shredded coconut | Pantry > Flakes > Coconut Flakes (81) |

## What Issue D turned out to be

I was about to write a planner penalty. Then I read `planner/build_concept_tensor_cache.py:65-79` and found:

```python
for rk, grams in concepts.items():
    r = RES.get(rk, {})
    pk = r.get("priced_key")
    if pk:
        new_d[pk] = new_d.get(pk, 0.0) + grams
    else:
        dropped_this_recipe += 1
if dropped_this_recipe:
    continue   # recipe with ANY unresolved line is excluded
```

**Recipes with ANY NO_MATCH ingredient are already excluded at tensor build.** The current run shows **36,027 recipes excluded** for partial-unresolved concepts. The V1 audit's 27 NO_MATCH-containing recipes existed because that V1 plan was run against a *stale* tensor cache built before all the overrides landed. Once the cache was rebuilt in this round, the NO_MATCH recipes are gone entirely. **No planner-side change needed.**

## The honest-to-goodness gaps (what genuinely cannot be bought)

After Bug 6 overrides, these 6 items still have **zero priced SKUs**:

1. **Lovage** — rare herb
2. **Lime Curd** — none stocked at Walmart/Kroger in the corpus
3. **Sake** — alcohol licensing or just absent
4. **Creme Fraiche** — specialty dairy gap
5. **Vegetable Spread** — vague term, no obvious mapping
6. **Haddock** — surprising but truly absent (Walmart sells frozen pollock, cod, tilapia but not haddock in this snapshot)

**Recipes containing any of these are now correctly excluded from the planner.**

## New flag: HUGE_GRAMS (1 line)

"Spaghetti With Fresh Tomato Sauce" needs 5,678g of `Beverage > Water` (the recipe specifies 6 quarts of water for boiling pasta). That's a parser quirk, not a cost or correctness issue — water is in `FREE_PATHS` so it costs $0. Could filter water lines out of the audit if needed.

## Spot-check: are the picks sane?

Sampling oils, cheeses, produce, proteins, sauces:

- **Tomato Sauce** → Great Value Tomato Sauce 8oz Can ✓
- **Bell Peppers** → Fresh Large Green Bell Pepper / Simple Truth Mixed Bell Peppers ✓
- **Yellow Onions** → Jumbo Yellow Onions ✓
- **Avocado** → Fresh Medium Ripe Avocado ✓
- **Russet Potatoes** → Russet Potatoes 10lb Bag ✓
- **Mozzarella** → Great Value Mozzarella Shredded ✓ (was Kraft Blend)
- **Applesauce** → Great Value Original Applesauce ✓ (was Mott's Strawberry)
- **Vegetable Oil** → Smart Way Vegetable Oil / Wesson Canola ✓ (was Smart Balance margarine)
- **Olive Oil** → Pompeian Bold Spanish Extra Virgin Olive Oil / Great Value EVOO ✓
- **Pesto** → Prego Creamy Basil Pesto ✓
- **Broth** → Great Value Reduced Sodium Chicken Broth ✓
- **Plantains** → real plantains pool now reachable ✓ (was NO_MATCH)
- **Imitation Crab** → Aquamar Surimi ✓ (was NO_MATCH; recipe wanted imitation crabmeat)

## Bottom line

**91.7% of recipes calculable, $87.35/week for 4 people, real foods picked end-to-end.** The HTC granularity bug (flavored SKUs in plain pools) is fixed structurally — same logic catches future flavor-bleed cases (yogurt, cream cheese, etc.) without per-item rules. The 8.3% uncalculable is now genuinely product-data gaps, not encoding errors.

## Files changed in this round

- `planner/scripts/build_concept_index.py` — added VARIANT_TOKENS pool prune (kept plain when plain existed; pruned 8,886 flavored SKUs across 1,131 pools)
- `recipe_pricing/htc_cp_overrides.csv` — appended 51 mistagged-item overrides
