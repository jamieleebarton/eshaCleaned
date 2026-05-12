# Retail Mapper — Official Plan (v1)

**Date:** 2026-04-28
**Owner working dir:** `/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/`
**Status:** spec ready for execution

---

## 0. Mission

Build our **own retail product taxonomy** for ~462,646 GTIN-level products in `product_esha_fixy.csv`. ESHA, FNDDS, and SR28 are nutrition references we map *to*, not the structural truth.

Outcome: every product gets a `retail_leaf` (our taxonomy) plus a vector of orthogonal attributes (form, cut, flavor, storage, prep state, diet, etc.). ESHA/FNDDS codes follow from the leaf, not the other way around.

---

## 1. Why current state fails

Three structural bugs in the existing pipeline:

1. **Hot-leaf magnets at the ESHA layer.** Substring-only identity rules like `plant_milk_identity:almond → ESHA 16455` swallow almond juice, almond protein powder, almond maple powder, dairy+almond blends. Same pattern at every category.
2. **Cluster builder skips orphans.** Every wrong assignment we've audited has `fixy_signal_type = no_fixy_overlap` or `fixy_overlap_no_cluster_flag` — clusters never re-challenge upstream identity errors.
3. **No multi-axis decomposition.** ESHA leaves are 1-D (a name). Real products live on at least 8 orthogonal axes. Missing axes = collapsed-dimension bugs (apple noodle kugel routed to "Apple, cinnamon, cooked").

`v6` corrected ~280K rows on FNDDS via fixy_done ground truth + title propagation, but `best_esha_code` is still poisoned and the cluster taxonomy doesn't have the leaves we need.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  product_esha_fixy.csv  (462,646 rows)                              │
│  + fixy_done/ ground truth (1.03M curated fdc_id→FNDDS rows)        │
│  + ingredients (per fdc_id from fixy_done)                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        │  STAGE 1 — Discovery pipelines              │
        │  (TF-IDF, ngrams, ingredient clusters,      │
        │  brand-locked proper nouns)                 │
        │  → axes/*.tsv  (vocabularies, learned)      │
        └──────────────────────┬──────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        │  STAGE 2 — Title parser                     │
        │  Decomposes title (+ingredients fallback)   │
        │  into 12-axis vector + TYPE classifier      │
        │  → parsed_titles.csv                        │
        └──────────────────────┬──────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        │  STAGE 3 — Retail tree + ESHA/FNDDS gate    │
        │  Builds our hierarchy from parsed axes,     │
        │  routes each product to a retail_leaf,      │
        │  gates ESHA codes by FORM/CATEGORY match    │
        │  → product_esha_fixy.v7.csv                 │
        └──────────────────────┬──────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        │  STAGE 4 — Composite dishes & combo packs   │
        │  Routes ~45K composite_dish to recipe       │
        │  pipeline, ~? combo_pack to per-component   │
        │  nutrition aggregation                      │
        │  → composite_dishes.csv, combo_packs.csv    │
        └─────────────────────────────────────────────┘
```

---

## 3. Inputs

| Source | Path | Use |
|---|---|---|
| Master product file | `implementation/output/product_esha_fixy.csv` | 462K rows, source of truth for SKUs |
| Ground-truth FNDDS labels | `fixy_done/<FNDDS>.csv` × 5,203 | 1.03M fdc_id→FNDDS curated rows (also include `description`, `ingredients`) |
| Cleaned ESHA canonical | `esha_cleaned_canonical.csv` | ~50K ESHA leaves with `Description`, `EshaCode`, `canonical_shopping_item` |
| Recipe pipeline (existing) | `implementation/output/hestia_recipes_calculator_native.csv` | 1.1GB recipe-level decompositions for composite dishes |
| Existing v6 outputs | `retail_mapper/product_esha_fixy.v6.csv` | FNDDS already corrected — start point for ESHA fix |

---

## 4. The taxonomy

### 4.1 The tree (hierarchical)

```
SUPERCATEGORY → CATEGORY_GROUP → CATEGORY → retail_leaf
                                                  ↑
                                           parameterized by axes 4–12
```

Examples:

```
Beverage › Fruit-based Drinks › Smoothie     › Acai-Blueberry-Watermelon w/ Chia Seeds
Beverage › Plant-based Milk   › Almond Milk  › Pumpkin Spice
Beverage › Plant-based Milk   › Almond Milk  › Plain Unsweetened
Beverage › Coffee Creamer     › Almond       › Vanilla
Snack    › Fruit & Nuts       › Apple Chips  › Cinnamon
Snack    › Fruit Sauces       › Applesauce   › Cinnamon Sweetened
Snack    › Combo Packs        › Dipper       › Apple Slices + Peanut Butter
Meal     › Composite Dishes   › Casserole    › Apple Noodle Kugel
Meal     › Composite Dishes   › Stew         › Beef Stew w/ Potatoes & Carrots
Dairy    › Yogurt             › Greek Yogurt › Strawberry
Pantry   › Spreads            › Nut Butter   › Almond, Smooth, Unsalted
```

### 4.2 The 12 axes

| # | Axis | Required for | Examples / Vocabulary source |
|---|---|---|---|
| 1 | **TYPE** | all | `single | combo_pack | composite_dish` (top-level fork) |
| 2 | **CATEGORY** | all | apple, almond, beef, milk, yogurt — discovered from head nouns + ingredient clusters |
| 3 | **FORM** | all | juice, butter, milk, candy, bar, kit, sauce, powder — `axes/form.tsv` |
| 4 | **CUT** | when applicable | whole, sliced, diced, shredded, ground, chunks — `axes/cut.tsv` |
| 5 | **PREPARATION_STATE** | when applicable | raw, par-cooked, fully-cooked, ready-to-eat — `axes/preparation_state.tsv` |
| 6 | **STORAGE** | all | fresh, frozen, refrigerated, canned, dried, shelf-stable, vacuum-sealed — `axes/storage.tsv` |
| 7 | **FLAVOR** | when applicable | vanilla, chocolate, BBQ, cinnamon — `axes/flavor_universal.tsv` + per-bucket TF-IDF |
| 8 | **FLAVOR_BLEND** | when applicable | `[acai, blueberry, watermelon]` — list, derived from multi-flavor titles |
| 9 | **INCLUSIONS** | when applicable | `[chia seeds, walnuts, chocolate chips, fruit pieces]` — mix-ins separate from flavor |
| 10 | **BRAND_FLAVOR** | rare | "Chunky Monkey", "Bunny Tracks" — `axes/brand_flavors.tsv` (data-mined) |
| 11 | **CLAIMS** (composite) | optional | sweetener, fat, sodium, diet, audience, macro — recorded as sub-vector |
| 12 | **PROVENANCE** | optional | Italian, USDA Commodity, imported, regional — surfacing for variety SKUs |

### 4.3 TYPE schemas

#### TYPE = single
```
{ TYPE: single,
  category: "almond",
  form: "milk",
  cut: null,
  prep_state: "ready-to-drink",
  storage: "shelf-stable",
  flavor: "vanilla",                    # null if plain
  flavor_blend: null,                   # only for multi-flavor
  inclusions: [],
  brand_flavor: null,
  claims: { sweetener: "unsweetened", diet: ["plant-based","dairy-free"] },
  provenance: null }
```

#### TYPE = combo_pack
```
{ TYPE: combo_pack,
  pack_format: "dipper",                # dipper | snack-pack | tray | lunchables | bundle
  components: [
    { role: "primary",   axes: { category: "apple", form: "raw", cut: "sliced", storage: "fresh" } },
    { role: "secondary", axes: { category: "peanut", form: "butter", storage: "shelf-stable" } } ],
  ratio: { primary: 0.7, secondary: 0.3 } }   # if known, otherwise null
```

#### TYPE = composite_dish
```
{ TYPE: composite_dish,
  dish_type: "kugel",                   # soup, stew, casserole, wrap, bowl, salad, sandwich, sub, kit, dinner, tray, meal
  primary: { category: "apple", form: "cooked" },
  secondaries: [ { category: "noodle", form: "egg-noodle" }, { category: "egg" } ],
  sauce_dressing: null,
  preparation: "frozen",
  audience: "adult" }
```

### 4.4 Beverage supercategory (per the acai-blueberry-watermelon question)

Drinks are a special case because they fan out into many subtypes that overlap:

```
Beverage
├── Plant-based Milk      (almond, oat, soy, coconut, cashew, pea, rice, hemp)
├── Dairy Milk            (cow, goat — whole/2%/skim/lactose-free)
├── Cream/Half&Half/Creamer
│   └── Coffee Creamer (dairy + non-dairy variants)
├── Fruit-based Drinks
│   ├── Juice (100%)
│   ├── Juice Drink (<100%, sweetened)
│   ├── Smoothie
│   ├── Fruit Beverage / Blend
│   └── Cocktail / Mocktail
├── Coffee
│   ├── Brewed (RTD, cold brew, hot)
│   ├── Concentrate
│   └── Latte / Cappuccino / Mocha (RTD)
├── Tea
│   ├── Brewed (RTD)
│   ├── Bottled sweetened
│   └── Bagged/Loose-leaf
├── Functional / Energy
│   ├── Energy Drink
│   ├── Sport Drink
│   ├── Hydration / Electrolyte
│   ├── Protein Shake
│   └── Nutritional Shake
├── Carbonated
│   ├── Soda
│   ├── Sparkling Water
│   └── Hard Seltzer (out of scope — alcohol)
├── Probiotic / Fermented
│   ├── Kombucha
│   ├── Kefir
│   └── Drinking Yogurt
├── Water
│   ├── Plain (still / sparkling / mineral)
│   └── Flavored / Vitamin / Alkaline
└── Powdered Drinks (separate top-level — needs reconstitution)
```

For "Acai Blueberry Watermelon Smoothie with Chia Seeds":
```
SUPERCATEGORY: Beverage
CATEGORY_GROUP: Fruit-based Drinks
CATEGORY: Smoothie
TYPE: single
FORM: ready-to-drink
STORAGE: refrigerated (most likely) — or frozen if from frozen bag
FLAVOR_BLEND: [acai, blueberry, watermelon]
INCLUSIONS: [chia seeds]
CLAIMS: { likely diet: [non-GMO, vegan], possibly sweetener: sweetened }
retail_leaf: Beverage › Fruit-based Drinks › Smoothie › Multi-berry-melon w/ chia
```

Decision: **smoothies with multiple flavors get one leaf per blend**, but the leaf name is composed mechanically from `sorted(FLAVOR_BLEND)` + INCLUSIONS — not hand-curated. Sibling smoothies with the same blend land on the same leaf.

---

## 5. Discovery pipelines

All output to `retail_mapper/axes/*.tsv` for human review before being used as gates.

### 5.1 Form / cut / storage / prep / dish / combo vocabularies (`axes/discover_axes.py`)

Hand-seeded starter sets, expanded by mining the corpus:

1. **Seed** each axis with ~30-100 known tokens (e.g. FORM = juice, butter, milk, sauce, ...).
2. **Frequency-mine** the title corpus for high-frequency unassigned tokens.
3. **For each unassigned token at TF ≥ 100**: print top 3 `branded_food_category` values it co-occurs with. Human reviewer (you) classifies into axis or rejects.
4. Iterate to ~95% coverage of top-1000 tokens.

Outputs:
- `axes/form.tsv` (column: token, score, sample_titles)
- `axes/cut.tsv`, `axes/storage.tsv`, `axes/preparation_state.tsv`, `axes/dish_type.tsv`, `axes/combo_format.tsv`

### 5.2 Universal flavor lexicon (`discovery/discover_flavor_universal.py`)

Tokens that show up as flavors **across many categories** (vanilla, chocolate, cinnamon, strawberry, BBQ, garlic, ranch). Detection:
- Token is not in any other axis vocabulary
- Appears as a modifier (not the head noun) in titles from ≥3 distinct CATEGORY_GROUPS

Output: `axes/flavor_universal.tsv`

### 5.3 Per-bucket flavor TF-IDF (`discovery/discover_flavor_per_bucket.py`)

For each `(CATEGORY × FORM)` bucket with N ≥ 30 products:
- Strip CATEGORY/FORM/CUT/STORAGE tokens from titles
- Run TF-IDF on remaining tokens (1-grams + 2-grams)
- Top-K per bucket = bucket-specific flavor lexicon (PSL almondmilk, bunny tracks ice cream, etc.)

Output: `axes/flavor_by_bucket.tsv` (columns: category, form, token, tf, df, idf, score)

### 5.4 Brand-proper-noun flavors (`discovery/discover_brand_flavors.py`)

For each candidate 1-2 gram in title (after stripping known axes):
- Compute brand_share = max(brand_count) / total_count
- Filter: total_count ≥ 5 AND brand_share ≥ 0.7
- Output: `axes/brand_flavors.tsv` (columns: brand_owner, n_gram, n, share, sample_titles)

Demonstrated working on ice-cream bucket:
- "creamy creations" → H-E-B (n=51, share=1.00)
- "bunny tracks" → Wells (n=27, share=1.00)
- "double rainbow", "kroger deluxe", "french pot" — Graeter's, etc.

### 5.5 Ingredient clusters (`discovery/discover_ingredient_clusters.py`)

The `ingredients` field in `fixy_done/*.csv` and the existing `top_ingredient_terms` column give us nutrition-relevant decomposition. Build:

1. For each FNDDS bucket, extract ingredient lists from all products in `fixy_done/<FNDDS>.csv`.
2. Tokenize ingredient strings (handle parens, ALL-CAPS), lowercase, normalize.
3. Compute ingredient-centroid per FNDDS = top-K ingredients by TF-IDF.
4. Cluster FNDDS codes whose centroids are similar (cosine sim ≥ 0.7) → emergent **ingredient clusters** that group nutritionally-equivalent leaves.

Use cases:
- Disambiguate ambiguous titles ("CHUNKY MONKEY" → ingredients: cream + sugar + banana + walnuts + chocolate → matches ice-cream-banana-walnut-chocolate ingredient profile).
- Validate ESHA assignments ("ALMOND MAPLE POWDER" ingredients: almond meal, maple sugar → matches almond-meal-flour cluster, NOT almond-milk cluster).
- Feed `axes/category.tsv` discovery (CATEGORY tokens are head nouns confirmed by ingredients).

Output: `axes/ingredient_clusters.csv`, `axes/ingredient_centroid_per_fndds.tsv`

### 5.6 Spelling-merger lexicon (`axes/spelling.tsv`)

Compound food words written one-word vs two-word:
```
almondmilk    → almond milk
oatmilk       → oat milk
soymilk       → soy milk
coconutmilk   → coconut milk
peanutbutter  → peanut butter
icecream      → ice cream
sourcream     → sour cream
breadcrumbs   → bread crumbs
```

Manually curated initially (~50 entries), expanded as we encounter new ones in unassigned-token reports.

---

## 6. Title parser (`parsers/title_parser.py`)

Input: `(product_description, brand_owner, brand_name, branded_food_category, ingredients?)`
Output: 12-axis vector + TYPE + confidence per axis.

### 6.1 Pipeline

```
1. Pre-clean
   - lowercase, strip duplicate-tail-after-comma ("FOO BAR, FOO" → "FOO BAR")
   - apply axes/spelling.tsv merges (almondmilk → almond milk)
   - trim brand_name from title head if title starts with brand_name

2. Tokenize
   - regex [a-z][a-z0-9]+
   - emit 1-grams and 2-grams

3. Classify TYPE
   - dish_type token present OR branded_food_category in dish-categories → composite_dish
   - combo_pack signals (`with` + 2 distinct CATEGORY heads, "lunchables", "tray" + 2 CATs, "&" + 2 CATs) → combo_pack
   - else → single

4. Tag tokens (in priority order; first axis wins per token)
   - axes/storage.tsv          → STORAGE
   - axes/preparation_state.tsv → PREPARATION_STATE
   - axes/cut.tsv              → CUT
   - axes/form.tsv             → FORM (for single)
   - axes/dish_type.tsv        → dish_type (for composite_dish)
   - axes/combo_format.tsv     → pack_format (for combo_pack)
   - axes/sweetener.tsv, fat.tsv, sodium.tsv, diet.tsv → CLAIMS
   - axes/audience.tsv         → AUDIENCE
   - axes/brand_flavors.tsv    → BRAND_FLAVOR
   - axes/flavor_by_bucket.tsv (gated by current CATEGORY×FORM) → FLAVOR
   - axes/flavor_universal.tsv → FLAVOR (fallback)
   - remaining noun tokens → CATEGORY candidates

5. Resolve CATEGORY
   - Pick highest-frequency unconsumed noun matching axes/category.tsv
   - If multiple distinct CATEGORY heads present + TYPE != single → split into components
   - If FLAVOR_BLEND axis triggered (≥2 fruit/flavor tokens with ", " or "&" separators) → record as list

6. Confidence
   - Per axis: how many corroborating signals (title tokens, brand_owner pattern, branded_food_category prior)
   - Low-confidence axes flagged for ingredient-fallback pass

7. Ingredient fallback (if confidence low for CATEGORY/FORM/FLAVOR)
   - Look up ingredients via fdc_id (from fixy_done/*.csv)
   - Re-run tagging on ingredient string; vote with title parse
   - If still conflicting → emit as `NEEDS_REVIEW`
```

### 6.2 TYPE classifier specifics

| TYPE | Trigger |
|---|---|
| **composite_dish** | dish_type token (kugel, casserole, lasagna, soup, stew, wrap, bowl, sandwich, sub, plate, dinner, kit) OR `branded_food_category` ∈ {Frozen Dinners & Entrees, Other Soups, Canned Soup, Chili & Stew, Casseroles, Deli Salads, Prepared Subs & Sandwiches, Frozen Breakfast Sandwiches, Entrees Sides & Small Meals} |
| **combo_pack** | `branded_food_category` = `Pre-Packaged Fruit & Vegetable` AND title has dipper/secondary noun OR title contains `lunchables\|snack pack\|dippables\|duo\|bento` OR title has `<CAT> with <CAT>` where CATs are distinct AND not in dish-type list OR title has `tray` AND ≥2 distinct CATEGORY heads |
| **single** | otherwise |

Combo signals tested against composite signals — composite wins ties (kugel beats "with").

---

## 7. Retail tree builder (`retail_tree.py`)

Once all products are parsed, build the hierarchical tree:

1. Group products by `(SUPERCATEGORY, CATEGORY_GROUP, CATEGORY)` triple.
2. Within each, group by `(FORM, FLAVOR | FLAVOR_BLEND | BRAND_FLAVOR)` to form retail leaves.
3. Leaf name auto-generated:
   ```
   <CATEGORY> <FORM> <flavor-or-blend>
   "Almond Milk Pumpkin Spice"
   "Almond Milk Plain Unsweetened"
   "Smoothie Acai-Blueberry-Watermelon w/ Chia Seeds"
   "Ice Cream Chunky Monkey"
   ```
4. Leaves with <3 products in low-traffic categories → merge into parent's "Other" leaf.
5. Output: `retail_mapper/retail_tree.json` — full hierarchy with product GTIN lists per leaf.

---

## 8. ESHA / FNDDS gate (`marry_v7.py`)

For each parsed product:

1. **Phase 0 — Invalidate**: scan current `best_esha_code`. Compute ESHA's (CATEGORY, FORM) signature from its description. If product's parsed FORM ≠ ESHA's FORM (e.g. juice vs milk, kit vs cooked, powder vs milk) → invalidate `best_esha_code`, write reason to `v7_esha_invalidated`.
2. **Phase 1 — Truth**: fdc_id ∈ fixy_done → adopt FNDDS truth (already in v6, carry forward).
3. **Phase 2 — Title propagation**: as in v6.
4. **Phase 3 — ESHA leaf-anchored re-emission**: for each invalidated row, find ESHA codes whose (CATEGORY, FORM) match the parsed product, then pick by FLAVOR-token overlap. If none match → mark `NEEDS_NEW_LEAF` and emit to candidate file.
5. **Phase 4 — TYPE-aware routing**:
   - `single`: standard ESHA → FNDDS mapping
   - `combo_pack`: per-component ESHA codes; aggregate nutrition is weighted blend; emit one row per pack with component_esha_codes column
   - `composite_dish`: route to `hestia_recipes_calculator_native` recipe pipeline; ESHA = recipe-level reference, not single leaf
6. **Phase 5 — Authority**: ESHA → FNDDS dominance (as in v6).
7. **Phase 6 — Residual**: anything still unmapped → `unmapped.csv`.

### 8.1 FORM dictionary for ESHA gate

Each ESHA code's description is parsed once into a `(category, form)` signature:
```
"Almond Milk, Almond Breeze, original, unsweetened" → (almond, milk)
"Apple, cinnamon, cooked"                            → (apple, cooked)
"Apple, dried"                                       → (apple, dried)
"Apple, fresh, small 2 3/4 inch"                     → (apple, fresh/raw)
"Bar, energy, dark chocolate almond"                 → (energy-bar, bar)
```

Stored as `axes/esha_signatures.tsv` — 50K rows, computed once.

---

## 9. Outputs

| File | Description |
|---|---|
| `axes/spelling.tsv` | one-word→two-word merges |
| `axes/form.tsv`, `cut.tsv`, `storage.tsv`, `preparation_state.tsv`, `dish_type.tsv`, `combo_format.tsv` | hand-seeded + data-mined axis vocabularies |
| `axes/sweetener.tsv`, `fat.tsv`, `sodium.tsv`, `diet.tsv`, `audience.tsv` | claims axes |
| `axes/category.tsv` | canonical CATEGORY heads |
| `axes/flavor_universal.tsv` | cross-category flavor tokens |
| `axes/flavor_by_bucket.tsv` | per-(CATEGORY×FORM) TF-IDF flavor lexicon |
| `axes/brand_flavors.tsv` | brand-locked proper noun flavors (Chunky Monkey, etc.) |
| `axes/ingredient_clusters.csv` | nutrition-equivalent ingredient cluster groupings |
| `axes/ingredient_centroid_per_fndds.tsv` | TF-IDF ingredient profile per FNDDS |
| `axes/esha_signatures.tsv` | parsed (category, form) signature per ESHA code |
| `parsed_titles.csv` | full 12-axis vector per product |
| `retail_tree.json` | hierarchical retail taxonomy with product lists |
| `product_esha_fixy.v7.csv` | corrected mapping with retail_leaf column |
| `composite_dishes.csv` | composite-dish components linked to recipe pipeline |
| `combo_packs.csv` | combo-pack components with per-component ESHA |
| `unmapped.csv` | residuals for review |
| `needs_new_leaf.csv` | products that don't fit any existing ESHA leaf |

---

## 10. Phasing (order of execution)

Each phase emits reviewable outputs before the next phase commits to using them.

| Phase | Steps | Output | Wall time |
|---|---|---|---|
| **P1** | Run TF-IDF + bucket analysis on full corpus, emit unassigned-token report | `discovery/unassigned_tokens.csv` | ~5 min |
| **P2** | Hand-seed `axes/form.tsv`, `cut.tsv`, `storage.tsv`, `preparation_state.tsv`, `spelling.tsv` from data | seed files | 1-2 hr human review |
| **P3** | Run flavor discovery (universal + per-bucket + brand-locked) | `axes/flavor_*.tsv`, `axes/brand_flavors.tsv` | ~10 min |
| **P4** | Run ingredient cluster discovery from `fixy_done/` ingredient strings | `axes/ingredient_clusters.csv` | ~15 min |
| **P5** | Build category/super-category tree (hand-seeded SUPERCATEGORY + auto-fill) | `axes/category.tsv`, `axes/supercategory.tsv` | ~1 hr human review |
| **P6** | Implement title parser (`parsers/title_parser.py`) | parser unit tests pass on 100 hand-labeled examples | ~3 hr |
| **P7** | Run parser on full corpus | `parsed_titles.csv` (462K rows) | ~5 min |
| **P8** | Build retail tree from parsed output | `retail_tree.json` | ~5 min |
| **P9** | Compute ESHA signatures (`axes/esha_signatures.tsv`) | one-time | ~2 min |
| **P10** | Run `marry_v7.py` with FORM gate + TYPE-aware routing | `product_esha_fixy.v7.csv` + companion files | ~1 min |
| **P11** | Validation pass: regression-test against the bug examples (apple noodle kugel, almond juice, fried apples, pumpkin spice almond milk, chunky monkey, hummus + crackers) | `validation_report.md` | ~30 min |
| **P12** | Composite-dish recipe bridging via existing hestia pipeline | `composite_dishes.csv` linked to recipes | ~30 min |

Human review gates at: end of P1 (axis seeds), end of P5 (category tree), end of P11 (validation). No advancing past a gate without sign-off.

---

## 11. Validation regression set

After P10, every one of these example products must end up in the right retail leaf:

| Product | Expected retail_leaf | Expected ESHA gate behavior |
|---|---|---|
| HINT OF PUMPKIN SPICE ALMONDMILK | Beverage › Plant-based Milk › Almond Milk › Pumpkin Spice | ESHA = closest almond milk leaf (16454/16455 OK), FNDDS = 11350000 |
| LEMON GINGER COLD-PRESSED ALMOND JUICE | Beverage › Fruit-based Drinks › Juice › Almond | ESHA "Almond Milk, plain" REJECTED (form mismatch); routed to almond juice or vegetable-juice ESHA |
| ALMOND PROTEIN POWDER, UNFLAVORED | Pantry › Protein Powders › Almond Protein | ESHA "Almond Milk" REJECTED; mapped to almond meal or protein powder ESHA |
| APPLE NOODLE KUGEL | Meal › Composite Dishes › Casserole › Kugel | TYPE=composite_dish; routed to recipe pipeline; ESHA "Apple, cinnamon, cooked" REJECTED |
| FRIED APPLES | Snack › Fruit Sauces › Fried Apples (or new leaf) | ESHA "Apple, dried" REJECTED (form: fried ≠ dried); mapped to closest cooked-apple ESHA |
| CHUNKY MONKEY ICE CREAM | Frozen Dessert › Ice Cream › Chunky Monkey | BRAND_FLAVOR axis; ESHA = closest match by ingredients |
| APPLE SLICES WITH PEANUT BUTTER | Snack › Combo Packs › Dipper › Apple + Peanut Butter | TYPE=combo_pack; per-component ESHA codes |
| HUMMUS WITH PITA CHIPS | Snack › Combo Packs › Dipper › Hummus + Pita | TYPE=combo_pack |
| ACAI BLUEBERRY WATERMELON SMOOTHIE WITH CHIA SEEDS | Beverage › Fruit-based Drinks › Smoothie › Multi-berry-melon w/ chia | FLAVOR_BLEND=[acai,blueberry,watermelon]; INCLUSIONS=[chia seeds] |
| FULLY COOKED BACON | Meat › Bacon › Fully Cooked | PREPARATION_STATE=fully-cooked; ESHA gate uses prep state |
| ORIGINAL DAIRY + ALMOND BLEND MILK | Beverage › Dairy Milk › Blended Milks › Dairy+Almond | NOT routed to almond milk; new sub-leaf for blends |

---

## 12. What ESHA leaves we accept losing

Some retail leaves won't have a clean ESHA twin. Three policies:

1. **Closest sibling** (default) — pick the ESHA whose (CATEGORY, FORM) matches and whose other axes are nearest. Record `esha_match_quality` ∈ {exact, sibling, distant}.
2. **NEEDS_NEW_LEAF** — emit to a candidate file. If volume justifies, propose to upstream maintainer (or build our own custom-leaf table).
3. **Compositional** — for combo_packs and composite_dishes, no single ESHA. Compute weighted nutrition from components.

We do **not** force every retail leaf into an existing ESHA code. Ingredients always provide a nutrition floor.

---

## 13. Risks & open questions

| Risk | Mitigation |
|---|---|
| Axis vocabulary explosion — handcrafting takes too long | Auto-seed from data + frequency thresholds + iterate weekly |
| TF-IDF surfaces noise in low-volume buckets | Min N=30 per bucket; below that, fall back to universal flavor lexicon |
| Brand flavors collide with real flavors ("vanilla" appears for many brands) | brand_share threshold ≥0.7 + min_total ≥5; vanilla ends up in universal lexicon |
| Composite-dish detection false-positives ("apple with cinnamon" is a single, not composite) | "with" alone insufficient; require dish_type token OR composite category |
| Ingredient parsing is messy (parenthetical sub-ingredients) | Use existing top_ingredient_terms column where possible; light regex for fixy_done strings |
| Existing pipeline (`_runner.py`) overwriting our outputs | All retail_mapper writes stay in `retail_mapper/` directory — never write to `implementation/output/` |

---

## 14. What's deferred

- **Nutrition computation** for combo_pack and composite_dish — leaves the door open for the existing hestia recipe pipeline, doesn't reimplement.
- **Embedding-based retail-leaf clustering** — possible v2 if hand-axes hit accuracy ceiling.
- **Multi-language titles** — corpus is English-only currently, no plan to expand.

---

## 15. First execution step

After plan approval: run **P1** — generate `discovery/unassigned_tokens.csv` showing every high-frequency token NOT covered by my proposed seeds, ranked by impact, with sample titles. That's the input to the human axis-seeding pass (P2).

This is the keystone. Everything else flows from human-verified axis vocabularies.
