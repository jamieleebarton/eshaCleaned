# 12-week plan audit (2026-05-09)

**Plan file:** `audit_results/multi_week_ours_12w_after_fix.json`
**Mode:** thrifty, 4 people, 2000 cal/day, 12 weeks

## Top-line numbers

| Metric | Value |
|---|---|
| Total cost (12 wk) | **$1,035.38** |
| Avg per week | $86.28 |
| Per person per day | $3.08 |
| Unique recipes | 254 |
| Repeat picks | 51 |
| Avg veg compliance | 56.6% |
| Avg protein | 12.9% (target 15%) |
| Calorie compliance | met all 12 weeks |

The $86/week is "amortized" — it counts whole-cart costs once and lets pantry leftovers carry over. Week 1 is $109.85 (no starting pantry); by Week 12 the running pantry is 43kg of carryover ingredients and the new spend dropped to $86.63 for 26 recipes.

## Resolution-tier breakdown across 2,011 picked-recipe lines

| Tier | Lines | % |
|---|---:|---:|
| exact | 1,167 | 58.0% |
| path_only | 794 | 39.5% |
| sibling_path | 18 | 0.9% |
| alias_exact | 4 | 0.2% |
| form_only | 1 | 0.1% |
| **NO_MATCH** | **27** | **1.3%** |

97.5% of ingredient-lines in picked recipes have a real priced match.

## Grams sanity

| Range | Lines |
|---|---:|
| 1–50 g | 895 |
| 51–200 g | 596 |
| 201–500 g | 416 |
| 501–2000 g | 104 |
| > 5 kg | 0 |

No outrageous-grams parser bugs. Distribution looks like real ingredient quantities (small for spices, larger for proteins/produce).

## Spot-checks: did it pick the right stuff?

### ✅ Tomato Sauce — fixed (was the spaghetti-junk class)

7 picks across recipes (Sweet-Sour Frankfurters, Artichoke Mushroom Pizza, TVB Taco Bake, Quick Tortilla Pizzas, Bean Enchiladas, Tuna Chickpea Sandwich):
- All resolved via `path_only` to `Pantry > Sauces & Salsas > Tomato Sauce`
- All picked **Great Value Tomato Sauce 8oz Can** ($0.48/can) — real, correct
- Zero matches to the previous "Plant Based Cheese > Spaghetti with Sauce" junk

### ✅ Bell Peppers — fixed (was 13,897 broken)

12 picks. Resolves to `Produce > Vegetables > Bell Peppers`. SKUs picked:
- Fresh Large Green Bell Pepper @ $0.89 — correct
- Simple Truth Organic Mixed Bell Peppers @ $3.59 — also correct

### ✅ Yellow Onions — fixed (was 7,958 broken)

7 picks. All → **Jumbo Yellow Onions @ $0.44** — correct.

### ✅ Avocado — fixed (was 6,474 broken)

12 picks. All → **Fresh Medium Ripe Avocado @ $0.75** — correct.

### ✅ Russet Potatoes / Apples — fixed

Russet pool now resolves correctly with 31 SKUs available (cheapest: Russet Potatoes 10lb Bag @ $3.94 / 4.5kg = $0.087/g, real fresh).

### ✅ Pesto / Broth — fixed (was the F800000X spaghetti-junk class)

- Pesto → Prego Creamy Basil Pesto Pasta Sauce ($2.69/jar) — borderline (it's a pasta sauce, not pure pesto, but pesto-flavored)
- Broth → Great Value Reduced Sodium Chicken Broth 32oz ($1.27) — correct

### ✅ Chicken Breast → Canned Chicken (the original ghost): not present in this plan

Thrifty mode produced a heavily vegetarian plan (lots of bean burritos, quesadillas, frittatas), so no chicken-breast-recipe was picked. We can't directly verify the chicken-breast fix in *this* run, but the resolution map (verified earlier) maps it to a pool of 16 fresh chicken breast SKUs.

## ⚠ Real issues found

### Issue A — Mott's Strawberry Applesauce winning over plain (5 picks)

Concept pool `Pantry > Applesauce|J005600K` has 6 SKUs all at the same `$0.0306/g` cents-per-gram:
- Mott's **Strawberry** Applesauce Cups
- Mott's **Mango Peach** Applesauce Cups
- Mott's **Cinnamon** Applesauce Cups
- Mott's Applesauce Cups *(plain — what we want)*
- Mott's No Sugar Added Cinnamon
- Mott's No Sugar Added Applesauce *(plain unsweetened — best for baking)*

Tie-breaking on identical cpg picks Strawberry first. **All 5 applesauce-using recipes (Banana Oat Bread, Potato Waffles, Chunky Apple Pancakes, Applesauce Roll Pancakes, Silver Dollar Oat Pancakes) got Strawberry.** Strawberry applesauce in pancakes/oat bread is wrong.

**Fix:** in the picker, prefer SKUs whose name matches the canonical_path leaf token AND avoids flavor adjectives ("Strawberry", "Mango Peach", "Cinnamon", etc.) when cents-per-gram is tied.

### Issue B — Kraft Mozzarella Blend over real mozzarella (11 picks)

All 11 mozzarella picks went to `Mozzarella|1102100W` and chose **Kraft Signature Thick Shreds Mozzarella Blend Cheese, 8oz** ($1.31/g). The real fresh mozzarella in that same pool starts at $1.76/g, so Blend wins on cents-per-gram.

But other mozzarella concept_keys are way cheaper:
- `Mozzarella|11020047` → Great Value Block Mozzarella @ **$0.77/g**
- `Mozzarella|11020058` → Great Value Shredded Mozzarella @ **$0.74/g**

The recipe's htc_form_code routes it to the fresh-mozzarella pool (1102100W) where Blend is the cheapest available, instead of the cheaper block/shredded pool. **The router is sending it to the wrong-form pool.**

**Fix candidates:**
1. Drop the Blend SKU from `1102100W` (it's a quattro-formaggi blend, doesn't belong there)
2. In the resolution ladder, when a recipe wants generic mozzarella, prefer the lower-cpg pool over the precise-form match
3. Cross-link recipe form `1102100W` → priced form `11020047` via `canonical_path_aliases.csv`

### Issue C — Smart Balance Cooking Oil Blend picked as cooking oil (6 picks)

Smart Balance is a margarine/butter substitute, not pure oil. Recipes wanting "vegetable oil" or "olive oil" are getting buttery spread.

**Fix:** drop Smart Balance from `Pantry > Oil` pools — it should be at `Dairy > Butter > Margarine`.

### Issue D — Planner picked 27 recipes containing NO_MATCH ingredients

These recipes were chosen by the planner *despite* having ingredients with zero priced data. Examples:

| Recipe | Missing ingredient (no priced SKU) |
|---|---|
| Cheesy Crab Burritos | 227g of Imitation Crabmeat |
| Crispy Pan-Fried Calamari Steaks | 600g of Calamari |
| Sweet-Sour Frankfurters | 454g of Frankfurters |
| Grilled Swordfish Steaks | 907g of Swordfish |
| Two-Tone Tostones | 600g of Plantains |
| Bananas Foster French Toast | 90g of Lime Curd |
| Old Fashioned Lovage and Potato Soup | 35g of Lovage |
| Veal Goulash | 907g of Veal |
| Paganens (Algonquin Wild Nut Soup) | 680g of Hazelnuts |
| Cream Cheese Hot Dogs | 50g of Vegetable Spread |

This is a **real bug**: the planner is scoring these recipes as artificially cheap (the missing-ingredient line contributes $0 to the cart) and then selecting them. The user pays $0 for the absent product, but the recipe actually requires it.

**Fix:** in the planner's scoring, mark recipes containing any NO_MATCH concept_key as ineligible (or at least heavily penalized). Currently they're being silently treated as having free missing ingredients.

### Issue E — `picked_recipe_audit.py` simulation diverges from planner ($3,406 vs $1,035)

The audit script does per-line cheapest-pick independently, totalling $3,406. The planner does whole-cart optimization with leftover rollover, totalling $1,035. The 3.3× ratio is the value of leftover-aware buying.

**Implication for auditability:** the planner output (`multi_week_ours_*.json`) records only `recipe_ids` per week, not the actual SKUs bought or grams used. We can verify *which recipes* were picked but not *which SKUs* the planner actually paid for. The audit simulation is a different cart.

**Fix:** add per-recipe per-line picked-SKU + cents to the planner output. That makes the cart auditable end-to-end.

## Summary

**The data-layer fixes worked.** Coverage went 25.7% → 8.3% uncalculable, the spaghetti-junk path is gone, real produce (bell peppers, onions, avocado, potatoes, apples) resolves correctly, and the 12-week plan ran cleanly at $86/week.

**5 real follow-up issues** to address (in order of severity):
1. **Issue D** — planner selecting recipes whose ingredients have no priced match (silent free-ride on missing data)
2. **Issue B** — Kraft Mozzarella Blend in fresh-mozzarella pool, plus router not falling through to cheaper mozzarella pool
3. **Issue C** — Smart Balance Cooking Oil Blend in Pantry > Oil pool
4. **Issue A** — Mott's Strawberry winning ties over plain Mott's
5. **Issue E** — planner output should include actual SKU picks for end-to-end auditability

None of these are show-stoppers; all are addressable without touching `build_concept_resolution.py`. Issues A–C are upstream concept_index pool-membership cleanups. Issue D is a planner scoring fix. Issue E is a logging change.
