# STRUCTURED_MATCHER_SPEC — Calculator → audit-driven product compatibility

**Last edit:** 2026-05-02 (owner-authored; transcribed and committed as the canonical spec).
**Supersedes:** `FIX_PLAN.md` Steps 4–9. Step 3 (`accept_via_audit` introduced as first check, commit `88af680`) stays — it is the foothold this spec extends.
**Anchor:** `GOAL.md` — the active plan now points at this document.

---

## The thesis

Stop patching the calculator like it is still a title-regex matcher. The calculator must connect four things:

1. Raw recipe ingredient text.
2. Our normalized canonical ingredient (~18K canonical items already exist).
3. Nutrition identity: FNDDS / SR28 / ESHA.
4. Retail product identity: Walmart/Kroger product with price, package size, and retail path.

The current code is still behaving like we do not have a taxonomy. We do. `full_corpus_audit.csv` has it: `canonical_path`, `canonical_label`, `variant`, `flavor`, `form_texture_cut`, `processing_storage`, `claims`, `retail_leaf_path`, `fndds_code`, `sr28_code`, `esha_code`, `match_source`, `match_score`, `matched_key`, `portions_json`. That is enough structure to make a real matcher.

The legacy `_reject_combo_product()` blocks valid products by global title-word blocklist (`pasta`, `salad`, `bread`, `tortilla`, `mix`, ...). That made sense only when we had no trustworthy product classification. We now have it. Default behavior must shift from "reject by title word" to "accept/reject by structured taxonomy compatibility."

If a `macaroni` candidate has `canonical_path` indicating `Pantry > Pasta > Macaroni`, FNDDS/SR28/ESHA close to macaroni, dry-pasta form, and is not a kit/salad/sauce/flavored side dish, it must be accepted, even if the title contains the word "pasta." Rejecting because the title contains "pasta" is backwards.

---

## Part 1 — Instrument the matcher (read-only)

Add a debug/audit mode that emits one row per (canonical, candidate product) pair, regardless of accept/reject:

```
raw_ingredient
canonical_key
canonical_name
expected_fndds_code
expected_sr28_code
expected_esha_code
expected_retail_path           (if known)

product_title
product_source                 (walmart_search / kroger_search / retail_surface_bridge / api_cache_exact)
product_price
product_package_grams
product_fdc_id
product_upc
product_canonical_path
product_retail_leaf_path
product_variant
product_flavor
product_form_texture_cut
product_processing_storage
product_fndds_code
product_sr28_code
product_esha_code

accepted                       (bool)
rejection_reason               (string; empty if accepted)
acceptance_path                (one of: audit_exact, audit_compatible, nutrition_code_match,
                                legacy_branch, legacy_combo_reject, unclassified_fallback)
score                          (compatibility score, see Part 2)
```

This report makes it observable why a candidate was accepted or rejected. It is the empirical baseline against which Parts 2–4 are measured.

**Done:** any failure in Parts 2–4 must be diff-able against this report's rows.

---

## Part 2 — Structured product compatibility

Build:

```python
def structured_product_compatibility(
    canonical: CanonicalSpec,
    product_audit: ProductAuditClassification,
) -> CompatibilityResult: ...
```

`CompatibilityResult`:

- `decision: 'accept' | 'reject' | 'uncertain'`
- `score: float` (0.0–1.0; used for ranking among accepted)
- `reasons: list[str]` (positive evidence)
- `hard_reject_flags: list[str]` (rejection causes — flavor mismatch, kit detected, etc.)
- `matched_dimensions: dict[str, str]` (per-dimension verdict; see below)

### Six compatibility dimensions

1. **Canonical path compatibility.** Examples:
   - `Dairy > Milk > Whole` is compatible with `milk`, `whole milk`.
   - `Beverage > Plant Milk > Almond Milk` is compatible with `almond milk`, NOT `milk`.
   - `Pantry > Pasta > Macaroni` is compatible with `macaroni`.
   - `Produce > Alliums > Green Onion` is compatible with `green onion` and `scallion` (canonical aliases of each other).
   - `Beverage > Vegetable Juice > Tomato Juice` is compatible with `tomato juice`. Do not require category string match.

2. **Nutrition code compatibility (FNDDS / SR28 / ESHA).** Treated as evidence, NOT gospel.
   - If two or more of FNDDS/SR28/ESHA agree or are close → strong evidence.
   - One wrong code, but retail path and canonical label strong → do not auto-reject.
   - All three point to a different food family AND retail path also says different → reject.
   - All three point to a different family BUT retail path strongly matches → uncertain (mark for review).

3. **Variant compatibility.**
   - whole milk ↔ whole milk (allow); skim milk should not match whole milk unless fallback explicitly allowed.
   - brown sugar ↔ brown sugar (allow); brown sugar must not match brown-sugar-flavored oatmeal.
   - pork butt must not match ham shank (different cut, different curing state).
   - plain butter must not match butter spread with olive oil unless spread is explicitly allowed.

4. **Form compatibility (`form_texture_cut`).**
   - tomato juice → liquid juice form. Tomato paste does not match.
   - macaroni → dry pasta form. Macaroni salad / boxed prepared mac and cheese does not match.
   - green onion → fresh produce form. Seasoning powder does not match.

5. **Flavor compatibility.** Reject flavored products when canonical expects plain.
   - brown sugar must reject brown-sugar-flavored oatmeal.
   - plain oatmeal must reject maple-brown-sugar instant oatmeal unless recipe explicitly wants flavored instant.
   - plain turkey must reject applewood-smoked deli slices when recipe wants raw or plain turkey.

6. **Combo / prepared-food detection.** Structured and contextual, NOT global title blocklist.
   - macaroni ingredient → reject macaroni salad, mac-and-cheese kit, prepared pasta meal.
   - lettuce ingredient → reject salad kit.
   - chicken breast ingredient → reject chicken pot pie.
   - tortilla ingredient → accept tortillas, reject tortilla chips when recipe wants tortillas.
   - bread ingredient → accept bread, reject breaded chicken when recipe wants bread.

   The check fires only when the canonical expects a base ingredient AND the product's `processing_storage`/`canonical_path` indicates kit/prepared/combo.

---

## Part 3 — Replace `_reject_combo_product()`

Do not delete blindly. Sequence:

1. Log every time `_reject_combo_product()` fires. Per call: `canonical_key`, `product_title`, would-have-been-decision, would the new structured matcher have accepted instead.
2. Bypass `_reject_combo_product()` when audit classification is available and the structured matcher returned a confident decision.
3. Use `_reject_combo_product()` only for products with `classification_method='unclassified'` or no UPC.
4. Once structured matching covers the common canonicals (Part 7 win conditions), delete `_reject_combo_product()`.

---

## Part 4 — Fix `surface_esha_override`

Today: when an ESHA-priority canonical fires (macaroni, ramen noodles, chicken-flavored ramen noodles), the resolver short-circuits and never calls retail product matching. The output is `shopping_gap` even when the cache has correct products.

Required behavior:

- An ESHA override may set `nutrition_state` and an `esha_code`.
- It may influence canonical identity.
- It MUST NOT short-circuit product matching.
- Retail matching must still run.

Result: a canonical with ESHA override returns `walmart_pick`, `kroger_pick`, `walmart_options[]`, `kroger_options[]`, and a real `shopping_state` (not gap-by-default).

Concretely: split `_apply_surface_esha_override()` so the nutrition-side decision (set `esha_code`, set `nutrition_state`, append `surface_esha_override:...:<reason>` to path) is separate from the retail-products-side decision (which always runs).

---

## Part 5 — Canonical-to-retail-path bridge

Build `Hestia/api/data/canonical_retail_bridge.db` (or `.csv`) — generated, not hand-authored. Schema:

```
canonical_key
canonical_name
fndds_code
sr28_code
esha_code
expected_canonical_path        (the audit's path string the canonical maps to)
expected_retail_leaf_path
allowed_variants               (JSON list, nullable)
forbidden_variants             (JSON list, nullable)
allowed_forms                  (JSON list, nullable)
forbidden_forms                (JSON list, nullable)
allowed_processing_storage     (JSON list, nullable)
forbidden_processing_storage   (JSON list, nullable)
allow_flavored                 (bool, default false)
allow_combo                    (bool, default false)
notes
```

Generation strategy:

1. For each canonical in `canonical_to_esha.csv`/`canonical_items.csv`, find the dominant `canonical_path` in `full_corpus_audit.csv` for that canonical's fndds_code / esha_code / canonical_label.
2. Tie-break by `canonical_label` token overlap with the canonical_key.
3. For variants/forms/flavors/processing — pull the most common values associated with the dominant path; emit those as `allowed_*`.
4. Default `allow_flavored=false`, `allow_combo=false` (per the default-prep-state rule already documented in the RUVS spec).
5. High-impact canonicals (the Part 7 test list) get spot-reviewed; the long tail stays auto-generated.

Do NOT hand-author 18K rows.

---

## Part 6 — Prices come from the cache, not the audit

The audit tells us **what the product is**. The Walmart/Kroger cache (`api_cache.db`) tells us **what's available** plus price, package size, retailer, title, URL.

Product matching:

1. Candidate products come from cache.
2. Attach audit classification by UPC / FDC ID / title match (already done — `product_audit_classification.db`).
3. Use audit classification to decide compatibility (Part 2).
4. Use cache data to choose the best purchasable item by price and package suitability.

Don't expect the audit file itself to solve pricing.

---

## Part 7 — Required test canonicals

Run the matcher before and after every change in this spec on:

```
milk          | whole milk     | almond milk
butter        | brown sugar    | oats
oatmeal       | macaroni       | green onion
tomato juice  | pork butt      | chicken drumsticks
turkey        | cheddar cheese | cheese
flour         | tortillas      | bread
lettuce       | canned corn
```

For each, output:

```
raw test ingredient
resolved canonical
expected nutrition codes
expected retail path
candidates found
accepted count
rejected count
top 5 accepted products
top 10 rejection reasons
ESHA override fired? (Y/N)
retail matching ran? (Y/N)
_reject_combo_product fired? (Y/N)
audit classification used? (Y/N)
```

This is the report Part 10 demands.

---

## Part 8 — Win conditions (definition of done)

This work is not fixed until ALL of these hold:

1. macaroni: `accepted > 0`.
2. green onion: accepts products called "Green Onions" (not only "scallion").
3. tomato juice: accepts products in `Beverage > Vegetable Juice` when they are actually tomato juice.
4. chicken drumsticks: still accepts (regression check).
5. pork butt: does NOT accept ham shank.
6. butter: does NOT accept butter-with-olive-oil spread unless spread is explicitly allowed.
7. brown sugar: does NOT accept brown-sugar-flavored oatmeal.
8. oats / oatmeal: does NOT accept flavored instant oatmeal unless requested.
9. ESHA override does NOT prevent retail matching.
10. `_reject_combo_product()` is no longer the default authority for classified products.

---

## Part 9 — What NOT to do

- Do not add more `if canonical_key == "..."` branches.
- Do not extend the title blocklist.
- Do not call an LLM for normal products.
- Do not treat FNDDS/SR28/ESHA as perfect — evidence, not gospel.
- Do not treat retail category as perfect — evidence.
- Do not let nutrition override bypass shopping.
- Do not call something a "recipe alias problem" unless raw ingredient resolution actually failed.

Critical:

> Two distinct failure modes:
>
> A. Raw recipe ingredient cannot resolve to canonical.
> B. Canonical resolves correctly, but retail product matching fails.
>
> Most of tonight's failures are B, not A. Adding aliases is the wrong instrument.

---

## Part 10 — Deliverables

When this spec is executed, produce:

1. Code changes (committed, per part).
2. Before/after audit report for the Part 7 canonicals.
3. List of remaining unresolved failures bucketed into:
   - canonical resolution failures
   - no retail candidates (cache miss)
   - unclassified retail products (BM25 below threshold)
   - audit classification conflict (audit says X, retail path says Y)
   - package size / grams extraction failure
   - true ambiguous ingredient (LLM territory)
4. Recommendation: should we generate the canonical-to-retail-path bridge table (Part 5)? Expected: yes.
5. Clear answer to the gating question:

   **"Can we now use structured audit classification as the primary product acceptance path and demote `_reject_combo_product()` to unclassified-fallback only?"**

   Expected: yes, for canonicals where audit data exists. The exception list (canonicals with no audit coverage) is itself a deliverable.

---

## Execution order

1. **Part 1** (instrumentation, read-only, ground truth).
2. **Part 4** (ESHA override fix — small, surgical, unblocks macaroni and ramen).
3. **Part 5** (canonical-to-retail-path bridge — generated, not hand-authored).
4. **Part 2** (structured compatibility, reads the bridge).
5. **Part 3** (demote `_reject_combo_product()` to unclassified-fallback).
6. **Part 7** test sweep + report (Part 10 deliverable).
7. Address remaining classification gaps (BM25 threshold, recipe-side aliases for the small residual that's actually Problem A).
