# Eliminate regex/string-matching — use HTC positions

The encoder is the one place that makes identity decisions. Every other piece of
code that does `if "beef" in cp.lower()` or `"vegetable" in path` is duplicating
encoder logic, which is exactly the bug we keep tripping on (canned tomatoes
under `Pantry > Canned Vegetables` failed our `"produce" in cp` test even though
the encoder gives them group **6** = Vegetables).

## What HTC positions encode (8-char code)

```
position  meaning              examples
--------  -------              --------
   1      group               1=Dairy 2=RedMeat 3=Poultry 4=Fish 5=Eggs
                              6=Vegetables 7=Fruit 8=Bakery 9=Legume?
                              B=Oil C=Sweetener D=Beverage E=Spice
                              F=Sauce G=Pastry H=Prepared M=Baby N=NonFood
   2      family within group 2A=Beef 2B=Pork 2C=Lamb (etc; per encoder rules)
   3-4    food                specific identity
   5      form                whole/sliced/ground/etc.
   6      processing          cooked/raw/dried/etc.
   7      ptype               product type modifier
   8      check digit         encoder-derived
```

## Where we currently have regex / string-match logic that should be HTC-positional

### 1. `_protein_from_path()` — multiple files
```python
# WRONG — string-matching cp:
if "beef" in cp_low or "veal" in cp_low: return 0
if "pork" in cp_low or "ham" in cp_low: return 1
...
```
**Replace with**: `htc_code[0]` lookup.
```python
HTC_GROUP_TO_PROTEIN = {
    "2": 0,  # red meat (beef/pork/lamb — further family discrim if needed)
    "3": 2,  # poultry
    "4": 3,  # fish/shellfish
    "5": 4,  # eggs
    "9": 5,  # legumes
}
def _protein_from_htc(htc): return HTC_GROUP_TO_PROTEIN.get((htc or "?")[0], -1)
```

### 2. Food-group derivation in `build_concept_tensor_cache.per_recipe_totals()` (already deprecated by recipes2.csv overlay, but if we ever need a fallback)
```python
# WRONG:
if "produce" in cp_low and "vegetable" in cp_low: veg_g += grams
elif "dairy" in cp_low: dairy_g += grams
```
**Replace with**: HTC-positional.
```python
HTC_GROUP_TO_FOODGROUP = {
    "1":"dairy", "2":"protein", "3":"protein", "4":"protein", "5":"protein",
    "6":"vegetables", "7":"fruits", "8":"grains", "9":"protein",
    "B":"fats", "C":"sweets", "D":"beverages",
    "E":"seasoning", "F":"condiment", "G":"grains", "H":"meal",
    "M":"baby", "N":"non_food",
}
def _foodgroup_from_htc(htc): return HTC_GROUP_TO_FOODGROUP.get((htc or "?")[0], "other")
```

### 3. NAME_BLOCKLIST in `build_concept_index.py` (lure/baby/charcoal text scan)
**Keep as-is** — this is a SKU-name filter for products that the encoder COULDN'T have known about (Walmart calls a product "Bait" or "Charcoal" but it's at consensus_canonical = food path). HTC of those bad rows is `00000000` (we already quarantine). The remaining text-scan catches edge cases where consensus_canonical was correct but the SKU is genuinely a non-food. Acceptable.

### 4. ANTI_MODIFIERS in `calculate_recipe_cost_v7.py` (gluten-free / skim / sugar-free etc.)
**Keep as-is for now** — these are claim-level modifiers (positions in HTC are form/processing only, not claims). Claims live in priced_products' `claims` field. A future cleanup could replace this dict with claim-bitmask matching from priced_products' `claims` column.

### 5. `_recipe_filter_tokens()` in calculator (recipe-leaf string matching)
**This is path-leaf substring matching** — needed because recipes ask for "Dijon mustard" but priced concept is at path "Mustard" (parent). Recipe-side leaf says Dijon; priced-side leaf says Mustard. Different abstractions. **Keep**, but document that this layer only fires when concept resolution falls back to a parent path.

### 6. `_protein_from_path` → `_protein_from_htc` in:
- `planner/build_concept_tensor_cache.py`
- `planner/scripts/run_htc_battery.py`
- `planner/scripts/run_htc_week.py`
- `planner/scripts/audit_plan.py`
- `planner/scripts/compare_hestia_vs_ours.py`

All should import from one canonical helper.

## Plan

### Phase 1 — Single source of truth for HTC group → semantics
Create `planner/htc_groups.py` with:
```python
HTC_GROUP_NAMES = {"1":"Dairy", "2":"Red Meat", "3":"Poultry", ...}
HTC_GROUP_TO_PROTEIN_SOURCE = {"2":0, "3":2, "4":3, "5":4, "9":5}
HTC_GROUP_TO_FOODGROUP     = {...}
def protein_source(htc): ...
def foodgroup(htc): ...
def is_non_food(htc): return (htc or "?")[0] in {"M","N"}
```

### Phase 2 — Replace regex callers
For every script in section 6 above: replace `_protein_from_path()` with `protein_source(htc)`. The HTC code is already on every concept_index entry as `htc_form` (8-char). We use `htc_form[0]` for group.

### Phase 3 — Verify against current behavior
Build a comparison: for each priced concept_key, compute protein source via HTC vs current path-regex. Diff. Should agree on the vast majority; disagreements expose either (a) encoder bugs, or (b) regex edge cases the encoder handles right. Either way useful.

### Phase 4 — Drop the path-regex food_group fallback
Once confident HTC group classification works, remove the ad-hoc cp_low checks in `per_recipe_totals()` entirely (the recipes2.csv overlay is preferred anyway, but fallback should also be HTC-positional, not regex).

### Phase 5 — Document HTC group reservoirs in encoder
Cross-reference `recipe_mapper/v1/htc/encoder.py group_from_canonical_path` against the table above. Where the encoder has additional codes (e.g., is there a `9` group for legumes? `D` for beverages? `G`?), add them. Where the table has codes the encoder doesn't emit, drop them.

## Won't-fix (these stay as regex/string-match, by design)

- ANTI_MODIFIERS in calculator (claims, not encoded in HTC positions 1-7)
- NAME_BLOCKLIST (SKU-name layer to catch consensus_canonical bridge errors)
- Recipe-leaf token filter (per-line filter for path-relaxation, not encoder logic)
- Encoder itself's internal regex (it's the source of truth)

## Definition of done

1. `_protein_from_path()` deleted from all 5 scripts; replaced with HTC-positional `protein_source(htc)`
2. Comparison report: HTC-derived protein source matches old path-regex on >95% of priced concept_keys
3. `per_recipe_totals()`'s remaining cp_low chains either deleted (overlay sufficient) or rewritten as HTC-positional
4. One canonical `planner/htc_groups.py` module imported everywhere
5. Battery + audit reruns produce the same numbers (within 0.5pp on every metric) as before — proves the refactor is a no-op behaviorally, just cleaner code
