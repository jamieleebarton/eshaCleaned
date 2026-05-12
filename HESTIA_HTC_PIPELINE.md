# Hestia HTC Pipeline — what we are doing

## Goal

Build a meal planner that:
1. Picks recipes from a 489k-recipe corpus that fit configurable plate templates (breakfast/lunch/dinner) and household constraints (calories, protein %, budget).
2. For each recipe ingredient, resolves to a **real grocery SKU** (Walmart, Kroger, Meijer) so the user gets a shopping list with real prices.
3. Computes accurate per-recipe **macros** (kcal/protein/fat/carb/fiber/sodium) from the picked SKUs.

The whole system pivots on a single identity key: the **HTC code** (Hestia Taxonomy Code) — an 8-character positional code that encodes group/family/food/form/processing/ptype.

---

## The pipeline (left to right)

```
┌─────────────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│ recipes_unified.csv     │    │ priced_products_v2.db│    │ FNDDS nutrient lkp │
│ 4.7M ingredient lines   │    │ 169k SKUs             │    │ 11,923 codes        │
│ (recipe_id, ingredient, │    │ (UPC, name, price,    │    │ (kcal/protein/etc   │
│  grams, htc_code)       │    │  consensus_fndds,     │    │  per 100g)          │
│                         │    │  consensus_canonical, │    │                     │
│                         │    │  htc_form_code)       │    │                     │
└────────────┬────────────┘    └──────────┬────────────┘    └─────────┬──────────┘
             │                            │                           │
             ▼                            ▼                           ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │  htc_reference.json — 1,984 HTC codes, each carrying:            │
       │    • cheapest matching SKU at form-aware HTC + canonical_path    │
       │    • macros per 100g (sourced from priced_products consensus_fndds│
       │      → FNDDS lookup, crystallized HTC-keyed)                     │
       │    • food_group, protein_source, perishability, allergens        │
       └──────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │  tensor cache (planner/data/tensor_cache/)                       │
       │    • recipe_db_tensors.pt — recipe → ingredient grams sparse     │
       │    • ingredient_index.pt   — HTC code → integer idx              │
       │    • template_tensors.pt   — recipe → plate template assignment  │
       └──────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │  SparseCascadePlanner (Hestia, ported to esha_audit_bundle)      │
       │    • takes ScoringConfig, household, day count                   │
       │    • returns weekly plan: recipes per slot + cost + macros       │
       └──────────────────────────────────────────────────────────────────┘
```

---

## Encoder semantics

The HTC encoder lives at `recipe_mapper/v1/htc/encoder.py`. Key call:

```python
encode("", description=ingredient_text, food_name=product_identity_fixed,
        canonical_path=canonical_path, identity_mode=False)
```

`identity_mode=False` populates positions 5-7 (form/processing/ptype). Without it, "whole ham" and "sliced ham" collapse to the same code.

Position layout:
- **1**: group (1=Dairy, 2=Meat, 3=Egg, etc.)
- **2**: family
- **3-4**: food (specific identity within family)
- **5**: form (sliced/whole/ground/...)
- **6**: processing (cooked/raw/dried/...)
- **7**: ptype
- **8**: check digit

---

## What's done (working)

| Layer | Status |
|---|---|
| Recipes re-encoded with `identity_mode=False` | ✅ 99.3% of htc_codes changed from stale cache |
| `priced_products.htc_form_code` populated for 169k SKUs | ✅ 5,341 distinct form-aware codes |
| `htc_reference.json` keyed on form-aware HTC | ✅ 2,252 htc-exact matches (was 30) |
| Calculator (`calculate_recipe_cost_v7`) Strategy A uses form_htc | ✅ |
| Planner tensor cache built form-aware | ✅ 392k recipes |
| 8 planner configs run end-to-end | ✅ thrifty/balanced/high_protein/budget/families |

**Verified resolutions (encoder + reference correctly differentiate):**
- whole ham (`2401030U`) → Kroger Fully Cooked Boneless Half Ham
- sliced ham (`2401001F`) → Land O' Frost Sandwich Sliced Deli Lunch Meat
- ground beef (`2001002A`) → Kroger 85/15 Ground Beef
- whole chicken (`3009000J`) → Heritage Farm Bone-In Whole Chicken
- chicken breast (`3001000K`) → Simple Truth Natural Chicken Breasts
- ground cinnamon (`E202002M`) → Great Value Ground Cinnamon
- whole cinnamon stick (`E20A009T`) → Private Selection Cinnamon Sticks
- olive oil → Simple Truth Extra Virgin Olive Oil
- watercress → Watercress (Meijer)

---

## What's broken (open)

### 1. Within-family form discrimination still misses
Some ingredients resolve to the right family but wrong form/variant. Examples:
- `extra firm tofu` → Silken Tofu (different texture)
- `Dijon mustard` → Honey Mustard (different food)
- `unsalted butter` → Salted Butter (wrong claim)
- `whole milk` ≡ `skim milk` (encoder doesn't pick up fat-content as a form modifier for milk)

### 2. Per-SKU macro calculations sometimes wrong
When a recipe picks a real SKU but that SKU's `consensus_fndds` is incorrect/missing, macros come out wrong. Examples found:
- Tuna Salad: 0.4g total protein (6oz can of tuna alone is ~40g)
- Pizza Sticks: 65g fiber (should be ~10g)
- Pan-Seared Trout: 101g carb (should be ~5g)
- Veg Chicken Nuggets: 89g fat (should be ~25g)

When the SKU pick is right AND its consensus_fndds is right, macros are sane (Grilled Cheese, Ham Omelette).

### 3. Cost inflation in planner output
Across all 8 battery configs, cost-per-1000-kcal lands at $6-15 vs real-world $1-3. Likely cause: planner using package price instead of per-recipe-gram cost. Calculator's `LINE-ATTRIBUTABLE COST` ($1-8 per recipe) is sane; the planner's full-week total is inflated.

### 4. Recipe pool bias toward bread/cheese/eggs
Most configs pick grilled cheese, pizza, French onion soup, scrambled eggs because those are the cheapest fits. Family configs especially converge on pizza variants (5/12 picks). Not a data bug — the templates DO match these recipes — but scoring config tuning needed for variety.

### 5. Protein consistently undershoots target by 2-5 percentage points
Across all configs. Either scoring weight on protein is too soft, or HTC reference protein values per ingredient are systematically low.

---

## Files (this session's artifacts)

| File | Purpose |
|---|---|
| `planner/data/htc_reference.json` | 1,984 HTC codes → SKU + macros + food_group + perishability |
| `planner/data/recipe_htc_grams.json` | 489k recipes' HTC grams_dict |
| `planner/data/tensor_cache/*.pt` | Form-aware tensor cache (210 MB) |
| `planner/build_htc_tensor_cache.py` | Builds the tensor cache |
| `planner/scripts/build_htc_reference.py` | Builds htc_reference.json |
| `planner/scripts/build_htc_grams_dict.py` | Aggregates grams per recipe by HTC |
| `planner/scripts/restamp_recipes_unified_htc.py` | Re-encodes recipes_unified with form-aware HTC |
| `planner/scripts/run_htc_week.py` | Run 1 week with one config |
| `planner/scripts/run_htc_battery.py` | Run 8 configs, compare results |
| `scripts/encode_priced_products_form_aware.py` | Adds htc_form_code column to priced_products |
| `recipe_pricing/scan_macro_outliers.py` | Bridge-error detector (currently OOMs — needs streaming) |
| `planner/data/battery_results.json` | 8-config battery output |

---

## Next decisions

1. **Trace the cost inflation** — biggest user-visible bug. Start with one recipe; trace from cents/gram → recipe attribution → planner aggregation.
2. **Audit per-SKU `consensus_fndds`** for the SKUs that produce broken macros. Is the FNDDS code wrong, or is the FNDDS lookup table itself sparse?
3. **Tighten encoder for fat-content modifiers** (whole milk, skim milk, light/regular variants).
4. **Add veg/protein quotas** to scoring config so planner can't bypass them.
