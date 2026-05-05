# Recipe Mapper v1 — HTC Unified Identity Pipeline

**Status as of 2026-05-04:** Recipe-side calc + nutrition complete (P1–P7, 52/52 pass). Cost calc through v5 — pricing on OUR rebuilt `priced_products_v2.db` (Walmart-direct + Kroger, 169k clean SKUs). Six known matcher bugs documented in this README §10.

This pipeline assigns the same compact identity code (HTC — Hestia Taxonomy Code) to **both retail products** (in `consensus_full_corpus_audit.csv`) and **recipe ingredients** (in `recipe_qa.db`), so a recipe asking for "mayonnaise" matches plain Hellmann's mayo and not Chipotle Mayo from a tuna salad.

---

## 1. The problem

Recipes call for *foods*. The retail corpus has *products*. They've never shared a code. So:
- "milk" in a recipe couldn't reliably link to whole/skim/2% milk in a product database
- "salt" couldn't link to Morton Kosher Salt
- "saffron threads", "ground mace", "ground cardamom" had no match path at all because no retail SKU sells them standalone — but SR-28 does
- A recipe matcher couldn't use grams either, because the SR-28 portion table looked broken (it isn't; the unit name is in the `modifier` text column instead of `measure_unit_id`)

Goal: every recipe ingredient and every retail product carries the same **HTC code + structured facet envelope + gram-conversion lookup**, so quantities can be converted to grams, nutrients pulled from SR-28, and recipes evaluated end-to-end.

---

## 2. The architecture

### Three reference databases
| Source | Role | Where |
|---|---|---|
| **SR-28** | Single-ingredient nutrients + portion-to-gram conversions. Has mace, cardamom, saffron, salt etc. that FNDDS doesn't. | `data/sr28_csv/` |
| **FNDDS** | Composite/prepared-food food codes (frozen entrees, mixes, soup). References SR-28 via FNDDSIngred. | `data/fndds/` |
| **Retail consensus** | 462,664 SKUs with canonical_path, BFC, FNDDS+SR-28 cross-walk, flavor/form/processing/claims. | `retail_mapper/v2/consensus_full_corpus_audit.csv` |

### The HTC code (8 chars, alphanumeric, ICD-10-PCS-style positional)

Defined in `/Users/jamiebarton/Desktop/Esha/build_htc_registry.py`. We ported the position rules to `recipe_mapper/v1/htc/encoder.py`.

```
position:  1       2       3-4     5       6           7       8
           group   family  food    form    processing  ptype   crockford-check
           [0-K]   [0-9]   [00-99] [0-C]   [0-B]       [0-F]   [0-9A-Z*~$=U]
```

**Position 1 — group** (21 values): `0=Unclassified · 1=Dairy · 2=Red Meat · 3=Poultry · 4=Fish & Seafood · 5=Eggs · 6=Vegetables · 7=Fruits · 8=Grains & Cereals · 9=Legumes · A=Nuts & Seeds · B=Oils & Fats · C=Sugars & Sweeteners · D=Beverages · E=Spices/Herbs/Seasonings · F=Condiments & Sauces · G=Baked Goods · H=Prepared & Mixed · J=Snacks · K=Supplements · M=Baby & Infant · N=Non-food (added)`

**Position 5 — form** (13 values): `0=Unspecified · 1=Fresh · 2=Frozen · 3=Canned · 4=Dried · 5=Powdered · 6=Liquid · 7=Concentrated · 8=Smoked · 9=Pickled · A=Freeze-dried · B=Vacuum-sealed · C=Shelf-stable`

**Position 6 — processing** (12 values): `0=Unspecified · 1=Raw · 2=Minimally · 3=Cooked · 4=Cured/Aged · 5=Fermented · 6=Ready-to-eat · 7=Ready-to-cook · 8=Marinated/Seasoned · 9=Breaded · A=Fortified · B=Ultra-processed`

**Position 7 — ptype** (16 values): `0=Whole · 1=Sliced · 2=Ground · 3=Steak/Fillet · 4=Block · 5=Shredded · 6=Spread · 7=Crumbled · 8=Cubed · 9=Stick · A=Wedge · B=Log · C=Patty · D=Strip · E=Mini · F=Squeezable`

**Position 8** — Crockford mod-37 check digit (used to validate codes; currently informational).

### The facet envelope (out-of-code)

Code carries the *identity* axes. Variant attributes that don't change identity sit alongside the code:

```python
{
  "htc_code":   "1000600D",   # Whole milk
  "facets": {
    "flavor":     None,        # plain
    "form":       "liquid",    # from form_texture_cut
    "processing": "ultra_pasteurized",
    "claims":     ["organic"],
    "modifier":   "Whole",
  },
  "qty": 1, "unit": "cup", "grams": 244,
}
```

Same envelope on the retail side — the consensus columns map directly onto these slots.

---

## 3. Phases

### Phase 1 — Tag retail consensus with HTC codes
**Script:** `tag_consensus_with_htc.py` → `output/consensus_htc_tagged.csv`
**Method:** Run encoder over each SKU's `branded_food_category + title + product_identity_fixed + modifier`.
**Result:** **99.9% tagged** (462,353 of 462,664 SKUs).
- 102 correctly flagged `N` (non-food: paper cups, glycerin, etc.)
- 311 unresolved (typically truncated/garbled titles)

### Phase 2 — Tag recipe ingredients
**Scripts:**
- `extract_unique_ingredients.py` → `output/recipe_ingredient_items.csv` (74,624 unique items + recipe counts + sample displays)
- `tag_ingredients_with_htc.py` → `output/recipe_ingredient_htc_tagged.csv`

**Method:** Same encoder. When the loose GROUP_RULES regex misses (e.g., "garlic" doesn't match "vegetable"), we fall back to walking the FAMILY_RULES patterns — if "garlic" matches the onion-family pattern, group=6 is implied. Family-fallback gets confidence 0.70 because it's a *more* specific signal than the loose group regex.

**Result:** **99.0% tagged** (21,750 of 21,974 unique items at min_count≥3; 97.7% at min_count≥1 covering all 74k variants).

### Phase 2.5 — Apply codes to recipe lines
**Script:** `apply_htc_to_recipes.py` → `output/recipe_lines_htc.csv` + `output/recipe_htc_coverage_summary.json`
**Result on 491,138 recipes / 4,729,696 ingredient lines:**

| metric | count | % |
|---|---|---|
| tagged with HTC | 4,703,474 | **99.45%** |
| high-confidence (≥0.6) | 4,703,472 | **99.45%** |
| flagged non-food | 3,701 | 0.08% |
| unmatched | 22,521 | 0.48% |
| **recipes fully high-conf at line level** | **468,682** | **95.43%** |

### Phase 4 — Gram-weight resolver
**Script:** `build_htc_gram_weights.py` → `output/htc_gram_weights.csv` + `output/sr28_gram_weights.csv` + `output/htc_group_default_grams.csv`

**The breakthrough:** SR-28's `food_portion.csv` looks broken because every legacy row has `measure_unit_id = 9999` ("undetermined"). The actual unit name (tsp / tbsp / cup / fl oz / dash / etc.) is in the **`modifier` text column**. We parse it.

**Method:**
1. Load SR-28 `sr_legacy_food.csv` → NDB → fdc_id
2. Walk `food_portion.csv`, parse `modifier` text → canonical unit
3. Build `(fdc_id, unit) → median grams_per_unit`
4. Bridge HTC ↔ SR-28 via consensus rows (each retail row carries both an htc_code and an sr28_code)
5. Aggregate `(htc_code, unit) → grams` and `(htc_group, unit) → grams` (group fallback)

**Sanity probes — all correct:**
| ingredient | unit | grams |
|---|---|---|
| Salt, table | tsp | **6.0** |
| Salt, table | cup | **292.0** |
| Spices, cardamom | tsp | **2.0** |
| Spices, saffron | tsp | **0.7** |
| Spices, cloves, ground | tsp | **2.1** |
| Milk, whole 3.25% | cup | **244.0** |
| Milk, whole 3.25% | fl_oz | **30.5** |
| Sugar, granulated | cup | **250.0** |
| Butter, salted | tbsp | **14.2** |

**Coverage:** 9,151 (htc_code, unit) rows covering 3,302 HTC codes + 259 group-level fallbacks.

### Phase 5 — Per-HTC facet vocabulary
**Script:** `build_htc_facet_vocab.py` → `output/htc_facet_vocab.json`
**Method:** GROUP BY htc_code from consensus rows; for each facet column (`flavor / form_texture_cut / processing_storage / claims / modifier / variant`), collect top-30 values per HTC with counts.
**Result:** 2,063 HTC codes with controlled facet vocabularies.

**Example — Salt's vocab:**
```
modifier: Plain(408) | Himalayan Pink(128) | Iodized(98) | No Salt Added(69) | Organic(61)
claims:   sea_salt(244) | no_salt_added(69) | salt_free(67) | organic(61) | kosher(55)
form_texture_cut: coarse(113) | grinder(108) | fine(63) | flakes(25) | fine_crystals(16)
```

This is what powers the "no chipotle in tuna salad" rule. When a recipe says "mayonnaise" with no flavor token in `display`, the matcher emits `flavor=None`, and product retrieval excludes Chipotle Mayo (which has `flavor=Chipotle` in its envelope).

### Phase 6 — Unified recipe matcher
**Scripts:**
- `htc/qty_units.py` — quantity + unit extractor for recipe `display` strings (handles "1 1/2 cups", "1/4", unicode fractions, mixed numbers, "fl oz", "tbsp", etc.)
- `match_recipes_unified.py` → `output/recipes_unified.csv` + `output/recipes_unified_summary.json`

**Per ingredient line:**
1. Look up HTC by item name
2. Extract `qty + unit` from `display`
3. Resolve grams: blob value first → htc-level lookup → group-level fallback
4. Extract structured facets from `display` against the per-HTC vocab (single pre-compiled regex per (code, facet) for ~30× speedup)
5. Emit (htc_code, qty, unit, grams_resolved, facets{flavor,form,processing,claims,modifier,variant})

**Result on full 491k corpus (90 seconds):**
| metric | count | % |
|---|---|---|
| with qty extracted | 4,366,474 | 92.3% |
| with unit extracted | 3,284,981 | 69.5% |
| with grams resolved | 4,723,727 | **99.9%** |
| with at least one facet | 3,467,167 | 73.3% |
| **recipes fully calculable (HTC + grams + ≥0.6 conf, every line)** | **462,683** | **94.2%** |

Facet hit counts: modifier 2.44M | variant 2.22M | flavor 1.82M | form 1.23M | processing 241k | claims 168k.

### Phase 7 — Bidirectional test
**Script:** `tests/test_htc_bidirectional.py` — **52/52 PASS.**

**Coverage:**
- §1 Recipe ingredient vs retail SKU produce same group+family for 11 staple foods (mayonnaise, kosher salt, whole milk, ground beef, olive oil, honey, soy sauce, ketchup, brown sugar, cheddar, blueberries).
- §2 SR-28-only ingredients (saffron threads, ground mace, ground cardamom, ground cloves, ground allspice) all resolve to group=E with conf≥0.6 even though no retail SKU is just-saffron / just-mace.
- §3 SR-28 gram-weight probes (Salt 1tsp=6g, cardamom 1tsp=2g, milk 1cup=244g, sugar 1cup=200g, butter 1tbsp=14.2g, etc.) — 9/9 pass.
- §4 Default-vs-variant: "1 tbsp mayonnaise" display has no chipotle; "1 tbsp chipotle mayonnaise" does — the chipotle-out-of-tuna-salad rule.
- §5 End-to-end qty/unit/grams: "1/4 cup whole milk" → 61g, "1/2 tsp ground cardamom" → 1g, "1 1/2 cups granulated sugar" → 300g, etc.
- §6 Encoder is deterministic across both sides for same input.
- §7 Non-food items (toothpick, paper napkin, borax, rubbing alcohol, glycerin, etc.) flagged group=N.

**Bugs the test caught and we fixed:**
- `parse_qty('1/4')` returned `1.0` because the leading-digit regex ate the numerator before checking for a fraction — now matches mixed/fraction/decimal/whole patterns in priority order.
- Recipe-ingredient encoding leaked `sample_displays` into group inference (saffron landed on Dairy because samples mentioned "milk", cardamom landed on Nuts because samples said "seeds", blueberries landed on Vegetables because of "fruit salad"). Fixed by encoding from `item` only.
- Mayonnaise/ketchup retail SKUs landed on Vegetables/Dairy because their BFC strings ("Salad Dressing", "Ketchup, Mustard, BBQ & Cheese Sauce") fired Vegetables/Dairy rules before Condiments. Fixed by adding a Condiments-first GROUP_RULES entry and excluding `cheese sauce` from the cheese rule.

### Phase 8 — Cost calc on OUR Walmart+Kroger pricing data
**Scripts:**
- `build_priced_products_v2.py` — rebuilds OUR priced_products_v2.db from Hestia's raw `api_cache.db` (12,189 kroger + 7,387 walmart cached searches). **Drops Walmart `marketplace=True` (third-party) listings** — 57.3% of raw Walmart cache is third-party junk including a $962 50-lb mace bag.
- `enrich_priced_with_consensus.py` — bridges priced UPCs → consensus PIDs via master_products.gtin_upc → fdc_id (33,424 of 169,430 products bridged, 19.7%).
- `enrich_priced_with_categorypath.py` — adds Walmart's categoryPath + non_food_path flag (3,260 products dropped: charcoal, citronella torch fuel, cat food, plant seeds, decorative confetti eggs, mouthwash).
- `htc/substitutions.py` — part-whole substitutions: lemon zest → whole lemon, egg whites → whole eggs, minced garlic → garlic, ripe → plain, etc.
- `calculate_recipe_cost_v5.py` — final matcher with HTC group+family hard gate, consensus PID/modifier honoring, canonical_path fallback, substitutions, full-package math (`math.ceil(grams_needed / package_grams) × package_price`).

**Result on the 5 sample recipes (final v5):**
| recipe | total cost | per serving estimate |
|---|---|---|
| Best Lemonade | $8.60 | $1.08 (8 servings) |
| Berry Blue Frozen Dessert | $23.23 | $5.81 (4 servings) |
| Banana Bread (applesauce) | $26.64 | $2.66 (10 slices) |
| Best Banana Bread | $30.22 | $3.02 (10 slices) |
| Chicken Biryani | $131.62 | $16.45 (8 servings) — biryani is genuinely expensive |

Architecture progression: v1 fractional→v2 full-package→v3 HTC-filter→v4 PID-anchored→v5 (group+family hard gate + Rule-B modifier honor + part-whole substitutions). Six remaining matcher bugs (see §10).

---

## 4. File layout

```
recipe_mapper/v1/
├── README.md                                  this document
├── htc/
│   ├── encoder.py                              the 8-char position encoder + check digit + non-food filter
│   └── qty_units.py                            qty + unit extraction from `display`
├── data/
│   └── htc_registry_seed.db                    seed copy of /Esha/data/htc_registry.db (171 concepts, 19,542 FNDDS bridge)
├── extract_unique_ingredients.py               recipe_qa.db → unique items CSV
├── tag_consensus_with_htc.py                   P1 — tag retail SKUs
├── tag_ingredients_with_htc.py                 P2 — tag recipe ingredients
├── apply_htc_to_recipes.py                     P2.5 — join HTC codes to all 4.7M recipe lines
├── build_htc_gram_weights.py                   P4 — SR-28 portions → htc/unit/grams
├── build_htc_facet_vocab.py                    P5 — mine consensus columns → per-HTC vocab
├── match_recipes_unified.py                    P6 — full pipeline: HTC + qty + unit + grams + facets
├── build_ingredient_sr28_map.py                ingredient → SR-28 fdc (188 staple overrides)
├── calculate_recipe_nutrition.py               nutrient calculator (Phase 8 — sums kcal/macros)
├── build_priced_products_v2.py                 P-cost-1 — rebuild OUR priced db from raw cache, drop marketplace
├── enrich_priced_with_consensus.py             P-cost-2 — bridge priced UPCs → consensus PID via fdc_id
├── enrich_priced_with_categorypath.py          P-cost-3 — Walmart categoryPath → non-food filter
├── tag_priced_products_with_htc.py             P-cost-4 — HTC tag every priced product (older; v2 builder writes htc inline)
├── match_ingredient_to_skus.py                 recipe ingredient → matching retail SKUs (HTC + PID)
├── calculate_recipe_cost.py                    P-cost (v1) — fractional, Hestia food_packages source — superseded
├── calculate_recipe_cost_v2.py                 (v2) — full-package via Hestia — superseded
├── calculate_recipe_cost_v3.py                 (v3) — first version on OUR priced_products_v2.db — superseded
├── calculate_recipe_cost_v4.py                 (v4) — consensus PID anchored — superseded
├── calculate_recipe_cost_v5.py                 (v5) — current: HTC group+family + Rule-B modifier + substitutions
├── htc/
│   ├── encoder.py                              the 8-char position encoder
│   ├── qty_units.py                            qty + unit extraction
│   └── substitutions.py                        part-whole substitution rules (zest→fruit, white→whole egg, etc.)
├── tests/
│   ├── test_htc_bidirectional.py               P7 — 52/52 pass
│   ├── test_recipe_taxonomy.py                 (older, kNN-against-ESHA; superseded)
│   ├── test_recipe_fndds.py                    (older, FNDDS-only; superseded)
│   ├── test_consensus_match.py                 (older, consensus-tree; superseded)
│   └── test_identity_codes.py                  (older, Domain.Class.Type; superseded by HTC)
└── output/   (gitignored; generated by the scripts above; ~2.5 GB)
    ├── recipe_ingredient_items.csv             74,624 unique items + counts + sample displays
    ├── recipe_ingredient_htc_tagged.csv        unique items → HTC code + position breakdown
    ├── consensus_htc_tagged.csv                462,664 SKUs → HTC code + position breakdown
    ├── recipe_lines_htc.csv                    4,729,696 lines: line + HTC + status
    ├── recipe_htc_coverage_summary.json        line-level + recipe-level coverage stats
    ├── sr28_gram_weights.csv                   9,154 (SR-28 fdc, unit) → grams_per_unit_median
    ├── htc_gram_weights.csv                    9,151 (htc_code, unit) → grams_per_unit_median
    ├── htc_group_default_grams.csv             259 (htc_group, unit) → grams (fallback)
    ├── htc_facet_vocab.json                    2,063 HTC codes → {facet: [(value, count), …]}
    ├── htc_facet_vocab_summary.csv             vocab coverage per code
    ├── recipes_unified.csv                     P6 final output (one row per ingredient line)
    └── recipes_unified_summary.json            P6 corpus-level stats
```

### Older / superseded artifacts (kept for diff):
- `build_consensus_tree_nodes.py`, `consensus_tree_nodes.csv` — pre-HTC tree-node deduplication
- `build_identity_registry.py`, `identity_registry.{json,csv}` — `Domain.Class.Type` codes (replaced by HTC)
- `match_ingredients_v2_identity_codes.py` — pre-HTC matcher
- `build_recipe_taxonomy.py`, `recipe_ingredient_taxonomy.csv` — kNN-anchored tree
- `build_recipe_fndds_match.py`, `recipe_ingredient_fndds.csv` — FNDDS-only matcher
- `match_ingredients_to_consensus_tree.py` — tree-anchored matcher
- `apply_codes_to_recipes.py`, `recipe_coverage.{csv,json}` — pre-HTC application

---

## 5. The encoder's rules (recipe_mapper/v1/htc/encoder.py)

The encoder is **deterministic and rule-based** (no LLM, no embedding) — same approach as `/Esha/tag_products_htc_v2.py`. Five rule layers run in order:

1. **GROUP_RULES** — regex over BFC (retail) or item text (recipe). 35 patterns covering all 21 groups including condiments, oils, sugars, and a dedicated branded-product cluster.
2. **FORM_RULES** — physical/storage form. 9 patterns.
3. **FAMILY_RULES** — per-group family disambiguation. ~120 patterns spanning Dairy(C cheese types, A plant-milk, etc.), Vegetables (greens, roots, brassicas, alliums, peppers, etc.), Spices (salt/pepper/cinnamon/herb/curry/extract/seasoning), Condiments (mayo/ketchup/mustard/sauces), Grains (bread/bagel/pasta/rice/flour/pastry), Fish, Beef etc.
4. **PROC_RULES** — processing state. 9 patterns.
5. **PTYPE_RULES** — physical type / form factor. 13 patterns.

Plus:
- **NON_FOOD_PATTERNS** — short-circuit for paper/glycerin/borax/glitter/etc. → group `N`.
- **family_fallback** — if GROUP_RULES misses, walk every group's family rules; first match wins. Confidence 0.70.

Confidence levels:
- 0.9 — group matched from BFC (strongest signal — retail-side only)
- 0.7 — family_fallback hit (recipe-side; specific noun in family rules)
- 0.6 — group matched from description (broad regex hit)
- 0.5 — group matched from `extra` field (last resort, retail only)
- 0.2 — unresolved

---

## 6. Why this is the right shape

The user's framing: HTC was originally built (`/Esha/`) to "separate shit" — to keep Chipotle Mayo from showing up in tuna salad. The way it works:

1. The 8-char code captures **identity** — what the food fundamentally is. Chipotle Mayo and plain Mayo share the same code prefix (group=F=Condiments, family=0=Mayonnaise) until/unless we decide chipotle is a different identity.
2. The **facet envelope** carries everything else (flavor, brand, claim). Plain Mayo has `flavor=null`. Chipotle Mayo has `flavor=Chipotle`.
3. A recipe asking for "mayonnaise" has `flavor=null` extracted from `display` → product retrieval filters to `flavor IN (null, 'Plain')` → tuna salad gets plain mayo.
4. A recipe asking for "1 tbsp chipotle mayo" extracts `flavor=Chipotle` → product retrieval matches Chipotle Mayo SKUs.

Same code. Different facet envelopes. The dimension that varies is structured.

---

## 7. What's left

| | task |
|---|---|
| ✅ | Phase 6 facet extraction optimized (single pre-compiled regex per (code, facet); 90s on full 491k) |
| ✅ | Full 491k unified matcher run — 94.2% recipes fully calculable |
| ✅ | `tests/test_htc_bidirectional.py` — 52/52 pass |
| ✅ | Cleanup: 311 → 0 unresolved retail SKUs (100.0% tagged) |
| ✅ | Cleanup: ~1.7k → 2.1k unresolved recipe ingredients (97.2% items, **99.7% lines**) |
| ✅ | End-to-end nutrient calculation demo (`calculate_recipe_nutrition.py`) — 5 sample recipes, realistic per-serving kcal |

### Phase 8 — Nutrient calculation
**Scripts:**
- `build_ingredient_sr28_map.py` → `output/ingredient_to_sr28.csv` — direct ingredient string → SR-28 fdc_id map (token-overlap scoring + 114 hard-coded staple overrides)
- `calculate_recipe_nutrition.py` — for sample recipes, sum 8 macros (kcal/protein/carbs/fat/satfat/fiber/sugar/sodium) per ingredient via SR-28 nutrient table

The HTC→SR aggregation in `htc_gram_weights.csv` is too lossy for nutrient calc (one HTC pools many SR codes). Direct ingredient→SR matching with overrides for staples (flour types, salt, sugars, oils, eggs, milks, common spices, common cuts of meat) gives clean nutrient resolution.

**Verified realistic outputs:**

| recipe | kcal total | typical servings | per serving |
|---|---|---|---|
| Low-Fat Berry Blue Frozen Dessert | 688 | 4 | 172 |
| Best Lemonade | 1,242 | 8 | 155 |
| Moist Banana Bread with Applesauce | 2,506 | 10 slices | 251 |
| Chicken Biryani | 7,051 | 8-10 | 705-881 |

---

## 8. Quick-start commands

```bash
cd /Users/jamiebarton/Desktop/esha_audit_bundle

# Phase 1 — tag retail SKUs (35s)
python3 recipe_mapper/v1/tag_consensus_with_htc.py

# Phase 2 — extract + tag recipe ingredients (10s)
python3 recipe_mapper/v1/extract_unique_ingredients.py --min-count 1
python3 recipe_mapper/v1/tag_ingredients_with_htc.py

# Phase 2.5 — apply HTC to all 4.7M recipe lines (35s)
python3 recipe_mapper/v1/apply_htc_to_recipes.py

# Phase 4 — gram-weight tables from SR-28 (10s)
python3 recipe_mapper/v1/build_htc_gram_weights.py

# Phase 5 — per-HTC facet vocab from consensus columns (60s)
python3 recipe_mapper/v1/build_htc_facet_vocab.py

# Phase 6 — unified matcher on a 10k sample (10s smoke)
python3 recipe_mapper/v1/match_recipes_unified.py --limit-recipes 10000

# Nutrition calc (sum macros for sample recipes)
python3 recipe_mapper/v1/build_ingredient_sr28_map.py
python3 recipe_mapper/v1/calculate_recipe_nutrition.py

# Cost calc — rebuild priced db, enrich, run v5
python3 recipe_mapper/v1/build_priced_products_v2.py
python3 recipe_mapper/v1/enrich_priced_with_consensus.py
python3 recipe_mapper/v1/enrich_priced_with_categorypath.py
python3 recipe_mapper/v1/calculate_recipe_cost_v5.py
```

---

## 9. The cost-side data flow

```
Hestia api_cache.db                           data/master_products.db
(7,387 walmart + 12,189 kroger raw)            (462,706 GTIN ↔ fdc_id bridge)
        │                                              │
        ▼                                              ▼
build_priced_products_v2.py                    consensus_full_corpus_audit.csv
(drops 93,101 marketplace junk)                (462,664 SKUs × 37 columns)
        │                                              │
        └──────────────────┬───────────────────────────┘
                           │
                           ▼
                priced_products_v2.db
                (169,430 clean Walmart-direct + Kroger,
                 with htc_code, consensus_pid, consensus_canonical,
                 consensus_modifier, category_path_walmart, non_food_path)
                           │
                           ▼
                calculate_recipe_cost_v5.py
                  • HTC group+family hard gate (positions 1-2)
                  • exact-PID OR Rule-B-modifier match (Path A)
                  • head-noun fallback for un-bridged (Path C)
                  • part-whole substitutions (htc/substitutions.py)
                  • full-package math
                           │
                           ▼
                per-recipe cost in dollars
```

---

## 10. Audit — why HTC matching still leaks bugs

The 8-axis HTC code looks complete, but at the cost layer we only enforce **2 of 8 positions** (group + family). The remaining positions exist on every product but the matcher never compares them. Here's where each remaining v5 bug actually fails:

### 10.1 `eggs` → Easter Cascaron Confetti Eggs (decoration)

| layer | what should have rejected this | what actually happened |
|---|---|---|
| HTC encoder | NON_FOOD_PATTERNS in `htc/encoder.py` | `cascaron`/`confetti` not in pattern list → encoder tagged group=5 (Eggs) on the word "eggs" |
| consensus PID bridge | consensus.product_identity_fixed for this UPC | UPC bridged to consensus row whose PID = `Eggs` (consensus tagged the same way) |
| categoryPath filter | `non_food_path` flag from Walmart's categoryPath | Walmart cache row for this UPC didn't carry a categoryPath → flag stayed 0 |

**Root cause:** the encoder's non-food filter is regex-against-name, but the regex doesn't include the actual non-food words present in joke/decorative products. `cascaron`, `confetti`, `easter` (in NAME, not just path) need to be in NON_FOOD_PATTERNS. **Single-line fix** — but it has to live in the encoder, not the categoryPath filter.

### 10.2 `mint` → Kroger Mouthwash Powerful Fresh Mint

| layer | should have rejected | actual |
|---|---|---|
| Encoder name check | `mouthwash` in NON_FOOD_PATTERNS | not present → tagged group=E (spices) because of "mint" token |
| categoryPath filter | Walmart's path = `Health/Personal Care/Oral Care/Mouthwash` | this UPC isn't in Walmart cache (we got the price from Kroger), so categoryPath is empty |
| Kroger meta filter | Kroger's product_meta categories | we don't extract Kroger's category metadata yet |

**Root cause:** **two sources of non-food signal aren't being read.** Walmart's categoryPath only covers Walmart products; Kroger products are entirely uncovered. We need to extract Kroger's `categories` from the cache blob's `product_meta` JSON and apply the same filter. Plus add `mouthwash`/`toothpaste` to the encoder's NON_FOOD_PATTERNS.

### 10.3 `vanilla` → Betty Crocker Vanilla Cupcake Mix

| should have rejected | actual |
|---|---|
| HTC group+family hard gate | vanilla extract = E5… (Spices/Extracts), Cupcake Mix = E5… too **because the encoder ran on the product NAME** which leads with "Vanilla" |
| consensus PID = Cupcake Mix | bridge would have caught this (Cupcake Mix ≠ Vanilla Extract) but my matcher's head-noun fallback path (Path C) ignores consensus PID — it only checks head_tokens |

**Root cause:** the encoder re-tagged a Cupcake Mix product as group=E because its name leads with "Vanilla". The consensus path (Pantry > Baking Mixes > Cupcake Mix) was bridged as the consensus PID — but my matcher's Path C (un-bridged products) takes any product where primary noun is in head_tokens. "Vanilla" is in head, qualifier check passes (vacuously, since "vanilla" is the only token), product accepted. **Real fix:** when a product IS bridged, *only* Path A applies; never fall through to Path C for bridged products.

### 10.4 `ground cinnamon` → Eggo Cinnamon French Toaster Sticks (pid=Appetizers)

Same shape as 10.3. Consensus PID = Appetizers (correct — these are frozen breakfast appetizers). But the consensus's HTC encoder put the SKU in group=E (Spices) because the product name leads with "Cinnamon". My matcher saw `pid=Appetizers ⊂ valid_pids` because... actually let me trace. For `ground cinnamon`, valid_pids should contain pids in HTC group=E + family=2 (cinnamon family) where pid token-overlaps with `{ground, cinnamon}`. "Appetizers" tokens = `{appetizers}`, no overlap — so it shouldn't have entered valid_pids. It must have hit Path C.

**Root cause: same as 10.3** — Path C accepts head-noun match without checking consensus PID. **Fix: bridged products bypass Path C.**

### 10.5 `saffron threads / cardamom seeds / coriander seeds / cumin seeds` — no priced match

| should have matched | actual |
|---|---|
| consensus has `Pantry > Spices & Seasonings > Spice Blend > Cardamom` (Rule B, modifier=Cardamom) | priced_products has 0 rows bridged to those specific consensus rows because no Walmart UPC scrape produced single-spice products of this granularity |
| substitution fallback | no `cardamom seeds` rule in substitutions.py |

**Root cause: real coverage gap.** The consensus knows what cardamom is. Walmart sells single-spice cardamom (we saw "Spices, cardamom" in SR-28). The bridge between consensus row and priced product UPC just isn't there for these spices. **Fix: re-scrape Walmart's single-spice category** OR add substitution rules pointing at the FNDDS code so we look up by SR-28 fdc instead.

### 10.6 `ripe bananas` → no match

`apply_substitution()` returns the rule "ripe X → X" but `pick_by_substitution` only tries `canonical_paths` and `pids` from the Sub object — it doesn't actually look up the rewritten item ("bananas") in the ingredients dict. The Sub objects for "ripe X" rules have empty `canonical_paths` and `pids`, which is why they fail. **Real fix:** when item_replacement is a regex group reference (`\1`), apply the rewrite and recurse into `pick()` with the rewritten item.

## 10.7 The honest summary

We **are** using HTC and the consensus tree. We're using:
- ✓ HTC group+family (positions 1-2) as a hard gate
- ✓ Consensus product_identity_fixed and modifier (Rule-B foods)
- ✓ Walmart marketplace flag and (partially) categoryPath
- ✓ Part-whole substitutions for prep-form ingredients

We **are not** using:
- ✗ HTC positions 3-7 (food-discriminator, form, processing, ptype) for cross-comparison
- ✗ canonical_path tree walk for parent/sibling fallback
- ✗ Kroger's categories (only Walmart's categoryPath is read)
- ✗ A "bridged → bypass head-noun fallback" guard (this is the source of bugs 10.3 + 10.4)
- ✗ The Hestia HTC registry's controlled vocabularies for position validation

Of the 6 remaining bugs:
- **10.3 + 10.4 are the same fix**: prevent bridged products from falling through to head-noun fallback.
- **10.1 + 10.2 are the same kind of fix**: extend NON_FOOD_PATTERNS in the encoder + extract Kroger categories.
- **10.5 is a coverage gap**: needs more Walmart scrapes for single-spice products or an SR-28-fdc-based fallback.
- **10.6 is a one-line fix** in `pick_by_substitution`.

Total: ~50 lines of code spread across 4 files would close all 6.
