# Wrong-Class Pick Fix Plan — Durable, No Blockers

Date: 2026-05-11
Audit input: `recipe_pricing/picked_recipe_audit_r4_at_r5_LINES.csv`
Authority contract: `docs/DATA_AUTHORITY_CONTRACT.md`

## Principle

We do **not** patch this with a negative-lexicon CSV or an "ignore these SKUs"
blocker list. Every fix lands in one of the files the data authority contract
already names, and the rebuild cascade (`planner/scripts/rebuild_pricing_pipeline.py`)
propagates the change to every downstream artifact.

Every bad pick falls into exactly one of two classes:

- **Class A — SKU mis-coded.** The product sits in the wrong `retail_leaf_path`
  and the encoder derives the wrong `htc_full_code`. Fix in
  `recipe_pricing/reclassify_canonical_paths.py` (MISROUTES table). Re-encode
  cascades the new code through the contract.
- **Class B — SKU correctly coded, resolver leaks across concepts.** The picker
  matched the SKU to a *different* concept at a permissive tier
  (`path_only`/`form_only`/`parent_path_only`). Fix in
  `planner/scripts/build_concept_resolution.py` by tightening the tier rules.

No SKU-level allow/deny CSV is added.

---

## Class A — SKU mis-codes (fix via MISROUTES + re-encode)

For each pattern below, add a tuple to the `MISROUTES` list in
`recipe_pricing/reclassify_canonical_paths.py`. Format is already established
in the file (see `fresh_tomato_at_canned` at line 190):

```python
(name_regex, from_path_regex, new_path, rule_tag, new_canonical_label)
```

### A1. String / snack-stick cheese is sitting in the non-food bucket

**Evidence.** ~200 SKUs whose name contains "String Cheese" or "Cheese Snack
Sticks" carry `htc_full_code = ~N0000009-*-0000` (the non-food catch-all) and
empty `retail_leaf_path`. Recipes asking for `Cheddar` pick these because the
resolver falls to `form_only`/`parent_path_only` and there is no real-bucket
competitor.

**Fix.** New MISROUTE: move the whole class to a real dairy leaf so the encoder
re-derives a cheese identity code, *not* the cooking-cheddar identity.

```python
(r"(string cheese|cheese (snack )?sticks?|mozzarella string|cheese heads)",
    r"^$|^Non-Food|^~N0000009",
    "Dairy > Cheese > Cheese Snack > String Cheese",
    "string_cheese_at_nonfood", "String Cheese"),
```

This also fixes the Sargento "Sharp Cheddar Cheese Snack Sticks" pattern,
because after re-encode the identity code is the cheese-snack leaf, not
`1101000H` (cooking cheddar). 42 line-item hits resolved.

### A2. Blue Bonnet "Vegetable Oil Sticks" is shelved under cooking oil

**Evidence.** `Blue Bonnet Vegetable Oil Sticks` carries
`htc_full_code = ~140B000B-7DD2A4-0000` (margarine identity) but
`retail_leaf_path = Pantry > Oil > Vegetable Oil`. Code and path disagree —
re-encode would resolve this on its own *if* the path were correct. Sibling
SKU `Blue Bonnet Original Vegetable Oil Spread Sticks` is already correctly at
`Dairy > Butter > Margarine > Vegetable Oil`.

```python
(r"\b(margarine|vegetable oil (spread )?stick)s?\b",
    r"^Pantry > Oil",
    "Dairy > Butter > Margarine > Vegetable Oil",
    "margarine_at_oil", "Margarine"),
```

21 line-item hits resolved.

### A3. Alafia Grape Leaves is coded as avocado

**Evidence.** `Alafia Grape Leaves, 16 oz` carries
`htc_full_code = ~6018000R-000000-0000` (where `6018` is the avocado identity
prefix), empty `retail_leaf_path`, empty `canonical_label`. The encoder used a
substring "leaves" or vendor SKU fluke. Grape leaves are jarred
Mediterranean specialty produce; the closest existing leaf in the catalog is
`Produce > Vegetables` (need to add `> Grape Leaves`).

```python
(r"\bgrape leaves\b|\bdolma\b",
    r"^$|^Produce > Vegetables > Avocado|^~6018",
    "Produce > Vegetables > Grape Leaves",
    "grape_leaves_at_avocado", "Grape Leaves"),
```

13 line-item hits resolved. Critical because the SKU is $10.99 each, so this
one rule pulls $143 of fake spend out of the audit.

### A4. McCormick Strawberries & Cream Finishing Sugar is in the Extract bucket

**Evidence.** `~E500000*-000000-0000` is the extract/flavoring bucket. The
product is flavored granulated sugar.

```python
(r"finishing sugar|flavored sugar|sanding sugar|sprinkle sugar",
    r"^$|^Pantry > Baking > (Extract|Flavoring)",
    "Pantry > Sweeteners > Sugar > Flavored Sugar",
    "flavored_sugar_at_extract", "Flavored Sugar"),
```

6 line-item hits resolved.

### A5. Ocean Spray Citrus Splash sits in the non-food bucket

**Evidence.** `~N0000009-000000-0000`, no path, no label. It is a juice drink.

```python
(r"^Ocean Spray.*Citrus Splash|citrus splash.*grapefruit",
    r"^$|^~N0000009",
    "Beverage > Juice > Juice Drink > Citrus Blend",
    "citrus_splash_at_nonfood", "Citrus Juice Drink"),
```

4 line-item hits resolved. Lifts the "Limes → Citrus Splash juice" misfire,
because juice drinks then no longer compete for the `Limes` produce concept
(they sit on a different aisle).

### Class A summary

- **5 MISROUTE tuples** added.
- Resolves ~86 line items / ~85 distinct recipes in the audit sample of 251.
- All five SKUs end up with a correct `htc_full_code` after `reencode_after_reclassify.py` runs.
- No allow/deny CSV is added; existing tooling (`reclassify_log.csv` already in
  the repo) records every row touched.

---

## Class B — Resolver leaks across concepts (fix in `build_concept_resolution.py`)

These bad picks are NOT SKU mis-codes. The SKU sits in the correct bucket; the
problem is the resolver matches across concepts at a permissive tier.

### Tier-by-tier rule changes

Today the resolver lets a `form_only` / `parent_path_only` match win when no
exact peer exists in the pool. Two guardrails are missing:

#### B1. Concept-family lock for HTC family 6x (produce)

Within `Produce > Vegetables` the identity codes differ at position 1–2
(`6018`=avocado, `6011`=lettuce, `6102`=baby carrots, `6A03`=peas-and-carrots
canned). A `parent_path_only` collapse to `Produce > Vegetables` is therefore
**always** a different food. Add to `build_concept_resolution.py`:

> When `expected.htc_full_code[:4] != candidate.htc_full_code[:4]` AND both
> sit under `Produce`, fail the resolution. Emit `NO_MATCH`, do not fall
> through to a sibling.

Fixes: Baby Carrots → Peas-and-Carrots (26 lines), and any future
cross-vegetable substitution.

#### B2. Spice identity lock under `Pantry > Spices & Seasonings`

Every spice has a distinct identity code (`E40B...`=cumin, `E304A...`=bay
leaves, `E40...`=oregano). A `parent_path_only` collapse to "Spices &
Seasonings" picks an arbitrary spice. Rule:

> Within `Pantry > Spices & Seasonings`, never resolve `parent_path_only`. If
> the exact identity is absent from the priced pool, emit `NO_MATCH` and the
> shopping list shows the closest in-catalog spice with a `SUBSTITUTE` flag,
> not silently.

Fixes: Oregano → Bay Leaves (5), Cumin → Bay Leaves (also flagged
elsewhere). Spice resolutions become honest about substitutions.

#### B3. Sweetener subtype lock

`Pantry > Sweeteners` has incompatible subtypes: granulated sugar, brown
sugar, agave, honey, maple syrup, molasses. Recipe-physics differ (wet vs dry,
sucrose vs fructose). `form_only` resolution across subtypes is wrong.

> Within `Pantry > Sweeteners`, restrict `form_only` and below to the same
> direct parent. `Brown Sugar` may only resolve within `Sweeteners > Sugar >
> Brown Sugar`; if pool is empty, fail.

Fixes: Brown Sugar → Agave (17 lines).

#### B4. Animal-vs-plant boundary lock for `Meat & Seafood`

MorningStar veggie crumbles sit at `Meal > Plant Based > *`. The `Meat &
Seafood > Bacon` concept resolved to them at a permissive tier.

> If concept_key starts with `Meat & Seafood`, candidate path must not start
> with `Meal > Plant Based`. Reject before form/parent collapse.

Fixes: Bacon → MorningStar (5 lines), and the entire plant-based crossover
class for future recipes.

#### B5. Form-context lock for cooking cheese

The Sargento cheese-snack-stick case (residual after A1 is applied) is when
the SKU's htc_form_code marks `snack stick` form. Cooking recipes do not
ask for snack-stick form. The recipe side already encodes a *cooking* form
expectation (shred / block / grated) in `recipe_ingredient_taxonomy_v2.csv`.

> For `Dairy > Cheese > *`, when recipe form ∈ {shred, block, grated,
> sliced, melted}, candidate `htc_form_code` must not be a snack-stick form
> (`N000009J`, `N0000009`, `N000609M`). This is a form-compat rule, not a
> name filter.

This rule reuses the form_code dimension that already exists; it is not a
new CSV.

### Class B summary

- **5 resolver guardrails** added in `planner/scripts/build_concept_resolution.py`.
- Each one is a structural rule expressed in HTC code or path prefix — not
  per-SKU.
- Together they shut every remaining cross-concept leak in the audit.

---

## Order of operations (matches the data authority contract)

Run the existing rebuild script — do not invent a new path:

```bash
python3 planner/scripts/rebuild_pricing_pipeline.py
```

Inside that, the relevant ordered steps are:

1. **Edit** `recipe_pricing/reclassify_canonical_paths.py` — add 5 MISROUTE
   tuples (Class A).
2. **Edit** `planner/scripts/build_concept_resolution.py` — add 5 resolver
   guardrails (Class B).
3. Reclassify product canonical paths.
4. Re-encode product HTC identity/form/full codes.
5. Re-tag recipe `htc_code` / `htc_full_code`.
6. (Gram normalization steps — unchanged.)
7. Data preflight (`recipe_pricing/preflight_data_contract.py`).
8. Rebuild concept index.
9. Rebuild concept resolution (now with new guardrails).
10. Rebuild tensor cache.
11. Preflight again.

Preflight already enforces `htc_code ≡ encoder(canonical_path)` so a bad
MISROUTE rule is caught before the planner sees it.

---

## Regression tests (add before merging)

Add a new test alongside `implementation/tests/test_codex_deepseek_taxonomy_review.py`:

```python
# test_known_misroutes_stay_fixed.py
EXPECTATIONS = [
    # (recipe concept_key fragment, picked_sku must_not contain)
    ("Produce > Vegetables > Avocado",     "Grape Leaves"),
    ("Produce > Vegetables > Baby Carrots","Peas"),
    ("Dairy > Cheese > Cheddar",           "Snack Sticks"),
    ("Dairy > Cheese > Cheddar",           "String Cheese"),
    ("Pantry > Oil > Vegetable Oil",       "Stick"),
    ("Pantry > Sweeteners > Sugar > Brown","Agave"),
    ("Pantry > Spices & Seasonings > Oreg","Bay Leaves"),
    ("Dairy > Cream",                      "Sugar"),
    ("Meat & Seafood > Bacon",             "Veggie"),
    ("Meat & Seafood > Bacon",             "MorningStar"),
    ("Produce > Fruit > Limes",            "Citrus Splash"),
]
```

The test runs the resolver against the 251-recipe sample and asserts that
none of these substring pairs co-occur on the same line. Fast (loads the
existing LINES csv) and runs in CI on every pipeline change.

---

## What is explicitly NOT being done

- **No** "blocklist" CSV under `recipe_pricing/`.
- **No** negative-lexicon filter inside the cost calculator.
- **No** per-SKU manual overrides in `htc_cp_overrides.csv` — that file
  remains scoped to recipe-side mapping fixes per its `REVIEWED_OVERRIDE` role.
- **No** mods to the picker / planner-runtime selection logic. All fixes are
  in the data layer (reclassify) or the concept-resolution layer that feeds
  the planner.

---

## Estimated impact

| Layer | Hits today | After fix |
|---|--:|--:|
| Class A SKU mis-codes (avocado, cheese-stick, oil-stick, citrus-splash, finishing-sugar) | ~86 lines / 85 recipes | 0 |
| Class B resolver leaks (carrots, sugars, spices, bacon, cheese-form) | ~67 lines / 65 recipes | 0 |
| Combined wrong-class footprint | ~153 lines, ~60% of recipes | <2% of recipes (residual `NO_MATCH` cases, now visible) |

After this lands, the planner can expose line items to a customer-facing
shopping list without the trust-killing substitutions.
