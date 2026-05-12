# Plan: Make Every Recipe Line Calculatable

Goal: zero `BLOCKED` lines in `recipe_normalization_nebius_calculation_lines.csv`. Every line gets a deterministic `consumed_grams` and a named `policy_applied` tag for audit. We test against Nebius output, but the calculator does not depend on Nebius cooperation — it owns the defaults.

---

## 1. Live failure inventory (n=17 blocked lines)

From `implementation/output/recipe_normalization_nebius_calculation_lines.csv` after the candidate Nebius run:

| Bucket | Count | Examples | Root cause |
|---|---:|---|---|
| `selected_option_required` | 10 | 19546 L1 (ham bone OR ham hock OR ground beef); 24789 L0/L7/L8/L10/L12; 4627 L3/L13/L14; 352979 L8 | Calculator has only one `selected_option_required` rule (chili+dried). Every other alt-group falls through. |
| Ambiguous identity (`all_input`, `matchability=BLOCKED`) | 3 | synthetic L1 (100% bran), L2 (100% fruit juice), L13 (prepared chili) | No fallback when the model can't disambiguate the product identity. |
| `uptake_policy_required` | 2 | 39 L18 (vegetable oil), L19 (ghee) | No uptake-default rule wired up. |
| `yield_policy_required` | 1 | 71 L0 (4 lbs bone-in chicken pieces) | Calculator only matches the literal string `"ham bone"`. |
| `sodium_absorption_policy_required` | 1 | 39 L17 (Salt, to taste, in cooking water) | No sodium-absorption default. |

The four cases the previous agent fixed for recipe 11737 (ham bone, bay leaf, chili+dried, Worcestershire range) were solved with **substring matches**, not policy classes. The fix did not generalize.

---

## 2. The prompt contradiction

`RECIPE_NORMALIZATION_NEBIUS_PROMPT_DRAFT.md` is internally inconsistent:

- Lines 188–193: tells Nebius to mark `yield_policy_required` / `retention_policy_required` / `selected_option_required` and **preserve** alternatives — i.e. emit `BLOCKED` and hand the decision to the calculator.
- Lines 195–200: for ranges, tells Nebius to **rewrite** the visible amount to the midpoint, set `range_policy=midpoint`, and set `consumed_grams` to the midpoint grams (i.e. emit `CALCULATION_READY`).
- Lines 287–293: tells Nebius to attach `uptake_policy_required` / `retention_policy_required` / `sodium_absorption_policy_required` flags and leave them as `BLOCKED`.

So one paragraph says "compute the default and emit READY," and the next says "preserve and emit BLOCKED." Nebius defaulted to BLOCKED everywhere except the four cases where it happened to follow the rewrite rule. **The prompt has to commit to one model.** We will commit to: **Nebius preserves data, calculator applies defaults.** That is the simpler invariant and it does not depend on prompt fidelity.

---

## 3. Design principle

> The calculator dispatches on the **policy class** in `consumption.consumption_policy` and `matchability.status`, never on substrings of the ingredient name. Every policy class has a documented numeric default. Nebius's only job is to expose the data the default needs (source_grams, range_low/high, role, alternatives list).

If a policy class has no documented default yet, that is a gap we close in this plan, not a reason to leave the line BLOCKED.

---

## 4. Deterministic defaults per policy class

These are the rules to encode in `build_recipe_normalization_nebius_calculation.py`. Each emits `calculation_status="CALCULATION_READY"`, populates `consumed_grams`, and records `policy_applied`.

### 4.1 `yield_policy_required` (bone-in / shell-on / rind-on / peel-on)

Lookup table on `role` + `product_identity` keywords (not literal ingredient strings):

| Class | Edible yield | Tag |
|---|---:|---|
| Bone-in pork (ham bone, ham hock, pork shoulder bone-in) | 25% | `bone_in_pork_yield_25pct_applied` |
| Bone-in poultry (chicken pieces, drumsticks, thighs, wings, whole bird) | 70% | `bone_in_poultry_yield_70pct_applied` |
| Bone-in beef / lamb (shank, short rib, oxtail) | 60% | `bone_in_beef_lamb_yield_60pct_applied` |
| Shell-on shrimp / crab / lobster | 50% | `shell_on_shellfish_yield_50pct_applied` |
| Whole fish / fish with head and tail | 55% | `whole_fish_yield_55pct_applied` |
| Citrus / melon / squash with rind, peel-on | 70% (default) | `peel_on_produce_yield_70pct_applied` |
| Fallback (yield_policy_required, no class match) | 50% | `yield_policy_default_50pct_applied` |

`consumed_grams = source_grams * yield`.

### 4.2 `retention_policy_required` (removed-aromatic / coating residue)

| Class | Retained | Tag |
|---|---:|---|
| Removed aromatic (bay leaf, cinnamon stick, whole spices in cheesecloth, herb stems, peppercorns in sachet, kombu) | 0% | `removed_aromatic_zero_consumption_applied` |
| Coating flour / breadcrumbs / cornmeal / dredge | 25% of source_grams | `coating_retention_25pct_applied` |
| Sugar dusting / cocoa dusting | 10% | `dusting_retention_10pct_applied` |
| Fallback | 0% | `retention_policy_default_zero_applied` |

### 4.3 `uptake_policy_required` (frying / sauteing oil/fat)

| Class | Uptake of source_grams | Tag |
|---|---:|---|
| Sauté / pan-coat oil for short cook (vegetable oil, olive oil, butter, ghee for sauté) | 25% | `saute_uptake_25pct_applied` |
| Shallow-fry coating oil | 50% | `shallow_fry_uptake_50pct_applied` |
| Deep-fry oil | 10% | `deep_fry_uptake_10pct_applied` |
| Fallback | 25% | `uptake_policy_default_25pct_applied` |

Cue selection from `original_display` / `culinary_use` ("for frying" → deep-fry; "for sautéing" / "to coat the pan" → sauté; default if no cue → 25%).

### 4.4 `sodium_absorption_policy_required` (salt in cooking water)

| Class | Absorbed of source_grams | Tag |
|---|---:|---|
| Salt in pasta / blanching / boiling water | 10% | `pasta_water_sodium_10pct_applied` |
| Salt in brining liquid | 15% | `brine_sodium_15pct_applied` |
| Salt "to taste" applied directly to dish (`role=consumed`) | 100% of source_grams | `to_taste_source_grams_default_applied` (already exists) |
| Fallback | 10% | `sodium_absorption_default_10pct_applied` |

### 4.5 `selected_option_required` (alternative groups) — the biggest bucket

This is where we have to be explicit. Three sub-rules, evaluated in order:

1. **Equivalent alternatives** (already in code via `equivalent_alternatives_policy_applied`): if all alternatives share the same `category_path` / role, take `source_grams` and tag `equivalent_alternatives_policy_applied`. Already works.
2. **Materially different but role-consistent**: if all alternatives share the same `role` (e.g. all are `consumed` proteins, all are `consumed` cheeses), pick the **first listed alternative** as the canonical one. Tag `first_alternative_default_applied`. `consumed_grams = source_grams` adjusted by that alternative's yield class if 4.1 applies (e.g. ham bone vs ham hock vs ground beef → first is ham bone → also apply bone-in pork yield).
3. **Conditional alternative** (e.g. "milk or water if using chicken"): pick the unconditional branch. If both branches are conditional, pick the first. Tag `conditional_alternative_default_applied`.
4. **Fallback**: pick first alternative, tag `selected_option_first_alternative_applied`.

### 4.6 Ambiguous identity (`matchability.status=BLOCKED`, policy=`all_input`)

| Sub-class | Default | Tag |
|---|---|---|
| Identity ambiguous but quantity is concrete (`source_grams > 0`) | use `source_grams` as best-effort, mark calculation ready, flag for downstream nutrition match | `identity_ambiguous_source_grams_default_applied` |
| Identity ambiguous AND quantity unknown | EXCLUDED with reason | `excluded_unresolvable` |

The downstream nutrition-code match still has to deal with the ambiguity, but the **gram calculation** is no longer blocked.

### 4.7 Range midpoint (already partially handled)

Today it only fires when `raw_status==BLOCKED`. Fix: apply midpoint **whenever `range_low` and `range_high` are both present**, regardless of raw status. Tag `range_midpoint_default_applied`.

---

## 5. Prompt simplification

Edit `RECIPE_NORMALIZATION_NEBIUS_PROMPT_DRAFT.md`:

- Replace lines 195–200 (the "rewrite to midpoint" block) with: *"Preserve `range_low`, `range_high`, `unit`, and `source_grams`. Do not compute the midpoint. The calculator will."*
- Replace lines 188–193 (per-ingredient default hints) with a generic statement: *"For any line that needs a deterministic default (yield, uptake, retention, sodium absorption, range midpoint, alternative selection), set the appropriate `consumption_policy` flag and `calculation_status=BLOCKED`. Always populate `source_grams`, `range_low`/`range_high`, `role`, `alternatives`, and `culinary_use` so the calculator can apply its default."*
- Add an explicit list of the policy classes Nebius is allowed to emit, matched 1:1 with the calculator's defaults in §4 of this plan.

This kills the "preserve vs compute" contradiction. Nebius's job becomes: extract data, classify policy, never compute.

---

## 6. Implementation steps

1. **Refactor `calculation_default`** in `build_recipe_normalization_nebius_calculation.py` to dispatch on `raw_policy` (the policy class), not substrings. Keep substring lookups only for sub-classification within a class (e.g. "deep-fry" vs "sauté" inside `uptake_policy_required`).
2. **Add a yield-class lookup module** (`implementation/recipe_calculation_defaults.py`): tables for §4.1–4.4 keyed by simple keyword sets.
3. **Add ambiguous-identity fallback** keyed off `matchability.status=BLOCKED` + `source_grams > 0`.
4. **Lift the range-midpoint guard** so it fires regardless of raw status.
5. **Add `selected_option_required` cascade** per §4.5. Pull the alternatives list from the Nebius `alternatives` array (currently empty in many candidate rows — Nebius will need to populate it; until then, fall back to "first alternative parsed from original_display").
6. **Edit the prompt** per §5 and re-run the candidate generation against Nebius.
7. **Expand `tests/test_recipe_normalization_nebius_calculation.py`** with one test per policy class, covering at minimum:
   - bone-in chicken pieces (recipe 71 L0)
   - alt group with mixed yield classes (recipe 19546 L1)
   - all-protein alt group (recipe 24789 L0)
   - cheese-blend alt group (recipe 24789 L8)
   - conditional alt group (recipe 24789 L12)
   - garlic powder vs garlic clove alt group (recipe 4627 L3)
   - milk vs sour cream alt group (recipe 4627 L13)
   - vegetable oil sauté uptake (recipe 39 L18)
   - salt-to-taste in cooking water (recipe 39 L17)
   - ambiguous identity 100% bran (synthetic L1)
   - range midpoint already-`READY` line (verify no regression)
8. **Run the calculator** against the existing candidate JSONL and verify `blocked_lines=0` for every recipe in the summary CSV.
9. **Re-run Nebius** with the updated prompt to verify Nebius now emits the data the calculator needs (alternatives list populated, no surprise policy classes).

---

## 7. Acceptance criteria

- `recipe_normalization_nebius_calculation_summary.csv`: every row `calculatable=yes`, `blocked_lines=0`.
- `recipe_normalization_nebius_calculation_lines.csv`: every row has either `calculation_status=CALCULATION_READY` with a non-null `calculated_grams` and a `policy_applied` value, or `calculation_status=EXCLUDED` with a documented reason.
- The test suite covers one representative line per policy class.
- The prompt no longer contains the "rewrite to midpoint" instruction or any other Nebius-side default computation.

---

## 8. What this plan does NOT do

- It does not pick the **nutritionally correct** alternative — it picks a deterministic one. A user-driven override layer is a separate task.
- It does not resolve **ambiguous product identity** for nutrition matching — the gram is calculated, but the FNDDS/SR28/ESHA match is still flagged downstream.
- It does not change the **role classifier** in Nebius. If Nebius mis-tags a process_medium as consumed, the wrong default fires. We accept that risk for now and surface it via the `policy_applied` audit tag.
