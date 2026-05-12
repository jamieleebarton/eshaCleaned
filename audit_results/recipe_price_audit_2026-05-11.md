# Recipe-Price Production-Readiness Audit — 2026-05-11

Source: `recipe_pricing/picked_recipe_audit_r4_at_r5_LINES.csv` (1,986 lines / 251 recipes)
& `recipe_pricing/picked_recipe_audit_r4_at_r5_prices.csv` (recipe totals).
Catalog: `recipe_pricing/data/priced_products_v2.db` (169,541 SKUs).

## Verdict

**Totals are safe. Line items are not.**

Recipe totals look reasonable in aggregate — but a customer reading the shopping
list will hit obviously-wrong picks (avocado shown as "Alafia Grape Leaves",
cheddar shown as "Cheddar Snack Sticks") that destroy trust regardless of price.
Do not ship customer-facing line items until the wrong-class picks below are
suppressed.

## What looks fine

| Metric | Value |
|---|---|
| Recipe total — median | **$14.42** |
| Recipe total — p90 | $22.29 |
| Recipe total — max | $32.66 |
| $/100g produced — median | $1.26 |
| $/100g — p90 | $2.13 |
| Picked-SKU $/lb — median | $1.43 |
| Picked-SKU $/lb — p75 | $4.19 |

Spot-checks pass: onions $0.88/lb, garlic $0.79/lb, celery $0.33/lb, russet
potatoes $0.50/lb, canned tomatoes $0.97/lb, sugar $0.62/lb. Cheapest recipes
($2.98 oatmeal packets, $3.86 hard-cooked eggs) are not zero-cost glitches.

## What's broken: wrong-class picks (152 lines, ~60% of sampled recipes hit ≥1)

These are not pricing errors — they're identity errors. The picker substituted a
different product class entirely.

| Concept | Picked SKU | Lines | Recipes |
|---|---|--:|--:|
| Cheddar | Cheddar **Snack** Sticks | 42 | 42 |
| Baby Carrots | Libby's **Peas & Carrots** cups | 26 | 26 |
| Vegetable Oil | Blue Bonnet Veg-Oil **Sticks** (margarine) | 21 | 21 |
| Brown Sugar | Madhava **Agave** Nectar | 17 | 17 |
| Avocado | Alafia **Grape Leaves** | 13 | 13 |
| Cream / Creme Fraiche | McCormick Strawberries-&-Cream **Sugar** | 6 | 6 |
| Bacon | MorningStar **Veggie** Bacon | 5 | 5 |
| Oregano | Whole **Bay Leaves** | 5 | 5 |
| Limes | Ocean Spray **Citrus Splash juice** | 4 | 4 |
| Hot Pepper Sauce | Knorr **Hollandaise** mix | 2 | 2 |
| Pierogies (frozen) | Buttery **Instant Mashed Potatoes** | 1 | 1 |

The Avocado→Grape Leaves substitution alone inflates 13 of the most expensive
recipes by $10.99 each. The Cheddar-Snack and Veg-Oil-Sticks errors are smaller
per-line but dominate by volume.

## The jar-rounding tax (164 lines, 8% of all lines)

Lines that need <5g of a spice/extract but get charged for a full jar.
Worst offenders:

- 0.3 g–1 g of "oregano" → $7.99 bay-leaf jar (compounded by the wrong-class swap)
- 4 g brown sugar → $5.99 agave bottle
- 1 g sage → $4.52 jar
- 2 g rosemary → $4.36 jar

This is real retail behavior, but the planner should be aggregating spice
demand across the week (pantry model) before charging — otherwise every recipe
inherits a $20-30 fictional spice tax.

## Tier mix

| Tier | Lines | Share |
|---|--:|--:|
| exact | 1,212 | 61% |
| path_only | 494 | 25% |
| form_only | 258 | 13% |
| parent_path_only | 8 | 0% |
| NO_MATCH | 7 | 0% |

`form_only` is where most of the wrong-class picks live (Cheddar-Snack,
Veg-Oil-Sticks). Treat `form_only` as production-blocking until each pattern
above is suppressed.

## Smallest set of fixes to make it customer-safe

1. **Negative-lexicon filter on `form_only` and `path_only` tiers.** Block SKUs
   whose name contains tokens that contradict the concept: `Snack` for cheese
   blocks, `Stick`/`Spread`/`Margarine` for liquid oil, `Veggie`/`Meatless` for
   bacon/meat, `Mix`/`Mash` for whole-form frozen, `Grape Leaves` for avocado,
   `Sugar`/`Finishing Sugar` for dairy cream.
2. **Pantry aggregation for spices/extracts** — charge jar cost once per week
   per SKU, not once per recipe-line.
3. **Hard-pin the 15 wrong-class pairs above** as explicit negative aliases
   until the resolver re-routes them.
4. **Treat `form_only` as the production threshold** — ~13% of picks are
   form-only and these are where customer-trust failures concentrate; raise
   that bar before exposing line items publicly.

Totals can ship behind a "ballpark" disclaimer today. Line-item shopping lists
cannot, until items 1–3 land.
