# Comprehensive Analysis: Every Reason Recipe Ingredient Normalization Has Failed

> Synthesized from 18,379-row canonical surface map, 509K-recipe database, 126-phase reducer POC, 4 parallel implementation trees, and 18 months of iteration artifacts.
> Date: 2026-04-30

---

## Table of Contents

1. [Semantic Ambiguity & Multi-Item Ingredients](#1-semantic-ambiguity--multi-item-ingredients)
2. [Missing Taxonomy Leaves & Vocabulary Gaps](#2-missing-taxonomy-leaves--vocabulary-gaps)
3. [Granularity Mismatches](#3-granularity-mismatches)
4. [Brand-Name Ingredients](#4-brand-name-ingredients)
5. [Measurement & Quantity Parsing Failures](#5-measurement--quantity-parsing-failures)
6. [Encoding & Data Quality Issues](#6-encoding--data-quality-issues)
7. [Non-Food Items Misclassified](#7-non-food-items-misclassified)
8. [Proxy / Poison Assignments](#8-proxy--poison-assignments)
9. [Cross-Validation Disagreements](#9-cross-validation-disagreements)
10. [Coverage vs. Correctness Tradeoffs](#10-coverage-vs-correctness-tradeoffs)
11. [Structural / Architectural Failures](#11-structural--architectural-failures)
12. [Attribute Extraction Failures](#12-attribute-extraction-failures)
13. [LLM / Model-Specific Failures](#13-llm--model-specific-failures)
14. [Recipe Context Blindness](#14-recipe-context-blindness)
15. [Summary Statistics](#15-summary-statistics)

---

## 1. Semantic Ambiguity & Multi-Item Ingredients

### 1.1 "Or" Alternatives — The #1 Normalization Debt
**Frequency:** 71,501 display lines | **Impact:** HIGHEST

Recipes constantly give cooks options. The normalizer cannot silently pick one without context.

| Pattern | Example |
|---------|---------|
| Fat-level options | `1 cup vanilla yogurt, 1% or nonfat` |
| Sweetener swaps | `Sugar or honey, to taste` |
| Meat options | `1 1/2 lbs Italian sausage, hot or mild, crumbled or sliced` |
| Extract/liqueur swap | `3 tablespoons amaretto liqueur or 1 teaspoon almond extract` |
| Nut swaps | `50 g walnuts or pecans, chopped` |
| Broth swaps | `5 cups vegetable broth or chicken broth` |
| Butter/margarine | `chilled butter or stick margarine` |
| Multi-oil options | `2 tablespoons butter or 2 tablespoons peanut oil or 2 tablespoons olive oil or 2 tablespoons other oil` |

**Why it fails:** The pipeline explicitly forbids silent collapse of alternatives (Guardrail #20). Every `or` forces manual review or multi-ingredient split logic. `recipe_true_alternatives_other` is the largest work-queue bucket: **1,495 rows, 24,706 occurrences (36.7% of all debt)**.

### 1.2 "And" / "&" Composites — Multi-Food Lines
**Frequency:** 270,991 lines | **Impact:** HIGH

| Pattern | Example |
|---------|---------|
| Prep-state chaining | `2 hot green chili peppers, seeded and stemmed` |
| Multi-step prep | `12 ounces extra firm tofu, water-packed, patted dry and cut into 1-inch cubes` |
| Brand + compound | `philadelphia chive & onion cream cheese spread` |
| Citrus juice + zest + rind | `1 tablespoon lemon zest, finely grated (from about 1-2 lemons, avoiding white pith)` |
| Mixed-with | `2 tablespoons cornstarch, dissolved in 2 tablespoons water` |

**Why it fails:** `"and"` is intentionally NOT a composite trigger in `composite_router.py`. Only `"with"`, `"filled"`, `"stuffed"`, `"&"` trigger composite routing. So `"macaroni and cheese"` is NOT treated as composite. The system either splits manually (66 rows with `|||` pipe separators) or leaves unresolved.

### 1.3 Component Splits (Encoded Multi-Ingredient Surfaces)
**Frequency:** 66 rows | **Impact:** MEDIUM

Surfaces explicitly encoded as multiple components using `|||` pipe separators:
- `black pepper|||;garlic powder|||`
- `egg yolk|||;egg white|||`
- `ground beef|||;ground pork|||`
- `ham|||;turkey|||`
- `lemon|||;lime|||`
- `monterey jack cheese|||;cheddar cheese|||`
- `olive oil|||;salt|||;black pepper|||`

**Why it fails:** These cannot normalize to a single nutrition code because they represent combinations. They are explicitly blocked from item-field fallback.

### 1.4 Generic / Ambiguous Terms
**Frequency:** 1,270+ rows | **Impact:** HIGH

| Surface | Ambiguity |
|---------|-----------|
| `100% bran` | 100% of what? Brand? Content? |
| `100% fruit juice` | Which fruit? Generic proxy used apple juice backbone. |
| `3-cheese blend cheese` | Which three cheeses? Mexican blend used as proxy. |
| `16-bean mix` | Which 16 beans? Pinto used as proxy. |
| `accent seasoning` | MSG-based? Salt-based? Exact composition unknown. |
| `all purpose seasoning` | Composition varies wildly by brand. |
| `barbecue sauce family` | Which style? Kansas City? Carolina? Texas? |

**Why it fails:** The normalizer is dictionary-bound. Without a pre-registered canonical key for the exact blend/mix/seasoning, it returns `None` or falls back to a generic proxy.

---

## 2. Missing Taxonomy Leaves & Vocabulary Gaps

### 2.1 Extracts & Flavorings
**FNDDS has:** Only "Yeast extract spread" (Marmite/Vegemite).  
**Missing:** Vanilla extract, almond extract, rum extract, lemon extract, peppermint extract, banana extract, orange extract, coffee extract.

**Impact:** These contribute negligible calories but are essential for allergen detection and recipe completeness. They default to `reviewed_nutrition_unknown` (2,218 rows, 12.1%).

### 2.2 Additives & Colorings
- Red food coloring, blue food coloring, gel food coloring
- Active dry yeast vs. instant yeast vs. compressed yeast (only generic "Yeast" in FNDDS)
- Ammonium bicarbonate, ammonium carbonate (chemical leaveners)

### 2.3 Modern / Plant-Based Products
**ESHA/SR28/FNDDS frozen at 2015-2018.** Missing:
- Oat milk, almond milk, soy milk, coconut milk (as dairy alternatives — coconut milk exists but in different context)
- Impossible Burger, Beyond Meat
- Protein milks, protein shakes
- Plant-based creamers
- Keto-friendly sweeteners (allulose, monk fruit)

### 2.4 Specialty / Ethnic Ingredients
- Saffron threads, ground mace, cardamom seeds
- Fish sauce (nam pla), pappadams, mango chutney
- Sazon with culantro, garam masala, za'atar
- Harissa, gochujang, tamarind paste, miso
- Whole spices: cumin seeds, coriander seeds, cardamom pods, cinnamon sticks, peppercorns
- Rice varieties: basmati, jasmine, arborio (only generic "rice" exists)
- Achiote, ajvar, aburage, ackee

### 2.5 Prepared Forms
- Toasted almonds
- Cream cheese frosting
- Shredded cheddar (as distinct from block cheddar)
- Fresh vs. dried herbs (basil, oregano, thyme)
- Active starter vs. sourdough starter vs. dry yeast

### 2.6 Source Gap Statistics
- **610 food items** genuinely missing from ESHA (per `esha_gap_summary.md`)
- **~300 RESCUED_EXOTIC_CLASS matches** where proxy is correct family but wrong flavor/specificity
- **53 rows** where BOTH ESHA and FNDDS lack a safe match, so only SR28 backbone is retained
- **416 rows** with `NO_IDENTITY_NODE` in the retail food taxonomy
- **313 rows** with `NEEDS_NEW_LEAF` in the retail food taxonomy

---

## 3. Granularity Mismatches

### 3.1 Recipe Wants Specific, Database Has Generic
| Recipe Calls For | Database Has | Problem |
|-----------------|--------------|---------|
| `chipotle honey blueberry potato chips` | `Potato chips, plain` | Specificity gap |
| `vanilla extract` | *Not in FNDDS* | Missing category |
| `Häagen-Dazs Vanilla Bean ice cream` | `Ice cream, vanilla` | Brand specificity |
| `fresh basil leaves` | `Basil, fresh` (exists) vs. `Basil, dried` | Form matters |
| `Golden Delicious apple` | `Apple, raw, with skin` | Variety ignored |
| `whole wheat pastry flour` | `Flour, all-purpose` | Type specificity |

### 3.2 Vitamin Fortification Ambiguity (The "Vitamin A & D" Problem)
ESHA has 4 separate milk codes based on fortification:
- Code 1: "Milk, whole, 3.25%, with added vitamin D"
- Code 2: "Milk, 2%, with added vitamin A & D"
- Code 4: "Milk, 1%, with added vitamin A & D"
- Code 6: "Milk, nonfat/skim, with added vitamin A & D"

**Recipes say:** `"1 cup milk"`  
**Problem:** Recipes don't specify fortification. Matching becomes probabilistic. Most US milk is fortified, but organic/raw milk products and international recipes may use unfortified.

### 3.3 ESHA Too Granular
- Vitamin distinctions recipes don't care about create unnecessary splits
- 586 cheese entries — excessive fragmentation
- Garlic had only 1 entry for 531K recipes; should split fresh/powder/salt

---

## 4. Brand-Name Ingredients

### 4.1 Brands in Recipe Lines
- `1 box German chocolate cake mix` (brand-specific, FNDDS has generic)
- `Cool Whip` (whipped topping brand)
- `Splenda` (sweetener brand)
- `Philadelphia cream cheese` (brand + product)
- `Ritz crackers` (brand required for identity)
- `Kraft parmesan cheese`
- `Oscar Mayer bacon`

### 4.2 Brand-Only Fragility
- 297 rows in approved file are pure brand names with no generic category
- Brand candidate misses: All-Bran, Almond Joy, Baileys, Aperol, Jack Daniel's
- Products are marketing language: "Frozen dairy dessert" vs. "Ice cream" — legal distinction vs. canonical code

### 4.3 Override Evidence
The `recipe_item_overrides` table (10,291 rows) shows brands are a top disambiguation signal:
- `crackers` → needs Ritz, water crackers, or Cobblestone Wheat
- `chocolate` → needs brand + form (dark, semisweet, unsweetened baking)

---

## 5. Measurement & Quantity Parsing Failures

### 5.1 Quantity Leakage into Product Field
**424 rows** where product field doubles as quantity field:
- `1 lb New York strip steak`
- `8 oz dried fettuccine`
- `boneless skinless chicken breast halves (about 1 1/2 pounds)`
- `butternut squash (about 2 lbs)`
- `whole chicken (3 1/2 lb)`

### 5.2 Unicode Fractions
`1⁄4`, `1⁄2`, `1⁄3`, `3⁄4`, `1 1⁄2` — these are NOT the same as ASCII `1/4`, `1/2`.  
Parser needs U+2044 fraction slash and vulgar fraction preprocessing.

### 5.3 Compound Quantity Expressions
- `1 (1/16 ounce) bag black tea`
- `1 can (5.5 oz) baby corn, drained`
- `2 cans (10.75 oz each) black beans`
- `7 ounces (1/2 of a 14-ounce jar) Ragu pizza sauce`
- `1⁄42 cup` (garbled fraction from bad OCR)

### 5.4 Range Parsing
- `10-12 cardamom pods`
- `4 to 5 cups all-purpose flour`
- `3-4 large tomatoes`

### 5.5 The "Head of Lettuce" Problem
FNDDS says: 1 head = 609g (large) or 309g (small). Recipe says `"1 head iceberg lettuce, chopped"`. Which one?

### 5.6 Grams Precedence Bug
**~404K drifted lines (10.5%)** caused by normalized-line grams overriding recipe-level grams. Discovered after 90+ phases.

### 5.7 "To Taste" / Garnish / Frying
- `Salt, to taste`
- `Black pepper, to taste`
- `Water, to cover chicken (about 6-8 cups)`
- `Oil, for frying`

These require `reviewed_quantity_policies.csv` (7,625 policies) and `reviewed_to_taste_defaults.csv` (189 defaults).

---

## 6. Encoding & Data Quality Issues

### 6.1 Mojibake / Encoding Corruption
**184 rows** with UTF-8 decoded as Latin-1:
- `aj√≠ amarillo paste` → `ají amarillo paste`
- `aliz√© gold passion liqueur` → `alizé gold passion liqueur`
- `bacardi frozen pi√±a colada concentrate` → `bacardi frozen piña colada concentrate`
- `beef consomm√©` → `beef consommé`
- `chilled cr√®me fra√Æche` → `chilled crème fraîche`

### 6.2 Regex Artifacts
**8 rows** with raw regex backreferences in canonical_surface:
- `condensed cream of \1 soup`
- `cream of \g<food> soup`
- `dried \1`
- `fresh \g<herb>`

### 6.3 Truncated Strings
- `hummu` → `hummus`
- `israeli couscou` → `couscous`
- `octopu` → `octopus`
- `whole wheat couscou` → `whole wheat couscous`

### 6.4 OCR / Typo Errors
- `sun- tomatoe` → `sun-dried tomato`
- `tomatoe` → `tomato`
- `pimiento` inconsistent with `pimento`

### 6.5 Duplicate Surfaces
6 surfaces appear exactly twice: `arugula`, `candied fruit`, `fresh lemon juice`, `kale`, `nectarines`, `radicchio`.

### 6.6 Over-Engineered Variant Names
- `green_onion_green`
- `egg_yolk_yolk`
- `red_onion_red`

### 6.7 Empty / Artifact Rows
- 1 row with entirely empty `canonical_surface` (trailing artifact)
- 17 rows with blank `record_type`
- ~400 rows where `record_type` is a food category name instead of `ingredient`

---

## 7. Non-Food Items Misclassified

### 7.1 Chemicals Labeled as Ingredients
- `ammonia`, `bleach`, `boric acid`, `chlorine bleach`
- `grease`, `hydrogen peroxide`, `lye`, `mineral spirits`
- `plaster of paris`, `armor all cleaner`

### 7.2 Tools / Supplies
- `baking paper`, `baking sheet`, `balloon`
- `bamboo toothpicks`, `barbecue skewers`
- `alder wood chips` (for smoking, not eating)

### 7.3 Non-Food Artifacts
- `a human adult vitamin mineral tablet`
- `aerosol shaving cream`
- `antique teacup with saucer`
- `aspirin tablets`
- `baby oil`

### 7.4 Food Items Misclassified as Non-Food
- `boneless, skinless chicken breast` → labeled `non_ingredient`
- `boneless, skinless chicken thigh` → labeled `non_ingredient`
- `Broken cheese fragment needs source context` → labeled `non_ingredient`
- `Bechamel is a prepared component` → labeled `non_ingredient`

### 7.5 Parser Fragments
- `:`, `)`, `-`, `or`, `up`, `um`, `dd`, `nd` treated as foods
- `egg plus 1 egg yolk` — parser fragment
- `40% bran flakes` — parser noise

---

## 8. Proxy / Poison Assignments

### 8.1 Wave1 Historical Poison / Repair Debt
**~500+ rows** carry Wave1 repair narratives. Wave1 was an earlier pass that introduced bad direct nutrition anchors.

Top poison categories:
- `wave1_blank_direct_transformed_poison` (97 rows)
- `wave1_liqueur_proxy_poison` (53 rows)
- `wave1_transformed_proxy_poison` (68 rows)
- `wave1_seasoning_proxy_poison` (49 rows)
- `wave1_direct_flower_family_poison` (25 rows)
- `wave1_bridge_conflict_candy_poison` (9 rows)
- `wave1_direct_white_bread_poison` (8 rows)

### 8.2 Hot-Leaf Magnets
Generic tokens repeatedly attracted unrelated products:
- `apple`, `almond`, `milk`, `juice`, `cream`, `sandwich`, `snack`, `sauce`
- Modifiers: `original`, `natural`, `fresh`, `whole`, `pieces`, `baby`

### 8.3 Wrong-Flavor Proxies
- `grape juice` routed to `cranberry juice drink`
- `pepper jelly` routed to `apple/mint jelly`
- `harissa` / `gochujang` landed on `pasta sauce`
- Alcohol-class exotics all fell to generic `brandy`

### 8.4 Product-Tag Precision Gaps
- `cream` → El Mexicano Crema Oaxaquena (specialty product)
- `water` → Essentia branded water
- `carrot` → Peas & Carrots mixed veg
- `apple` → Marketside baked pie
- `flour` → PUPURU Cassava poundo
- `granulated sugar` → Dallies Pink Sanding Sugar 3.5oz
- `egg` → Egg Beaters (liquid) instead of shell eggs

### 8.5 Proxy Candidate Statistics
- **6,112 rows (33.3%)** are `reference_proxy_candidate` — uncertain nutrition match
- **2,587 rows (14.1%)** are `product_proxy_candidate` — retail median nutrition, not accepted SR28/FNDDS
- **819 rows (4.5%)** are general `proxy_candidate`
- **2,218 rows (12.1%)** are `reviewed_nutrition_unknown`

**Combined: ~59% of the file lacks a confident, direct nutrition match.**

### 8.6 Auto-Batched Proxy Pollution
- **458 rows** in `canonical_items.csv` marked `proxy_auto_batched`
- These polluted proxies MUST NOT drive shopping (per architecture rule)
- **3,703 Tier B Esha codes** are auto-batched SR28/FNDDS proxies awaiting review

---

## 9. Cross-Validation Disagreements

### 9.1 SR28-ESHA Disagreement
- **41.99%** of rows with SR28 reference are provably wrong (2,408 rows)
- **2,060 rows** where ESHA match and SR28 root have zero token overlap
- High wrong% by tier: T8_SECOND_SUBSET 26.57%, T5_HEAD_SUBSET 19.69%, T2_FAMILY_SUBSET 18.43%, T1_EXACT 20.83%

### 9.2 Model Churn
- 7 rows changed product family 4+ times across pipeline stages (Qwen → Pre1 → Pre2 → Resolved → Approved)
- Models did not converge: Qwen wrote hedged strings, Llama replaced with brands, gpt-oss invented SKUs

### 9.3 Audit Disagreement
- `esha_audit`, `sr28_audit`, `fndds_audit` columns show DISAGREE / ORIG_ONLY / RFT_FILL / BOTH_EMPTY patterns
- Many rows where RFT agrees with one source but disagrees with others

---

## 10. Coverage vs. Correctness Tradeoffs

### 10.1 Metric Substitution
| Metric | What It Measures | What It Was Sold As |
|--------|-----------------|---------------------|
| 97.37% repeated-line mapping | Occurrence mass for frequent lines | "We mapped 97% of ingredients" |
| 97.15% product-card reachability | Product/no-buy/external-gap for ready cards | "97% of recipes have products" |
| 69.76% recipe-level mapped required lines | ACTUAL recipe coverage | **Ignored in favor of the 97s** |

### 10.2 Coverage Chasing
- `vSelf` raised coverage by assigning through compatible-looking heads but reintroduced wrong assignments
- `vCluster` projected cluster decisions, preserving cluster-level mistakes
- Review queue was terminal output, not system memory — same aliases rediscovered every round

### 10.3 Ethnic Bias in Coverage
- American/European: 85-95%
- Asian: 60-75%
- Indian: 60-70%
- Mexican: 75-85%
- Middle Eastern: 65-75%

### 10.4 Accuracy-Scale Tradeoff
- POC (100 items) → 95%
- Pilot (1K) → 85%
- Scale (10K) → 60%
- Production (462K) → 45%

### 10.5 Cascade Effect
Fixing "milk" to prefer 2% broke "whole milk" recipes.

---

## 11. Structural / Architectural Failures

### 11.1 The 126-Phase Scratch Factory
Reducer POC exploded into **126 phases, 352 data files, 39 report directories** — never replaced the 700K-row exact-alias table. Existence of rerun phases (`phase86_rerun_guarded_visible_choice`) is evidence of iterative hacking without convergence.

### 11.2 Four Parallel Implementation Trees
- `implementation/` — canonical package
- `codex implementation/` — bounded launch package
- `kimi_implementation/` — Tier 1 production track
- `swarm_round1/`, `swarm_round2/` — paired CSV review rounds

These are not merged; each is self-contained. Rules exist in 4+ places.

### 11.3 Calculator Is a Reporting Layer
Real math: 133 lines (`nutrition.py`).  
Everything else: 1,200-line audit monster (`audit_recipe_qa_nutrition_calculation.py`).

### 11.4 Review Queue = Knowledge Graveyard
No feedback loop to convert reviewed decisions into durable mapper rules. Same aliases rediscovered every round.

### 11.5 130-Line Hardcoded `classify()` Function
Monolithic `if/elif/else` chains in `build_recipe_calculation_work_queue.py`.

### 11.6 God Object
`resolver_context.py` contains **80+ hardcoded Path objects**.

### 11.7 No Explicit Schema Contract
Audit DB schema known only by reading SQL strings in three different files.

### 11.8 Three Matcher Paths
- LayeredResolver
- MitigationResolver
- RecipeMapper

### 11.9 Two Calculator Paths
- `calculator.py`
- `surface_lab_calculator.py`

### 11.10 Observability Untrustworthy
Stale/missing artifact references, invalid queues, missing upstreams, count mismatches.

---

## 12. Attribute Extraction Failures

### 12.1 Missing Attributes
**3,682 instances** missing prep, form, state, size, style, packaging extraction.

### 12.2 Wrong-Column Placement
- `ground` in state instead of form
- `whole` in form instead of style
- `leaf` in form instead of packaging

### 12.3 Attribute Collapse
**2,378 rows (~13%)** where attributes merged/collapsed during normalization.

### 12.4 Fluff vs. Style Confusion
- `organic`, `natural`, `premium` stripped as fluff when sometimes they should be style

### 12.5 Prep-State Leakage
**1,318 rows** where product field contains prep/pack-state descriptors (`canned`, `shredded`, `drained`, `chopped`).

### 12.6 Single-Pass Token Scan Limitation
`attribute_extractor.py` is order-dependent and cannot handle stacked modifiers:
- `"extra virgin olive oil"` — `"extra"` may be stripped as fluff, `"virgin"` not in vocabulary
- Head noun is simply the rightmost residual token

---

## 13. LLM / Model-Specific Failures

### 13.1 Display-Text Echo
**30.4% of approved file (3,081 rows)** is just recipe display text with numbers stripped — not normalization.

### 13.2 Fake SKU Generation
**75 rows** contain fake SKU numbers (`SKU: 12345678`).

### 13.3 Tautological Reasoning
**200 rows** where LLM reasoning just restates the product name.

### 13.4 Cuisine Drift
**11 survivors** where Asian pasta downgraded to Western or vice versa.

### 13.5 Hallucinated Products
Models invented plausible-sounding products that don't exist in `master_products.db`.

### 13.6 Unbalanced Parentheses
Broken parenthetical examples due to CSV truncation or model cutoff.

### 13.7 Claim Order Wrong
`organic`, `low_sodium` returned in wrong order.

### 13.8 Over-Modeling Default States
Model added `shelf_stable`, `canned`, `frozen`, `fully_cooked` when not needed.

### 13.9 Component Omissions
Dip/soup/tortilla component identities missing from LLM output.

---

## 14. Recipe Context Blindness

### 14.1 No Cross-Ingredient Context
The normalizer processes each ingredient line **in isolation**. It cannot use recipe neighborhood to disambiguate:
- `"oil"` in a dessert recipe likely means vegetable oil, not olive oil
- `"flour"` in a cake means all-purpose flour
- `"cheese"` in a Mexican dish means Oaxaca, not cheddar
- `"nuts"` in a pecan pie means pecans, not walnuts

### 14.2 Override Evidence from `recipe_item_overrides`
The table proves context is required for correct mapping:

| Ambiguous Item | Default | Contextual Override |
|----------------|---------|---------------------|
| `cream` | heavy cream | half-and-half (lighter context), sour cream (Mexican context) |
| `nuts` | pecans | walnuts (banana bread), peanuts (Asian context) |
| `pasta` | spaghetti | fusilli (shape specified), linguine (seafood context) |
| `cheese` | cheddar | Oaxaca (Mexican), paneer (Indian), mozzarella (pizza) |
| `stock` | chicken | vegetable (vegetarian), pork (French cassoulet) |
| `beans` | kidney | pinto (Mexican), cannellini (Italian) |
| `wine` | red | white (fish dish), sherry (Spanish), shaoxing (Chinese) |

### 14.3 Cuisine Context Lost
- Indian curry → chicken stock (beef too strong)
- French cassoulet → pork stock (matches pork/duck theme)
- Cream of Broccoli Soup → vegetable broth (vegetarian)

---

## 15. Summary Statistics

### From the 18,379-Row Canonical Surface Map

| Category | Rows | % of File |
|----------|------|-----------|
| Reference proxy candidate (uncertain) | 6,112 | 33.3% |
| Empty rft_verdict (never routed) | 12,450 | 67.7% |
| Product proxy candidate (uncertain) | 2,587 | 14.1% |
| Reviewed nutrition unknown | 2,218 | 12.1% |
| Generic blend/mix/seasoning surfaces | 1,270 | 6.9% |
| Explicit non_ingredient | 523 | 2.8% |
| Wave1 historical poison/repair | ~500+ | ~2.7% |
| RFT NO_IDENTITY_NODE | 416 | 2.3% |
| RFT NEEDS_NEW_LEAF | 313 | 1.7% |
| Missing from ESHA/FNDDS/SR28 | ~400+ | ~2.2% |
| Wrong-family record_type | ~400 | ~2.2% |
| Component splits | 66 | 0.4% |
| Multi-item / option surfaces | 40 | 0.2% |
| Measurements embedded in surface | 26 | 0.1% |

### From the Recipe Database

| Pattern | Frequency |
|---------|-----------|
| " or " alternatives in display | 71,501 lines |
| Multi-food "and"/"&" lines | 270,991 lines |
| Parenthetical asides | 494,186 lines |
| Long composite lines (>80 chars) | 15,880 lines |
| recipe_item_overrides needed | 10,291 rows |

### From the Pipeline Work Queue

| Bucket | Rows | Occurrences | % of Debt |
|--------|------|-------------|-----------|
| recipe_true_alternatives_other | 1,495 | 24,706 | 36.74% |
| recipe_dictionary_gaps | 1,775 | 23,676 | 35.21% |
| recipe_component_splits_other | 418 | 6,329 | 9.41% |
| parser_fragment_review | 401 | 5,814 | 8.65% |
| recipe_qualified_tuple_review | 171 | 3,014 | 4.48% |
| recipe_brand_noise_review | 50 | 775 | 1.15% |
| recipe_fresh_frozen_alternatives | 22 | 287 | 0.43% |
| recipe_alt_butter_margarine | 13 | 158 | 0.23% |
| recipe_cooked_drained_meat_prep | 4 | 52 | 0.08% |

---

## Conclusion

The normalization system fails for **15 major categories** spanning semantic ambiguity, missing taxonomy, granularity mismatches, brand contamination, measurement fragility, data quality, misclassification, proxy pollution, cross-validation disagreement, metric substitution, architectural debt, attribute extraction limitations, LLM hallucinations, and — most critically — **recipe context blindness**.

The dominant failure mode is not hard parsing errors (there are virtually no 1-2 character items). The danger is **semantic collapse**: the normalizer sees a plausible generic term and assigns a default product, ignoring recipe context, alternatives, prep state, and form that change nutrition and shopping identity.

**~59% of canonical surfaces lack a confident direct nutrition match.**  
**67.7% never made it through retail food taxonomy routing.**  
**The honest recipe-level coverage is ~69.76%, not the 97% often cited.**

The path forward requires: closing the review loop, building recipe-context disambiguation, expanding the taxonomy with ethnic/modern ingredients, and stopping the 126-phase scratch factory.
