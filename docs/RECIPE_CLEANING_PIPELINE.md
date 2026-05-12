# Recipe Cleaning Pipeline

The end-to-end flow for turning raw recipe text into a planner-ready
shopping list + cost + macros. Captures what's done, what's running, and
what's still pending so we don't lose the thread.

## Goal

Recipes come in with author noise: alternations (`X or Y`), bare ambiguous
nouns (`bread`, `cheese`, `noodles`), recipe-derived items (`egg wash`,
`simple syrup`, `lobster shells`), garnish trailers (`for serving`,
`to taste`), unbuyable items (`live lobster carcass`, `wood ash`), and
quantity ambiguity (`2 to 4 tbsp`, `a handful`, `(8-12 oz can)`).

Hestia stores recipes as canonical foods (`mayonnaise`, not `Hellmann's
fat-free organic mayonnaise`). At plan time the user's facets (organic,
low_fat, vegan, etc.) project onto canonical → query Walmart/Kroger
products with matching `claims` → pick cheapest matching SKU → compute
cost + macros from grams_resolved.

## Current state

### ✅ Done

1. **HTC code system** — 8-char positional code per identity, plus
   `htc_full_code` 18-char extended for SKU-level. All 8 corpus files
   agree on htc_code for the same identity.
2. **Generic-PIF spice fix** — Walmart cumin/paprika/etc. moved off the
   generic `Spice Blend` leaf into specific spice leaves; htc_code
   re-derived. ~440 products + recipe ingredient rows fixed.
3. **Coverage report** — `recipe_pricing/build_coverage_report.py`
   reports per-item: covered_full / covered_price / covered_macros /
   missing_both. As of 2026-05-06: 70.1% items / 78.7% recipe-refs
   fully covered (price + macros).
4. **Buyability classifier** — RUNNING right now on the full 491,058
   recipes from `recipe_qa.db` via DeepSeek (deepseek-chat, ~$126,
   ~10h, started 2026-05-06 ~22:30, ETA midday 2026-05-07).
   - Schema per (recipe_id, line_index): buyability, canonical_buy_form,
     identity_resolved, base_ingredients, usage, rationale
   - 80% complete at last check; 0 errors; cache hit rate 98.3%
5. **Aggregator** — `recipe_pricing/aggregate_buyability.py` produces
   `buyability_per_line.csv`, `buyability_per_item.csv`,
   `buyability_recipe_health.csv` from the streaming output. At 80%:
   80.0% recipes ready / 15.9% ready_with_substitutions / 4.1%
   specialty_required / 0.05% needs_review.

### ⏳ In flight

- The classifier still has ~2h to go. Resume on failure: re-run with
  `--resume` flag — already-classified recipe_ids are skipped.

### ❌ Pending (post-classifier)

1. **`derive_buyform_htc.py`** — for each unique canonical_buy_form,
   derive (htc_code, canonical_path) using the same encoder pipeline
   (`recipe_pricing/cleanup_llm_output.py:derive_htc`). Output:
   `buy_form_to_htc.csv`. Required so the calculator can join on
   htc_code (the canonical_buy_form text alone won't join to products).

2. **Quantity ambiguity normalization** —
   `recipe_pricing/normalize_quantity_ambiguity.py` (TODO).
   ~117k recipe-lines have ambiguous quantity:
     - 75,575 numeric ranges (`2 to 4 tbsp`, `4-5 pods`)
     - 39,995 vague qty (`a pinch`, `a handful`)
     - 1,050 size ranges (`(10.5-14 oz can)`)
   Cheap regex+lookup fix, no extra DeepSeek $. Target lower-bound or
   midpoint for ranges; lookup table (pinch=0.5g, handful=30g, etc.)
   for vague. Updates grams_resolved + grams_source in recipes_unified.
   See `memory/project_quantity_ambiguity_pending.md`.

3. **`build_cleaned_recipes.py`** — joins
     - recipes_unified.csv (qty/grams/raw display + facets)
     - buyability_classifications.jsonl (canonical_buy_form/usage/etc.)
     - buy_form_to_htc.csv (htc + canonical_path)
     - ingredient_full_audit.csv (walmart_hits/nutrition_hits)
   Output: `recipes_cleaned.csv` — one row per recipe-line, fully
   resolved, with `calc_decision` column (calculate / shop_only / skip /
   review).

4. **`calculate_recipe_cost_v7.py`** — the planner. Reads
   recipes_cleaned + user facets, queries `priced_products_v2.db` for
   matching products at the canonical_path, picks cheapest cpg matching
   user's claims, computes per-recipe (shopping_list, total_cost,
   total_macros, decision_points). Already validated end-to-end on the
   "Buffalo Potatoes" + cayenne pepper sauce example: 30g × 0.69¢/g =
   $0.21 line cost; shopping list adds Frank's RedHot 64oz Jug $12.97.

5. **Item-level cleanups skipped by classifier** — to be handled by
   small post-process scripts:
     - B. Implicit claims (`1% milk` → claim=low_fat) — facet projection
       at runtime handles this; user picks facet, planner filters.
     - H. Regional vocab (courgette→zucchini, aubergine→eggplant,
       rocket→arugula) — synonym map, ~20 entries, regex pass.
     - I. Compound `salt and pepper to taste` — sometimes one ingredient
       in classifier output where it should be two. Regex split on
       known compound pairs.
     - K. Missing Bucket 3 modifiers — corpus audit to find leaks (e.g.
       `confectioner's sugar`, `superfine sugar` that didn't get caught).

### Planner architecture (the goal)

```
recipe_id, line_index
  ↓ recipes_unified
qty, unit, grams_resolved, prep_facets, raw display+item

  ↓ buyability classifier
canonical_buy_form, buyability, usage, identity_resolved, base_ingredients

  ↓ buy_form_to_htc
htc_code, canonical_path

  ↓ ingredient_full_audit
walmart_hits, nutrition_hits  →  has_macros, has_price flags

  ↓ build_cleaned_recipes
calc_decision: calculate | shop_only | skip | review

  ↓ calculate_recipe_cost_v7 (with user facets)
priced_products_v2.db query at canonical_path with claims filter
→ pick cheapest cpg
→ compute line cost = grams × cpg
→ compute line macros = grams × (kcal_per_100g / 100)
→ aggregate to recipe totals
→ surface: shopping list, decision points, broken-recipe warnings
```

## Honesty checklist

What we've actually accomplished and what we haven't:

- [x] Recipe identity ambiguity — done by classifier (97% buyable, 1.6%
      alternation, 0.8% derivative, etc.)
- [x] Bare ambiguous nouns (`bread`, `cheese`, `noodles`, `nuts`, etc.)
      — resolved to specific SKUs from recipe context (with v2 prompt's
      "must commit to a SKU" framing)
- [x] Facet-bare nouns (`milk`, `butter`, `sugar`, `eggs`, `flour`,
      `oil`) — kept bare so user facets project at runtime
- [x] Garnish/to_taste/optional flagging — usage axis
- [x] Derivative tracing (egg wash, simple syrup, lobster cooking
      liquid) — base_ingredients trail
- [x] Garbage detection (cookware in ingredients, non-recipes, 4-way
      meat alternation) — unbuyable/nonsense flags
- [ ] **Quantity ambiguity (`2 to 4 tbsp`, `a handful`)** — NOT YET.
      Pending regex+lookup pass. ~117k lines (~2.5%).
- [ ] HTC code for canonical_buy_form — derive_buyform_htc.py pending.
- [ ] Cleaned recipe rows — build_cleaned_recipes.py pending.
- [ ] Planner v7 — pending.
- [ ] Regional vocab synonyms — pending.

## Files

- Inputs:
  - `data/recipe_qa.db` (recipes with steps + ingredients_json)
  - `recipe_pricing/buyability_input_full.jsonl` (491,058 recipes)
- Classifier:
  - `recipe_pricing/classify_buyability_via_deepseek.py` (the runner)
  - `recipe_pricing/buyability_classifications.jsonl` (streaming output)
  - `recipe_pricing/buyability_classifier.log` (progress log)
- Aggregator:
  - `recipe_pricing/aggregate_buyability.py`
  - `recipe_pricing/buyability_per_line.csv`
  - `recipe_pricing/buyability_per_item.csv`
  - `recipe_pricing/buyability_recipe_health.csv`
- Coverage:
  - `recipe_pricing/build_coverage_report.py`
  - `recipe_pricing/coverage_report.csv`
  - `recipe_pricing/coverage_summary.txt`
- TODO scripts (not yet written):
  - `recipe_pricing/derive_buyform_htc.py`
  - `recipe_pricing/normalize_quantity_ambiguity.py`
  - `recipe_pricing/build_cleaned_recipes.py`
  - `recipe_mapper/v1/calculate_recipe_cost_v7.py`
