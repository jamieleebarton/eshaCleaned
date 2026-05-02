# INVESTIGATION — Why `api_cache_exact:accepted=0 rejected=25` keeps firing

**Last edit:** 2026-05-02 (joining engineer, post-universe-sweep)
**Status:** Read-only — no code changes proposed inside this file. See `FIX_PLAN.md` for the action items.
**Companion docs:** `GOAL.md` (anchor), `FIX_PLAN.md` (sequenced steps).

---

## Executive summary

The calculator already has the right canonical (`macaroni`, `chicken drumstick`, `green onion`, `tomato juice`), the cache already has the right products (Barilla elbow pasta, Tyson drumsticks, bunched scallions, Campbell's V8 / Walmart Great Value tomato juice), and the audit already classifies those products correctly under the right `canonical_path`. The reason `accepted=0 rejected=25` keeps firing is that `surface_lab_calculator._product_acceptance_reason()` does not look up the audit. It walks ~60 hand-tuned `if canonical_key == ...` branches and falls into a catch-all that calls `_reject_combo_product()`, whose hard-coded blocklist contains `pasta`, `tortilla`, `salad`, `mix`, `medley`, `bread`, `chips`, `entree`, etc. Any cached product whose title carries one of those tokens — and most retailer titles do, because that is how categories get embedded in branded SKU names — gets rejected as `combo_or_prepared_product:pasta` even though the product is exactly the right thing. Tonight's audit-tagging work (commits a5e26b42 + 03b72ee2) shipped the substrate that lets us delete this entire chain. The filter file itself is the final piece. **Replace `_product_acceptance_reason()` with `accept_via_audit(product, canonical, expected_audit_path)`. The 60 per-canonical branches and the combo blocklist become deletable.**

---

## The filter chain today (numbered, with line numbers)

`/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/calculator.py`
1. `calculate_line(display, item, grams_hint)` — `calculator.py:510`. Composition is `non_food → layered_resolver → portion_resolver → sr28_nutrition → product_matcher`.
2. `match_products(...)` (line 691) returns up to 25 candidates from `master_products.product_code_tags` keyed by FNDDS code.
3. If no FNDDS-keyed match, `search_products(shopping_canonical, limit=25, canonical=shopping_canonical)` (line 698) — pulls 25 from `api_cache.db` by FTS title match. **Note:** the path emitted in `universe_calc.json` shows `shopping_products:api_cache_exact:accepted=0 rejected=25`, so for the four canonicals under investigation this is the FTS-on-api_cache route.

`/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/surface_lab_calculator.py`
4. `_review_products(products, canonical, limit=25)` — line 4193. Iterates each candidate and calls `_product_acceptance_reason(product, canonical)`. Splits into `accepted` and `rejected` lists, both capped at 25.
5. `_product_acceptance_reason(product, canonical)` — line 3797. The decision tree:
   - Calls `_accept_milk_product`, `_accept_egg_product`, `_accept_mayonnaise_product`, `_accept_oil_product`, `_accept_cocoa_powder_product`, `_accept_raw_produce_product`, `_accept_breadcrumb_product`, `_accept_fresh_mint_product`, `_accept_hot_sauce_product`, `_accept_recipe_volume_edge_product`, `_accept_sparse_audit_product`, `_accept_batch11_product`, `_accept_batch12_product`, `_accept_batch9_product`, `_accept_batch10_product` — each returns `None` if its canonical_key set does not match, otherwise a final `(bool, reason)`.
   - Followed by an inline cascade of ~50 `if canonical_key == "..."` / `if canonical_key in {...}` blocks (stew meat, pork chop, buttermilk, cream cheese, swiss cheese, scallion/green onion, mushroom, sunflower seed, dry pasta, monosodium glutamate, chickpea flour, peas, rice chex, rum, southern comfort, vinaigrette, baking apple, pizza sauce, tomato juice, tomato puree, etc.).
   - **Default tail** (lines 4170–4175):
     ```python
     combo_reject = _reject_combo_product(canonical, product)
     if combo_reject:
         return False, combo_reject
     if canonical_tokens and canonical_tokens <= tokens:
         return True, "contains_required_canonical_terms"
     if _has_phrase(product.description, canonical):
         return True, "contains_canonical_phrase"
     return False, "missing_required_canonical_terms"
     ```
6. `_reject_combo_product(canonical, product)` — line ~3760. Hard-coded combo blocklist:
   ```python
   combo_terms = {"bar", "bars", "blend", "bread", "casserole", "chips",
                  "dinner", "dinners", "entree", "fry", "medley", "mix",
                  "mixed", "pasta", "salad", "side", "sides", "stir",
                  "tortilla", "tortillas"}
   extra_combo = product_tokens & (combo_terms - canonical_tokens)
   if extra_combo:
       return "combo_or_prepared_product:" + ...
   ```
7. `price_product_filters.py` provides two adjacent gates: `is_retail_price_reject(name, canonical)` (line 142) and `passes_retail_identity(name, canonical, category)` (line 178). Each one is itself a per-canonical `if canonical_key == ...` cascade for ~17 canonicals (half-and-half, whole ham, salt, egg, black pepper, onion, green onion, butter, cheddar cheese, parmesan cheese, tomato, olive oil, sugar, flour, mayonnaise, milk). These are run upstream of `_review_products` and reject products before they ever reach the acceptance cascade. Same shape, same brittleness.

The single inflection point — every rejection in `universe_calc.json` flows through it — is **step 6**, the default tail's `_reject_combo_product` call.

---

## Why the rules over-reject — case-by-case

The four samples from `universe_calc.json` and what is happening to them:

### 1. `canonical=macaroni` (esha=38061, "Pasta, macaroni, enriched, dry"), 2 occurrences

- **No `if canonical_key == "macaroni"` branch.** There is one for `dry pasta` (line ~4060 in `surface_lab_calculator.py`) but `dry pasta` ≠ `macaroni`. The resolver canonicalizes the recipe input "macaroni" / "1 1/2 lbs macaroni" to `macaroni`, not `dry pasta`.
- The line falls to the default tail. `canonical_tokens = {"macaroni"}`. For any product whose title contains "macaroni", `canonical_tokens <= tokens` is true and the line wants to accept.
- But `_reject_combo_product` runs first. The blocklist contains `pasta`. Every cached macaroni product carries `pasta` in its title or category — Barilla "Elbow Macaroni Pasta", Great Value "Elbow Macaroni Enriched Pasta", Kroger "Elbow Macaroni 16 oz Pasta", etc. Result: `combo_or_prepared_product:pasta` for all 25 candidates.
- **Audit substrate already has the answer.** `full_corpus_audit.csv` rows for fndds 58122000 / 58145110 etc. assign `canonical_path = "Pantry > Pasta > Macaroni > Plain"` (or "> Cheese Sauce" for mac-and-cheese boxes). A generic accept rule that checked "does the audit's canonical_path start with `Pantry > Pasta > Macaroni > Plain`?" would accept the elbow macaroni and reject the mac-and-cheese boxes deterministically.

### 2. `canonical=chicken drumstick` (esha=15056, "Chicken, drumstick, skinless, raw"), 3 occurrences

- **No `if canonical_key == "chicken drumstick"` branch.** There IS one for plain `chicken` (line ~1914) — that one explicitly accepts when tokens contain `drumsticks`/`drums` AND the category is poultry/meat. But the resolver routes "chicken drumsticks" to the canonical `chicken drumstick` (singular), not to `chicken`.
- Default tail. `canonical_tokens = {"chicken", "drumstick"}`. Most retailer drumstick SKUs are titled "Tyson Fresh Chicken Drumsticks", "Just Bare Boneless Chicken Drumsticks Stir-Fry Kit", "Perdue Drumsticks BBQ Mix", etc. Many of those plurals tokenize as `drumsticks` (with the trailing s), so `canonical_tokens <= tokens` already fails for the plural-only titles (`{"chicken","drumstick"} <= {"chicken","drumsticks",...}` is False). Those go to `missing_required_canonical_terms`.
- The few that survive identity (singular drumstick somewhere in the description) then hit `_reject_combo_product` and fail on `stir`, `mix`, `kit` (kit is not in the list — but `mix`, `stir`, `fry` all are). Plain "Tyson Fresh Chicken Drumsticks" with no extra modifier should pass the default tail; if it isn't passing, it's because its tokens contain `fresh`-style descriptors that survive normalization but the product description doesn't quite carry the singular form. (Reading-only: the singular/plural mismatch is the most likely culprit and matches the green-onion rule's bespoke plural handling.)
- **Audit substrate already has the answer.** Audit row 1370632 ("HARVESTLAND, FRESH CHICKEN DRUMSTICKS"): `canonical_path = "Meat & Seafood > Poultry > Plain > Chicken Drumsticks"`, `processing_storage = "fresh"`, `confidence = 0.95`. A rule that accepts when audit's canonical_path starts with `Meat & Seafood > Poultry > ... > Chicken Drumsticks` is one comparison.

### 3. `canonical=green onion` (esha=5709, "Onion, green, chopped, fresh"), 4 occurrences

- There IS a per-canonical branch (`canonical_key in {"scallion", "green onion"}` at line ~2445). It checks identity (`scallion`/`scallions` token OR phrase contains `green onion(s)` / `spring onion(s)`), then a 35-token reject set (`bacon`, `bean`, `cabbage`, `carrot`, `cilantro`, `cream`, `dip`, `ranch`, `salad`, `kit`, `wonton`, etc.), and finally a category gate that requires `fruit/herb/onion/produce/vegetable`. Final fallback: `green_onion_requires_produce_category`.
- Three concrete failure modes in cache:
  1. The cached titles for the four occurrences of `green onion` in tonight's sweep are mostly **salad-kit and recipe-mix products** that contain the words "green onion" inside a long title — see audit rows 1067231 ("Southwest ... Green Onion ... Chopped Salad Kit") and 1067233 ("Savoy Cabbage, Carrot, Celery, Green Onion ... Asian Chopped Salad Kit"). These hit reject tokens `salad`/`cabbage`/`carrot`/`kit`/`wonton` — correctly classified as salad kits, not bunches of scallions. So 0 of 25 was probably correct here, BUT only because the cache has no plain scallion bunches under FTS-on-`green onion` — not because the rule worked; it would also reject a real scallion bunch named "Bunches Green Onions Sweet Slaw Pack".
  2. Plural-only titles ("Green Onions, Bunch, 1 each") tokenize to `{"green","onions"}` — `_contains_phrase(desc, "green onion")` checks for the singular phrase, so plurals match via the `_contains_phrase("green onions")` arm correctly. (Identity is OK here.)
  3. Category gate: Kroger files green onions under `Produce > Fresh Vegetables > Onions & Garlic` which contains `produce` — accepts. Walmart files them under `Fresh Food > Vegetables > Onions, Garlic & Shallots` which also contains `vegetable` — accepts. So when a clean bunch is in the cache, this rule should pass; the fact that 0/25 accepted means **the cache has no plain scallion bunches under the FTS-on-green-onion query**, only salad kits. That is itself a real defect: scallions are FTS-indexed under "green onions" plural and the FTS-search call is hitting only kit-products. The fix is the same — accept by audit canonical_path, not by FTS-string-match.
- **Audit substrate already has the answer.** Audit canonical_path for plain scallion = `Produce > Fresh Vegetables > Onions > Green Onions > Plain`. Salad kits = `Produce > Salad Kits > ...`. One audit lookup separates them with no token list.

### 4. `canonical=tomato juice` (esha=3984), 4 occurrences

- Per-canonical branch at line 2734:
  ```python
  if canonical_key == "tomato juice":
      if "tomato" not in tokens or "juice" not in tokens:
          return False, "missing_tomato_juice_identity"
      reject = tokens & {"beef", "carrot", "celery", "clam", "cocktail", "diced", "vegetable"}
      if reject:
          return False, "not_plain_tomato_juice:" + "/".join(sorted(reject))
      if any(term in category for term in ("beverage", "drink", "juice")):
          return True, "tomato_juice_label"
      return False, "tomato_juice_requires_juice_category"
  ```
- The 25 cached products are dominated by V8 (`tokens` contains `vegetable` → reject), Sacramento (`canned`, but tokens don't include reject set, so reject set passes — moves to category gate), Campbell's tomato juice (passes identity, passes reject, but its retailer category is often `Pantry > Canned & Packaged > Canned Vegetables`, which contains neither `beverage` nor `drink` nor `juice` → final fallback `tomato_juice_requires_juice_category`).
- **Audit substrate already has the answer.** Audit row 1143245 ("TOMATOES IN TOMATOE JUICE") canonical_path = `Pantry > Canned Vegetables > Whole > Tomatoes > Peeled` — that's whole tomatoes IN juice, not tomato juice; this one should not be accepted for `tomato juice` canonical. Plain Campbell's V8 has audit canonical_path `Beverage > Juice > Vegetable Blend > V8` — different from plain tomato juice. Sacramento Tomato Juice = `Beverage > Juice > Tomato > Plain`. The audit splits `Beverage > Juice > Tomato > Plain` cleanly from `Beverage > Juice > Vegetable Blend > V8`. The accept rule = "audit canonical_path starts with `Beverage > Juice > Tomato > Plain`" handles all 25 deterministically with no `vegetable` blocklist.

### Cross-cutting: the combo blocklist eats correct candidates whenever the canonical is itself NOT in the combo list

Pasta canonicals (macaroni, spaghetti, ziti, penne, etc.) all blow up because `pasta` is in the combo set but those canonicals' tokens are `{"macaroni"}` etc. — `combo_terms - canonical_tokens` therefore still contains `pasta` and any product with pasta in the title is rejected. Same shape for "tortilla wraps" canonical where the canonical token is `tortilla` (saved by `combo_terms - canonical_tokens`), but `tortilla chip` canonical fails because `chips` is in combo-set and `tortilla chip` does not include `chips`. Same shape for any canonical whose retail SKUs typically include "salad", "mix", "side", "blend", "kit", "medley". This is the dominant rejection pattern in `universe_calc.json` for canonicals that don't have a hand-written branch.

---

## What the audit substrate already provides

`/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2/full_corpus_audit.csv` (462,712 rows, May 1 23:16) carries per-row:

- `canonical_path` (e.g., `Pantry > Pasta > Macaroni > Plain`, `Meat & Seafood > Poultry > Plain > Chicken Drumsticks`, `Produce > Salad Kits > Southwest`, `Beverage > Juice > Tomato > Plain`)
- `canonical_label`, `variant`, `flavor`, `form_texture_cut`, `processing_storage`, `claims`
- `confidence` (0.0–1.0; the four representative rows shown above are 0.85–0.95)
- `fndds_code`, `sr28_code` (USDA crosswalk anchors)

That file is keyed on FDC IDs, so it directly classifies the ~17,837 cache UPCs that have an FDC mapping. The remaining ~74,797 retailer-private UPCs were classified tonight via BM25 title-match against per-fndds_code audit-derived docs (commit a5e26b42). The result is `/Users/jamiebarton/Desktop/Hestia/api/data/product_audit_classification.db`:

- 17,837 rows with `classification_method = audit_fdc_match` (high confidence)
- 52,303 rows with `classification_method = audit_title_bm25` (BM25 above the calibrated threshold)
- 22,494 rows `unclassified` (residual — the only cases that need DeepSeek)
- 92,634 rows total, UPC-keyed, with the same `canonical_path` / `variant` / `form_texture_cut` / `processing_storage` columns as the audit

Spot-check by canonical path:

- `Pantry > Pasta > Macaroni > Plain` — populated; FDC and BM25 routes both agree on plain elbow macaroni vs mac-and-cheese boxes
- `Meat & Seafood > Poultry > Plain > Chicken Drumsticks` — populated; processing_storage = `fresh` separates fresh from frozen
- `Produce > Fresh Vegetables > Onions > Green Onions > Plain` — separable from `Produce > Salad Kits > ...`
- `Beverage > Juice > Tomato > Plain` — separable from `Beverage > Juice > Vegetable Blend > V8`

The substrate is in place. The filter just doesn't read it.

---

## Why audit-tagging is necessary but insufficient on its own

Tonight's two commits shipped the data:

- **a5e26b42** — `api/scripts/tag_api_cache_to_audit.py` populated `product_audit_classification.db`.
- **03b72ee2** — universe sweep + gap aggregator + walmart weight extractor; ran the planner across 259 recipes and dumped per-line resolver paths to `universe_calc.json`, classified gaps in `universe_gaps.{md,jsonl}`.

But the calculator's filter chain was not modified by either commit. It still calls `_product_acceptance_reason` → cascade of 60 hand-tuned `canonical_key` branches → default tail → `_reject_combo_product`. The classification table sits unused. **The filter must be taught to read the classification table before any of the audit-tagging payoff materializes in the universe sweep.** That is the single change FIX_PLAN.md proposes.

---

## The five categories of bugs the universe sweep surfaced (counts from `universe_gaps.md`)

| Class | Count | Cause | Audit-fix?|
|---|---|---|---|
| `generic_term` | 333 | Recipe text uses a vague noun ("cheese", "broth", "fish") that has no canonical-specific resolution | No — recipe-text problem, not a filter problem; RUVS verify_line is correct here |
| **`wrong_form_likely`** | **51** | Filter accepted a product that's the wrong form (e.g., shelf-stable dinner accepted as plain pasta) | **Yes — audit `processing_storage` / `variant` rules out the wrong form deterministically** |
| **`shopping_gap`** | **46** | Filter rejected ALL 25 cached candidates for a clean canonical (the four samples in this doc) | **Yes — audit `canonical_path` accepts the cached products that the regex/category rule rejects** |
| `nutrition_unknown` | 28 | No SR28/ESHA row resolved — separate from the filter chain | No (resolver-side issue, not a filter issue) |
| `or_option_in_text` | 23 | Recipe line has `"milk, cream, or chicken stock"` preserved as one canonical | No (recipe-text problem; needs RUVS verify_line) |
| `range_in_text` | 21 | Recipe line has `"8–10 chicken drumsticks"` preserved as one quantity | No (recipe-text problem; portion_resolver issue, not filter) |
| `no_canonical` | 16 | Resolver had no alias for the line ("ziploc bag", "toothpick", "coot", "oleo") | Mostly non-food (audit-tagging not applicable); 6/16 are food terms with no alias mapping |

Two of the six rollup classes — **`wrong_form_likely` (51) and `shopping_gap` (46)** — together 97 lines, 5.6% of the 1,740-line universe — are exactly the failure mode an audit-driven accept rule replaces. The other four classes are recipe-text or alias problems that the audit substrate cannot fix.

A separate residual concern surfaced in `universe_gaps.md`'s "Top 20 unresolved canonicals" — `ziploc bag`, `toothpick`, `toothpicks`. These are non-food equipment lines that escaped `non_food_words.csv`. Five-minute fix: add the missing tokens to that lexicon.

---

## What I am not certain of (read-only honesty)

- For `chicken drumstick`, the singular-vs-plural failure mode is inferred from the rule body — I did not run the calculator against the live cache to confirm which exact reason string fires for each of the 25 rejections. The four reason strings most likely in the trace are `missing_required_canonical_terms` (default tail, plural mismatch) and `combo_or_prepared_product:mix` / `:stir` / `:fry`. To confirm precisely, run the existing dump (`/tmp/calc_plan13.json`) with `decision="reject"` filter and tally by `reason`. Not necessary to ship the fix.
- The 25 cached products under each canonical are FTS-keyword matches on `api_cache.db` — I did not enumerate them per-canonical because the calculator output was not run with rejected-product details exposed. The rule analysis above is sufficient to commit to the fix.
- `_reject_combo_product` runs in BOTH the per-canonical branches' default fallthrough AND the catch-all default tail — meaning even canonicals with hand-written branches are subject to the combo blocklist after the branch's own reject-set passes. I read this from the rule bodies; double-check in the next session if any of the 60 branches deliberately bypass the combo check (none did in the ~10 I read in detail).

---

## One-line conclusion

**The audit-driven classification table that shipped tonight makes the 60-branch / 100-token filter chain deletable. Until the filter is taught to read it, every shopping-gap and wrong-form fix gets re-litigated through brittle hand-tuning. Do step 1 of `FIX_PLAN.md` first.**
