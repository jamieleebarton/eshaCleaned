# Recipe Calculator — Plan to Done

The calculator (`recipe_pricing/calculate_recipe_cost_v7.py`) is built and
runs end-to-end. This plan lists what stands between "runs" and "actually
produces correct shopping lists + costs + macros for any recipe in the
corpus."

## Acceptance criteria for "calculator works"

For 100 random recipes, the calculator must:
1. Pick a CORRECT Walmart/Kroger SKU for every line that's marked `calculate`
   or `shop_only` (no water-softener-salt-for-salt errors)
2. Compute attributable line cost = grams × cents/gram for every `calculate` line
3. Compute attributable line macros (kcal, protein, fat, carb, fiber, sodium)
4. Aggregate to recipe-level: shopping_list, cart_total, line_cost_total,
   macro_totals, decision_points, broken_flags
5. Skip `derivative` lines from shopping list (already shopping for upstream)
6. Skip `shop_only` lines from quantity calc (to_taste/garnish/optional)
7. Surface `unbuyable`/`nonsense` recipes in `broken_flags` for review

We're not there yet. ~70% of SKU picks are clean today; the remaining 30%
are bridge errors in `priced_products_v2.db`.

## Tier 1 — Blocking for ACCURATE COST (next 2-3 hours)

These are the changes that make the calculator's cost numbers trustworthy
on a random recipe. Without them, ~30% of lines pick wrong SKUs.

### 1.1 Wait for classifier to finish (~50 min)
Background process PID 28140. ETA ~50 min from 2026-05-07 morning.
After: `recipe_pricing/buyability_classifications.jsonl` complete on all
491,058 recipes.

### 1.2 Re-run post-process cleanup on full classifier output (~1 min)
`python3 recipe_pricing/post_process_cleanup.py`
Rebuilds `buyability_classifications_cleaned.jsonl` with brand-strip,
facet-capture, assorted-flag, dangling-token-sweep applied.

### 1.3 Re-run buy_form → canonical_path lookup (~30 sec)
`python3 recipe_pricing/build_buy_form_lookup.py`
Rebuilds `buy_form_to_canonical_path.csv`. The 7,033 currently-unresolved
canonical_buy_form values may shrink after seeing the full classifier output.

### 1.4 Clean priced_products source data — `clean_priced_products.py` (NEW SCRIPT)
The biggest blocker. Audit `priced_products_v2.db` for products mis-filed
at wrong canonical_path. Known patterns:
- Water softener salt at `Pantry > Spices > Salt` (filter: name contains
  "softener"/"pellets"/"ice melt")
- Butter pecan ice cream at `Dairy > Butter` (filter: name contains "pecan"
  + "ice cream"/"frozen")
- Hawaiian Punch at `Pantry > Lemon Juice` (filter: name contains "punch"/
  "berry flavor"/"drink")
- Sauerkraut at `Pantry > Spices > Black Pepper` (filter: name contains
  "sauerkraut" but consensus_pid is "Black Pepper")
- Cleaning vinegar at `Pantry > Vinegar` (filter: name contains "cleaning")
- Diced tomatoes at `Pantry > Spices > Oregano` (filter: name contains
  "tomatoes" but consensus_pid is "Oregano")

Approach: build a name-vs-pid sanity rule set. If name disagrees with pid,
reclassify or remove. Estimated 500-1500 product rows to fix.
Output: updated `priced_products_v2.db` (or sidecar exclusion list).

### 1.5 Improve canonical_buy_form → canonical_path coverage
For the 7k unresolved buy_forms, manual or LLM-assisted mapping.
Targets: `cayenne pepper sauce`, `dry onion soup mix`, `baking potatoes`,
`cooked lobster meat`, etc. — items with no api_cache or recipe_taxonomy
backing.

Approach: write `extend_buy_form_lookup.py` that takes the unresolved list
and tries fuzzy match against canonical_paths in `priced_products_v2.db`.

### 1.6 Re-run calculator on demo + spot-check
After 1.1-1.5, run `calculate_recipe_cost_v7.py` on the same 4 demo recipes
and verify SKU picks are clean.

## Tier 2 — Blocking for MACROS (~1 hour)

The calculator currently emits cost but not macros. We need:

### 2.1 Macro lookup table
`priced_products_v2.db` already has `consensus_fndds` (FNDDS food code) per
product. Bridge to FNDDS macro data:
- Source: `data/fndds/` directory (FNDDS nutrient files)
- Build: `recipe_pricing/build_macro_lookup.py` — for each FNDDS food code,
  emit kcal/100g, protein_g/100g, fat_g/100g, carb_g/100g, fiber_g/100g,
  sodium_mg/100g
- Output: `recipe_pricing/macros_by_fndds.csv`

### 2.2 Wire macros into calculator
In `calculate_recipe_cost_v7.py::calculate()`, after picking SKU:
```python
fndds = product["consensus_fndds"]
macros = macro_lookup.get(fndds)
if macros and grams > 0:
    line.kcal = grams * macros["kcal_per_100g"] / 100
    line.protein_g = grams * macros["protein_per_100g"] / 100
    # etc.
```

### 2.3 Aggregate macros at recipe level
Sum line.kcal across `calculate`-decision lines (skip shop_only/derivative).
Render in the recipe output.

## Tier 3 — Facet projection (~30 min)

User says "I want low_fat" → calculator filters Walmart products with
`low_fat` claim, prefers cheapest matching.

### 3.1 Build claims-by-product lookup
`api_cache_taxonomy_v2.csv` already has `claims` column per product. Index:
`upc → [claim_flags]`. Cross-reference to `priced_products_v2.db` by
`upc` join (priced_products has `upc` column).

Output: `recipe_pricing/product_claims.csv` (upc, claims).

### 3.2 Wire facets into calculator
In `find_cheapest()`, after retrieving candidates, filter:
- if user_facets: keep products whose `claims` include all user_facets
- if no match: fall back to no-facet pick + flag in decision_points

### 3.3 Validate
Run on 5 recipes with `--facets organic,low_fat` and verify:
- For `milk` line: planner picks an organic low-fat milk SKU
- For `butter` line: planner picks an organic low-fat butter SKU (or flags
  no-match if unavailable)

## Tier 4 — QA + reporting (~1 hour)

### 4.1 Coverage report on 100 random recipes
`python3 calculate_recipe_cost_v7.py --random 100 --json > /tmp/qa.json`
Then a quick analysis: % of recipes with all lines priced, % with at least
one no-SKU line, % with broken_flags, total cart cost distribution.

### 4.2 Spot-check 10 recipes manually
Pick 10 random recipes, check:
- Shopping list makes sense (no garbage SKUs)
- Cart total is reasonable (no $50,000 carts)
- Decision points correctly surface alternations/optionals
- Broken flags catch the actual broken recipes (cookware, etc.)

### 4.3 Output schema
For downstream consumers, define stable JSON output:
```json
{
  "recipe_id": "...",
  "title": "...",
  "shopping_list": [{"sku_name": "...", "upc": "...", "size_grams": ...,
                     "size_display": "...", "price_cents": ...}],
  "cart_total_cents": ...,
  "line_total_cents": ...,
  "macros": {"kcal": ..., "protein_g": ..., "fat_g": ..., "carb_g": ...,
             "fiber_g": ..., "sodium_mg": ...},
  "lines": [{"line_index": 0, "raw_display": "...", "decision": "...",
             "canonical_buy_form": "...", "extracted_claims": [],
             "sku_picked": "...", "line_cost_cents": ..., "macros": {...}}],
  "decision_points": ["alternation [5]: ...", "optional [9]: ..."],
  "broken_flags": [],
  "user_facets": ["organic", "low_fat"]
}
```

Add `--json` flag to `calculate_recipe_cost_v7.py` that emits this schema.

## Tier 5 — Deferred (post-launch)

Not blocking for the calculator to be usable. Address as we hit them.

- **Recipe-context LLM re-pass** — for items the regex post-process can't
  fix (`100% fruit jelly` → fruit cue from "Fig Newtons" title). ~10-100
  items. Can run another targeted DeepSeek pass when needed.
- **Non-recipe filter** — exclude ~200 craft projects (kissing balls,
  massage oils, water-mark removal). Recipe-level filter, separate pass.
- **HTC code derivation for canonical_buy_form** — use the existing encoder
  to give every canonical_buy_form an htc_code for cleaner joins.
- **Brand map expansion** — as we find more brand leaks (Reynolds, Anchor,
  Eden, etc.), add to STRIP_BRANDS in post_process_cleanup.
- **More identity-conflict rules** — as we find more bridge errors that
  noise filter doesn't catch.

## Tier 6 — Polish

- **Streaming calculator** — currently loads all recipes into memory.
  For 491k recipes that's fine but if we go bigger we'd need streaming.
- **Caching** — if we run the calculator repeatedly with same facets,
  cache the SKU picks per (canonical_path, facets).
- **CLI ergonomics** — `--save-csv`, `--save-json`, `--by-recipe`, etc.

## Sequencing

The shortest path from where we are today to "calculator produces accurate
output for any recipe":

```
1.1  Wait for classifier  (~50 min, in flight)
1.2  Re-run cleanup        (~1 min)
1.3  Re-run buy_form       (~30 sec)
1.4  Clean priced_products (~30-60 min) — biggest impact
1.5  Extend buy_form       (~15 min)
2.1  Build macro lookup    (~30 min)
2.2  Wire macros           (~15 min)
2.3  Aggregate macros      (~10 min)
3.1  Claims lookup         (~10 min)
3.2  Wire facets           (~15 min)
3.3  Validate              (~10 min)
4.1  Coverage report       (~10 min)
4.2  Manual spot-check     (~30 min)
4.3  JSON output schema    (~15 min)
```

**Total: ~3-4 hours of focused work after the classifier finishes.**
**No more DeepSeek $.** All deterministic post-processing.

## Files this plan creates / modifies

**New scripts:**
- `recipe_pricing/clean_priced_products.py` (Tier 1.4)
- `recipe_pricing/extend_buy_form_lookup.py` (Tier 1.5)
- `recipe_pricing/build_macro_lookup.py` (Tier 2.1)
- `recipe_pricing/build_product_claims_lookup.py` (Tier 3.1)
- `recipe_pricing/qa_calculator.py` (Tier 4.1)

**Modified:**
- `recipe_pricing/calculate_recipe_cost_v7.py` — wire in macros + facets
  + JSON output (Tiers 2.2, 3.2, 4.3)

**Updated docs:**
- `docs/CALCULATOR_PLAN.md` (this file) — checked off as we go
- `docs/RECIPE_CLEANING_PIPELINE.md` — current state of pipeline
