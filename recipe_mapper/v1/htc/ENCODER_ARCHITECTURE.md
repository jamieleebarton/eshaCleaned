# Recipe-side HTC encoder architecture

**Status:** documented 2026-05-09 to support encoder fix work (Phases 2–6).

## Pipeline (recipe ingredient text → htc_code → canonical_path)

```
recipe_ingredient_items.csv (22k unique items)
        │
        ▼
tag_ingredients_with_htc.py:90
        │
        │  encode(category="", description=item, extra="", food_name=item)
        ▼
recipe_mapper/v1/htc/encoder.py::encode()
        │
        │  Input: 5 strings (category, description, extra, food_name, modifier)
        │  Output: HTC = (group, family, food, form, processing, ptype, check)
        ▼
recipe_ingredient_htc_tagged.csv (item → htc_code)
        │
        ▼
restamp_recipes_unified_htc.py
        │
        ▼
recipes_unified.csv (4.7M lines, each line carries htc_code from encoder)
        │
        ▼
build_recipe_concept_grams.py:104-114
        │
        │  cp = item_overrides[item]
        │       or htc_to_path[htc_form_code]   ← from consensus_htc_tagged.csv
        │       or title_to_path[item]
        ▼
recipe concept_key = f"{cp}|{htc_form_code}"
```

**Two-layer mapping**: encoder produces `htc_code`; downstream `build_recipe_concept_grams.py` derives `canonical_path` from a separate FNDDS lookup keyed on htc_code. Either layer can be wrong.

## encoder.py::encode() — internal flow

For recipe-side calls (`category=""`, `food_name=item`, no canonical_path):

```
1. NON_FOOD_PATTERNS check                        → if match: group="N", short-circuit
2. Poultry-deli override                          → fires only with non-empty cat
3. explicit_group_hint (pizza dough/sauce)        → mostly inert for plain recipe items
4. group = path_group OR explicit OR cat-match    → all empty for recipe side → "0"
5. group = _match_first(GROUP_RULES, description) ← THIS is where recipe items get grouped
6. if still 0: try extra
7. if still 0: family-fallback over combined text
8. family_from_identity using FAMILY_RULES[group]
9. food_slot_registry lookup
10. code_from_parts() + Crockford check
```

**Step 5 is the key decision point for recipe ingredient classification.** GROUP_RULES is an ordered list of `(regex, group_letter)` pairs evaluated top-to-bottom; the FIRST match wins.

## GROUP_RULES order matters — and that's where the bugs live

I ran `encode()` on every Phase 0 REAL_BUG item and traced the rule index that fires. Results below.

### Class 1 — wrong GROUP routed by GROUP_RULES (encoder bug, fix in encoder.py)

| recipe item | encoder produces | rule # | matched pattern | should be |
|---|---|---|---|---|
| chicken broth | g3 (Poultry) → `300C000D` | 22 | `chicken\|turkey\|poultry…` | gJ (Pantry/Broth) |
| chicken stock / low-sodium etc. | same | 22 | same | same |
| beef broth / stock | g2 (Red Meat) → `200D000S` | 17 | `\bbeef\b…` | gJ |
| vegetable broth / stock | g6 (Vegetables) → `6035000N` | 27 | `vegetable\|veggie…` | gJ |
| fish stock | g4 (Fish) → `406E0009` | 23 | `\bfish\b\|seafood…` | gJ |
| baking soda | gD (Beverage) → `D20G000~` | 37 | beverage rule matching "soda" | gJ (Pantry/Baking) |
| bicarbonate of soda | same | 37 | same | gJ |
| almond extract | gA (Nuts) → `A001000P` | 34 | nut rule matching "almond" | gE/gJ (Pantry/Baking Extracts) |
| rum extract | gD (Beverage) → `DA9K0004` | 37 | beverage rule matching "rum" | gE/gJ |
| maple extract | gE (Spices) → `E500000*` | 38 | spice rule matching "extract" | gJ (Pantry/Baking Extracts more specifically) |
| vanilla bean | g9 (Legumes) → `902Q000W` | 33 | legume rule matching "bean" | gJ (Pantry/Baking Extracts > Vanilla Bean Paste) |
| milk chocolate chips | g1 (Dairy) → `1001000$` | 0 | dairy rule matching "milk" | gJ (Pantry/Chocolate Chips) |
| sweetened flaked coconut | g1 (Dairy via family-fallback) → `1A00000T` | family_fallback | "coconut" matched FAMILY_RULES[1][A] | gJ (Pantry/Flakes/Coconut Flakes) |
| fresh mint | gE (Spices) → `E300000X` | 36 | spice rule matching "mint" | g6 (Produce > Herbs) for *fresh* — gE is fine for *dried* |
| ground red pepper | g6 (Vegetables) → `66080000` | 14 | bell-pepper rule | gE (Pantry/Spices/Cayenne) — "ground red pepper" = cayenne |
| dried onion flakes | g6 (Vegetables) → `65010004` | 10 | onion rule | gE (Pantry/Spices) — dried flakes are spice form |

**Total class-1 impact: ~70k recipe lines** (broth cluster ~44k + baking soda 32k + extracts 5.6k + vanilla bean 1k + chocolate chips 1.2k + coconut 1.1k + ground red pepper 1.9k + dried onion flakes 1.2k + fresh mint 3.1k).

### Class 2 — group correct, htc→cp lookup wrong (data bug, fix in consensus_htc_tagged.csv)

| recipe item | encoder produces | derived cp (wrong) | issue |
|---|---|---|---|
| red/dry red/sherry/port/marsala wine | gD f8 → `D8000007` | Beverage > Mixes > Slushie Mix | htc D8000007's most-common FDC cp is mistagged |
| orange marmalade | gF fA → `FA00000*` | Pantry > Spreads > Lime Curd | mistagged FDC |
| catsup | gF f1 → `F1000000` | Pantry > Condiments > Spring Rolls | mistagged FDC |
| sauerkraut | gF f9 → `F900000C` | Pantry > Dips & Spreads > Vegetable Spread | mistagged FDC |
| pimientos | gF f9 → `F900000C` | (same as sauerkraut — same htc!) | family rule problem AND mistag |
| grenadine | gD fB → `DB00000Y` | Pantry > Flour > Drink Mix | mistagged FDC |

**Total class-2 impact: ~10k recipe lines.** Class-2 fixes don't touch encoder.py — they need either a consensus_htc_tagged.csv re-tag (FDC-by-FDC) or a layer-2 override.

### Peanut butter cluster — needs both encoder AND data inspection

`peanut butter` correctly hits rule #4 (peanut|almond|cashew|sunflower|seed|nut)+butter → group A. So the encoder is RIGHT for peanut butter. But Phase 0 says it routes to "Snack > Bars > Protein Bars". That means htc `A0FZ000Q` (the encoder's output) maps via consensus_htc_tagged.csv to "Snack > Bars > Protein Bars". Which is class-2 — wrong FDC tagging at that htc. Probably need to confirm and either re-tag or override.

## Where consensus_htc_tagged.csv goes wrong

This file is the htc-code → canonical_path map. Built upstream by `tag_consensus_with_htc.py` (115 lines). Each FDC entry gets:
- canonical_path (assigned by another upstream step)
- htc_code (assigned by this script using the same encoder)

The file has 25,729 distinct htc_codes. For a recipe-side htc to resolve to the right cp, ENOUGH FDC entries with that htc must be tagged at the right path that they outvote noise.

The `min FDC agree ≥ 2` gate I added in `build_recipe_concept_grams.py:74` (Bug 1) drops htc_codes where only 1 FDC agrees. It saved 18,620 recipes from the F800000X "Plant Based Cheese > Spaghetti with Sauce" mistag. The class-2 bugs above are likely cases where 2-3 FDCs agree on a wrong cp (so the gate doesn't help) but the agreement is still wrong.

## Files in scope for Phase 2 fix list

| File | What lives there | Who calls it |
|---|---|---|
| `recipe_mapper/v1/htc/encoder.py` (739 lines) | `encode()`, `GROUP_RULES`, `FAMILY_RULES`, `FORM_RULES`, `PROC_RULES`, `PTYPE_RULES`, `group_from_canonical_path` | tag_ingredients_with_htc.py + tag_consensus_with_htc.py + retail-side tagger |
| `recipe_mapper/v1/htc/food_slots.py` (20k lines) | food_slot_registry — maps (group, family, identity_text) → food_slot id (positions 3-4) | encoder.py |
| `recipe_mapper/v1/htc/food_slot_registry.csv` (13MB) | the registry data | food_slots.py |
| `recipe_mapper/v1/tag_ingredients_with_htc.py` | recipe-side driver. Calls encode() per item | manual run |
| `recipe_mapper/v1/tag_consensus_with_htc.py` | FNDDS-side driver. Tags consensus_htc_tagged.csv via encode() | manual run |
| `planner/scripts/restamp_recipes_unified_htc.py` | re-stamps htc on recipes_unified.csv from the per-item htc table | manual run after encoder change |

## Architectural observation

**Both retail and recipe sides use the SAME `encode()` function.** That's why a single broken GROUP_RULE poisons both:
- A canned-chicken SKU at canonical_path `Pantry > Canned Meat > Canned Chicken` gets group J via path_group (correct, top-level pantry).
- A "chicken broth" recipe with no canonical_path gets group 3 via GROUP_RULES (wrong — chicken poultry).
- Different htc_codes → different concept_keys → won't bridge directly.
- Resolution ladder eventually rescues it via path_only IF the recipe-side cp (derived via htc lookup of its bad htc) somehow lands at "Pantry > Broth & Stock". It doesn't — htc 300C000D → "Meat & Seafood > Poultry > Chicken" via FNDDS.

**Implication:** the cleanest Phase 3 strategy is to reorder GROUP_RULES so high-impact disambiguation rules (broth, stock, extract, baking, chocolate chips, vanilla bean, etc.) fire BEFORE the broad nouns (chicken, beef, milk, soda, bean, almond). Existing precedent for this pattern: lines 285–296 already do this for spice-vs-vegetable disambiguation (garlic powder before garlic, ground spices before red meat).

## Ready for Phase 2

Phase 2 deliverable: `ENCODER_FIX_LIST.md` — a table of (rule_to_add_or_modify, regex_pattern, target_group, position_in_GROUP_RULES_list) for each Class-1 fix, plus a separate list of Class-2 mistagged FDCs to address.

For each Class-1 fix, the change is: insert a new rule at the top of GROUP_RULES (or before the offending rule) that catches the specific item pattern and routes to the right group. ~10 new rules total.

For Class-2 fixes: either patch consensus_htc_tagged.csv directly (~6 rows), or add a `(htc_code → cp)` override layer in build_recipe_concept_grams.py.
